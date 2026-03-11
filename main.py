import asyncio, os, logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from database import init_db, get_user, db_run, db_get, db_all, db_insert
from database import get_setting, update_setting, add_balance, get_next_room_code
from texts import t, REGIONS, REGIONS_RU

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN  = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@xazdent")
ADMIN_IDS  = [int(x) for x in os.getenv("ADMIN_IDS","").split(",") if x.strip()]
CARD_NUM   = "9860020138100068"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp  = Dispatcher(storage=MemoryStorage())
router = Router()

# ── STATES ───────────────────────────────────────────────
class PS(StatesGroup):
    name = State(); phone = State(); region = State(); address = State()

class NS(StatesGroup):
    # FIX 3: tezlashtirilgan, faqat 3 ta majburiy + confirm
    product = State(); qty = State(); unit = State()
    deadline = State(); confirm = State()

class BulkNS(StatesGroup):
    # FIX 1: bir nechta ehtiyoj birdaniga
    items = State(); deadline = State(); confirm = State()

class TS(StatesGroup):
    amount = State(); receipt = State()

class OS(StatesGroup):
    product = State(); price = State(); delivery = State()

class SS(StatesGroup):
    cat = State(); name = State()

class AddProduct(StatesGroup):
    name = State(); price = State(); unit = State(); desc = State()

# ── KEYBOARDS ────────────────────────────────────────────
def ik(*rows): return InlineKeyboardMarkup(inline_keyboard=list(rows))
def ib(text, data): return InlineKeyboardButton(text=text, callback_data=data)
def rk(*rows, resize=True, one_time=False):
    return ReplyKeyboardMarkup(keyboard=list(rows), resize_keyboard=resize, one_time_keyboard=one_time)

def kb_lang():
    return ik([ib("🇺🇿 O'zbekcha","lang_uz"), ib("🇷🇺 Русский","lang_ru")])

def kb_role(lg):
    return ik([ib(t(lg,"role_clinic"),"role_clinic")],
              [ib(t(lg,"role_seller"),"role_seller")])

def kb_clinic(lg):
    return rk(
        [KeyboardButton(text="📋 Ehtiyojlarim"), KeyboardButton(text="➕ Yangi ehtiyoj")],
        [KeyboardButton(text="📦 Ko'p ehtiyoj"),  KeyboardButton(text="💰 Hisobim")],
        [KeyboardButton(text="🏠 Omborxona"),     KeyboardButton(text="⚙️ Profil")],
    )

def kb_seller(lg):
    return rk(
        [KeyboardButton(text="🔔 Yangi ehtiyojlar"), KeyboardButton(text="📤 Takliflarim")],
        [KeyboardButton(text="🏪 Do'konim"),          KeyboardButton(text="💰 Hisobim")],
        [KeyboardButton(text="⚙️ Profil")],
    )

def kb_regions(lg):
    regs = REGIONS if lg != "ru" else REGIONS_RU
    rows = []
    for i in range(0, len(regs), 2):
        row = [ib(regs[i], f"reg_{i}")]
        if i+1 < len(regs): row.append(ib(regs[i+1], f"reg_{i+1}"))
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_units():
    return ik([ib("📌 Dona","unit_dona"), ib("⚖️ Kg","unit_kg"), ib("💧 Litr","unit_litr")])

def kb_deadline(lg):
    return ik([ib("⚡️ 2 soat","dl_2"),  ib("🕐 24 soat","dl_24")],
              [ib("📅 3 kun","dl_72"),   ib("🗓 1 hafta","dl_168")])

def kb_delivery():
    return ik([ib("⚡️ 2 soat","del_2"),  ib("🕐 24 soat","del_24")],
              [ib("📅 2 kun","del_48"),   ib("🗓 1 hafta","del_168")])

def kb_skip_cancel():
    return ik([ib("⏭ O'tkazish","skip"), ib("❌ Bekor","cancel")])

def kb_confirm():
    return ik([ib("✅ Joylash","confirm"), ib("❌ Bekor","cancel")])

def kb_offer_action(oid):
    return ik([ib("✅ Qabul","acc_"+str(oid)), ib("❌ Rad","rej_"+str(oid))])

def kb_shop_cats():
    return ik([ib("🦷 Terapevtik","cat_1")], [ib("⚙️ Jarrohlik & Implant","cat_2")],
              [ib("🔬 Zubtexnik","cat_3")],   [ib("🧪 Dezinfeksiya","cat_4")],
              [ib("💡 Asbob-uskunalar","cat_5")])

def kb_prod_units():
    return ik([ib("📌 Dona","pu_dona"), ib("⚖️ Kg","pu_kg"), ib("💧 Litr","pu_litr")])

def kb_stat_period():
    return ik([ib("📅 Bu oy","stat_month"), ib("📆 Bu yil","stat_year")],
              [ib("🗓 Hammasi","stat_all")])

# ── HELPERS ──────────────────────────────────────────────
async def get_lang(uid):
    u = await get_user(uid)
    return u["lang"] if u else "uz"

async def has_profile(uid):
    u = await get_user(uid)
    return u and u["clinic_name"] and u["phone"] and u["region"]

async def post_channel(need):
    dl_map = {2:"2 soat",24:"24 soat",72:"3 kun",168:"1 hafta"}
    dl_txt = dl_map.get(need["deadline_hours"], f"{need['deadline_hours']}s")
    budget_txt = f"\n💰 Budjet: {need['budget']:,.0f} so'm gacha" if need.get("budget") else ""
    note_txt   = f"\n📝 {need['extra_note']}" if need.get("extra_note") else ""
    owner      = await get_user(need["owner_id"])
    words = need["product_name"].split()
    tags  = " ".join(f"#{w.lower()}" for w in words[:3] if len(w) > 2)
    txt = (
        f"📋 *BUYURTMA #{need['id']}*\n\n"
        f"🦷 {need['product_name']}\n"
        f"📦 {need['quantity']} {need['unit']}\n"
        f"⏱ {dl_txt} ichida"
        f"{budget_txt}{note_txt}\n\n"
        f"📍 {owner['region'] or ''}\n\n"
        f"{tags}\n💬 @XazdentBot da taklif yuboring"
    )
    try:
        msg = await bot.send_message(CHANNEL_ID, txt)
        return msg.message_id
    except Exception as e:
        log.error(f"Kanal xato: {e}")
        return None

# FIX 6: Barcha takliflar bitta xabarda, narx bo'yicha saralangan
async def send_offers_summary(uid, need_id):
    """Klinikaga barcha takliflarni bitta xabarda yuboradi"""
    nd   = await db_get("SELECT * FROM needs WHERE id=?", (need_id,))
    if not nd: return
    offs = await db_all(
        "SELECT o.*,u.full_name,u.phone,s.shop_name,s.total_deals FROM offers o "
        "JOIN users u ON o.seller_id=u.id LEFT JOIN shops s ON s.owner_id=u.id "
        "WHERE o.need_id=? AND o.status='pending' ORDER BY o.price ASC", (need_id,)
    )
    if not offs: return
    
    txt = f"📩 *{nd['product_name']}* — {len(offs)} ta taklif\n"
    txt += f"_(Arzondan qimmatga saralangan)_\n\n"
    for i, o in enumerate(offs, 1):
        shop  = o["shop_name"] or o["full_name"] or "Sotuvchi"
        deals = o["total_deals"] or 0
        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}."
        txt  += (
            f"{medal} *{shop}* ({'⭐'*min(deals//5+1,5) if deals else '🆕'})\n"
            f"   💰 {o['price']:,.0f} so'm/{nd['unit']}\n"
            f"   🚚 {o['delivery_hours']} soat\n"
            f"   🦷 {o['product_name']}\n\n"
        )
    
    # Inline tugmalar: har bir taklif uchun "Qabul" tugmasi
    rows = [[ib(f"✅ {i}. Qabul — {o['price']:,.0f} so'm", f"acc_{o['id']}")] for i,o in enumerate(offs,1)]
    rows.append([ib("📋 Ehtiyojlarimga qaytish","back_needs")])
    
    try:
        await bot.send_message(uid, txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except Exception as e:
        log.error(f"Summary yuborishda xato: {e}")

# ── START ─────────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    u = await get_user(msg.from_user.id)
    if not u:
        await db_run("INSERT OR IGNORE INTO users(id,username,full_name) VALUES(?,?,?)",
                     (msg.from_user.id, msg.from_user.username, msg.from_user.full_name))
        u = await get_user(msg.from_user.id)

    if u and u["role"] not in (None, "none"):
        lg  = u["lang"] or "uz"
        kb  = kb_clinic(lg) if u["role"]=="clinic" else kb_seller(lg)
        txt = "🏥 *Klinika paneli*" if u["role"]=="clinic" else "🛒 *Sotuvchi paneli*"
        await msg.answer(txt, reply_markup=kb)
        return
    await msg.answer(t("uz","welcome"), reply_markup=kb_lang())

@router.callback_query(F.data.startswith("lang_"))
async def cb_lang(call: CallbackQuery):
    lg = call.data[5:]
    await db_run("UPDATE users SET lang=? WHERE id=?", (lg, call.from_user.id))
    await call.message.edit_text(t(lg,"welcome"), reply_markup=kb_role(lg))
    await call.answer()

@router.callback_query(F.data.startswith("role_"))
async def cb_role(call: CallbackQuery):
    role = call.data[5:]
    await db_run("UPDATE users SET role=? WHERE id=?", (role, call.from_user.id))
    lg  = await get_lang(call.from_user.id)
    kb  = kb_clinic(lg) if role=="clinic" else kb_seller(lg)
    txt = "🏥 *Klinika paneli*" if role=="clinic" else "🛒 *Sotuvchi paneli*"
    await call.message.delete()
    await call.message.answer(txt, reply_markup=kb)
    await call.answer()

# ── PROFIL (FIX 4: darhol so'raydi) ──────────────────────
@router.message(F.text == "⚙️ Profil")
async def show_profile(msg: Message, state: FSMContext):
    u  = await get_user(msg.from_user.id)
    is_seller  = u and u["role"] == "seller"
    name_label = "🏪 Do'kon nomi" if is_seller else "🏥 Klinika nomi"
    txt = (
        f"⚙️ *Profil*\n\n"
        f"{name_label}: {u['clinic_name'] or '—'}\n"
        f"📞 Tel: {u['phone'] or '—'}\n"
        f"📍 Hudud: {u['region'] or '—'}\n"
        f"🏠 Manzil: {u['address'] or '—'}\n"
        f"💰 Balans: {u['balance'] or 0:.1f} ball"
    )
    await msg.answer(txt, reply_markup=ik([ib("✏️ Profilni tahrirlash","edit_profile")]))

async def _start_profile_flow(target, uid, state):
    """FIX 4: profil to'ldirishni darhol boshlaydi"""
    lg = await get_lang(uid)
    u  = await get_user(uid)
    await state.set_state(PS.name)
    ask = "🏪 Do'kon nomingizni kiriting:" if u and u["role"]=="seller" else "🏥 Klinika / ism-familiyangizni kiriting:"
    if hasattr(target, 'message'):
        await target.message.answer(ask)
        await target.answer()
    else:
        await target.answer(ask)

@router.callback_query(F.data == "edit_profile")
async def cb_edit_profile(call: CallbackQuery, state: FSMContext):
    await _start_profile_flow(call, call.from_user.id, state)

@router.message(PS.name)
async def ps_name(msg: Message, state: FSMContext):
    lg = await get_lang(msg.from_user.id)
    await state.update_data(clinic_name=msg.text)
    await state.set_state(PS.phone)
    kb = rk([KeyboardButton(text="📞 Raqamni yuborish", request_contact=True)], one_time=True)
    await msg.answer("📞 Telefon raqamingizni yuboring:", reply_markup=kb)

@router.message(PS.phone, F.contact)
async def ps_phone(msg: Message, state: FSMContext):
    await state.update_data(phone=msg.contact.phone_number)
    await state.set_state(PS.region)
    lg = await get_lang(msg.from_user.id)
    await msg.answer("📍 Viloyatingizni tanlang:", reply_markup=kb_regions(lg))

@router.callback_query(F.data.startswith("reg_"), PS.region)
async def ps_region(call: CallbackQuery, state: FSMContext):
    lg  = await get_lang(call.from_user.id)
    idx = int(call.data[4:])
    regs = REGIONS if lg != "ru" else REGIONS_RU
    region = regs[idx].split(" ",1)[1] if " " in regs[idx] else regs[idx]
    await state.update_data(region=region)
    await state.set_state(PS.address)
    await call.message.answer("🏠 Aniq manzilingizni kiriting:", reply_markup=ReplyKeyboardRemove())
    await call.answer()

@router.message(PS.address)
async def ps_address(msg: Message, state: FSMContext):
    d  = await state.get_data()
    lg = await get_lang(msg.from_user.id)
    await db_run("UPDATE users SET clinic_name=?,phone=?,region=?,address=? WHERE id=?",
                 (d["clinic_name"], d["phone"], d["region"], msg.text, msg.from_user.id))
    await state.clear()
    u  = await get_user(msg.from_user.id)
    kb = kb_clinic(lg) if u["role"]=="clinic" else kb_seller(lg)
    txt = "✅ Profil saqlandi! Endi ehtiyoj yozing." if u["role"]=="clinic" else "✅ Profil saqlandi! Do'konim bo'limiga kiring."
    await msg.answer(txt, reply_markup=kb)

# ── OMBORXONA ─────────────────────────────────────────────
@router.message(F.text == "🏠 Omborxona")
async def omborxona_menu(msg: Message):
    u = await get_user(msg.from_user.id)
    rooms = await db_all("SELECT * FROM rooms WHERE owner_id=? AND status='active'", (msg.from_user.id,))
    if not rooms:
        await msg.answer("🏠 *Omborxona*\n\nHali omborxona yo'q.",
                         reply_markup=ik([ib("➕ Omborxona ochish","new_room")])); return
    txt = "🏠 *Omborxonalarim:*\n\n"
    for r in rooms:
        cnt   = (await db_get("SELECT COUNT(*) as c FROM needs WHERE room_id=? AND status='active'",(r["id"],)))["c"]
        emoji = {"small":"🔹","standard":"🔷","premium":"💎"}.get(r["room_type"],"📦")
        txt  += f"{emoji} `{r['room_code']}` — {cnt}/{r['max_needs']} aktiv e'lon\n"
    await msg.answer(txt, reply_markup=ik([ib("➕ Yangi omborxona","new_room")]))

@router.callback_query(F.data=="new_room")
async def cb_new_room(call: CallbackQuery):
    lg = await get_lang(call.from_user.id)
    if not await has_profile(call.from_user.id):
        await call.message.answer("⚠️ Avval profilingizni to'ldiring.",
                                  reply_markup=ik([ib("✏️ Profilni to'ldirish","edit_profile")]))
        await call.answer(); return
    await call.message.answer("📦 Omborxona turini tanlang:",
        reply_markup=ik([ib("🔹 Kichik (10 e'lon) — Bepul","room_small")],
                        [ib("🔷 Standart (25 e'lon) — Bepul","room_standard")],
                        [ib("💎 Premium (150 e'lon) — Bepul","room_premium")]))
    await call.answer()

@router.callback_query(F.data.startswith("room_"))
async def cb_room(call: CallbackQuery):
    rtype = call.data[5:]
    max_n = {"small":10,"standard":25,"premium":150}[rtype]
    code  = await get_next_room_code(rtype)
    if not code:
        await call.message.answer("❌ Xona topilmadi."); return
    await db_insert("INSERT INTO rooms(room_code,room_type,owner_id,max_needs) VALUES(?,?,?,?)",
                    (code, rtype, call.from_user.id, max_n))
    await call.message.edit_text(f"✅ *Omborxona yaratildi!*\n\n🏠 Xona: `{code}`")
    await call.answer("✅")

# ── EHTIYOJ — TEZKOR (FIX 3) ─────────────────────────────
@router.message(F.text == "➕ Yangi ehtiyoj")
async def quick_need(msg: Message, state: FSMContext):
    if not await has_profile(msg.from_user.id):
        # FIX 4: darhol profil to'ldirishga o'tadi
        await msg.answer("⚠️ Profilingiz to'ldirilmagan. Hozir to'ldiramiz 👇")
        await _start_profile_flow(msg, msg.from_user.id, state)
        return
    # Birinchi omborxonani avtomatik topish
    room = await db_get(
        "SELECT r.* FROM rooms r WHERE r.owner_id=? AND r.status='active' "
        "ORDER BY r.id LIMIT 1", (msg.from_user.id,)
    )
    if not room:
        await msg.answer("🏠 Avval omborxona oching.",
                         reply_markup=ik([ib("➕ Omborxona ochish","new_room")])); return
    # Xona limitini tekshirish
    cnt = (await db_get("SELECT COUNT(*) as c FROM needs WHERE room_id=? AND status='active'",(room["id"],)))["c"]
    if cnt >= room["max_needs"]:
        await msg.answer(f"⚠️ Omborxona to'la ({cnt}/{room['max_needs']}). Yangi omborxona oching.",
                         reply_markup=ik([ib("➕ Yangi omborxona","new_room")])); return
    await state.update_data(room_id=room["id"], room_code=room["room_code"])
    await state.set_state(NS.product)
    await msg.answer("🦷 *Nima kerak?*\n\n_Masalan: Xarizma plomba A2, 3M ESPE_",
                     reply_markup=ReplyKeyboardRemove())

@router.message(NS.product)
async def ns_product(msg: Message, state: FSMContext):
    await state.update_data(product=msg.text)
    await state.set_state(NS.qty)
    await msg.answer("📦 *Miqdori?* (raqam + birlik)\n\n_Masalan: 5 dona, 2 kg_",
                     reply_markup=ik([ib("1 dona","q_1"), ib("2 dona","q_2"),
                                      ib("5 dona","q_5"), ib("10 dona","q_10")]))

@router.callback_query(F.data.startswith("q_"), NS.qty)
async def ns_qty_btn(call: CallbackQuery, state: FSMContext):
    val = call.data[2:]
    await state.update_data(qty=float(val), unit="dona")
    await state.set_state(NS.deadline)
    await call.message.answer("⏱ *Qachongacha kerak?*", reply_markup=kb_deadline("uz"))
    await call.answer()

@router.message(NS.qty)
async def ns_qty_text(msg: Message, state: FSMContext):
    text = msg.text.strip()
    # "5 dona", "2 kg", "3" kabi formatlarni parse qilish
    parts = text.split()
    try:
        qty  = float(parts[0].replace(",","."))
        unit = parts[1] if len(parts) > 1 else None
        await state.update_data(qty=qty, unit=unit)
        if unit:
            await state.set_state(NS.deadline)
            await msg.answer("⏱ *Qachongacha kerak?*", reply_markup=kb_deadline("uz"))
        else:
            await state.set_state(NS.unit)
            await msg.answer("⚖️ O'lchov birligi:", reply_markup=kb_units())
    except:
        await msg.answer("❌ Masalan: `5 dona` yoki `2 kg` yozing")

@router.callback_query(F.data.startswith("unit_"), NS.unit)
async def ns_unit(call: CallbackQuery, state: FSMContext):
    await state.update_data(unit=call.data[5:])
    await state.set_state(NS.deadline)
    await call.message.answer("⏱ *Qachongacha kerak?*", reply_markup=kb_deadline("uz"))
    await call.answer()

@router.callback_query(F.data.startswith("dl_"), NS.deadline)
async def ns_deadline(call: CallbackQuery, state: FSMContext):
    await state.update_data(dl=int(call.data[3:]))
    d = await state.get_data()
    await state.set_state(NS.confirm)
    preview = f"🦷 *{d['product']}*\n📦 {d['qty']} {d.get('unit','dona')}\n⏱ {call.data[3:]} soat ichida"
    await call.message.answer(f"✅ *Tasdiqlang:*\n\n{preview}", reply_markup=kb_confirm())
    await call.answer()

@router.callback_query(F.data=="confirm", NS.confirm)
async def ns_confirm(call: CallbackQuery, state: FSMContext):
    d       = await state.get_data()
    expires = (datetime.now()+timedelta(hours=d["dl"])).isoformat()
    nid     = await db_insert(
        "INSERT INTO needs(room_id,owner_id,product_name,quantity,unit,deadline_hours,expires_at) VALUES(?,?,?,?,?,?,?)",
        (d["room_id"], call.from_user.id, d["product"], d["qty"], d.get("unit","dona"), d["dl"], expires)
    )
    nd  = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
    mid = await post_channel(dict(nd))
    if mid:
        await db_run("UPDATE needs SET channel_message_id=? WHERE id=?", (mid, nid))
    # FIX 2: to'g'ri kanal linki
    chan = CHANNEL_ID.lstrip("@")
    link = f"[Kanalda ko'rish](https://t.me/{chan}/{mid})" if mid else ""
    await state.clear()
    await call.message.edit_text(
        f"✅ *E'lon joylashtirildi!*\n\n"
        f"🦷 {d['product']}\n"
        f"📦 {d['qty']} {d.get('unit','dona')}\n\n"
        f"{link}"
    )
    await call.answer("✅")

# ── FIX 1: KO'P EHTIYOJ BIRDANIGA ────────────────────────
@router.message(F.text == "📦 Ko'p ehtiyoj")
async def bulk_need_start(msg: Message, state: FSMContext):
    if not await has_profile(msg.from_user.id):
        await msg.answer("⚠️ Profilingiz to'ldirilmagan.",
                         reply_markup=ik([ib("✏️ To'ldirish","edit_profile")])); return
    room = await db_get("SELECT * FROM rooms WHERE owner_id=? AND status='active' ORDER BY id LIMIT 1",
                        (msg.from_user.id,))
    if not room:
        await msg.answer("🏠 Avval omborxona oching.",
                         reply_markup=ik([ib("➕ Omborxona ochish","new_room")])); return
    await state.update_data(room_id=room["id"], room_code=room["room_code"])
    await state.set_state(BulkNS.items)
    await msg.answer(
        "📦 *Ko'p ehtiyoj — ro'yxat usuli*\n\n"
        "Har bir mahsulotni yangi qatorda yozing:\n\n"
        "```\n5 dona Xarizma A2\n2 kg GC Fuji IX\n1 dona Endomotor\n```\n\n"
        "_Format: miqdor + birlik + nom_",
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(BulkNS.items)
async def bulk_items(msg: Message, state: FSMContext):
    lines   = [l.strip() for l in msg.text.strip().split("\n") if l.strip()]
    parsed  = []
    errors  = []
    for line in lines:
        parts = line.split(None, 2)
        if len(parts) >= 3:
            try:
                qty  = float(parts[0].replace(",","."))
                unit = parts[1]
                name = parts[2]
                parsed.append({"qty": qty, "unit": unit, "name": name})
            except:
                errors.append(line)
        else:
            errors.append(line)
    if not parsed:
        await msg.answer("❌ Format xato. Masalan:\n`5 dona Xarizma A2`"); return
    await state.update_data(bulk_items=parsed)
    await state.set_state(BulkNS.deadline)
    preview = "\n".join([f"• {p['qty']} {p['unit']} — {p['name']}" for p in parsed])
    err_txt = f"\n\n⚠️ Qabul qilinmadi: {', '.join(errors)}" if errors else ""
    await msg.answer(
        f"📋 *{len(parsed)} ta mahsulot:*\n\n{preview}{err_txt}\n\n⏱ Qachongacha kerak?",
        reply_markup=kb_deadline("uz")
    )

@router.callback_query(F.data.startswith("dl_"), BulkNS.deadline)
async def bulk_deadline(call: CallbackQuery, state: FSMContext):
    await state.update_data(dl=int(call.data[3:]))
    d     = await state.get_data()
    items = d["bulk_items"]
    await state.set_state(BulkNS.confirm)
    preview = "\n".join([f"• {p['qty']} {p['unit']} — {p['name']}" for p in items])
    await call.message.answer(
        f"✅ *Tasdiqlang:*\n\n{preview}\n\n⏱ {call.data[3:]} soat ichida\n\n"
        f"*{len(items)} ta e'lon joylashtiriladi*",
        reply_markup=kb_confirm()
    )
    await call.answer()

@router.callback_query(F.data=="confirm", BulkNS.confirm)
async def bulk_confirm(call: CallbackQuery, state: FSMContext):
    d       = await state.get_data()
    items   = d["bulk_items"]
    expires = (datetime.now()+timedelta(hours=d["dl"])).isoformat()
    count   = 0
    for item in items:
        nid = await db_insert(
            "INSERT INTO needs(room_id,owner_id,product_name,quantity,unit,deadline_hours,expires_at) VALUES(?,?,?,?,?,?,?)",
            (d["room_id"], call.from_user.id, item["name"], item["qty"], item["unit"], d["dl"], expires)
        )
        nd  = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
        mid = await post_channel(dict(nd))
        if mid:
            await db_run("UPDATE needs SET channel_message_id=? WHERE id=?", (mid, nid))
        count += 1
    await state.clear()
    await call.message.edit_text(
        f"✅ *{count} ta e'lon joylashtirildi!*\n\n"
        f"Sotuvchilar ko'rib chiqadi va taklif yuboradi.\n"
        f"📋 Takliflar kelganda *Ehtiyojlarim* bo'limida ko'rasiz."
    )
    await call.answer("✅")

# ── EHTIYOJLARIM — MARKAZLASHGAN TAKLIF KO'RISH ──────────
@router.message(F.text == "📋 Ehtiyojlarim")
async def my_needs(msg: Message):
    needs = await db_all(
        "SELECT n.*, (SELECT COUNT(*) FROM offers o WHERE o.need_id=n.id AND o.status='pending') as offer_count "
        "FROM needs n WHERE n.owner_id=? ORDER BY n.created_at DESC LIMIT 20",
        (msg.from_user.id,)
    )
    if not needs:
        await msg.answer("📭 Hali e'lon yo'q.", reply_markup=ik([ib("➕ Yangi ehtiyoj","quick_need_btn")])); return

    await msg.answer(f"📋 *Ehtiyojlarim:* {len(needs)} ta")
    for n in needs:
        st    = {"active":"🟢","paused":"⏸","done":"✅","cancelled":"❌"}.get(n["status"],"📋")
        count = n["offer_count"] or 0
        badge = f" │ 📩 *{count} taklif*" if count > 0 else ""
        
        rows = []
        if count > 0:
            rows.append([ib(f"📩 {count} ta taklifni ko'rish", f"view_offers_{n['id']}")])
        rows.append([
            ib("♻️ Qayta", f"repost_{n['id']}"),
            ib("⏸", f"pause_{n['id']}"),
            ib("✅ Tugat", f"done_{n['id']}")
        ])
        await msg.answer(
            f"{st} *{n['product_name']}* — {n['quantity']} {n['unit']}{badge}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )

@router.callback_query(F.data=="quick_need_btn")
async def quick_need_btn(call: CallbackQuery, state: FSMContext):
    await call.answer()
    class FakeMsg:
        from_user = call.from_user
        async def answer(self, *a, **kw): await call.message.answer(*a, **kw)
    await quick_need(FakeMsg(), state)

# FIX: Takliflarni ko'rish — bitta xabarda
@router.callback_query(F.data.startswith("view_offers_"))
async def view_offers(call: CallbackQuery):
    nid  = int(call.data[12:])
    nd   = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
    offs = await db_all(
        "SELECT o.*,u.full_name,u.phone,s.shop_name,s.total_deals "
        "FROM offers o JOIN users u ON o.seller_id=u.id "
        "LEFT JOIN shops s ON s.owner_id=u.id "
        "WHERE o.need_id=? AND o.status='pending' ORDER BY o.price ASC", (nid,)
    )
    if not offs:
        await call.answer("Taklif yo'q", show_alert=True); return

    txt = f"📩 *{nd['product_name']}* uchun takliflar\n_{len(offs)} ta, arzondan qimmatga:_\n\n"
    for i, o in enumerate(offs, 1):
        shop  = o["shop_name"] or o["full_name"] or "Sotuvchi"
        deals = o["total_deals"] or 0
        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}."
        stars = "⭐"*min(deals//5+1,5) if deals else "🆕"
        txt  += f"{medal} *{shop}* {stars}\n   💰 {o['price']:,.0f} so'm/{nd['unit']}\n   🚚 {o['delivery_hours']} soat\n   🦷 {o['product_name']}\n\n"

    rows = [[ib(f"✅ {i}. Qabul ({o['price']:,.0f} so'm)", f"acc_{o['id']}")] for i,o in enumerate(offs,1)]
    rows.append([ib("◀️ Orqaga","back_needs")])
    await call.message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()

@router.callback_query(F.data=="back_needs")
async def back_needs(call: CallbackQuery):
    await call.answer()

# FIX 5: Taklif qabul qilindi → sotuvchidan lokatsiya, vrachdan ham
@router.callback_query(F.data.startswith("acc_"))
async def accept_offer(call: CallbackQuery):
    oid = int(call.data[4:])
    o   = await db_get(
        "SELECT o.*,u.full_name,u.phone,s.shop_name FROM offers o "
        "JOIN users u ON o.seller_id=u.id LEFT JOIN shops s ON s.owner_id=u.id WHERE o.id=?", (oid,)
    )
    if not o:
        await call.answer("Taklif topilmadi", show_alert=True); return

    await db_run("UPDATE offers SET status='accepted' WHERE id=?", (oid,))
    await db_run("UPDATE needs SET status='paused' WHERE id=?", (o["need_id"],))
    await db_run("UPDATE shops SET total_deals=total_deals+1 WHERE owner_id=?", (o["seller_id"],))

    name  = o["shop_name"] or o["full_name"] or "Sotuvchi"
    phone = o["phone"] or "—"

    # Klinikaga sotuvchi ma'lumoti
    clinic = await get_user(call.from_user.id)
    await call.message.edit_text(
        f"✅ *Qabul qilindi!*\n\n"
        f"🏪 {name}\n"
        f"📞 {phone}\n\n"
        f"_Sotuvchi siz bilan bog'lanadi._"
    )

    # FIX 5: Sotuvchiga klinika lokatsiyasi yuboriladi
    try:
        clinic_txt = (
            f"🎉 *Taklifingiz qabul qilindi!*\n\n"
            f"🏥 {clinic['clinic_name'] or clinic['full_name'] or 'Klinika'}\n"
            f"📞 {clinic['phone'] or '—'}\n"
            f"📍 {clinic['region'] or '—'}\n"
            f"🏠 {clinic['address'] or '—'}"
        )
        await bot.send_message(o["seller_id"], clinic_txt)
    except Exception as e:
        log.error(f"Sotuvchiga xabar yuborishda xato: {e}")

    await call.answer("✅ Qabul qilindi!")

@router.callback_query(F.data.startswith("rej_"))
async def reject_offer(call: CallbackQuery):
    oid = int(call.data[4:])
    await db_run("UPDATE offers SET status='rejected' WHERE id=?", (oid,))
    await call.answer("❌ Rad etildi")

# FIX: Qayta aktivlashtirish va kanalga qayta chiqarish
@router.callback_query(F.data.startswith("repost_"))
async def repost_need(call: CallbackQuery):
    nid = int(call.data[7:])
    nd  = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
    if not nd:
        await call.answer("E'lon topilmadi", show_alert=True); return

    # Statusni aktiv qilish
    new_expires = (datetime.now()+timedelta(hours=nd["deadline_hours"])).isoformat()
    await db_run("UPDATE needs SET status='active', expires_at=? WHERE id=?", (new_expires, nid))

    # Kanalga qayta chiqarish
    mid = await post_channel(dict(nd))
    if mid:
        await db_run("UPDATE needs SET channel_message_id=? WHERE id=?", (mid, nid))

    chan = CHANNEL_ID.lstrip("@")
    link = f"[Kanalda ko'rish](https://t.me/{chan}/{mid})" if mid else ""
    await call.message.answer(
        f"♻️ *{nd['product_name']}* qayta joylashtirildi!\n\n{link}"
    )
    await call.answer("✅")

@router.callback_query(F.data.startswith("pause_"))
async def cb_pause(call: CallbackQuery):
    nid = int(call.data[6:])
    await db_run("UPDATE needs SET status='paused' WHERE id=?", (nid,))
    await call.answer("⏸ Pauza")

@router.callback_query(F.data.startswith("done_"))
async def cb_done(call: CallbackQuery):
    nid = int(call.data[5:])
    await db_run("UPDATE needs SET status='done' WHERE id=?", (nid,))
    await call.answer("✅ Yakunlandi")

@router.callback_query(F.data=="cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await call.answer("Bekor qilindi")

# ── BALANS ────────────────────────────────────────────────
@router.message(F.text == "💰 Hisobim")
async def show_balance(msg: Message):
    u          = await get_user(msg.from_user.id)
    balls      = u["balance"] or 0
    elon_price = float(await get_setting("elon_price") or 0.5)
    possible   = int(balls / elon_price) if elon_price > 0 else 0
    await msg.answer(
        f"💰 *Hisobingiz*\n\n"
        f"⚡️ Ball: *{balls:.1f}*\n\n"
        f"⛽️ Balansingiz — benziningiz!\n"
        f"📋 Joylashtira olasiz: *{possible} ta e'lon*\n"
        f"_(1 e'lon = {elon_price} ball = {int(elon_price*1000):,} so'm)_",
        reply_markup=ik([ib("➕ Hisob to'ldirish","topup")],
                        [ib("📊 Statistika","my_stats_menu")])
    )

@router.callback_query(F.data=="topup")
async def topup_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(TS.amount)
    await call.message.answer(
        f"💳 *Hisob to'ldirish*\n\n"
        f"⚡️ 1 ball = 1 000 so'm\n\n"
        f"Qancha so'm o'tkazmoqchisiz?\n_Faqat raqam. Masalan: 50000_"
    )
    await call.answer()

@router.message(TS.amount)
async def topup_amount(msg: Message, state: FSMContext):
    try:
        amount     = float(msg.text.replace(" ","").replace(",",""))
        ball_price = float(await get_setting("ball_price") or 1000)
        balls      = amount / ball_price
        await state.update_data(amount=amount, balls=balls)
        await state.set_state(TS.receipt)
        await msg.answer(
            f"✅ *{amount:,.0f} so'm → {balls:.1f} ball*\n\n"
            f"💳 Ushbu kartaga P2P o'tkazing:\n\n"
            f"`{CARD_NUM}`\n_Komilova M_\n\n"
            f"📸 O'tkazma screenshotini shu botga yuboring:"
        )
    except:
        await msg.answer("❌ Faqat raqam kiriting!")

@router.message(TS.receipt, F.photo)
async def topup_receipt(msg: Message, state: FSMContext):
    d   = await state.get_data()
    fid = msg.photo[-1].file_id
    tid = await db_insert(
        "INSERT INTO transactions(user_id,amount,balls,type,receipt_file_id) VALUES(?,?,?,'topup',?)",
        (msg.from_user.id, d["amount"], d["balls"], fid)
    )
    u    = await get_user(msg.from_user.id)
    name = u["clinic_name"] or u["full_name"] or str(msg.from_user.id)
    for aid in ADMIN_IDS:
        try:
            await bot.send_photo(aid, fid,
                caption=f"💳 *Yangi chek #{tid}*\n\n👤 {name}\n💰 {d['amount']:,.0f} so'm → {d['balls']:.1f} ball",
                reply_markup=ik(
                    [ib("✅ Tasdiqlash",f"adm_ok_{tid}_{msg.from_user.id}_{d['balls']}"),
                     ib("❌ Rad",        f"adm_rej_{tid}_{msg.from_user.id}")]
                )
            )
        except: pass
    await state.clear()
    await msg.answer("✅ Chek yuborildi! Admin 15-30 daqiqada tasdiqlaydi.")

@router.callback_query(F.data.startswith("adm_ok_"))
async def adm_confirm(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    parts = call.data.split("_")
    tid, uid, balls = parts[2], parts[3], parts[4]
    await db_run("UPDATE transactions SET status='confirmed',confirmed_by=? WHERE id=?",
                 (call.from_user.id, int(tid)))
    await add_balance(int(uid), float(balls))
    try: await bot.send_message(int(uid), f"🎉 *Hisobingiz to'ldirildi!*\n\n+{float(balls):.1f} ball qo'shildi")
    except: pass
    await call.message.edit_caption(call.message.caption + "\n\n✅ TASDIQLANDI", reply_markup=None)
    await call.answer("✅")

@router.callback_query(F.data.startswith("adm_rej_"))
async def adm_reject(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    parts = call.data.split("_")
    tid, uid = parts[2], parts[3]
    await db_run("UPDATE transactions SET status='rejected' WHERE id=?", (int(tid),))
    try: await bot.send_message(int(uid), "❌ Chekingiz rad etildi. Admin bilan bog'laning.")
    except: pass
    await call.message.edit_caption(call.message.caption + "\n\n❌ RAD ETILDI", reply_markup=None)
    await call.answer("❌")

# ── STATISTIKA (oylik / yillik / kategoriya) ─────────────
@router.callback_query(F.data=="my_stats_menu")
async def stats_menu(call: CallbackQuery):
    await call.message.answer("📊 *Statistika davri:*", reply_markup=kb_stat_period())
    await call.answer()

@router.callback_query(F.data.startswith("stat_"))
async def show_stats(call: CallbackQuery):
    uid    = call.from_user.id
    period = call.data[5:]
    u      = await get_user(uid)
    now    = datetime.now()

    if period == "month":
        date_filter = f"AND strftime('%Y-%m', created_at) = '{now.strftime('%Y-%m')}'"
        label = f"Bu oy ({now.strftime('%B %Y')})"
    elif period == "year":
        date_filter = f"AND strftime('%Y', created_at) = '{now.strftime('%Y')}'"
        label = f"Bu yil ({now.strftime('%Y')})"
    else:
        date_filter = ""
        label = "Butun vaqt"

    if u["role"] == "clinic":
        total_n = (await db_get(f"SELECT COUNT(*) as c FROM needs WHERE owner_id=? {date_filter}", (uid,)))["c"]
        done_n  = (await db_get(f"SELECT COUNT(*) as c FROM needs WHERE owner_id=? AND status='done' {date_filter}", (uid,)))["c"]
        acc_o   = (await db_get(
            f"SELECT COUNT(*) as c FROM offers o JOIN needs n ON o.need_id=n.id "
            f"WHERE n.owner_id=? AND o.status='accepted' {date_filter.replace('created_at','n.created_at')}", (uid,)
        ))["c"]
        # Kategoriya bo'yicha xarajat hisoblash
        cat_rows = await db_all(
            f"SELECT o.product_name, SUM(o.price) as total FROM offers o "
            f"JOIN needs n ON o.need_id=n.id "
            f"WHERE n.owner_id=? AND o.status='accepted' "
            f"{date_filter.replace('created_at','o.created_at')} "
            f"GROUP BY o.product_name ORDER BY total DESC LIMIT 5", (uid,)
        )
        cat_txt = ""
        if cat_rows:
            cat_txt = "\n\n💡 *Eng ko'p xaridlar:*\n"
            for r in cat_rows:
                cat_txt += f"• {r['product_name']}: {r['total']:,.0f} so'm\n"

        total_spent_row = await db_get(
            f"SELECT COALESCE(SUM(o.price * n.quantity),0) as s FROM offers o "
            f"JOIN needs n ON o.need_id=n.id "
            f"WHERE n.owner_id=? AND o.status='accepted' "
            f"{date_filter.replace('created_at','o.created_at')}", (uid,)
        )
        total_spent = total_spent_row["s"] if total_spent_row else 0

        await call.message.answer(
            f"📊 *Statistika — {label}*\n\n"
            f"📋 E'lonlar: *{total_n}*\n"
            f"✅ Yakunlangan: *{done_n}*\n"
            f"🤝 Qabul qilingan: *{acc_o}*\n"
            f"💰 Taxminiy xarajat: *{total_spent:,.0f} so'm*"
            f"{cat_txt}"
        )
    elif u["role"] == "seller":
        shop    = await db_get("SELECT * FROM shops WHERE owner_id=?", (uid,))
        total_o = (await db_get(f"SELECT COUNT(*) as c FROM offers WHERE seller_id=? {date_filter}", (uid,)))["c"]
        acc_o   = (await db_get(f"SELECT COUNT(*) as c FROM offers WHERE seller_id=? AND status='accepted' {date_filter}", (uid,)))["c"]
        rej_o   = (await db_get(f"SELECT COUNT(*) as c FROM offers WHERE seller_id=? AND status='rejected' {date_filter}", (uid,)))["c"]
        deals   = shop["total_deals"] if shop else 0
        await call.message.answer(
            f"📊 *Do'kon statistikasi — {label}*\n\n"
            f"📤 Yuborilgan takliflar: *{total_o}*\n"
            f"✅ Qabul: *{acc_o}* | ❌ Rad: *{rej_o}*\n"
            f"🤝 Jami yakunlangan: *{deals}*"
        )
    await call.answer()

# ── SOTUVCHI: DO'KON ──────────────────────────────────────
@router.message(F.text == "🏪 Do'konim")
async def my_shop(msg: Message):
    shop = await db_get("SELECT * FROM shops WHERE owner_id=? AND status='active'", (msg.from_user.id,))
    if not shop:
        await msg.answer("🏪 Do'koningiz yo'q yoki tasdiqlanmagan.",
                         reply_markup=ik([ib("➕ Do'kon ochish","open_shop")])); return
    products = await db_all("SELECT * FROM products WHERE shop_id=? AND is_active=1 ORDER BY id DESC", (shop["id"],))
    prod_txt = "\n\n📦 *Mahsulotlar:*\n" if products else "\n\n📦 _Hali mahsulot yo'q._"
    for p in products:
        prod_txt += f"• {p['name']} — {p['price']:,.0f} so'm/{p['unit']}\n"
    await msg.answer(
        f"🏪 *{shop['shop_name']}*\n📂 {shop['category']}\n"
        f"📍 {shop['region'] or '—'}\n🤝 Xaridlar: *{shop['total_deals'] or 0} ta*{prod_txt}",
        reply_markup=ik([ib("➕ Mahsulot qo'shish",f"addprod_{shop['id']}")],
                        [ib("🗑 O'chirish",        f"delprod_{shop['id']}")])
    )

@router.callback_query(F.data=="open_shop")
async def open_shop_cb(call: CallbackQuery, state: FSMContext):
    if not await has_profile(call.from_user.id):
        await call.message.answer("⚠️ Avval profilingizni to'ldiring.",
                                  reply_markup=ik([ib("✏️ To'ldirish","edit_profile")])); await call.answer(); return
    await state.set_state(SS.cat)
    await call.message.answer("📂 Do'kon kategoriyasi:", reply_markup=kb_shop_cats())
    await call.answer()

@router.callback_query(F.data.startswith("cat_"), SS.cat)
async def ss_cat(call: CallbackQuery, state: FSMContext):
    await state.update_data(cat=call.data)
    await state.set_state(SS.name)
    await call.message.answer("🏪 Do'kon nomini kiriting:")
    await call.answer()

@router.message(SS.name)
async def ss_name(msg: Message, state: FSMContext):
    d = await state.get_data()
    u = await get_user(msg.from_user.id)
    await db_insert("INSERT INTO shops(owner_id,shop_name,category,phone,region) VALUES(?,?,?,?,?)",
                    (msg.from_user.id, msg.text, d["cat"], u["phone"], u["region"]))
    await state.clear()
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid,
                f"🏪 *Yangi do'kon!*\n\n📛 {msg.text}\n👤 {u['clinic_name'] or u['full_name']}\n📞 {u['phone']}",
                reply_markup=ik([ib("✅ Tasdiqlash",f"shopok_{msg.from_user.id}"),
                                  ib("❌ Rad",       f"shoprej_{msg.from_user.id}")])
            )
        except: pass
    await msg.answer("⏳ Do'kon admin tasdiqlashini kutmoqda.")

@router.callback_query(F.data.startswith("shopok_"))
async def shop_ok(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    uid = int(call.data[7:])
    await db_run("UPDATE shops SET status='active' WHERE owner_id=?", (uid,))
    try: await bot.send_message(uid, "✅ Do'koningiz faollashdi!")
    except: pass
    await call.message.edit_text(call.message.text + "\n\n✅ TASDIQLANDI", reply_markup=None)
    await call.answer("✅")

@router.callback_query(F.data.startswith("shoprej_"))
async def shop_rej(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    uid = int(call.data[8:])
    await db_run("UPDATE shops SET status='rejected' WHERE owner_id=?", (uid,))
    await call.message.edit_text(call.message.text + "\n\n❌ RAD ETILDI", reply_markup=None)
    await call.answer("❌")

# Mahsulot qo'shish
@router.callback_query(F.data.startswith("addprod_"))
async def add_prod(call: CallbackQuery, state: FSMContext):
    await state.update_data(shop_id=int(call.data[8:]))
    await state.set_state(AddProduct.name)
    await call.message.answer("📦 Mahsulot nomi:")
    await call.answer()

@router.message(AddProduct.name)
async def ap_name(msg: Message, state: FSMContext):
    await state.update_data(prod_name=msg.text)
    await state.set_state(AddProduct.price)
    await msg.answer("💰 Narxi (so'mda):")

@router.message(AddProduct.price)
async def ap_price(msg: Message, state: FSMContext):
    try:
        await state.update_data(prod_price=float(msg.text.replace(" ","").replace(",","")))
        await state.set_state(AddProduct.unit)
        await msg.answer("⚖️ O'lchov birligi:", reply_markup=kb_prod_units())
    except: await msg.answer("❌ Faqat raqam!")

@router.callback_query(F.data.startswith("pu_"), AddProduct.unit)
async def ap_unit(call: CallbackQuery, state: FSMContext):
    await state.update_data(prod_unit=call.data[3:])
    await state.set_state(AddProduct.desc)
    await call.message.answer("📝 Tavsif? (ixtiyoriy)",
                              reply_markup=ik([ib("⏭ O'tkazish","skip_desc")]))
    await call.answer()

@router.callback_query(F.data=="skip_desc", AddProduct.desc)
async def ap_skip(call: CallbackQuery, state: FSMContext):
    await _save_prod(call.message, state, None)
    await call.answer()

@router.message(AddProduct.desc)
async def ap_desc(msg: Message, state: FSMContext):
    await _save_prod(msg, state, msg.text)

async def _save_prod(msg, state, desc):
    d = await state.get_data()
    await db_insert("INSERT INTO products(shop_id,name,price,unit,description) VALUES(?,?,?,?,?)",
                    (d["shop_id"], d["prod_name"], d["prod_price"], d["prod_unit"], desc))
    await state.clear()
    await msg.answer(f"✅ *{d['prod_name']}* qo'shildi — {d['prod_price']:,.0f} so'm/{d['prod_unit']}")

@router.callback_query(F.data.startswith("delprod_"))
async def del_prod_list(call: CallbackQuery):
    products = await db_all("SELECT * FROM products WHERE shop_id=? AND is_active=1", (int(call.data[8:]),))
    if not products: await call.answer("Mahsulotlar yo'q", show_alert=True); return
    rows = [[ib(f"🗑 {p['name']}", f"delp_{p['id']}")] for p in products]
    await call.message.answer("O'chirish:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()

@router.callback_query(F.data.startswith("delp_"))
async def del_prod(call: CallbackQuery):
    pid = int(call.data[5:])
    p   = await db_get("SELECT name FROM products WHERE id=?", (pid,))
    await db_run("UPDATE products SET is_active=0 WHERE id=?", (pid,))
    await call.message.edit_text(f"🗑 *{p['name']}* o'chirildi.", reply_markup=None)
    await call.answer("✅")

# ── SOTUVCHI: EHTIYOJLAR LENTI ───────────────────────────
@router.message(F.text == "🔔 Yangi ehtiyojlar")
async def seller_feed(msg: Message):
    needs = await db_all(
        "SELECT n.*,u.region,u.address,u.clinic_name FROM needs n "
        "JOIN users u ON n.owner_id=u.id "
        "WHERE n.status='active' ORDER BY n.created_at DESC LIMIT 20"
    )
    if not needs: await msg.answer("📭 Hozircha aktiv ehtiyoj yo'q."); return
    await msg.answer(f"🔔 *Aktiv ehtiyojlar:* {len(needs)} ta")
    for n in needs:
        b = f"\n💰 Budjet: {n['budget']:,.0f} so'm" if n.get("budget") else ""
        await msg.answer(
            f"🦷 *{n['product_name']}*\n📦 {n['quantity']} {n['unit']}\n"
            f"⏱ {n['deadline_hours']} soat{b}\n📍 {n['region'] or ''}",
            reply_markup=ik([ib("📤 Taklif yuborish", f"offer_{n['id']}_{n['unit']}")])
        )

@router.message(F.text == "📤 Takliflarim")
async def my_offers(msg: Message):
    offs = await db_all(
        "SELECT o.*,n.product_name as need_prod FROM offers o "
        "JOIN needs n ON o.need_id=n.id WHERE o.seller_id=? ORDER BY o.created_at DESC LIMIT 20",
        (msg.from_user.id,)
    )
    if not offs: await msg.answer("📭 Hali taklif yo'q."); return
    await msg.answer(f"📤 *Takliflarim:* {len(offs)} ta")
    for o in offs:
        st = {"pending":"⏳","accepted":"✅","rejected":"❌"}.get(o["status"],"📤")
        await msg.answer(
            f"{st} *{o['need_prod']}*\n💰 {o['price']:,.0f} so'm\n🚚 {o['delivery_hours']} soat"
        )

@router.callback_query(F.data.startswith("offer_"))
async def start_offer(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    nid, unit = int(parts[1]), parts[2]
    existing = await db_get("SELECT id FROM offers WHERE need_id=? AND seller_id=?", (nid, call.from_user.id))
    if existing:
        await call.answer("⚠️ Bu e'longa taklif yubordingiz!", show_alert=True); return
    nd = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
    await state.update_data(need_id=nid, need_unit=unit, req_product=nd["product_name"])
    await state.set_state(OS.product)
    await call.message.answer(f"🦷 Qaysi mahsulot taklif qilasiz?\n\n_So'rov: {nd['product_name']}_")
    await call.answer()

@router.message(OS.product)
async def os_product(msg: Message, state: FSMContext):
    await state.update_data(offer_prod=msg.text)
    d = await state.get_data()
    await state.set_state(OS.price)
    await msg.answer(f"💰 Narxini kiriting (1 {d['need_unit']} uchun, so'mda):")

@router.message(OS.price)
async def os_price(msg: Message, state: FSMContext):
    try:
        await state.update_data(price=float(msg.text.replace(" ","").replace(",","")))
        await state.set_state(OS.delivery)
        await msg.answer("🚚 Yetkazib berish muddati:", reply_markup=kb_delivery())
    except: await msg.answer("❌ Faqat raqam!")

@router.callback_query(F.data.startswith("del_"), OS.delivery)
async def os_delivery(call: CallbackQuery, state: FSMContext):
    hours = int(call.data[4:])
    d     = await state.get_data()
    u     = await get_user(call.from_user.id)
    await db_insert(
        "INSERT INTO offers(need_id,seller_id,product_name,price,delivery_hours) VALUES(?,?,?,?,?)",
        (d["need_id"], call.from_user.id, d["offer_prod"], d["price"], hours)
    )
    # Klinikaga xabar — bitta xabarda barcha takliflar
    nd = await db_get(
        "SELECT n.*,u2.id as cid FROM needs n JOIN users u2 ON n.owner_id=u2.id WHERE n.id=?",
        (d["need_id"],)
    )
    # Yangi taklif keldi deb klinikaga xabar
    try:
        await bot.send_message(nd["cid"],
            f"📩 *Yangi taklif keldi!*\n\n"
            f"🦷 {nd['product_name']}\n"
            f"💰 {d['price']:,.0f} so'm/{d['need_unit']}\n"
            f"🚚 {hours} soat",
            reply_markup=ik([ib(f"📩 Barcha takliflarni ko'rish", f"view_offers_{d['need_id']}")])
        )
    except Exception as e: log.error(e)
    await state.clear()
    await call.message.answer("✅ Taklif yuborildi!")
    await call.answer("✅")

# ── ADMIN DASHBOARD ───────────────────────────────────────
@router.message(Command("admin"))
async def admin_panel(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("⛔️ Ruxsat yo'q."); return
    total_u   = (await db_get("SELECT COUNT(*) as c FROM users", ()))["c"]
    clinics   = (await db_get("SELECT COUNT(*) as c FROM users WHERE role='clinic'", ()))["c"]
    sellers   = (await db_get("SELECT COUNT(*) as c FROM users WHERE role='seller'", ()))["c"]
    active_n  = (await db_get("SELECT COUNT(*) as c FROM needs WHERE status='active'", ()))["c"]
    total_n   = (await db_get("SELECT COUNT(*) as c FROM needs", ()))["c"]
    pending_t = (await db_get("SELECT COUNT(*) as c FROM transactions WHERE status='pending'", ()))["c"]
    pending_s = (await db_get("SELECT COUNT(*) as c FROM shops WHERE status='pending'", ()))["c"]
    acc_off   = (await db_get("SELECT COUNT(*) as c FROM offers WHERE status='accepted'", ()))["c"]
    rev_row   = await db_get("SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE status='confirmed'", ())
    revenue   = rev_row["s"] if rev_row else 0

    await msg.answer(
        f"👨‍💼 *XAZDENT Admin*\n_{datetime.now().strftime('%d.%m.%Y %H:%M')}_\n\n"
        f"👥 Foydalanuvchilar: *{total_u}*\n  ├ 🏥 Klinikalar: {clinics}\n  └ 🛒 Sotuvchilar: {sellers}\n\n"
        f"📋 E'lonlar: *{total_n}* (🟢 {active_n} aktiv)\n"
        f"✅ Qabul qilingan takliflar: *{acc_off}*\n\n"
        f"⏳ Kutmoqda: 💳 {pending_t} chek | 🏪 {pending_s} do'kon\n\n"
        f"💰 Jami daromad: *{revenue:,.0f} so'm*",
        reply_markup=ik(
            [ib("💳 Kutayotgan cheklar","adm_pending_tx")],
            [ib("🏪 Kutayotgan do'konlar","adm_pending_shops")],
            [ib("⚙️ Sozlamalar","adm_settings")],
        )
    )

@router.callback_query(F.data=="adm_pending_tx")
async def adm_pending_tx(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    txs = await db_all(
        "SELECT t.*,u.full_name,u.clinic_name FROM transactions t "
        "JOIN users u ON t.user_id=u.id WHERE t.status='pending' ORDER BY t.created_at DESC LIMIT 10"
    )
    if not txs: await call.message.answer("✅ Kutayotgan cheklar yo'q."); await call.answer(); return
    for tx in txs:
        name = tx["clinic_name"] or tx["full_name"] or str(tx["user_id"])
        if tx["receipt_file_id"]:
            try:
                await call.message.answer_photo(tx["receipt_file_id"],
                    caption=f"💳 *Chek #{tx['id']}*\n👤 {name}\n💰 {tx['amount']:,.0f} so'm → {tx['balls']:.1f} ball",
                    reply_markup=ik([ib("✅ Tasdiqlash",f"adm_ok_{tx['id']}_{tx['user_id']}_{tx['balls']}"),
                                     ib("❌ Rad",        f"adm_rej_{tx['id']}_{tx['user_id']}")])
                )
            except: pass
    await call.answer()

@router.callback_query(F.data=="adm_pending_shops")
async def adm_pending_shops(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    shops = await db_all("SELECT s.*,u.full_name,u.phone FROM shops s JOIN users u ON s.owner_id=u.id WHERE s.status='pending'")
    if not shops: await call.message.answer("✅ Kutayotgan do'konlar yo'q."); await call.answer(); return
    for s in shops:
        await call.message.answer(
            f"🏪 *{s['shop_name']}*\n👤 {s['full_name']}\n📞 {s['phone']}\n📂 {s['category']}",
            reply_markup=ik([ib("✅ Tasdiqlash",f"shopok_{s['owner_id']}"),ib("❌ Rad",f"shoprej_{s['owner_id']}")])
        )
    await call.answer()

@router.callback_query(F.data=="adm_settings")
async def adm_settings(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    ball_price = await get_setting("ball_price") or "1000"
    elon_price = await get_setting("elon_price") or "0.5"
    await call.message.answer(
        f"⚙️ *Sozlamalar*\n\n💰 1 ball = *{ball_price} so'm*\n📋 1 e'lon = *{elon_price} ball*\n"
        f"💳 Karta: `{CARD_NUM}`\n\n`/setball 2000` | `/setelon 1`"
    )
    await call.answer()

@router.message(Command("setball"))
async def set_ball(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    try:
        await update_setting("ball_price", msg.text.split()[1])
        await msg.answer(f"✅ Ball narxi yangilandi: *{msg.text.split()[1]} so'm*")
    except: await msg.answer("❌ /setball 2000")

@router.message(Command("setelon"))
async def set_elon(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    try:
        await update_setting("elon_price", msg.text.split()[1])
        await msg.answer(f"✅ E'lon narxi: *{msg.text.split()[1]} ball*")
    except: await msg.answer("❌ /setelon 0.5")

# ── MAIN ─────────────────────────────────────────────────
async def main():
    await init_db()
    dp.include_router(router)
    log.info("🦷 XAZDENT Bot ishga tushdi!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
