import asyncio
import os
import logging
from datetime import datetime, timedelta

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    WebAppInfo,
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import json as _json
import aiohttp.web as _web
from database import (
    init_db, get_user, db_run, db_get, db_all, db_insert,
    get_setting, update_setting, add_balance,
)
from texts import t, REGIONS, REGIONS_RU

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ── CONFIG ────────────────────────────────────────────────────────────────────
BOT_TOKEN  = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@xazdent")
ADMIN_IDS  = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
WEBAPP_URL = os.getenv("WEBAPP_URL", "").rstrip("/")
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))

bot    = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp     = Dispatcher(storage=MemoryStorage())
router = Router()

# ── STATES ────────────────────────────────────────────────────────────────────
class RegState(StatesGroup):
    name     = State()
    phone    = State()
    region   = State()
    addr     = State()
    location = State()

class NeedState(StatesGroup):
    product  = State()
    qty      = State()
    deadline = State()

class BulkState(StatesGroup):
    items    = State()   # Mahsulotlar ro'yxati (list of dicts)
    deadline = State()

class TopupState(StatesGroup):
    amount  = State()
    receipt = State()

class OfferState(StatesGroup):
    price = State()
    note  = State()

class ShopState(StatesGroup):
    cat  = State()
    name = State()

class MyProductsState(StatesGroup):
    editing = State()   # ro'yxat tahrirlash

# ── KEYBOARDS ─────────────────────────────────────────────────────────────────
def ik(*rows):
    return InlineKeyboardMarkup(inline_keyboard=list(rows))

def ib(text, data=None, url=None, web_app=None):
    if web_app:
        return InlineKeyboardButton(text=text, web_app=web_app)
    if url:
        return InlineKeyboardButton(text=text, url=url)
    return InlineKeyboardButton(text=text, callback_data=data)

def rk(*rows, one_time=False):
    return ReplyKeyboardMarkup(keyboard=list(rows), resize_keyboard=True, one_time_keyboard=one_time)

def kb_lang():
    return ik([ib("🇺🇿 O'zbekcha", "lang_uz"), ib("🇷🇺 Русский", "lang_ru")])

def kb_role(lg):
    return ik(
        [ib("🏥 Vrach / Klinika",  "role_clinic")],
        [ib("🔬 Zubtexnik",         "role_zubtex")],
        [ib("🛒 Sotuvchi",          "role_seller")],
    )

def kb_clinic(lg):
    return rk(
        [KeyboardButton(text="📋 Ehtiyojlarim"), KeyboardButton(text="✏️ Ehtiyoj yozish")],
        [KeyboardButton(text="📩 Takliflar"),     KeyboardButton(text="💰 Hisobim")],
        [KeyboardButton(text="📦 Mahsulotlarim"), KeyboardButton(text="⚙️ Profil")],
    )

def kb_seller(lg):
    return rk(
        [KeyboardButton(text="🔔 Ehtiyojlar"),  KeyboardButton(text="📤 Takliflarim")],
        [KeyboardButton(text="🏪 Do'konim"),     KeyboardButton(text="💰 Hisobim")],
        [KeyboardButton(text="⚙️ Profil")],
    )

def kb_regions(lg):
    regs = REGIONS if lg != "ru" else REGIONS_RU
    rows = []
    for i in range(0, len(regs), 2):
        row = [ib(regs[i], f"reg_{i}")]
        if i + 1 < len(regs):
            row.append(ib(regs[i + 1], f"reg_{i+1}"))
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_deadline():
    return ik(
        [ib("⚡️ 2 soat", "dl_2"),  ib("🕐 24 soat", "dl_24")],
        [ib("📅 3 kun",  "dl_72"), ib("🗓 1 hafta",  "dl_168")],
    )

def kb_units():
    return ik([ib("📌 Dona", "unit_dona"), ib("⚖️ Kg", "unit_kg"), ib("💧 Litr", "unit_litr")])

def kb_delivery():
    return ik(
        [ib("⚡️ 2 soat", "del_2"),  ib("🕐 24 soat", "del_24")],
        [ib("📅 2 kun",  "del_48"), ib("🗓 1 hafta",  "del_168")],
    )

def kb_confirm():
    return ik([ib("✅ Ha, joylash", "confirm"), ib("❌ Bekor", "cancel")])

def kb_cancel():
    return ik([ib("❌ Bekor", "cancel")])

def kb_shop_cats():
    return ik(
        [ib("🦷 Terapevtik", "cat_1")],
        [ib("⚙️ Jarrohlik & Implant", "cat_2")],
        [ib("🔬 Zubtexnik", "cat_3")],
        [ib("🧪 Dezinfeksiya", "cat_4")],
        [ib("💡 Asbob-uskunalar", "cat_5")],
    )

# ── HELPERS ───────────────────────────────────────────────────────────────────
async def lang(uid):
    u = await get_user(uid)
    return (u["lang"] if u else None) or "uz"

async def has_profile(uid):
    u = await get_user(uid)
    return bool(u and u["clinic_name"] and u["phone"] and u["region"])

async def get_or_create_room(uid):
    """Foydalanuvchining default omborxonasini topadi yoki yaratadi (ko'rinmaydi)."""
    room = await db_get(
        "SELECT * FROM rooms WHERE owner_id=? AND status='active' ORDER BY id LIMIT 1", (uid,)
    )
    if room:
        return room
    rid = await db_insert(
        "INSERT INTO rooms(room_code,room_type,owner_id,max_needs) VALUES(?,?,?,?)",
        (f"AUTO{uid}", "premium", uid, 9999),
    )
    return await db_get("SELECT * FROM rooms WHERE id=?", (rid,))

async def post_to_channel(need_id, need):
    """1 ta ehtiyoj uchun kanal posti (qayta post uchun)."""
    dl_map = {2:"2 soat",24:"24 soat",72:"3 kun",168:"1 hafta"}
    dl_txt = dl_map.get(need["deadline_hours"], f"{need['deadline_hours']} soat")
    owner  = await get_user(need["owner_id"])
    words  = need["product_name"].split()
    tags   = " ".join(f"#{w.lower()}" for w in words[:3] if len(w)>2)
    txt = (
        f"📋 *BUYURTMA #{need_id}*\n\n"
        f"🦷 {need['product_name']}\n"
        f"📦 {need['quantity']} {need['unit']}\n"
        f"⏱ {dl_txt} ichida\n\n"
        f"📍 {owner['region'] or ''}\n\n"
        f"{tags}\n💬 @XazdentBot"
    )
    batch_id = need.get("batch_id")
    if WEBAPP_URL and batch_id:
        url = f"{WEBAPP_URL}/offer/{batch_id}"
        kb = ik([ib("💰 Narx taklif qilish →", web_app=WebAppInfo(url=url))])
    else:
        bot_info = await bot.get_me()
        kb = ik([ib("📤 Taklif yuborish", url=f"https://t.me/{bot_info.username}?start=offer_{need_id}")])
    try:
        m = await bot.send_message(CHANNEL_ID, txt, reply_markup=kb)
        return m.message_id
    except Exception as e:
        log.error(f"❌ Kanal xato: {e}")
        return None

async def post_batch_to_channel(batch_id, needs_list, owner):
    """Ko'p ehtiyoj uchun BITTA paket post."""
    if not needs_list:
        return None
    dl_map = {2:"2 soat",24:"24 soat",72:"3 kun",168:"1 hafta"}
    dl_txt = dl_map.get(needs_list[0]["deadline_hours"], "?")
    lines  = "\n".join([
        f"• {n['product_name']} — {n['quantity']} {n['unit']}"
        for n in needs_list[:15]
    ])
    if len(needs_list) > 15:
        lines += f"\n• ...va yana {len(needs_list)-15} ta"
    all_words = " ".join(n["product_name"] for n in needs_list[:5]).split()
    tags = " ".join(f"#{w.lower()}" for w in dict.fromkeys(all_words) if len(w)>2)[:80]
    txt = (
        f"📋 *BUYURTMA #{batch_id}* — {len(needs_list)} ta mahsulot\n\n"
        f"{lines}\n\n"
        f"📍 {owner.get('region') or ''}\n"
        f"⏱ {dl_txt} ichida\n\n"
        f"{tags}\n💬 @XazdentBot"
    )
    if WEBAPP_URL:
        url = f"{WEBAPP_URL}/offer/{batch_id}"
        kb = ik([ib("💰 Narx kiriting →", web_app=WebAppInfo(url=url))])
    else:
        bot_info = await bot.get_me()
        kb = ik([ib("📤 Taklif yuborish", url=f"https://t.me/{bot_info.username}?start=batch_{batch_id}")])
    try:
        m = await bot.send_message(CHANNEL_ID, txt, reply_markup=kb)
        log.info(f"✅ Batch kanal post: batch={batch_id} msg={m.message_id}")
        return m.message_id
    except Exception as e:
        log.error(f"❌ Batch kanal xato: {e}")
        return None

async def notify_sellers(need_id, need, owner):
    """Barcha sotuvchilarga lichkada xabar."""
    sellers = await db_all(
        "SELECT id FROM users WHERE role='seller' AND id!=? AND is_blocked=0",
        (owner["id"],),
    )
    if WEBAPP_URL and need.get("batch_id"):
        url = f"{WEBAPP_URL}/offer/{need['batch_id']}"
        kb = ik(
            [ib("💰 Narx kiriting →", web_app=WebAppInfo(url=url))],
            [ib("⏭ Keyinroq", "skip_notify")],
        )
    else:
        bot_info = await bot.get_me()
        deep_url = f"https://t.me/{bot_info.username}?start=offer_{need_id}"
        kb = ik(
            [ib("📤 Taklif yuborish", url=deep_url)],
            [ib("⏭ Keyinroq", "skip_notify")],
        )

    dl_map = {2: "2 soat", 24: "24 soat", 72: "3 kun", 168: "1 hafta"}
    txt = (
        f"📦 *Yangi buyurtma!*\n\n"
        f"🦷 {need['product_name']}\n"
        f"📦 {need['quantity']} {need['unit']}\n"
        f"⏱ {dl_map.get(need['deadline_hours'], '?')} ichida\n"
        f"📍 {owner['region'] or ''}"
    )
    sent = 0
    for s in sellers:
        try:
            await bot.send_message(s["id"], txt, reply_markup=kb)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    log.info(f"Notify: {sent}/{len(sellers)} sotuvchiga yuborildi")

# ── /start ─────────────────────────────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    uid = msg.from_user.id
    u = await get_user(uid)
    if not u:
        await db_run(
            "INSERT OR IGNORE INTO users(id,username,full_name) VALUES(?,?,?)",
            (uid, msg.from_user.username, msg.from_user.full_name),
        )
        u = await get_user(uid)

    # Deep link: /start offer_42
    args = msg.text.split(maxsplit=1)[1] if " " in (msg.text or "") else ""
    if args.startswith("offer_") and u and u["role"] == "seller":
        try:
            nid = int(args.split("_")[1])
            await _start_offer_bot(msg, state, nid)
            return
        except Exception:
            pass

    if u and u["role"] not in (None, "none", ""):
        lg  = u["lang"] or "uz"
        kb  = kb_clinic(lg) if u["role"] in ("clinic", "zubtex") else kb_seller(lg)
        txt = "🏥 *Klinika paneli*" if u["role"] in ("clinic", "zubtex") else "🛒 *Sotuvchi paneli*"
        await msg.answer(txt, reply_markup=kb)
        return

    await msg.answer(t("uz", "welcome"), reply_markup=kb_lang())

@router.callback_query(F.data == "skip_notify")
async def skip_notify(call: CallbackQuery):
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer("Keyinroq ko'rasiz")

# ── TIL ────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("lang_"))
async def cb_lang(call: CallbackQuery):
    lg = call.data[5:]
    await db_run("UPDATE users SET lang=? WHERE id=?", (lg, call.from_user.id))
    await call.message.edit_text(t(lg, "welcome"), reply_markup=kb_role(lg))
    await call.answer()

@router.callback_query(F.data.startswith("role_"))
async def cb_role(call: CallbackQuery, state: FSMContext):
    role = call.data[5:]
    uid  = call.from_user.id
    # zubtex ham clinic kabi saqlaymiz
    await db_run("UPDATE users SET role=? WHERE id=?", (role, uid))
    u  = await get_user(uid)
    lg = u["lang"] or "uz"
    await state.set_state(RegState.name)
    if role == "clinic":
        ask = "🏥 Klinika nomini kiriting:\n\n_Masalan: Sadaf Dental_"
    elif role == "zubtex":
        ask = "🔬 Zubtexnik ismingiz va ish joyingizni kiriting:"
    else:
        ask = "🏪 Do\'kon / kompaniya nomingizni kiriting:"
    await call.message.answer(ask, reply_markup=ReplyKeyboardRemove())
    await call.answer()

# ── RO'YXATDAN O'TISH ─────────────────────────────────────────────────────────
@router.message(RegState.name)
async def reg_name(msg: Message, state: FSMContext):
    await state.update_data(clinic_name=msg.text)
    lg = await lang(msg.from_user.id)
    kb = rk([KeyboardButton(text=t(lg, "btn_send_phone"), request_contact=True)], one_time=True)
    await state.set_state(RegState.phone)
    await msg.answer(t(lg, "ask_phone"), reply_markup=kb)

@router.message(RegState.phone, F.contact)
async def reg_phone(msg: Message, state: FSMContext):
    await state.update_data(phone=msg.contact.phone_number)
    lg = await lang(msg.from_user.id)
    await state.set_state(RegState.region)
    await msg.answer(t(lg, "ask_region"), reply_markup=kb_regions(lg))

@router.callback_query(F.data.startswith("reg_"), RegState.region)
async def reg_region(call: CallbackQuery, state: FSMContext):
    lg   = await lang(call.from_user.id)
    idx  = int(call.data[4:])
    regs = REGIONS if lg != "ru" else REGIONS_RU
    reg  = regs[idx].split(" ", 1)[1] if " " in regs[idx] else regs[idx]
    await state.update_data(region=reg)
    await state.set_state(RegState.addr)
    await call.message.answer(t(lg, "ask_address"), reply_markup=ReplyKeyboardRemove())
    await call.answer()

@router.message(RegState.addr)
async def reg_addr(msg: Message, state: FSMContext):
    await state.update_data(address=msg.text)
    await state.set_state(RegState.location)
    kb = rk(
        [KeyboardButton(text="📍 Lokatsiya yuborish", request_location=True)],
        [KeyboardButton(text="⏭ O\'tkazib yuborish")],
        one_time=True,
    )
    await msg.answer(
        "📍 Lokatsiyangizni yuboring\n_(ixtiyoriy — sotuvchi topishi osonlashadi)_",
        reply_markup=kb,
    )

@router.message(RegState.location, F.location)
async def reg_location(msg: Message, state: FSMContext):
    d = await state.get_data()
    await db_run(
        "UPDATE users SET clinic_name=?,phone=?,region=?,address=?,latitude=?,longitude=? WHERE id=?",
        (d["clinic_name"], d["phone"], d["region"], d["address"],
         msg.location.latitude, msg.location.longitude, msg.from_user.id),
    )
    await _finish_reg(msg, state)

@router.message(RegState.location, F.text == "⏭ O\'tkazib yuborish")
async def reg_location_skip(msg: Message, state: FSMContext):
    d = await state.get_data()
    await db_run(
        "UPDATE users SET clinic_name=?,phone=?,region=?,address=? WHERE id=?",
        (d["clinic_name"], d["phone"], d["region"], d["address"], msg.from_user.id),
    )
    await _finish_reg(msg, state)

async def _finish_reg(msg: Message, state: FSMContext):
    await state.clear()
    lg = await lang(msg.from_user.id)
    u  = await get_user(msg.from_user.id)
    if u["role"] in ("clinic", "zubtex"):
        kb    = kb_clinic(lg)
        panel = "🏥 *Klinika paneli*"
    else:
        kb    = kb_seller(lg)
        panel = "🛒 *Sotuvchi paneli*"
    await msg.answer(f"✅ Profil saqlandi!\n\n{panel}", reply_markup=kb)

# ── PROFIL ─────────────────────────────────────────────────────────────────────
@router.message(F.text == "⚙️ Profil")
async def show_profile(msg: Message, state: FSMContext):
    u  = await get_user(msg.from_user.id)
    lg = u["lang"] or "uz"
    txt = (
        f"⚙️ *Profil*\n\n"
        f"👤 {u['clinic_name'] or '—'}\n"
        f"📞 {u['phone'] or '—'}\n"
        f"📍 {u['region'] or '—'}\n"
        f"🏠 {u['address'] or '—'}\n"
        f"💰 Balans: {u['balance'] or 0:.1f} ball"
    )
    await msg.answer(txt, reply_markup=ik([ib("✏️ Tahrirlash", "edit_profile")]))

@router.callback_query(F.data == "edit_profile")
async def edit_profile(call: CallbackQuery, state: FSMContext):
    lg = await lang(call.from_user.id)
    u  = await get_user(call.from_user.id)
    await state.set_state(RegState.name)
    ask = t(lg, "ask_clinic_name") if u and u["role"] in ("clinic", "zubtex") else "🏪 Do'kon nomingizni kiriting:"
    await call.message.answer(ask, reply_markup=ReplyKeyboardRemove())
    await call.answer()

# ── EHTIYOJ YOZISH (3 savol) ──────────────────────────────────────────────────
@router.message(F.text == "✏️ Ehtiyoj yozish")
async def need_start(msg: Message, state: FSMContext):
    uid = msg.from_user.id
    if not await has_profile(uid):
        await msg.answer(
            "⚠️ Avval profilingizni to'ldiring!",
            reply_markup=ik([ib("✏️ Profilni to'ldirish", "edit_profile")]),
        )
        return
    await msg.answer(
        "📋 *Ehtiyoj yozish*\n\nQancha mahsulot kerak?",
        reply_markup=ik(
            [ib("1️⃣ 1 ta mahsulot", "need_single")],
            [ib("📋 Ko'p mahsulot (Mini App)", "need_bulk")],
        ),
    )

@router.callback_query(F.data == "need_single")
async def need_single(call: CallbackQuery, state: FSMContext):
    await state.set_state(NeedState.product)
    await call.message.answer(
        "🦷 *Nima kerak?*\n\n_Masalan: Xarizma plomba A2_",
        reply_markup=ReplyKeyboardRemove(),
    )
    await call.answer()

@router.callback_query(F.data == "need_bulk")
async def need_bulk(call: CallbackQuery, state: FSMContext):
    webapp_url = WEBAPP_URL
    if not webapp_url:
        # WEBAPP_URL yo'q — matn orqali kiritish
        await state.set_state(BulkState.items)
        await call.message.answer(
            "📋 *Ko'p mahsulot*\n\n"
            "Har bir mahsulotni yangi qatorda yozing:\n\n"
            "```\n5 dona Xarizma A2\n2 kg GC Fuji IX\n1 dona Endomotor\n```\n\n"
            "_Format: miqdor + birlik + nom_",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        uid  = call.from_user.id
        u    = await get_user(uid)
        name = (u["clinic_name"] or u["full_name"] or "Klinika").replace(" ", "+")
        url  = f"{webapp_url}/order?clinic={name}&uid={uid}"
        await call.message.answer(
            "📋 *Ko'p mahsulot buyurtmasi*\n\nQuyidagi tugmani bosing:",
            reply_markup=ik([ib("📋 Buyurtma yaratish →", web_app=WebAppInfo(url=url))]),
        )
    await call.answer()

@router.message(NeedState.product)
async def need_product(msg: Message, state: FSMContext):
    await state.update_data(product=msg.text)
    await state.set_state(NeedState.qty)
    await msg.answer(
        "📦 *Miqdori?*\n\n_Masalan: 5 dona, 2 kg, 1 litr_\n\nYoki tezkor:",
        reply_markup=ik(
            [ib("1 dona", "q_1_dona"), ib("2 dona", "q_2_dona"), ib("5 dona", "q_5_dona")],
            [ib("1 kg",   "q_1_kg"),  ib("2 kg",   "q_2_kg"),  ib("10 kg",  "q_10_kg")],
        ),
    )

@router.callback_query(F.data.startswith("q_"), NeedState.qty)
async def need_qty_btn(call: CallbackQuery, state: FSMContext):
    parts = call.data[2:].split("_")
    qty, unit = float(parts[0]), parts[1]
    await state.update_data(qty=qty, unit=unit)
    await state.set_state(NeedState.deadline)
    await call.message.answer("⏱ *Qachongacha kerak?*", reply_markup=kb_deadline())
    await call.answer()

@router.message(NeedState.qty)
async def need_qty_text(msg: Message, state: FSMContext):
    text  = msg.text.strip()
    parts = text.split(None, 1)
    try:
        qty  = float(parts[0].replace(",", "."))
        unit = parts[1].lower() if len(parts) > 1 else None
    except Exception:
        await msg.answer("❌ Noto'g'ri format. _Masalan: 5 dona yoki 2 kg_")
        return
    if unit:
        await state.update_data(qty=qty, unit=unit)
        await state.set_state(NeedState.deadline)
        await msg.answer("⏱ *Qachongacha kerak?*", reply_markup=kb_deadline())
    else:
        await state.update_data(qty=qty)
        await msg.answer("⚖️ *O'lchov birligi:*", reply_markup=kb_units())

@router.callback_query(F.data.startswith("unit_"), NeedState.qty)
async def need_unit(call: CallbackQuery, state: FSMContext):
    await state.update_data(unit=call.data[5:])
    await state.set_state(NeedState.deadline)
    await call.message.answer("⏱ *Qachongacha kerak?*", reply_markup=kb_deadline())
    await call.answer()

@router.callback_query(F.data.startswith("dl_"), NeedState.deadline)
async def need_deadline(call: CallbackQuery, state: FSMContext):
    dl = int(call.data[3:])
    await state.update_data(deadline=dl)
    d = await state.get_data()
    dl_map = {2: "2 soat", 24: "24 soat", 72: "3 kun", 168: "1 hafta"}
    preview = (
        f"🦷 *{d['product']}*\n"
        f"📦 {d['qty']} {d.get('unit','dona')}\n"
        f"⏱ {dl_map.get(dl, str(dl)+' soat')} ichida"
    )
    await call.message.answer(
        f"✅ *Tekshiring:*\n\n{preview}\n\nKanalga joylashtirilamizmi?",
        reply_markup=kb_confirm(),
    )
    await call.answer()

@router.callback_query(F.data == "confirm", NeedState.deadline)
async def need_confirm(call: CallbackQuery, state: FSMContext):
    d   = await state.get_data()
    uid = call.from_user.id
    u   = await get_user(uid)

    # Auto room
    room    = await get_or_create_room(uid)
    expires = (datetime.now() + timedelta(hours=d["deadline"])).isoformat()

    # Batch yaratish (jadval uchun)
    batch_id = await db_insert(
        "INSERT INTO batches(owner_id,deadline_hours,expires_at) VALUES(?,?,?)",
        (uid, d["deadline"], expires),
    )

    need_id = await db_insert(
        "INSERT INTO needs(batch_id,room_id,owner_id,product_name,quantity,unit,deadline_hours,expires_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (batch_id, room["id"], uid, d["product"], d["qty"], d.get("unit", "dona"), d["deadline"], expires),
    )

    # Batch ga need bog'lash
    await db_run("UPDATE batches SET status='active' WHERE id=?", (batch_id,))

    need = await db_get("SELECT * FROM needs WHERE id=?", (need_id,))
    mid  = await post_to_channel(need_id, dict(need))
    if mid:
        await db_run("UPDATE needs SET channel_message_id=? WHERE id=?", (mid, need_id))

    await state.clear()
    # Kanalga link
    product = d["product"]
    qty     = d["qty"]
    unit    = d.get("unit", "dona")
    if mid and isinstance(CHANNEL_ID, str):
        chan = CHANNEL_ID.lstrip("@")
        link = f"\n[Kanalda ko'rish](https://t.me/{chan}/{mid})"
    else:
        link = ""

    await call.message.edit_text(
        f"✅ *E'lon joylashtirildi!*\n\n"
        f"🦷 {product}\n"
        f"📦 {qty} {unit}"
        f"{link}",
    )
    await call.answer("✅")

    # Sotuvchilarga xabar (fon da)
    asyncio.create_task(notify_sellers(need_id, dict(need), dict(u)))

# ── BULK (matn orqali, WEBAPP_URL yo'q bo'lsa) ──────────────────────────────
@router.message(BulkState.items)
async def bulk_items(msg: Message, state: FSMContext):
    lines  = [l.strip() for l in msg.text.strip().split("\n") if l.strip()]
    parsed = []
    errors = []
    for line in lines:
        parts = line.split(None, 2)
        if len(parts) >= 3:
            try:
                qty  = float(parts[0].replace(",", "."))
                unit = parts[1]
                name = parts[2]
                parsed.append({"qty": qty, "unit": unit, "name": name})
            except Exception:
                errors.append(line)
        elif len(parts) == 2:
            try:
                qty  = float(parts[0].replace(",", "."))
                name = parts[1]
                parsed.append({"qty": qty, "unit": "dona", "name": name})
            except Exception:
                errors.append(line)
        else:
            errors.append(line)
    if not parsed:
        await msg.answer("❌ Format xato. Masalan:\n`5 dona Xarizma A2`")
        return
    await state.update_data(bulk_items=parsed)
    await state.set_state(BulkState.deadline)
    preview = "\n".join([f"• {p['qty']} {p['unit']} — {p['name']}" for p in parsed])
    err_txt = f"\n\n⚠️ Qabul qilinmadi: {', '.join(errors)}" if errors else ""
    await msg.answer(
        f"📋 *{len(parsed)} ta mahsulot:*\n\n{preview}{err_txt}\n\n⏱ Qachongacha kerak?",
        reply_markup=kb_deadline(),
    )

@router.callback_query(F.data.startswith("dl_"), BulkState.deadline)
async def bulk_deadline(call: CallbackQuery, state: FSMContext):
    dl = int(call.data[3:])
    await state.update_data(deadline=dl)
    d     = await state.get_data()
    items = d["bulk_items"]
    dl_map = {2: "2 soat", 24: "24 soat", 72: "3 kun", 168: "1 hafta"}
    preview = "\n".join([f"• {p['qty']} {p['unit']} — {p['name']}" for p in items])
    await call.message.answer(
        f"✅ *Tasdiqlang:*\n\n{preview}\n\n⏱ {dl_map.get(dl, str(dl)+' soat')} ichida\n\n"
        f"*{len(items)} ta e'lon joylashtiriladi*",
        reply_markup=kb_confirm(),
    )
    await call.answer()

@router.callback_query(F.data == "confirm", BulkState.deadline)
async def bulk_confirm(call: CallbackQuery, state: FSMContext):
    d       = await state.get_data()
    items   = d["bulk_items"]
    uid     = call.from_user.id
    u       = await get_user(uid)
    room    = await get_or_create_room(uid)
    expires = (datetime.now() + timedelta(hours=d["deadline"])).isoformat()

    batch_id = await db_insert(
        "INSERT INTO batches(owner_id,deadline_hours,expires_at) VALUES(?,?,?)",
        (uid, d["deadline"], expires),
    )

    saved_needs = []
    for item in items:
        nid = await db_insert(
            "INSERT INTO needs(batch_id,room_id,owner_id,product_name,quantity,unit,deadline_hours,expires_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (batch_id, room["id"], uid, item["name"], item["qty"], item["unit"], d["deadline"], expires),
        )
        need = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
        saved_needs.append(dict(need))

    # Bitta paket post
    mid = await post_batch_to_channel(batch_id, saved_needs, dict(u))
    if mid:
        for n in saved_needs:
            await db_run("UPDATE needs SET channel_message_id=? WHERE id=?", (mid, n["id"]))

    asyncio.create_task(notify_sellers_batch(batch_id, uid))
    await state.clear()

    chan = CHANNEL_ID.lstrip("@") if isinstance(CHANNEL_ID, str) else str(CHANNEL_ID)
    link = f"\n[Kanalda ko'rish](https://t.me/{chan}/{mid})" if mid else ""
    await call.message.edit_text(
        f"✅ *{len(saved_needs)} ta mahsulot joylashtirildi!*{link}\n\n"
        f"Sotuvchilar ko'rib taklif yuboradi.\n"
        f"📋 *Ehtiyojlarim* bo'limida kuzating."
    )
    await call.answer("✅")

async def notify_sellers_batch(batch_id: int, owner_id: int):
    """Batch dagi barcha ehtiyojlar haqida sotuvchilarga xabar."""
    needs   = await db_all("SELECT * FROM needs WHERE batch_id=?", (batch_id,))
    owner   = await get_user(owner_id)
    sellers = await db_all(
        "SELECT id FROM users WHERE role='seller' AND id!=? AND is_blocked=0", (owner_id,)
    )
    if not needs or not sellers:
        return

    preview = "\n".join([f"• {n['quantity']} {n['unit']} — {n['product_name']}" for n in needs[:5]])
    if len(needs) > 5:
        preview += f"\n• ...va yana {len(needs)-5} ta"

    if WEBAPP_URL:
        url = f"{WEBAPP_URL}/offer/{batch_id}"
        kb  = ik(
            [ib("💰 Narx kiriting →", web_app=WebAppInfo(url=url))],
            [ib("⏭ Keyinroq", "skip_notify")],
        )
    else:
        bot_info = await bot.get_me()
        kb = ik(
            [ib("📤 Taklif yuborish", url=f"https://t.me/{bot_info.username}?start=offer_{needs[0]['id']}")],
            [ib("⏭ Keyinroq", "skip_notify")],
        )

    dl_map = {2: "2 soat", 24: "24 soat", 72: "3 kun", 168: "1 hafta"}
    txt = (
        f"📦 *{len(needs)} ta buyurtma!*\n\n"
        f"{preview}\n\n"
        f"📍 {owner['region'] or ''}\n"
        f"⏱ {dl_map.get(needs[0]['deadline_hours'], '?')} ichida"
    )
    sent = 0
    for s in sellers:
        try:
            await bot.send_message(s["id"], txt, reply_markup=kb)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    log.info(f"Batch notify: {sent}/{len(sellers)} sotuvchiga")

# ── EHTIYOJLARIM ─────────────────────────────────────────────────────────────
@router.message(F.text == "📋 Ehtiyojlarim")
async def my_needs(msg: Message):
    needs = await db_all(
        "SELECT n.*, "
        "(SELECT COUNT(*) FROM offers o WHERE o.need_id=n.id AND o.status='pending') as offer_cnt "
        "FROM needs n WHERE n.owner_id=? ORDER BY n.created_at DESC LIMIT 20",
        (msg.from_user.id,),
    )
    if not needs:
        await msg.answer(
            "📭 Hali ehtiyoj yo'q.",
            reply_markup=ik([ib("✏️ Ehtiyoj yozish", "new_need")]),
        )
        return

    await msg.answer(f"📋 *Ehtiyojlarim:* {len(needs)} ta")
    for n in needs:
        st    = {"active": "🟢", "paused": "⏸", "done": "✅", "cancelled": "❌"}.get(n["status"], "📋")
        cnt   = n["offer_cnt"] or 0
        badge = f" | 📩 *{cnt} taklif*" if cnt > 0 else ""
        rows  = []
        if cnt > 0:
            rows.append([ib(f"📩 {cnt} ta taklif ko'rish", f"view_offers_{n['id']}")])
        if n.get("batch_id"):
            rows.append([ib("📊 Jadval ko'rish", f"view_batch_{n['batch_id']}")])
        rows.append([
            ib("🔄 Qayta", f"repost_{n['id']}"),
            ib("⏸", f"pause_{n['id']}"),
            ib("✅ Tugat", f"done_{n['id']}"),
        ])
        await msg.answer(
            f"{st} *{n['product_name']}* — {n['quantity']} {n['unit']}{badge}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

@router.callback_query(F.data == "new_need")
async def new_need_btn(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await need_start(call.message, state)

@router.callback_query(F.data.startswith("view_batch_"))
async def view_batch_offers(call: CallbackQuery):
    batch_id = int(call.data[11:])
    await _show_batch_table(call.message, batch_id)
    await call.answer()

async def _show_batch_table(target_msg, batch_id: int):
    """Batch dagi barcha takliflarni jadval ko'rinishida ko'rsatadi."""
    needs = await db_all(
        "SELECT * FROM needs WHERE batch_id=? AND status != 'cancelled' ORDER BY id",
        (batch_id,),
    )
    if not needs:
        await target_msg.answer("📭 Bu buyurtmada mahsulot yo'q.")
        return

    # Barcha sotuvchilarni topamiz
    sellers_map = {}  # seller_id → name
    for n in needs:
        offs = await db_all(
            "SELECT o.*, u.clinic_name, u.full_name FROM offers o "
            "JOIN users u ON o.seller_id=u.id "
            "WHERE o.need_id=? AND o.price > 0 ORDER BY o.price ASC",
            (n["id"],),
        )
        for o in offs:
            sid = o["seller_id"]
            if sid not in sellers_map:
                sellers_map[sid] = o["clinic_name"] or o["full_name"] or f"Sotuvchi{sid}"

    has_offers = len(sellers_map) > 0
    txt = f"📊 *Jadval #{batch_id}*\n_{len(needs)} ta mahsulot"
    txt += f", {len(sellers_map)} ta taklif_\n\n" if has_offers else " — taklif kutilmoqda_\n\n"

    rows_for_accept = []  # (need_id, best_offer_id, best_price, seller_name)

    for n in needs:
        offs = await db_all(
            "SELECT o.*, u.clinic_name, u.full_name FROM offers o "
            "JOIN users u ON o.seller_id=u.id "
            "WHERE o.need_id=? AND o.price > 0 ORDER BY o.price ASC",
            (n["id"],),
        )
        st = {"active":"🟢","paused":"⏸","done":"✅","cancelled":"❌"}.get(n["status"],"📋")
        txt += f"{st} *{n['product_name']}* — {n['quantity']} {n['unit']}\n"
        if offs:
            for i, o in enumerate(offs, 1):
                sname  = o["clinic_name"] or o["full_name"] or "Sotuvchi"
                marker = "✅ " if i == 1 else "   "
                note   = f" _{o['note']}_" if o.get("note") and o["note"] != "mavjud_emas" else ""
                txt   += f"  {marker}{i}. {sname} — {o['price']:,.0f} so'm{note}\n"
            if n["status"] == "active":
                best = offs[0]
                rows_for_accept.append((n["id"], best["id"], best["price"],
                                        best["clinic_name"] or best["full_name"] or "Sotuvchi"))
        else:
            txt += "  _taklif kelmagan_\n"
        txt += "\n"

    # Qabul tugmalari
    kb_rows = []
    if rows_for_accept:
        txt += "─────────────────\n"
        txt += "_Eng arzon taklif qabul qilish:_\n"
        for nid, oid, price, sname in rows_for_accept[:8]:
            short = sname[:12] + ("…" if len(sname) > 12 else "")
            kb_rows.append([ib(f"✅ {short} {price:,.0f}", f"acc_{oid}")])

    # Excel tugmasi
    kb_rows.append([ib("📥 Excel yuklab olish", f"xlsx_{batch_id}")])
    await target_msg.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))

@router.callback_query(F.data.startswith("xlsx_"))
async def download_xlsx(call: CallbackQuery):
    batch_id = int(call.data[5:])
    await call.answer("⏳ Excel tayyorlanmoqda...")
    path = await build_excel(batch_id)
    if not path:
        await call.message.answer("❌ Excel yaratib bo'lmadi (openpyxl o'rnatilmagan?)")
        return
    import aiofiles
    async with aiofiles.open(path, "rb") as f:
        data = await f.read()
    await call.message.answer_document(
        document=("jadval.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        caption=f"📊 Jadval #{batch_id}",
    )
    try:
        import os as _os
        _os.remove(path)
    except Exception:
        pass

@router.callback_query(F.data.startswith("view_offers_"))
async def view_offers(call: CallbackQuery):
    nid  = int(call.data[12:])
    nd   = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
    offs = await db_all(
        "SELECT o.*, u.full_name, u.phone, u.clinic_name "
        "FROM offers o JOIN users u ON o.seller_id=u.id "
        "WHERE o.need_id=? AND o.status='pending' ORDER BY o.price ASC",
        (nid,),
    )
    if not offs:
        await call.answer("Taklif yo'q hali", show_alert=True)
        return

    txt = f"📩 *{nd['product_name']}* uchun takliflar\n_{len(offs)} ta, arzondan:_\n\n"
    for i, o in enumerate(offs, 1):
        name  = o["clinic_name"] or o["full_name"] or "Sotuvchi"
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        txt  += f"{medal} *{name}*\n   💰 {o['price']:,.0f} so'm/{nd['unit']}\n   🚚 {o['delivery_hours']} soat\n\n"

    rows = [[ib(f"✅ {i}. Qabul — {o['price']:,.0f} so'm", f"acc_{o['id']}")] for i, o in enumerate(offs, 1)]
    rows.append([ib("◀️ Orqaga", "back")])
    await call.message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()

@router.callback_query(F.data.startswith("acc_"))
async def accept_offer(call: CallbackQuery):
    oid = int(call.data[4:])
    o   = await db_get(
        "SELECT o.*, u.full_name, u.phone, u.clinic_name, u.region, u.address "
        "FROM offers o JOIN users u ON o.seller_id=u.id WHERE o.id=?", (oid,)
    )
    if not o:
        await call.answer("Taklif topilmadi", show_alert=True)
        return

    await db_run("UPDATE offers SET status='accepted' WHERE id=?", (oid,))
    await db_run("UPDATE needs SET status='paused' WHERE id=?", (o["need_id"],))

    name  = o["clinic_name"] or o["full_name"] or "Sotuvchi"
    phone = o["phone"] or "—"
    await call.message.edit_text(
        f"✅ *Qabul qilindi!*\n\n🏪 {name}\n📞 {phone}\n\n_Sotuvchi siz bilan bog'lanadi._"
    )

    # Sotuvchiga klinika ma'lumoti
    clinic = await get_user(call.from_user.id)
    if clinic:
        try:
            await bot.send_message(
                o["seller_id"],
                f"🎉 *Taklifingiz qabul qilindi!*\n\n"
                f"🏥 {clinic['clinic_name'] or clinic['full_name'] or 'Klinika'}\n"
                f"📞 {clinic['phone'] or '—'}\n"
                f"📍 {clinic['region'] or '—'}\n"
                f"🏠 {clinic['address'] or '—'}",
            )
        except Exception:
            pass
    await call.answer("✅")

@router.callback_query(F.data.startswith("repost_"))
async def repost_need(call: CallbackQuery):
    nid     = int(call.data[7:])
    nd      = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
    expires = (datetime.now() + timedelta(hours=nd["deadline_hours"])).isoformat()
    await db_run("UPDATE needs SET status='active', expires_at=? WHERE id=?", (expires, nid))
    mid = await post_to_channel(nid, dict(nd))
    if mid:
        await db_run("UPDATE needs SET channel_message_id=? WHERE id=?", (mid, nid))
    chan = CHANNEL_ID.lstrip("@") if isinstance(CHANNEL_ID, str) else str(CHANNEL_ID)
    link = f"[Ko'rish](https://t.me/{chan}/{mid})" if mid else ""
    await call.message.answer(f"🔄 *{nd['product_name']}* qayta joylashtirildi! {link}")
    await call.answer("✅")

@router.callback_query(F.data.startswith("pause_"))
async def pause_need(call: CallbackQuery):
    await db_run("UPDATE needs SET status='paused' WHERE id=?", (int(call.data[6:]),))
    await call.answer("⏸ Pauza")

@router.callback_query(F.data.startswith("done_"))
async def done_need(call: CallbackQuery):
    await db_run("UPDATE needs SET status='done' WHERE id=?", (int(call.data[5:]),))
    await call.answer("✅ Yakunlandi")

# ── TAKLIFLAR (klinika uchun) ─────────────────────────────────────────────────
@router.message(F.text == "📩 Takliflar")
async def clinic_offers(msg: Message):
    uid  = msg.from_user.id
    offs = await db_all(
        "SELECT o.*, n.product_name as np, n.unit as nu, u.clinic_name, u.full_name, u.phone "
        "FROM offers o "
        "JOIN needs n ON o.need_id=n.id "
        "JOIN users u ON o.seller_id=u.id "
        "WHERE n.owner_id=? AND o.status='pending' ORDER BY o.price ASC LIMIT 30",
        (uid,),
    )
    if not offs:
        await msg.answer("📭 Hali taklif kelmagan.")
        return
    await msg.answer(f"📩 *Kelgan takliflar:* {len(offs)} ta\n_(arzondan qimmatga)_")
    for i, o in enumerate(offs, 1):
        name  = o["clinic_name"] or o["full_name"] or "Sotuvchi"
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        note  = f"\n📝 _{o['note']}_" if o.get("note") else ""
        await msg.answer(
            f"{medal} *{o['np']}*\n"
            f"💰 {o['price']:,.0f} so'm/{o['nu']}\n"
            f"🚚 {o['delivery_hours']} soat\n"
            f"🏪 {name}{note}",
            reply_markup=ik(
                [ib("✅ Qabul", f"acc_{o['id']}"), ib("❌ Rad", f"rej_{o['id']}")],
            ),
        )

@router.callback_query(F.data.startswith("rej_"))
async def reject_offer(call: CallbackQuery):
    await db_run("UPDATE offers SET status='rejected' WHERE id=?", (int(call.data[4:]),))
    await call.answer("❌ Rad etildi")

@router.callback_query(F.data == "back")
async def cb_back(call: CallbackQuery):
    await call.answer()

# ── JADVAL ────────────────────────────────────────────────────────────────────
async def build_table(batch_id: int) -> str:
    """Batch dagi ehtiyojlar va takliflar jadvalini matn sifatida qaytaradi."""
    needs = await db_all(
        "SELECT * FROM needs WHERE batch_id=? ORDER BY id", (batch_id,)
    )
    if not needs:
        return "Bo'sh jadval."

    lines = [f"📊 *Jadval #{batch_id}*\n"]
    for n in needs:
        offs = await db_all(
            "SELECT o.*, u.clinic_name, u.full_name FROM offers o "
            "JOIN users u ON o.seller_id=u.id "
            "WHERE o.need_id=? ORDER BY o.price ASC",
            (n["id"],),
        )
        lines.append(f"🦷 *{n['product_name']}* — {n['quantity']} {n['unit']}")
        if not offs:
            lines.append("   _Taklif kelmagan_")
        else:
            for i, o in enumerate(offs, 1):
                name   = o["clinic_name"] or o["full_name"] or "Sotuvchi"
                marker = "✅ " if i == 1 else ""
                lines.append(f"   {marker}{i}. {name} — {o['price']:,.0f} so'm")
        lines.append("")
    return "\n".join(lines)

async def build_excel(batch_id: int):
    """Excel fayl yaratadi, path qaytaradi."""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        return None

    needs = await db_all("SELECT * FROM needs WHERE batch_id=?", (batch_id,))
    sellers_set = set()
    need_offers = {}
    for n in needs:
        offs = await db_all(
            "SELECT o.*, u.clinic_name, u.full_name FROM offers o "
            "JOIN users u ON o.seller_id=u.id "
            "WHERE o.need_id=? ORDER BY o.price ASC",
            (n["id"],),
        )
        need_offers[n["id"]] = list(offs)
        for o in offs:
            sellers_set.add(o["clinic_name"] or o["full_name"] or f"Sotuvchi{o['seller_id']}")

    sellers = sorted(sellers_set)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Jadval #{batch_id}"

    # Header
    header = ["Mahsulot", "Miqdor", "Birlik"] + [f"{s}\n(1 ta narx)" for s in sellers] + ["Eng arzon jami"]
    for col, h in enumerate(header, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="4F81BD")
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center")

    for row_i, n in enumerate(needs, 2):
        ws.cell(row=row_i, column=1, value=n["product_name"])
        ws.cell(row=row_i, column=2, value=n["quantity"])
        ws.cell(row=row_i, column=3, value=n["unit"])
        offs      = need_offers[n["id"]]
        qty       = float(n["quantity"])
        min_total = None
        for o in offs:
            seller_name = o["clinic_name"] or o["full_name"] or f"Sotuvchi{o['seller_id']}"
            if seller_name in sellers:
                col_i   = sellers.index(seller_name) + 4
                unit_p  = o["price"]          # 1 ta uchun
                total_p = unit_p * qty        # jami
                # Katakda: "1 ta: 45,000" yozamiz, ustun sarlavhasida miqdor ko'rinadi
                ws.cell(row=row_i, column=col_i, value=unit_p)
                if min_total is None or total_p < min_total:
                    min_total = total_p
        if min_total is not None:
            last_col = len(sellers) + 4
            cell = ws.cell(row=row_i, column=last_col, value=min_total)
            cell.fill = PatternFill("solid", fgColor="E2EFDA")
            cell.font = Font(bold=True)

    # Column width
    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)

    path = os.path.join(BASE_DIR, f"jadval_{batch_id}.xlsx")
    wb.save(path)
    return path

# ── SOTUVCHI: EHTIYOJLAR ──────────────────────────────────────────────────────
@router.message(F.text == "🔔 Ehtiyojlar")
async def seller_feed(msg: Message):
    needs = await db_all(
        "SELECT n.*, u.region FROM needs n JOIN users u ON n.owner_id=u.id "
        "WHERE n.status='active' ORDER BY n.created_at DESC LIMIT 20"
    )
    if not needs:
        await msg.answer("📭 Hozircha aktiv ehtiyoj yo'q.")
        return

    await msg.answer(f"🔔 *Aktiv ehtiyojlar:* {len(needs)} ta")
    for n in needs:
        existing = await db_get(
            "SELECT id FROM offers WHERE need_id=? AND seller_id=?", (n["id"], msg.from_user.id)
        )
        if existing:
            kb = ik([ib("✅ Taklif yuborilgan", "noop")])
        elif WEBAPP_URL:
            url = f"{WEBAPP_URL}/offer/{n['batch_id'] or n['id']}"
            kb  = ik([ib("💰 Narx kiriting →", web_app=WebAppInfo(url=url))])
        else:
            kb = ik([ib("📤 Taklif yuborish", f"offer_{n['id']}")])

        dl_map = {2: "2 soat", 24: "24 soat", 72: "3 kun", 168: "1 hafta"}
        await msg.answer(
            f"🦷 *{n['product_name']}*\n"
            f"📦 {n['quantity']} {n['unit']}\n"
            f"⏱ {dl_map.get(n['deadline_hours'], '?')} ichida\n"
            f"📍 {n['region'] or ''}",
            reply_markup=kb,
        )

@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer("Allaqachon taklif yubordingiz")

# ── SOTUVCHI: BOT ICHIDA TAKLIF (Mini App yo'q bo'lsa) ───────────────────────
@router.callback_query(F.data.startswith("offer_"))
async def offer_start(call: CallbackQuery, state: FSMContext):
    nid = int(call.data[6:])
    await _start_offer_bot(call, state, nid)
    await call.answer()

async def _start_offer_bot(msg_or_call, state: FSMContext, nid: int):
    uid = msg_or_call.from_user.id
    nd  = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
    if not nd or nd["status"] != "active":
        txt = "⚠️ Bu ehtiyoj yopilgan yoki topilmadi."
        if hasattr(msg_or_call, "answer"):
            await msg_or_call.answer(txt)
        else:
            await msg_or_call.message.answer(txt)
        return

    exists = await db_get("SELECT id FROM offers WHERE need_id=? AND seller_id=?", (nid, uid))
    if exists:
        txt = "⚠️ Bu ehtiyojga allaqachon taklif yubordingiz!"
        if hasattr(msg_or_call, "answer"):
            await msg_or_call.answer(txt)
        else:
            await msg_or_call.message.answer(txt)
        return

    await state.update_data(need_id=nid, need_unit=nd["unit"], need_name=nd["product_name"])
    await state.set_state(OfferState.price)
    txt = (
        f"📦 *{nd['product_name']}* — {nd['quantity']} {nd['unit']}\n\n"
        f"💰 Narxingiz? _(1 {nd['unit']} uchun, so'mda)_"
    )
    no_stock = ik([ib("❌ Mavjud emas", f"no_stock_{nid}")])
    if hasattr(msg_or_call, "answer"):
        await msg_or_call.answer(txt, reply_markup=no_stock)
    else:
        await msg_or_call.message.answer(txt, reply_markup=no_stock)

@router.callback_query(F.data.startswith("no_stock_"))
async def no_stock(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ *Mavjud emas* deb belgilandi. Rahmat!")
    await call.answer()

@router.message(OfferState.price)
async def offer_price(msg: Message, state: FSMContext):
    try:
        price = float(msg.text.replace(" ", "").replace(",", ""))
    except Exception:
        await msg.answer("❌ Faqat raqam kiriting! _Masalan: 285000_")
        return
    await state.update_data(price=price)
    await state.set_state(OfferState.note)
    await msg.answer(
        "📝 Izoh? _(ixtiyoriy: brend, sifat, muddat...)_",
        reply_markup=ik([ib("⏭ Izohsiz yuborish", "offer_no_note")]),
    )

@router.callback_query(F.data == "offer_no_note", OfferState.note)
async def offer_no_note(call: CallbackQuery, state: FSMContext):
    await _save_offer(call, state, note=None)
    await call.answer()

@router.message(OfferState.note)
async def offer_note(msg: Message, state: FSMContext):
    await _save_offer(msg, state, note=msg.text)

async def _save_offer(obj, state: FSMContext, note):
    uid = obj.from_user.id
    d   = await state.get_data()
    u   = await get_user(uid)

    # Delivery default 24 soat
    await db_insert(
        "INSERT INTO offers(need_id,seller_id,product_name,price,unit,delivery_hours,note) VALUES(?,?,?,?,?,?,?)",
        (d["need_id"], uid, d["need_name"], d["price"], d["need_unit"], 24, note),
    )

    nd     = await db_get(
        "SELECT n.*, u2.id as cid FROM needs n JOIN users u2 ON n.owner_id=u2.id WHERE n.id=?",
        (d["need_id"],),
    )
    shop   = await db_get("SELECT shop_name FROM shops WHERE owner_id=? AND status='active'", (uid,))
    sname  = (shop["shop_name"] if shop else None) or u["clinic_name"] or u["full_name"] or "Sotuvchi"
    note_t = f"\n📝 _{note}_" if note else ""

    try:
        await bot.send_message(
            nd["cid"],
            f"📩 *Yangi taklif!*\n\n"
            f"🦷 {d['need_name']}\n"
            f"💰 *{d['price']:,.0f} so'm*/{d['need_unit']}\n"
            f"🏪 {sname}{note_t}",
            reply_markup=ik([ib(f"📩 Barcha takliflarni ko'rish", f"view_offers_{d['need_id']}")]),
        )
    except Exception as e:
        log.error(f"Klinikaga xabar xato: {e}")

    await state.clear()
    txt = f"✅ *Taklif yuborildi!*\n\n🦷 {d['need_name']}\n💰 {d['price']:,.0f} so'm/{d['need_unit']}"
    if note:
        txt += f"\n📝 {note}"
    if hasattr(obj, "answer"):
        await obj.answer(txt)
    else:
        await obj.message.answer(txt)

# ── SOTUVCHI: TAKLIFLARIM ─────────────────────────────────────────────────────
@router.message(F.text == "📤 Takliflarim")
async def my_offers(msg: Message):
    offs = await db_all(
        "SELECT o.*, n.product_name as np FROM offers o "
        "JOIN needs n ON o.need_id=n.id WHERE o.seller_id=? ORDER BY o.created_at DESC LIMIT 20",
        (msg.from_user.id,),
    )
    if not offs:
        await msg.answer("📭 Hali taklif yubormagansiz.")
        return
    await msg.answer(f"📤 *Takliflarim:* {len(offs)} ta")
    for o in offs:
        st = {"pending": "⏳", "accepted": "✅", "rejected": "❌"}.get(o["status"], "📤")
        await msg.answer(f"{st} *{o['np']}*\n💰 {o['price']:,.0f} so'm")

# ── DO'KON ────────────────────────────────────────────────────────────────────
@router.message(F.text == "🏪 Do'konim")
async def my_shop(msg: Message):
    shop = await db_get("SELECT * FROM shops WHERE owner_id=? AND status='active'", (msg.from_user.id,))
    if not shop:
        await msg.answer(
            "🏪 Do'koningiz yo'q yoki tasdiqlanmagan.",
            reply_markup=ik([ib("➕ Do'kon ochish", "open_shop")]),
        )
        return
    await msg.answer(
        f"🏪 *{shop['shop_name']}*\n"
        f"📂 {shop['category']}\n"
        f"🤝 Xaridlar: *{shop['total_deals'] or 0} ta*",
    )

@router.callback_query(F.data == "open_shop")
async def open_shop(call: CallbackQuery, state: FSMContext):
    if not await has_profile(call.from_user.id):
        await call.message.answer(
            "⚠️ Avval profilingizni to'ldiring!",
            reply_markup=ik([ib("✏️ To'ldirish", "edit_profile")]),
        )
        await call.answer()
        return
    await state.set_state(ShopState.cat)
    await call.message.answer("📂 Do'kon kategoriyasini tanlang:", reply_markup=kb_shop_cats())
    await call.answer()

@router.callback_query(F.data.startswith("cat_"), ShopState.cat)
async def shop_cat(call: CallbackQuery, state: FSMContext):
    cats = {
        "cat_1": "🦷 Terapevtik",
        "cat_2": "⚙️ Jarrohlik & Implant",
        "cat_3": "🔬 Zubtexnik",
        "cat_4": "🧪 Dezinfeksiya",
        "cat_5": "💡 Asbob-uskunalar",
    }
    await state.update_data(cat=cats.get(call.data, call.data))
    await state.set_state(ShopState.name)
    await call.message.answer("🏪 Do'kon nomini kiriting:\n\n_Masalan: DentalPlus Toshkent_")
    await call.answer()

@router.message(ShopState.name)
async def shop_name(msg: Message, state: FSMContext):
    d = await state.get_data()
    u = await get_user(msg.from_user.id)
    await db_insert(
        "INSERT INTO shops(owner_id,shop_name,category,phone,region) VALUES(?,?,?,?,?)",
        (msg.from_user.id, msg.text, d["cat"], u["phone"], u["region"]),
    )
    await state.clear()
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(
                aid,
                f"🏪 *Yangi do'kon!*\n\n"
                f"📛 {msg.text}\n"
                f"👤 {u['clinic_name'] or u['full_name']}\n"
                f"📞 {u['phone']}",
                reply_markup=ik(
                    [ib("✅ Tasdiqlash", f"shopok_{msg.from_user.id}"),
                     ib("❌ Rad", f"shoprej_{msg.from_user.id}")],
                ),
            )
        except Exception:
            pass
    await msg.answer("⏳ Do'kon admin tasdiqlashini kutmoqda.")

@router.callback_query(F.data.startswith("shopok_"))
async def shop_ok(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    uid = int(call.data[7:])
    await db_run("UPDATE shops SET status='active' WHERE owner_id=?", (uid,))
    try:
        await bot.send_message(uid, "✅ Do'koningiz faollashdi!")
    except Exception:
        pass
    await call.message.edit_text(call.message.text + "\n\n✅ TASDIQLANDI", reply_markup=None)
    await call.answer("✅")

@router.callback_query(F.data.startswith("shoprej_"))
async def shop_rej(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    uid = int(call.data[8:])
    await db_run("UPDATE shops SET status='rejected' WHERE owner_id=?", (uid,))
    await call.message.edit_text(call.message.text + "\n\n❌ RAD ETILDI", reply_markup=None)
    await call.answer("❌")

# ── BALANS ────────────────────────────────────────────────────────────────────
@router.message(F.text == "💰 Hisobim")
async def show_balance(msg: Message):
    u    = await get_user(msg.from_user.id)
    card = await get_setting("card_number") or "9860020138100068"
    await msg.answer(
        f"💰 *Hisobingiz*\n\n"
        f"⚡️ Ball: *{u['balance'] or 0:.1f}*\n\n"
        f"_(Hozircha e'lon bepul)_",
        reply_markup=ik([ib("➕ Hisob to'ldirish", "topup")]),
    )

@router.callback_query(F.data == "topup")
async def topup_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(TopupState.amount)
    await call.message.answer(
        "💰 *Hisob to'ldirish*\n\n"
        "Qancha so'm o'tkazmoqchisiz?\n_Faqat raqam kiriting._"
    )
    await call.answer()

@router.message(TopupState.amount)
async def topup_amount(msg: Message, state: FSMContext):
    try:
        amount    = float(msg.text.replace(" ", "").replace(",", ""))
        ballprice = float(await get_setting("ball_price") or 1000)
        balls     = amount / ballprice
    except Exception:
        await msg.answer("❌ Faqat raqam kiriting!")
        return
    card = await get_setting("card_number") or "9860020138100068"
    await state.update_data(amount=amount, balls=balls)
    await state.set_state(TopupState.receipt)
    await msg.answer(
        f"✅ *{amount:,.0f} so'm → {balls:.1f} ball*\n\n"
        f"💳 Ushbu kartaga P2P o'tkazing:\n\n"
        f"`{card}`\n_Komilova M_\n\n"
        f"📸 O'tkazma screenshotini yuboring:"
    )

@router.message(TopupState.receipt, F.photo)
async def topup_receipt(msg: Message, state: FSMContext):
    d   = await state.get_data()
    fid = msg.photo[-1].file_id
    tid = await db_insert(
        "INSERT INTO transactions(user_id,amount,balls,type,receipt_file_id) VALUES(?,?,?,'topup',?)",
        (msg.from_user.id, d["amount"], d["balls"], fid),
    )
    u    = await get_user(msg.from_user.id)
    name = u["clinic_name"] or u["full_name"] or str(msg.from_user.id)
    for aid in ADMIN_IDS:
        try:
            await bot.send_photo(
                aid, fid,
                caption=f"💳 *Yangi chek #{tid}*\n\n👤 {name}\n💰 {d['amount']:,.0f} so'm → {d['balls']:.1f} ball",
                reply_markup=ik(
                    [ib("✅ Tasdiqlash", f"adm_ok_{tid}_{msg.from_user.id}_{d['balls']}"),
                     ib("❌ Rad", f"adm_rej_{tid}_{msg.from_user.id}")],
                ),
            )
        except Exception:
            pass
    await state.clear()
    await msg.answer("✅ Chek yuborildi! Admin 15-30 daqiqada tasdiqlaydi.")

@router.callback_query(F.data.startswith("adm_ok_"))
async def adm_ok(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    parts = call.data.split("_")
    tid, uid, balls = int(parts[2]), int(parts[3]), float(parts[4])
    await db_run("UPDATE transactions SET status='confirmed',confirmed_by=? WHERE id=?", (call.from_user.id, tid))
    await add_balance(uid, balls)
    try:
        await bot.send_message(uid, f"🎉 *Hisobingiz to'ldirildi!*\n\n+{balls:.1f} ball")
    except Exception:
        pass
    await call.message.edit_caption(call.message.caption + "\n\n✅ TASDIQLANDI", reply_markup=None)
    await call.answer("✅")

@router.callback_query(F.data.startswith("adm_rej_"))
async def adm_rej(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    parts = call.data.split("_")
    tid, uid = int(parts[2]), int(parts[3])
    await db_run("UPDATE transactions SET status='rejected' WHERE id=?", (tid,))
    try:
        await bot.send_message(uid, "❌ Chekingiz rad etildi. Admin bilan bog'laning.")
    except Exception:
        pass
    await call.message.edit_caption(call.message.caption + "\n\n❌ RAD ETILDI", reply_markup=None)
    await call.answer("❌")

# ── /debug ───────────────────────────────────────────────────────────────────
@router.message(Command('debug'))
async def debug_cmd(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    info = (
        f'BOT_TOKEN: OK\n'
        f'CHANNEL_ID: {CHANNEL_ID}\n'
        f'WEBAPP_URL: {WEBAPP_URL or "YOQ!"}\n'
        f'ADMIN_IDS: {ADMIN_IDS}\n'
        f'BASE_DIR: {BASE_DIR}'
    )
    await msg.answer(info, parse_mode=None)

# ── /testchannel ──────────────────────────────────────────────────────────────
@router.message(Command("testchannel"))
async def test_channel(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    await msg.answer(str(CHANNEL_ID), parse_mode=None)
    try:
        m = await bot.send_message(CHANNEL_ID, 'Test xabar!')
        await msg.answer(f'OK! msg_id={m.message_id}', parse_mode=None)
    except Exception as e:
        await msg.answer(str(e)[:500], parse_mode=None)

# ── CANCEL ───────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer("Bekor qilindi")

# ── WEB APP DATA (Mini App dan kelgan) ────────────────────────────────────────
@router.message(F.web_app_data)
async def web_app_data(msg: Message, state: FSMContext):
    import json
    try:
        data = json.loads(msg.web_app_data.data)
    except Exception:
        await msg.answer("❌ Ma'lumot xato.")
        return

    if data.get("type") == "bulk_order":
        items    = data.get("items", [])
        deadline = int(data.get("deadline", 24))
        uid      = msg.from_user.id
        u        = await get_user(uid)

        if not items:
            await msg.answer("❌ Buyurtma bo'sh.")
            return

        room    = await get_or_create_room(uid)
        expires = (datetime.now() + timedelta(hours=deadline)).isoformat()

        batch_id = await db_insert(
            "INSERT INTO batches(owner_id,deadline_hours,expires_at) VALUES(?,?,?)",
            (uid, deadline, expires),
        )

        saved_needs = []
        for item in items:
            nid = await db_insert(
                "INSERT INTO needs(batch_id,room_id,owner_id,product_name,quantity,unit,deadline_hours,expires_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (batch_id, room["id"], uid,
                 item["name"], float(item["qty"]), item.get("unit","dona"),
                 deadline, expires),
            )
            need = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
            saved_needs.append(dict(need))

        # Bitta paket post kanalga
        mid = await post_batch_to_channel(batch_id, saved_needs, dict(u))
        if mid:
            for n in saved_needs:
                await db_run("UPDATE needs SET channel_message_id=? WHERE id=?", (mid, n["id"]))

        dl_map  = {2:"2 soat",24:"24 soat",72:"3 kun",168:"1 hafta"}
        preview = "\n".join([f"• {n['quantity']} {n['unit']} — {n['product_name']}" for n in saved_needs[:5]])
        if len(saved_needs) > 5:
            preview += f"\n...va yana {len(saved_needs)-5} ta"
        chan = CHANNEL_ID.lstrip("@") if isinstance(CHANNEL_ID, str) else str(CHANNEL_ID)
        link = f"\n[Kanalda ko'rish](https://t.me/{chan}/{mid})" if mid else ""
        await msg.answer(
            f"✅ *{len(saved_needs)} ta mahsulot joylashtirildi!*{link}\n\n"
            f"{preview}\n\n"
            f"⏱ {dl_map.get(deadline, str(deadline)+' soat')} ichida"
        )
        asyncio.create_task(notify_sellers_batch(batch_id, uid))

    elif data.get("type") == "offer":
        offers   = data.get("offers", [])
        batch_id = int(data.get("batch_id", 0))
        delivery = int(data.get("delivery", 24))
        uid      = msg.from_user.id
        u        = await get_user(uid)

        if not offers:
            await msg.answer("❌ Taklif bo'sh.")
            return

        shop  = await db_get("SELECT shop_name FROM shops WHERE owner_id=? AND status='active'", (uid,))
        sname = (shop["shop_name"] if shop else None) or u["clinic_name"] or u["full_name"] or "Sotuvchi"

        saved = 0
        unavail_count = 0
        for offer in offers:
            nid       = int(offer.get("need_id", 0))
            price     = float(offer.get("price", 0))
            unavail   = bool(offer.get("unavailable", False))
            note      = offer.get("note", "") or ""
            if not nid:
                continue
            nd = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
            if not nd:
                continue
            exists = await db_get("SELECT id FROM offers WHERE need_id=? AND seller_id=?", (nid, uid))
            if exists:
                continue
            if unavail:
                # Mavjud emas — 0 narx bilan saqlaymiz, note="mavjud_emas"
                await db_insert(
                    "INSERT INTO offers(need_id,batch_id,seller_id,product_name,price,unit,delivery_hours,note) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (nid, batch_id, uid, nd["product_name"], 0, nd["unit"], delivery, "mavjud_emas"),
                )
                unavail_count += 1
            elif price > 0:
                await db_insert(
                    "INSERT INTO offers(need_id,batch_id,seller_id,product_name,price,unit,delivery_hours,note) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (nid, batch_id, uid, nd["product_name"], price, nd["unit"], delivery, note),
                )
                saved += 1

        # Klinikaga xabar
        real_saved = saved
        if real_saved > 0:
            owner_rows = await db_all("SELECT DISTINCT owner_id FROM needs WHERE batch_id=?", (batch_id,))
            dl_map = {2:"2 soat",24:"24 soat",48:"2 kun",168:"1 hafta"}
            dl_txt = dl_map.get(delivery, f"{delivery} soat")
            for row in owner_rows:
                try:
                    await bot.send_message(
                        row["owner_id"],
                        f"📩 *Yangi taklif!*\n\n"
                        f"🏪 {sname}\n"
                        f"📦 {real_saved} ta mahsulotga narx berdi\n"
                        f"🚚 {dl_txt} ichida yetkazadi",
                        reply_markup=ik([ib("📩 Takliflarni ko'rish", f"view_batch_{batch_id}")]),
                    )
                except Exception:
                    pass

        parts = []
        if saved > 0:       parts.append(f"{saved} ta narx")
        if unavail_count > 0: parts.append(f"{unavail_count} ta mavjud emas")
        result_txt = " | ".join(parts) if parts else "hech narsa"
        await msg.answer(f"✅ *Yuborildi:* {result_txt}\n\n🏪 {sname}")

# ── KLINIKA MAHSULOTLARI (sevimlilar ro'yxati) ────────────────────────────────
@router.message(F.text == "📦 Mahsulotlarim")
async def my_products(msg: Message, state: FSMContext):
    uid      = msg.from_user.id
    products = await db_all(
        "SELECT * FROM clinic_products WHERE owner_id=? ORDER BY sort_order, id",
        (uid,),
    )
    if not products:
        await msg.answer(
            "📦 *Mahsulotlarim ro\'yxati bo\'sh*\n\n"
            "Ro\'yxat saqlasangiz, Mini App da avtomatik chiqadi.\n\n"
            "Har bir mahsulotni yangi qatorda yozing:\n"
            "_Masalan:\n"
            "Xarizma A2\n"
            "GC Fuji IX dona\n"
            "Latex qo\'lqop M_",
            reply_markup=ik([ib("✏️ Ro\'yxat kiritish", "edit_my_products")]),
        )
        return

    txt  = f"📦 *Mahsulotlarim:* {len(products)} ta\n\n"
    txt += "\n".join([f"{i}. {p['name']} ({p['unit']})" for i, p in enumerate(products, 1)])
    await msg.answer(
        txt,
        reply_markup=ik(
            [ib("✏️ Tahrirlash", "edit_my_products")],
            [ib("🗑 Hammasini o\'chirish", "clear_my_products")],
        ),
    )

@router.callback_query(F.data == "edit_my_products")
async def edit_my_products(call: CallbackQuery, state: FSMContext):
    uid      = call.from_user.id
    products = await db_all(
        "SELECT * FROM clinic_products WHERE owner_id=? ORDER BY sort_order, id", (uid,)
    )
    existing = "\n".join([p["name"] for p in products]) if products else ""
    await state.set_state(MyProductsState.editing)
    await call.message.answer(
        "✏️ *Mahsulotlar ro\'yxatini kiriting*\n\n"
        "Har bir mahsulotni yangi qatorda yozing.\n"
        "_Birlik ham yozsa bo\'ladi: `Latex qo\'lqop M dona`_\n\n"
        + (f"*Hozirgi ro\'yxat:*\n```\n{existing}\n```\n\n" if existing else "") +
        "Yangi ro\'yxatni yuboring:",
        reply_markup=ik([ib("❌ Bekor", "cancel")]),
    )
    await call.answer()

@router.message(MyProductsState.editing)
async def save_my_products(msg: Message, state: FSMContext):
    uid   = msg.from_user.id
    lines = [l.strip() for l in msg.text.strip().split("\n") if l.strip()]
    if not lines:
        await msg.answer("❌ Bo\'sh ro\'yxat. Qaytadan yuboring.")
        return

    # Eskilarni o\'chirib yangilarini saqlaymiz
    await db_run("DELETE FROM clinic_products WHERE owner_id=?", (uid,))
    for i, line in enumerate(lines):
        parts = line.rsplit(None, 1)
        # Oxirgi so\'z unit bo\'lishi mumkin
        known_units = {"dona", "kg", "litr", "quti", "paket", "ml", "gr", "mm"}
        if len(parts) == 2 and parts[1].lower() in known_units:
            name, unit = parts[0].strip(), parts[1].lower()
        else:
            name, unit = line.strip(), "dona"
        await db_insert(
            "INSERT INTO clinic_products(owner_id,name,unit,sort_order) VALUES(?,?,?,?)",
            (uid, name, unit, i),
        )

    await state.clear()
    await msg.answer(
        f"✅ *{len(lines)} ta mahsulot saqlandi!*\n\n"
        f"Endi *Ko\'p mahsulot* bosganda Mini App da shu ro\'yxat chiqadi."
    )

@router.callback_query(F.data == "clear_my_products")
async def clear_my_products(call: CallbackQuery):
    await db_run("DELETE FROM clinic_products WHERE owner_id=?", (call.from_user.id,))
    await call.message.edit_text("🗑 Ro\'yxat tozalandi.")
    await call.answer()

# ── FALLBACK ─────────────────────────────────────────────────────────────────
@router.message()
async def fallback(msg: Message, state: FSMContext):
    current = await state.get_state()
    if current:
        return  # FSM davom etayotgan bo'lsa ignore
    u  = await get_user(msg.from_user.id)
    lg = (u["lang"] if u else None) or "uz"
    if u and u["role"] in ("clinic", "zubtex"):
        await msg.answer("🏥 *Klinika paneli*", reply_markup=kb_clinic(lg))
    elif u and u["role"] == "seller":
        await msg.answer("🛒 *Sotuvchi paneli*", reply_markup=kb_seller(lg))
    else:
        await msg.answer(t(lg, "welcome"), reply_markup=kb_lang())

# ── MAIN ─────────────────────────────────────────────────────────────────────
# ── WEB SERVER (Mini App uchun) ───────────────────────────────────────────────
async def handle_order_page(request):
    path = os.path.join(BASE_DIR, "webapp", "order.html")
    if not os.path.exists(path):
        return _web.Response(text="order.html topilmadi", status=404)
    return _web.FileResponse(path)

async def handle_api_products(request):
    """GET /api/products/{uid} — klinikaning mahsulotlar ro'yxati"""
    uid      = int(request.match_info.get("uid", 0))
    products = await db_all(
        "SELECT name, unit FROM clinic_products WHERE owner_id=? ORDER BY sort_order, id",
        (uid,),
    )
    data = [{"name": p["name"], "unit": p["unit"]} for p in products]
    return _web.Response(
        text=_json.dumps(data, ensure_ascii=False),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )

# offer.html inline (fayl topilmasa ham ishlaydi)
_OFFER_HTML_PATH = os.path.join(BASE_DIR, "webapp", "offer.html")

async def handle_offer_page(request):
    path = _OFFER_HTML_PATH
    if os.path.exists(path):
        return _web.FileResponse(path)
    # Fallback — inline HTML
    log.warning(f"offer.html topilmadi: {path}, inline version ishlatilmoqda")
    return _web.Response(
        text=_get_offer_html_inline(),
        content_type="text/html",
        charset="utf-8",
    )

def _get_offer_html_inline():
    """offer.html inline version — fayl yo'q bo'lsa ishlatiladi."""
    return """<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>Narx kiriting</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:var(--tg-theme-bg-color,#fff);color:var(--tg-theme-text-color,#000);padding-bottom:90px}
.hdr{background:var(--tg-theme-secondary-bg-color,#f2f2f7);padding:14px 16px 10px;
  position:sticky;top:0;z-index:10;border-bottom:1px solid rgba(0,0,0,.08)}
.hdr h1{font-size:17px;font-weight:600}.hdr p{font-size:12px;opacity:.55;margin-top:2px}
.pb{height:3px;background:var(--tg-theme-secondary-bg-color,#f2f2f7)}
.pf{height:100%;background:var(--tg-theme-button-color,#007aff);transition:width .3s}
.spin{display:flex;align-items:center;justify-content:center;padding:60px 16px;
  flex-direction:column;gap:12px;color:var(--tg-theme-hint-color,#888);font-size:14px}
.sp{width:28px;height:28px;border:2.5px solid var(--tg-theme-secondary-bg-color,#ddd);
  border-top-color:var(--tg-theme-button-color,#007aff);border-radius:50%;animation:sp .7s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.item{border-bottom:1px solid rgba(0,0,0,.07);padding:12px 16px}
.item.unav{opacity:.45}
.ih{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.num{width:26px;height:26px;border-radius:50%;background:var(--tg-theme-secondary-bg-color,#f2f2f7);
  color:var(--tg-theme-hint-color,#888);font-size:11px;font-weight:600;
  display:flex;align-items:center;justify-content:center;flex-shrink:0}
.num.done{background:#E2EFDA;color:#3B6D11}
.nm{font-size:15px;font-weight:600;flex:1}
.qty{font-size:12px;color:var(--tg-theme-hint-color,#888);white-space:nowrap}
.pr{display:flex;align-items:center;gap:8px}
.pw{flex:1;position:relative}
.pi{width:100%;height:40px;border:1.5px solid rgba(0,0,0,.12);border-radius:10px;
  font-size:16px;font-weight:500;padding:0 52px 0 12px;
  background:var(--tg-theme-bg-color,#fff);color:var(--tg-theme-text-color,#000);
  outline:none;-webkit-appearance:none}
.pi:focus{border-color:var(--tg-theme-button-color,#007aff)}
.pi.ok{border-color:#3B6D11}
.ps{position:absolute;right:8px;top:50%;transform:translateY(-50%);
  font-size:11px;color:var(--tg-theme-hint-color,#888);pointer-events:none}
.hint{font-size:12px;color:#3B6D11;margin-top:4px;font-weight:500;display:none}
.ub{height:40px;padding:0 10px;border:1.5px solid rgba(0,0,0,.10);border-radius:10px;
  font-size:12px;background:transparent;color:var(--tg-theme-hint-color,#888);
  cursor:pointer;white-space:nowrap;flex-shrink:0}
.ub.on{background:#FCEBEB;border-color:#F09595;color:#A32D2D}
.ni{width:100%;margin-top:8px;border:1.5px solid rgba(0,0,0,.08);border-radius:10px;
  font-size:14px;padding:8px 12px;background:var(--tg-theme-secondary-bg-color,#f2f2f7);
  color:var(--tg-theme-text-color,#000);outline:none;resize:none;font-family:inherit;min-height:36px}
.dlr{padding:10px 16px;border-bottom:1px solid rgba(0,0,0,.07)}
.dll{font-size:13px;opacity:.55;margin-bottom:8px}
.chips{display:flex;gap:8px;flex-wrap:wrap}
.chip{padding:6px 14px;border-radius:16px;border:1px solid rgba(0,0,0,.12);
  font-size:13px;font-weight:500;cursor:pointer;background:transparent;
  color:var(--tg-theme-text-color,#000)}
.chip.sel{background:var(--tg-theme-button-color,#007aff);color:#fff;border-color:transparent}
.bot{position:fixed;bottom:0;left:0;right:0;padding:8px 16px 12px;
  background:var(--tg-theme-bg-color,#fff);border-top:1px solid rgba(0,0,0,.08);z-index:20}
.bi{display:flex;justify-content:space-between;font-size:12px;
  color:var(--tg-theme-hint-color,#888);margin-bottom:8px}
.ts{font-weight:600;color:var(--tg-theme-button-color,#007aff)}
.sb{width:100%;padding:14px;border:none;border-radius:12px;
  background:var(--tg-theme-button-color,#007aff);color:#fff;
  font-size:16px;font-weight:600;cursor:pointer}
.sb:disabled{opacity:.35;cursor:not-allowed}
</style>
</head>
<body>
<div class="hdr"><h1>💰 Narx kiriting</h1><p id="sub">Yuklanmoqda...</p></div>
<div class="pb"><div class="pf" id="pf" style="width:0%"></div></div>
<div id="ct"><div class="spin"><div class="sp"></div>Yuklanmoqda...</div></div>
<div class="dlr">
  <div class="dll">🚚 Yetkazib berish muddati:</div>
  <div class="chips">
    <button class="chip sel" data-val="2" onclick="sDl(this)">⚡️ 2 soat</button>
    <button class="chip" data-val="24" onclick="sDl(this)">🕐 24 soat</button>
    <button class="chip" data-val="48" onclick="sDl(this)">📅 2 kun</button>
    <button class="chip" data-val="168" onclick="sDl(this)">🗓 1 hafta</button>
  </div>
</div>
<div class="bot">
  <div class="bi"><span id="fc">0/0</span><span class="ts" id="tt"></span></div>
  <button class="sb" id="sb" onclick="send()" disabled>Narx kiriting</button>
</div>
<script>
var tg=window.Telegram&&window.Telegram.WebApp;
var bId=0,dlv=2,nds=[];
// batch_id ni URL path dan olish: /offer/42 yoki /offer/42?...
var _path=window.location.pathname;
var _parts2=_path.split('/');for(var _i=0;_i<_parts2.length-1;_i++){if(_parts2[_i]==='offer'){var _n=parseInt(_parts2[_i+1]);if(_n>0){bId=_n;break;}}}
// Query params dan ham tekshir
var qp=new URLSearchParams(window.location.search);
if(!bId&&qp.get('batch_id'))bId=parseInt(qp.get('batch_id'));
if(!bId&&qp.get('bid'))bId=parseInt(qp.get('bid'));
console.log('offer.html: bId='+bId+' path='+_path);
if(tg){tg.ready();tg.expand();}
function load(){
  if(!bId){showE("Buyurtma ID topilmadi (URL: "+window.location.href+")");return;}
  fetch('/api/needs/'+bId)
  .then(function(r){
    if(!r.ok) throw new Error('HTTP '+r.status);
    return r.json();
  })
  .then(function(d){
    if(!d||!d.length){
      showE("Mahsulot topilmadi (batch #"+bId+"). Buyurtma muddati tugagan bo'lishi mumkin.");
      return;
    }
    nds=d;render();
  })
  .catch(function(e){showE("Yuklab bo'lmadi (batch #"+bId+"): "+e.message);});
}
function showE(m){document.getElementById('ct').innerHTML='<div class="spin">'+m+'</div>';document.getElementById('sub').textContent='Xato';}
function esc(s){return(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function render(){
  document.getElementById('sub').textContent=nds.length+' ta mahsulot';
  var h='';
  for(var i=0;i<nds.length;i++){
    var n=nds[i];
    h+='<div class="item" id="it-'+n.id+'">'+
      '<div class="ih">'+
        '<div class="num" id="nm-'+n.id+'">'+(i+1)+'</div>'+
        '<div class="nm">'+esc(n.name)+'</div>'+
        '<div class="qty">Kerak: '+n.qty+' '+n.unit+'</div>'+
      '</div>'+
      '<div class="pr">'+
        '<div class="pw">'+
          '<input class="pi" id="pi-'+n.id+'" type="number" inputmode="numeric" '+
            'placeholder="1 '+n.unit+' narxi..." min="0" '+
            'oninput="oP('+n.id+','+n.qty+',\''+n.unit+'\')">'+
          '<span class="ps">so'm/'+n.unit+'</span>'+
        '</div>'+
        '<button class="ub" id="ub-'+n.id+'" onclick="tU('+n.id+')">Mavjud emas</button>'+
      '</div>'+
      '<div class="hint" id="ht-'+n.id+'"></div>'+
      '<textarea class="ni" id="ni-'+n.id+'" placeholder="Izoh..." rows="1"></textarea>'+
    '</div>';
  }
  document.getElementById('ct').innerHTML=h;
  ref();
}
function oP(id,qty,unit){
  var v=parseFloat(document.getElementById('pi-'+id).value)||0;
  var ht=document.getElementById('ht-'+id);
  var pi=document.getElementById('pi-'+id);
  if(v>0){
    pi.classList.add('ok');
    document.getElementById('ub-'+id).classList.remove('on');
    document.getElementById('it-'+id).classList.remove('unav');
    if(ht){ht.textContent=qty+' '+unit+' x '+v.toLocaleString()+' = '+(v*qty).toLocaleString()+" so'm";ht.style.display='block';}
  }else{pi.classList.remove('ok');if(ht)ht.style.display='none';}
  ref();
}
function tU(id){
  var b=document.getElementById('ub-'+id);
  var p=document.getElementById('pi-'+id);
  var it=document.getElementById('it-'+id);
  var ht=document.getElementById('ht-'+id);
  var on=b.classList.toggle('on');
  if(on){p.value='';p.classList.remove('ok');p.disabled=true;it.classList.add('unav');if(ht)ht.style.display='none';}
  else{p.disabled=false;it.classList.remove('unav');p.focus();}
  ref();
}
function ref(){
  var f=0,t=0;
  for(var i=0;i<nds.length;i++){
    var n=nds[i];
    var p=parseFloat((document.getElementById('pi-'+n.id)||{}).value)||0;
    var u=(document.getElementById('ub-'+n.id)||{}).classList&&document.getElementById('ub-'+n.id).classList.contains('on');
    var nm=document.getElementById('nm-'+n.id);
    if(u){f++;if(nm){nm.textContent='—';nm.classList.add('done');}}
    else if(p>0){f++;t+=p*n.qty;if(nm)nm.classList.add('done');}
    else{if(nm){nm.textContent=i+1;nm.classList.remove('done');}}
  }
  var pct=nds.length>0?Math.round(f/nds.length*100):0;
  document.getElementById('pf').style.width=pct+'%';
  document.getElementById('fc').textContent=f+'/'+nds.length+" to'ldirildi";
  document.getElementById('tt').textContent=t>0?'Jami: '+t.toLocaleString()+" so'm":'';
  var sb=document.getElementById('sb');
  sb.disabled=f===0;
  sb.textContent=f>0?('✅ '+f+' ta taklif yuborish'):'Narx kiriting';
}
function sDl(el){document.querySelectorAll('.chip').forEach(function(c){c.classList.remove('sel');});el.classList.add('sel');dlv=parseInt(el.dataset.val);}
function send(){
  var offs=[];
  for(var i=0;i<nds.length;i++){
    var n=nds[i];
    var pv=parseFloat((document.getElementById('pi-'+n.id)||{}).value)||0;
    var uv=(document.getElementById('ub-'+n.id)||{}).classList&&document.getElementById('ub-'+n.id).classList.contains('on');
    var nt=((document.getElementById('ni-'+n.id)||{}).value||'').trim();
    if(uv)offs.push({need_id:n.id,price:0,unavailable:true,note:nt});
    else if(pv>0)offs.push({need_id:n.id,price:pv,unavailable:false,note:nt});
  }
  if(!offs.length)return;
  var sb=document.getElementById('sb');
  sb.disabled=true;sb.textContent='⏳ Yuklanmoqda...';
  var uid=0;
  if(tg&&tg.initDataUnsafe&&tg.initDataUnsafe.user)uid=tg.initDataUnsafe.user.id;
  fetch('/api/submit_offer',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({payload:JSON.stringify({type:'offer',batch_id:bId,offers:offs,delivery:dlv}),user_id:uid,init_data:tg?tg.initData:''})
  }).then(function(r){return r.json();}).then(function(res){
    if(res.ok){sb.textContent='✅ Yuborildi!';setTimeout(function(){if(tg)tg.close();},1500);}
    else{sb.disabled=false;sb.textContent='✅ Taklif yuborish';alert('Xato: '+(res.error||'nomalum'));}
  }).catch(function(e){sb.disabled=false;sb.textContent='✅ Taklif yuborish';alert('Tarmoq xatosi: '+e.message);});
}
load();
</script>
</body>
</html>"""


async def handle_api_needs(request):
    """GET /api/needs/{batch_id} — batch dagi ehtiyojlar"""
    try:
        batch_id = int(request.match_info.get("batch_id", 0))
    except Exception:
        batch_id = 0

    if batch_id <= 0:
        return _web.Response(
            text=_json.dumps({"error": "batch_id noto'g'ri", "batch_id": batch_id}),
            content_type="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )

    # status filtrini olib tashlaymiz — done/paused ehtiyojlar ham ko'rinsin
    needs = await db_all(
        "SELECT id, product_name, quantity, unit, status FROM needs WHERE batch_id=? ORDER BY id",
        (batch_id,),
    )

    log.info(f"API /api/needs/{batch_id} -> {len(needs)} ta ehtiyoj")

    data = [
        {"id": n["id"], "name": n["product_name"], "qty": n["quantity"], "unit": n["unit"]}
        for n in needs
        if n["status"] not in ("cancelled",)
    ]
    return _web.Response(
        text=_json.dumps(data, ensure_ascii=False),
        content_type="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )

async def handle_submit_order(request):
    """order.html dan kelgan buyurtma — API orqali."""
    try:
        body    = await request.json()
        payload = body.get("payload", "")
        user_id = body.get("user_id")
        if not payload or not user_id:
            return _web.Response(
                text=_json.dumps({"ok": False, "error": "payload yoki user_id yo'q"}),
                content_type="application/json",
            )
        data     = _json.loads(payload)
        items    = data.get("items", [])
        deadline = int(data.get("deadline", 24))
        uid      = int(user_id)

        if not items:
            return _web.Response(
                text=_json.dumps({"ok": False, "error": "items bo'sh"}),
                content_type="application/json",
            )

        u = await get_user(uid)
        if not u:
            return _web.Response(
                text=_json.dumps({"ok": False, "error": "foydalanuvchi topilmadi"}),
                content_type="application/json",
            )

        room    = await get_or_create_room(uid)
        expires = (datetime.now() + timedelta(hours=deadline)).isoformat()

        batch_id = await db_insert(
            "INSERT INTO batches(owner_id,deadline_hours,expires_at) VALUES(?,?,?)",
            (uid, deadline, expires),
        )

        saved_needs = []
        for item in items:
            nid = await db_insert(
                "INSERT INTO needs(batch_id,room_id,owner_id,product_name,quantity,unit,deadline_hours,expires_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (batch_id, room["id"], uid,
                 item["name"], float(item["qty"]), item.get("unit","dona"),
                 deadline, expires),
            )
            need = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
            saved_needs.append(dict(need))

        mid = await post_batch_to_channel(batch_id, saved_needs, dict(u))
        if mid:
            for n in saved_needs:
                await db_run("UPDATE needs SET channel_message_id=? WHERE id=?", (mid, n["id"]))

        # Botda ham xabar yuboramiz
        dl_map   = {2:"2 soat",24:"24 soat",72:"3 kun",168:"1 hafta"}
        preview  = "\n".join([f"• {n['quantity']} {n['unit']} — {n['product_name']}" for n in saved_needs[:5]])
        chan = CHANNEL_ID.lstrip("@") if isinstance(CHANNEL_ID, str) else str(CHANNEL_ID)
        link = f"\n[Kanalda ko'rish](https://t.me/{chan}/{mid})" if mid else ""
        try:
            await bot.send_message(
                uid,
                f"✅ *{len(saved_needs)} ta mahsulot joylashtirildi!*{link}\n\n"
                f"{preview}\n\n"
                f"⏱ {dl_map.get(deadline, str(deadline)+' soat')} ichida",
            )
        except Exception as e:
            log.error(f"Buyurtmachi ga xabar xato: {e}")

        asyncio.create_task(notify_sellers_batch(batch_id, uid))

        return _web.Response(
            text=_json.dumps({"ok": True, "batch_id": batch_id, "count": len(saved_needs)}),
            content_type="application/json",
        )
    except Exception as e:
        log.error(f"submit_order xato: {e}")
        return _web.Response(
            text=_json.dumps({"ok": False, "error": str(e)}),
            content_type="application/json", status=500,
        )

async def handle_submit_offer(request):
    """Kanal orqali kelgan taklif — API orqali saqlanadi."""
    try:
        body     = await request.json()
        payload  = body.get("payload", "")
        user_id  = body.get("user_id")
        if not payload or not user_id:
            return _web.Response(
                text=_json.dumps({"ok": False, "error": "payload yoki user_id yo'q"}),
                content_type="application/json",
            )
        data = _json.loads(payload)
        if data.get("type") != "offer":
            return _web.Response(
                text=_json.dumps({"ok": False, "error": "noto'g'ri type"}),
                content_type="application/json",
            )

        uid      = int(user_id)
        offers   = data.get("offers", [])
        batch_id = int(data.get("batch_id", 0))
        delivery = int(data.get("delivery", 24))
        u        = await get_user(uid)
        if not u:
            return _web.Response(
                text=_json.dumps({"ok": False, "error": "foydalanuvchi topilmadi"}),
                content_type="application/json",
            )

        shop  = await db_get("SELECT shop_name FROM shops WHERE owner_id=? AND status='active'", (uid,))
        sname = (shop["shop_name"] if shop else None) or u["clinic_name"] or u["full_name"] or "Sotuvchi"

        saved = 0
        unavail_count = 0
        for offer in offers:
            nid     = int(offer.get("need_id", 0))
            price   = float(offer.get("price", 0))
            unavail = bool(offer.get("unavailable", False))
            note    = offer.get("note", "") or ""
            if not nid:
                continue
            nd = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
            if not nd:
                continue
            exists = await db_get("SELECT id FROM offers WHERE need_id=? AND seller_id=?", (nid, uid))
            if exists:
                continue
            if unavail:
                await db_insert(
                    "INSERT INTO offers(need_id,batch_id,seller_id,product_name,price,unit,delivery_hours,note) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (nid, batch_id, uid, nd["product_name"], 0, nd["unit"], delivery, "mavjud_emas"),
                )
                unavail_count += 1
            elif price > 0:
                await db_insert(
                    "INSERT INTO offers(need_id,batch_id,seller_id,product_name,price,unit,delivery_hours,note) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (nid, batch_id, uid, nd["product_name"], price, nd["unit"], delivery, note),
                )
                saved += 1

        if saved > 0:
            owner_rows = await db_all("SELECT DISTINCT owner_id FROM needs WHERE batch_id=?", (batch_id,))
            dl_map = {2:"2 soat",24:"24 soat",48:"2 kun",168:"1 hafta"}
            for row in owner_rows:
                try:
                    await bot.send_message(
                        row["owner_id"],
                        f"📩 *Yangi taklif!*\n\n"
                        f"🏪 {sname}\n"
                        f"📦 {saved} ta mahsulotga narx berdi\n"
                        f"🚚 {dl_map.get(delivery, str(delivery)+' soat')} ichida yetkazadi",
                        reply_markup=ik([ib("📩 Takliflarni ko'rish", f"view_batch_{batch_id}")]),
                    )
                except Exception:
                    pass

        parts = []
        if saved > 0: parts.append(f"{saved} ta narx")
        if unavail_count > 0: parts.append(f"{unavail_count} ta mavjud emas")
        return _web.Response(
            text=_json.dumps({"ok": True, "result": " | ".join(parts) if parts else "0"}),
            content_type="application/json",
        )
    except Exception as e:
        log.error(f"submit_offer xato: {e}")
        return _web.Response(
            text=_json.dumps({"ok": False, "error": str(e)}),
            content_type="application/json",
            status=500,
        )

async def start_webserver():
    app = _web.Application()
    app.router.add_get("/order",                  handle_order_page)
    app.router.add_get("/offer/{batch_id}",        handle_offer_page)
    app.router.add_get("/api/products/{uid}",      handle_api_products)
    app.router.add_get("/api/needs/{batch_id}",    handle_api_needs)
    app.router.add_post("/api/submit_order",       handle_submit_order)
    app.router.add_post("/api/submit_offer",       handle_submit_offer)
    webapp_dir = os.path.join(BASE_DIR, "webapp")
    if os.path.isdir(webapp_dir):
        app.router.add_static("/static", webapp_dir)
    runner = _web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = _web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info(f"🌐 Web server: http://0.0.0.0:{port}")

async def expire_checker():
    """Har 15 daqiqada muddati o'tgan ehtiyojlarni yopadi."""
    while True:
        try:
            now = datetime.now().isoformat()
            expired = await db_all(
                "SELECT * FROM needs WHERE status='active' AND expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            for n in expired:
                await db_run("UPDATE needs SET status='done' WHERE id=?", (n["id"],))
                # Kanal postini o'chirishga harakat
                if n.get("channel_message_id"):
                    try:
                        await bot.delete_message(CHANNEL_ID, n["channel_message_id"])
                    except Exception:
                        pass
            if expired:
                log.info(f"⏰ {len(expired)} ta ehtiyoj muddati tugadi")
        except Exception as e:
            log.error(f"Expire checker xato: {e}")
        await asyncio.sleep(900)  # 15 daqiqa

async def main():
    await init_db()
    dp.include_router(router)
    log.info("🦷 XAZDENT Bot ishga tushdi!")
    await start_webserver()
    asyncio.create_task(expire_checker())
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
