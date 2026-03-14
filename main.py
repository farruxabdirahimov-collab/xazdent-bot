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
CARD_NUM   = "9860020138100068"  # Komilova M

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp  = Dispatcher(storage=MemoryStorage())
router = Router()

# u2500u2500 STATES u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500
class PS(StatesGroup):
    name = State(); phone = State(); region = State(); address = State()

class NS(StatesGroup):
    product = State(); qty = State(); unit = State()
    budget = State(); deadline = State(); note = State(); confirm = State()
    room = State()

class TS(StatesGroup):
    amount = State(); receipt = State()

class OS(StatesGroup):
    product = State(); price = State(); delivery = State()

class SS(StatesGroup):
    cat = State(); name = State()

class AddProduct(StatesGroup):
    name = State(); price = State(); unit = State(); desc = State()

# u2500u2500 KEYBOARDS u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500
def ik(*rows): return InlineKeyboardMarkup(inline_keyboard=list(rows))
def ib(text, data): return InlineKeyboardButton(text=text, callback_data=data)
def rk(*rows, resize=True, one_time=False):
    return ReplyKeyboardMarkup(keyboard=list(rows), resize_keyboard=resize, one_time_keyboard=one_time)

def kb_lang():
    return ik([ib("ud83cuddfaud83cuddff O'zbekcha","lang_uz"), ib("ud83cuddf7ud83cuddfa u0420u0443u0441u0441u043au0438u0439","lang_ru")])

def kb_role(lang):
    return ik([ib(t(lang,"role_clinic"),"role_clinic")],
              [ib(t(lang,"role_seller"),"role_seller")])

def kb_clinic(lang):
    return rk(
        [KeyboardButton(text="📋 Ehtiyojlarim"),  KeyboardButton(text="✏️ Ehtiyoj yozish")],
        [KeyboardButton(text="📩 Takliflar"),       KeyboardButton(text="💰 Hisobim")],
        [KeyboardButton(text="⚙️ Profil")],
    )

def kb_seller(lang):
    return rk(
        [KeyboardButton(text="🔔 Yangi ehtiyojlar"), KeyboardButton(text="📤 Takliflarim")],
        [KeyboardButton(text="🏪 Do'konim"),         KeyboardButton(text="💰 Hisobim")],
        [KeyboardButton(text="⚙️ Profil")],
    )

def kb_regions(lang):
    regs = REGIONS if lang != "ru" else REGIONS_RU
    rows = []
    for i in range(0, len(regs), 2):
        row = [ib(regs[i], f"reg_{i}")]
        if i+1 < len(regs): row.append(ib(regs[i+1], f"reg_{i+1}"))
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_room_types(lang):
    return ik([ib(t(lang,"btn_small"),   "room_small")],
              [ib(t(lang,"btn_standard"),"room_standard")],
              [ib(t(lang,"btn_premium"), "room_premium")])

def kb_units(lang):
    return ik([ib(t(lang,"btn_dona"),"unit_dona"),
               ib(t(lang,"btn_kg"),  "unit_kg"),
               ib(t(lang,"btn_litr"),"unit_litr")])

def kb_deadline(lang):
    return ik([ib(t(lang,"btn_2h"),"dl_2"),  ib(t(lang,"btn_24h"),"dl_24")],
              [ib(t(lang,"btn_3d"),"dl_72"), ib(t(lang,"btn_1w"), "dl_168")])

def kb_delivery(lang):
    return ik([ib(t(lang,"btn_del_2h"),"del_2"),  ib(t(lang,"btn_del_24h"),"del_24")],
              [ib(t(lang,"btn_del_2d"),"del_48"), ib(t(lang,"btn_del_1w"), "del_168")])

def kb_skip(lang):
    return ik([ib(t(lang,"skip"),"skip"), ib(t(lang,"cancel"),"cancel")])

def kb_confirm(lang):
    return ik([ib(t(lang,"confirm"),"confirm")],
              [ib(t(lang,"edit"),"edit"), ib(t(lang,"cancel"),"cancel")])

def kb_offer_action(offer_id, lang):
    return ik([ib(t(lang,"btn_accept"),f"acc_{offer_id}"),
               ib(t(lang,"btn_reject"),f"rej_{offer_id}")])

def kb_shop_cats(lang):
    return ik([ib(t(lang,"cat_1"),"cat_1")],[ib(t(lang,"cat_2"),"cat_2")],
              [ib(t(lang,"cat_3"),"cat_3")],[ib(t(lang,"cat_4"),"cat_4")],
              [ib(t(lang,"cat_5"),"cat_5")])

def kb_prod_units():
    return ik([ib("ud83dudccc Dona","pu_dona"), ib("u2696ufe0f Kg","pu_kg"), ib("ud83dudca7 Litr","pu_litr")])

# u2500u2500 HELPERS u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500
async def lang(uid):
    u = await get_user(uid)
    return u["lang"] if u else "uz"

async def has_profile(uid):
    u = await get_user(uid)
    return u and u["clinic_name"] and u["phone"] and u["region"]

def need_preview_text(d, lg):
    dl = {2:"2 soat",24:"24 soat",72:"3 kun",168:"1 hafta"}.get(d.get("dl",24),"?")
    if lg == "ru":
        dl = {2:"2 u0447u0430u0441u0430",24:"24 u0447u0430u0441u0430",72:"3 u0434u043du044f",168:"1 u043du0435u0434u0435u043bu044f"}.get(d.get("dl",24),"?")
    b = f"\nud83dudcb0 Byudjet: {d['budget']:,.0f} so'm" if d.get("budget") else ""
    n = f"\nud83dudcdd {d['note']}" if d.get("note") else ""
    return f"ud83euddb7 *{d['product']}*\nud83dudce6 {d['qty']} {d['unit']}\nu23f1 {dl}{b}{n}"

async def post_channel(need_id, room_code, user, d):
    dl_txt = {2:"2 soat",24:"24 soat",72:"3 kun",168:"1 hafta"}.get(d.get("dl",24),"?")
    budget_txt = f"\n💰 Budjet: {d['budget']:,.0f} so'm gacha" if d.get("budget") else ""
    note_txt   = f"\n📝 {d['note']}" if d.get("note") else ""
    words = d["product"].split()
    tags  = " ".join(f"#{w.lower()}" for w in words[:3] if len(w)>2)
    reg   = f"#{(user['region'] or '').replace(' ','').lower()}"
    txt = (
        f"📋 *BUYURTMA #{need_id}*\n\n"
        f"🦷 {d['product']}\n"
        f"📦 {d['qty']} {d['unit']}\n"
        f"⏱ {dl_txt} ichida"
        f"{budget_txt}{note_txt}\n\n"
        f"📍 {user['region'] or ''}\n"
        f"🏠 {user['address'] or ''}\n\n"
        f"{tags} {reg}\n\n"
        f"💬 @XazdentBot"
    )
    try:
        msg = await bot.send_message(CHANNEL_ID, txt)
        log.info(f"✅ Kanal post: need={need_id}, msg={msg.message_id}")
        return msg.message_id
    except Exception as e:
        log.error(f"❌ Kanal xato (CHANNEL_ID={CHANNEL_ID!r}): {e}")
        return None

# u2500u2500 START u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500
@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    u = await get_user(msg.from_user.id)
    if not u:
        await db_run(
            "INSERT OR IGNORE INTO users(id,username,full_name) VALUES(?,?,?)",
            (msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
        )
        u = await get_user(msg.from_user.id)

    if u and u["role"] not in (None, "none"):
        lg  = u["lang"] or "uz"
        kb  = kb_clinic(lg) if u["role"]=="clinic" else kb_seller(lg)
        txt = t(lg,"clinic_menu") if u["role"]=="clinic" else t(lg,"seller_menu")
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
    lg  = await lang(call.from_user.id)
    kb  = kb_clinic(lg) if role=="clinic" else kb_seller(lg)
    txt = t(lg,"clinic_menu") if role=="clinic" else t(lg,"seller_menu")
    await call.message.delete()
    await call.message.answer(txt, reply_markup=kb)
    await call.answer()

# u2500u2500 PROFIL (FIX 1 & 2) u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500
@router.message(F.text.in_(["⚙️ Profil", "⚙️ Профиль"]))
async def show_profile(msg: Message):
    lg = await lang(msg.from_user.id)
    u  = await get_user(msg.from_user.id)
    is_seller  = u["role"] == "seller"
    name_label = "ud83cudfea Do'kon nomi" if is_seller else "ud83cudfe5 Klinika nomi"
    txt = (
        f"u2699ufe0f *Profil*\n\n"
        f"{name_label}: {u['clinic_name'] or 'u2014'}\n"
        f"ud83dudcde Tel: {u['phone'] or 'u2014'}\n"
        f"ud83dudccd Hudud: {u['region'] or 'u2014'}\n"
        f"ud83cudfe0 Manzil: {u['address'] or 'u2014'}\n"
        f"ud83dudcb0 Balans: {u['balance'] or 0:.1f} ball"
    )
    await msg.answer(txt, reply_markup=ik([ib("u270fufe0f Tahrirlash","edit_profile")]))

@router.callback_query(F.data == "edit_profile")
async def start_profile(call: CallbackQuery, state: FSMContext):
    lg = await lang(call.from_user.id)
    u  = await get_user(call.from_user.id)
    await state.set_state(PS.name)
    if u and u["role"] == "seller":
        await call.message.answer("ud83cudfea Do'kon nomingizni kiriting:\n\n_Masalan: DentalPlus Toshkent_")
    else:
        await call.message.answer(t(lg,"ask_clinic_name"))
    await call.answer()

@router.message(PS.name)
async def ps_name(msg: Message, state: FSMContext):
    lg = await lang(msg.from_user.id)
    await state.update_data(clinic_name=msg.text)
    await state.set_state(PS.phone)
    kb = rk([KeyboardButton(text=t(lg,"btn_send_phone"), request_contact=True)], one_time=True)
    await msg.answer(t(lg,"ask_phone"), reply_markup=kb)

@router.message(PS.phone, F.contact)
async def ps_phone(msg: Message, state: FSMContext):
    lg = await lang(msg.from_user.id)
    await state.update_data(phone=msg.contact.phone_number)
    await state.set_state(PS.region)
    await msg.answer(t(lg,"ask_region"), reply_markup=kb_regions(lg))

@router.callback_query(F.data.startswith("reg_"), PS.region)
async def ps_region(call: CallbackQuery, state: FSMContext):
    lg  = await lang(call.from_user.id)
    idx = int(call.data[4:])
    regs = REGIONS if lg != "ru" else REGIONS_RU
    region = regs[idx].split(" ",1)[1] if " " in regs[idx] else regs[idx]
    await state.update_data(region=region)
    await state.set_state(PS.address)
    await call.message.answer(t(lg,"ask_address"), reply_markup=ReplyKeyboardRemove())
    await call.answer()

@router.message(PS.address)
async def ps_address(msg: Message, state: FSMContext):
    lg = await lang(msg.from_user.id)
    d  = await state.get_data()
    await db_run(
        "UPDATE users SET clinic_name=?,phone=?,region=?,address=? WHERE id=?",
        (d["clinic_name"], d["phone"], d["region"], msg.text, msg.from_user.id)
    )
    await state.clear()
    u  = await get_user(msg.from_user.id)
    kb = kb_clinic(lg) if u["role"]=="clinic" else kb_seller(lg)
    if u["role"] == "seller":
        await msg.answer("u2705 Profil saqlandi! Endi *Do'konim* bo'limiga kiring.", reply_markup=kb)
    else:
        await msg.answer(t(lg,"profile_saved"), reply_markup=kb)

# ── AUTO ROOM (foydalanuvchi ko'rmaydi) ──────────────────────────────────
async def get_or_create_room(uid: int) -> dict:
    """Foydalanuvchining default omborxonasini topadi yoki yaratadi"""
    room = await db_get(
        "SELECT * FROM rooms WHERE owner_id=? AND status='active' ORDER BY id LIMIT 1",
        (uid,)
    )
    if room:
        return room
    # Avtomatik yaratish
    code = await get_next_room_code("premium")
    if not code:
        code = f"AUTO{uid}"
    rid = await db_insert(
        "INSERT INTO rooms(room_code,room_type,owner_id,max_needs) VALUES(?,?,?,?)",
        (code, "premium", uid, 999)
    )
    return await db_get("SELECT * FROM rooms WHERE id=?", (rid,))

# ── EHTIYOJ ──────────────────────────────────────────────────────────────
@router.message(F.text.in_(["✏️ Ehtiyoj yozish", "✏️ Записать потребность"]))
async def start_need_direct(msg: Message, state: FSMContext):
    lg = await lang(msg.from_user.id)
    if not await has_profile(msg.from_user.id):
        await msg.answer(t(lg,"profile_first"),
                         reply_markup=ik([ib("✏️ Profilni to'ldirish","edit_profile")])); return
    room = await get_or_create_room(msg.from_user.id)
    await state.update_data(room_id=room["id"], room_code=room["room_code"])
    await state.set_state(NS.product)
    await msg.answer("🦷 *Nima kerak?*\n\n_Masalan: Xarizma plomba A2, GC Fuji IX_",
                     reply_markup=ReplyKeyboardRemove())

@router.message(F.text.in_(["📋 Ehtiyojlarim", "📋 Мои заявки"]))
async def my_needs_menu(msg: Message):
    lg    = await lang(msg.from_user.id)
    needs = await db_all(
        "SELECT n.*,r.room_code FROM needs n JOIN rooms r ON n.room_id=r.id WHERE n.owner_id=? ORDER BY n.created_at DESC LIMIT 15",
        (msg.from_user.id,)
    )
    if not needs: await msg.answer(t(lg,"no_needs")); return
    await msg.answer(f"ud83dudccb *Ehtiyojlarim:* {len(needs)} ta")
    for n in needs:
        st = {"active":"ud83dudfe2","paused":"u23f8","done":"u2705","cancelled":"u274c"}.get(n["status"],"ud83dudccb")
        await msg.answer(
            f"{st} *{n['product_name']}* u2014 {n['quantity']} {n['unit']}",
            reply_markup=ik(
                [ib("ud83dudce9 Takliflar",f"offers_{n['id']}"), ib("u23f8 Pauza",f"pause_{n['id']}")],
                [ib("u2705 Yakunlash", f"done_{n['id']}")]
            )
        )

@router.message(NS.product)
async def ns_product(msg: Message, state: FSMContext):
    await state.update_data(product=msg.text)
    lg = await lang(msg.from_user.id)
    await state.set_state(NS.qty)
    await msg.answer(t(lg,"ask_qty"))

@router.message(NS.qty)
async def ns_qty(msg: Message, state: FSMContext):
    lg = await lang(msg.from_user.id)
    try:
        await state.update_data(qty=float(msg.text.replace(",",".")))
        await state.set_state(NS.unit)
        await msg.answer(t(lg,"ask_unit"), reply_markup=kb_units(lg))
    except: await msg.answer("u274c Faqat raqam!")

@router.callback_query(F.data.startswith("unit_"), NS.unit)
async def ns_unit(call: CallbackQuery, state: FSMContext):
    lg = await lang(call.from_user.id)
    await state.update_data(unit=call.data[5:])
    await state.set_state(NS.budget)
    await call.message.answer(t(lg,"ask_budget"), reply_markup=kb_skip(lg))
    await call.answer()

@router.callback_query(F.data=="skip", NS.budget)
async def ns_budget_skip(call: CallbackQuery, state: FSMContext):
    lg = await lang(call.from_user.id)
    await state.update_data(budget=None)
    await state.set_state(NS.deadline)
    await call.message.answer(t(lg,"ask_deadline"), reply_markup=kb_deadline(lg))
    await call.answer()

@router.message(NS.budget)
async def ns_budget(msg: Message, state: FSMContext):
    lg = await lang(msg.from_user.id)
    try: await state.update_data(budget=float(msg.text.replace(" ","").replace(",","")))
    except: await state.update_data(budget=None)
    await state.set_state(NS.deadline)
    await msg.answer(t(lg,"ask_deadline"), reply_markup=kb_deadline(lg))

@router.callback_query(F.data.startswith("dl_"), NS.deadline)
async def ns_deadline(call: CallbackQuery, state: FSMContext):
    lg = await lang(call.from_user.id)
    await state.update_data(dl=int(call.data[3:]))
    await state.set_state(NS.note)
    await call.message.answer(t(lg,"ask_note"), reply_markup=kb_skip(lg))
    await call.answer()

@router.callback_query(F.data=="skip", NS.note)
async def ns_note_skip(call: CallbackQuery, state: FSMContext):
    await state.update_data(note=None)
    await _show_preview(call.message, call.from_user.id, state)
    await call.answer()

@router.message(NS.note)
async def ns_note(msg: Message, state: FSMContext):
    await state.update_data(note=msg.text)
    await _show_preview(msg, msg.from_user.id, state)

async def _show_preview(msg, uid, state):
    lg = await lang(uid)
    d  = await state.get_data()
    await state.set_state(NS.confirm)
    await msg.answer(t(lg,"need_preview", preview=need_preview_text(d,lg)), reply_markup=kb_confirm(lg))

@router.callback_query(F.data=="confirm", NS.confirm)
async def ns_confirm(call: CallbackQuery, state: FSMContext):
    lg = await lang(call.from_user.id)
    d  = await state.get_data()
    u  = await get_user(call.from_user.id)
    expires = (datetime.now()+timedelta(hours=d["dl"])).isoformat()
    nid = await db_insert(
        "INSERT INTO needs(room_id,owner_id,product_name,quantity,unit,budget,deadline_hours,extra_note,expires_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (d["room_id"], call.from_user.id, d["product"], d["qty"], d["unit"], d.get("budget"), d["dl"], d.get("note"), expires)
    )
    mid = await post_channel(nid, d["room_code"], dict(u), d)
    if mid:
        await db_run("UPDATE needs SET channel_message_id=? WHERE id=?", (mid, nid))
    link = f"https://t.me/{CHANNEL_ID.replace('@','')}/{mid}" if mid else CHANNEL_ID
    await state.clear()
    await call.message.edit_text(t(lg,"need_posted", room=d["room_code"], link=link))
    await call.answer("u2705")

@router.callback_query(F.data=="cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await call.answer("Bekor qilindi")

@router.callback_query(F.data.startswith("pause_"))
async def cb_pause(call: CallbackQuery):
    nid = int(call.data[6:])
    await db_run("UPDATE needs SET status='paused' WHERE id=?", (nid,))
    await call.answer("u23f8 Pauza")

@router.callback_query(F.data.startswith("done_"))
async def cb_done(call: CallbackQuery):
    nid = int(call.data[5:])
    await db_run("UPDATE needs SET status='done' WHERE id=?", (nid,))
    await call.answer("u2705 Yakunlandi")

# u2500u2500 TAKLIFLAR (klinika) u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500
@router.message(F.text.in_(["📩 Takliflar", "📩 Предложения"]))
async def my_offers_page(msg: Message):
    lg    = await lang(msg.from_user.id)
    needs = await db_all(
        "SELECT id,product_name FROM needs WHERE owner_id=? AND status IN ('active','paused')", (msg.from_user.id,)
    )
    if not needs: await msg.answer(t(lg,"no_needs")); return
    rows = [[ib(n["product_name"], f"offers_{n['id']}")] for n in needs]
    await msg.answer("ud83dudce9 Qaysi e'lonning takliflarini ko'rmoqchisiz?",
                     reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@router.callback_query(F.data.startswith("offers_"))
async def show_offers(call: CallbackQuery):
    lg  = await lang(call.from_user.id)
    nid = int(call.data[7:])
    nd  = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
    offs= await db_all(
        "SELECT o.*,u.full_name,u.username,u.phone,s.shop_name FROM offers o "
        "JOIN users u ON o.seller_id=u.id LEFT JOIN shops s ON s.owner_id=u.id "
        "WHERE o.need_id=? ORDER BY o.price ASC", (nid,)
    )
    if not offs: await call.message.answer(t(lg,"no_offers")); await call.answer(); return
    await call.message.answer(t(lg,"offers_title", count=len(offs)))
    for i,o in enumerate(offs,1):
        shop = o["shop_name"] or o["full_name"] or "Sotuvchi"
        await call.message.answer(
            f"{i}. *{shop}*\nud83euddb7 {o['product_name']}\nud83dudcb0 {o['price']:,.0f} so'm/{nd['unit']}\nud83dude9a {o['delivery_hours']} soat",
            reply_markup=kb_offer_action(o["id"], lg)
        )
    await call.answer()

@router.callback_query(F.data.startswith("acc_"))
async def accept_offer(call: CallbackQuery):
    lg  = await lang(call.from_user.id)
    oid = int(call.data[4:])
    o   = await db_get(
        "SELECT o.*,u.full_name,u.phone,s.shop_name FROM offers o "
        "JOIN users u ON o.seller_id=u.id LEFT JOIN shops s ON s.owner_id=u.id WHERE o.id=?", (oid,)
    )
    await db_run("UPDATE offers SET status='accepted' WHERE id=?", (oid,))
    await db_run("UPDATE needs SET status='paused' WHERE id=?", (o["need_id"],))
    await db_run("UPDATE shops SET total_deals=total_deals+1 WHERE owner_id=?", (o["seller_id"],))
    name  = o["shop_name"] or o["full_name"] or "Sotuvchi"
    phone = o["phone"] or "u2014"
    await call.message.edit_text(t(lg,"offer_accepted", name=name, phone=phone))
    clinic = await get_user(call.from_user.id)
    try:
        await bot.send_message(o["seller_id"],
            f"ud83cudf89 *Taklifingiz qabul qilindi!*\n\n"
            f"ud83cudfe5 {clinic['clinic_name'] or clinic['full_name'] or 'Klinika'}\n"
            f"ud83dudcde {clinic['phone'] or 'u2014'}")
    except: pass
    await call.answer("u2705")

@router.callback_query(F.data.startswith("rej_"))
async def reject_offer(call: CallbackQuery):
    oid = int(call.data[4:])
    await db_run("UPDATE offers SET status='rejected' WHERE id=?", (oid,))
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("u274c Rad etildi")

# u2500u2500 BALANS (FIX 3) u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500
@router.message(F.text.in_(["💰 Hisobim", "💰 Мой счёт"]))
async def show_balance(msg: Message):
    lg         = await lang(msg.from_user.id)
    u          = await get_user(msg.from_user.id)
    balls      = u["balance"] or 0
    elon_price = float(await get_setting("elon_price") or 0.5)
    possible   = int(balls / elon_price) if elon_price > 0 else 0
    txt = (
        f"ud83dudcb0 *Hisobingiz*\n\n"
        f"u26a1ufe0f Ball: *{balls:.1f} ball*\n\n"
        f"u26fdufe0f Balansingiz u2014 benziningiz!\n"
        f"Qancha ko'p to'lsangiz, shuncha ko'p e'lon berasiz.\n\n"
        f"ud83dudccb Joylashtira olasiz: *{possible} ta e'lon*\n"
        f"_(1 e'lon = {elon_price} ball = {int(elon_price*1000):,} so'm)_"
    )
    await msg.answer(txt, reply_markup=ik(
        [ib("u2795 Hisob to'ldirish","topup")],
        [ib("ud83dudcca Statistikam","my_stats")]
    ))

@router.callback_query(F.data=="topup")
async def topup_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(TS.amount)
    await call.message.answer(
        f"ud83dudcb3 *Hisob to'ldirish*\n\n"
        f"u26a1ufe0f 1 ball = 1 000 so'm\n\n"
        f"Qancha so'm o'tkazmoqchisiz?\n"
        f"_Faqat raqam kiriting. Masalan: 50000_"
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
            f"u2705 *{amount:,.0f} so'm u2192 {balls:.1f} ball*\n\n"
            f"ud83dudcb3 Ushbu kartaga P2P o'tkazing:\n\n"
            f"`{CARD_NUM}`\n"
            f"_Komilova M_\n\n"
            f"ud83dudcf8 O'tkazma screenshotini shu botga yuboring:"
        )
    except: await msg.answer("u274c Faqat raqam kiriting!")

@router.message(TS.receipt, F.photo)
async def topup_receipt(msg: Message, state: FSMContext):
    lg  = await lang(msg.from_user.id)
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
                caption=f"ud83dudcb3 *Yangi chek #{tid}*\n\nud83dudc64 {name}\nud83dudcb0 {d['amount']:,.0f} so'm u2192 {d['balls']:.1f} ball",
                reply_markup=ik(
                    [ib("u2705 Tasdiqlash",f"adm_ok_{tid}_{msg.from_user.id}_{d['balls']}"),
                     ib("u274c Rad",        f"adm_rej_{tid}_{msg.from_user.id}")]
                )
            )
        except: pass
    await state.clear()
    await msg.answer(t(lg,"receipt_sent"))

@router.callback_query(F.data.startswith("adm_ok_"))
async def adm_confirm(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    parts = call.data.split("_")
    tid, uid, balls = parts[2], parts[3], parts[4]
    await db_run("UPDATE transactions SET status='confirmed',confirmed_by=? WHERE id=?",
                 (call.from_user.id, int(tid)))
    await add_balance(int(uid), float(balls))
    lg = await lang(int(uid))
    try: await bot.send_message(int(uid), t(lg,"balance_added", balls=float(balls)))
    except: pass
    await call.message.edit_caption(call.message.caption + "\n\nu2705 TASDIQLANDI", reply_markup=None)
    await call.answer("u2705")

@router.callback_query(F.data.startswith("adm_rej_"))
async def adm_reject(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    parts = call.data.split("_")
    tid, uid = parts[2], parts[3]
    await db_run("UPDATE transactions SET status='rejected' WHERE id=?", (int(tid),))
    try: await bot.send_message(int(uid), "u274c Chekingiz rad etildi. Admin bilan bog'laning.")
    except: pass
    await call.message.edit_caption(call.message.caption + "\n\nu274c RAD ETILDI", reply_markup=None)
    await call.answer("u274c")

# u2500u2500 SOTUVCHI: DO'KON (FIX 6) u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500
@router.message(F.text.in_(["🏪 Do'konim", "🏪 Мой магазин"]))
async def my_shop(msg: Message):
    lg   = await lang(msg.from_user.id)
    shop = await db_get("SELECT * FROM shops WHERE owner_id=? AND status='active'", (msg.from_user.id,))
    if not shop:
        await msg.answer(
            "ud83cudfea Do'koningiz yo'q yoki tasdiqlanmagan.",
            reply_markup=ik([ib("u2795 Do'kon ochish","open_shop")])
        ); return
    products = await db_all("SELECT * FROM products WHERE shop_id=? ORDER BY id DESC", (shop["id"],))
    prod_txt = "\n\nud83dudce6 *Mahsulotlar:*\n" if products else "\n\nud83dudce6 _Hali mahsulot qo'shilmagan._"
    for p in products:
        prod_txt += f"u2022 {p['name']} u2014 {p['price']:,.0f} so'm/{p['unit']}\n"
    deals = shop["total_deals"] or 0
    await msg.answer(
        f"ud83cudfea *{shop['shop_name']}*\n"
        f"ud83dudcc2 {shop['category']}\n"
        f"ud83dudccd {shop['region'] or 'u2014'}\n"
        f"ud83eudd1d Yakunlangan xaridlar: *{deals} ta*"
        f"{prod_txt}",
        reply_markup=ik(
            [ib("u2795 Mahsulot qo'shish", f"addprod_{shop['id']}")],
            [ib("ud83duddd1 Mahsulot o'chirish",  f"delprod_{shop['id']}")]
        )
    )

@router.callback_query(F.data=="open_shop")
async def open_shop_cb(call: CallbackQuery, state: FSMContext):
    lg = await lang(call.from_user.id)
    if not await has_profile(call.from_user.id):
        await call.message.answer(t(lg,"profile_first")); await call.answer(); return
    await state.set_state(SS.cat)
    await call.message.answer(t(lg,"ask_shop_cat"), reply_markup=kb_shop_cats(lg))
    await call.answer()

@router.message(F.text.in_(["➕ Do'kon ochish", "➕ Открыть магазин"]))
async def new_shop(msg: Message, state: FSMContext):
    lg       = await lang(msg.from_user.id)
    existing = await db_get("SELECT id FROM shops WHERE owner_id=?", (msg.from_user.id,))
    if existing:
        await msg.answer("u26a0ufe0f Sizda allaqachon do'kon bor. *Do'konim* bo'limiga kiring."); return
    if not await has_profile(msg.from_user.id):
        await msg.answer(t(lg,"profile_first")); return
    await state.set_state(SS.cat)
    await msg.answer(t(lg,"ask_shop_cat"), reply_markup=kb_shop_cats(lg))

@router.callback_query(F.data.startswith("cat_"), SS.cat)
async def ss_cat(call: CallbackQuery, state: FSMContext):
    lg = await lang(call.from_user.id)
    await state.update_data(cat=call.data)
    await state.set_state(SS.name)
    await call.message.answer(t(lg,"ask_shop_name"))
    await call.answer()

@router.message(SS.name)
async def ss_name(msg: Message, state: FSMContext):
    lg = await lang(msg.from_user.id)
    d  = await state.get_data()
    u  = await get_user(msg.from_user.id)
    await db_insert(
        "INSERT INTO shops(owner_id,shop_name,category,phone,region) VALUES(?,?,?,?,?)",
        (msg.from_user.id, msg.text, d["cat"], u["phone"], u["region"])
    )
    await state.clear()
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid,
                f"ud83cudfea *Yangi do'kon tasdiqlash kerak!*\n\n"
                f"ud83dudcdb {msg.text}\nud83dudc64 {u['clinic_name'] or u['full_name']}\nud83dudcde {u['phone']}",
                reply_markup=ik([ib("u2705 Tasdiqlash",f"shopok_{msg.from_user.id}"),
                                  ib("u274c Rad",       f"shoprej_{msg.from_user.id}")])
            )
        except: pass
    await msg.answer(t(lg,"shop_pending"))

@router.callback_query(F.data.startswith("shopok_"))
async def shop_ok(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    uid = int(call.data[7:])
    await db_run("UPDATE shops SET status='active' WHERE owner_id=?", (uid,))
    lg = await lang(uid)
    try: await bot.send_message(uid, t(lg,"shop_approved"))
    except: pass
    await call.message.edit_text(call.message.text + "\n\nu2705 TASDIQLANDI", reply_markup=None)
    await call.answer("u2705")

@router.callback_query(F.data.startswith("shoprej_"))
async def shop_rej(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    uid = int(call.data[8:])
    await db_run("UPDATE shops SET status='rejected' WHERE owner_id=?", (uid,))
    await call.message.edit_text(call.message.text + "\n\nu274c RAD ETILDI", reply_markup=None)
    await call.answer("u274c")

# u2500u2500 MAHSULOT QO'SHISH (FIX 6) u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500
@router.callback_query(F.data.startswith("addprod_"))
async def add_product_start(call: CallbackQuery, state: FSMContext):
    shop_id = int(call.data[8:])
    await state.update_data(shop_id=shop_id)
    await state.set_state(AddProduct.name)
    await call.message.answer("ud83dudce6 Mahsulot nomini kiriting:\n\n_Masalan: Xarizma plomba A2_")
    await call.answer()

@router.message(AddProduct.name)
async def ap_name(msg: Message, state: FSMContext):
    await state.update_data(prod_name=msg.text)
    await state.set_state(AddProduct.price)
    await msg.answer("ud83dudcb0 Narxini kiriting (so'mda):\n\n_Masalan: 45000_")

@router.message(AddProduct.price)
async def ap_price(msg: Message, state: FSMContext):
    try:
        price = float(msg.text.replace(" ","").replace(",",""))
        await state.update_data(prod_price=price)
        await state.set_state(AddProduct.unit)
        await msg.answer("u2696ufe0f O'lchov birligi:", reply_markup=kb_prod_units())
    except: await msg.answer("u274c Faqat raqam!")

@router.callback_query(F.data.startswith("pu_"), AddProduct.unit)
async def ap_unit(call: CallbackQuery, state: FSMContext):
    unit = call.data[3:]
    await state.update_data(prod_unit=unit)
    await state.set_state(AddProduct.desc)
    await call.message.answer("ud83dudcdd Qisqa tavsif? (ixtiyoriy)",
                              reply_markup=ik([ib("u23ed O'tkazish","skip_desc")]))
    await call.answer()

@router.callback_query(F.data=="skip_desc", AddProduct.desc)
async def ap_desc_skip(call: CallbackQuery, state: FSMContext):
    await _save_product(call.message, call.from_user.id, state, desc=None)
    await call.answer()

@router.message(AddProduct.desc)
async def ap_desc(msg: Message, state: FSMContext):
    await _save_product(msg, msg.from_user.id, state, desc=msg.text)

async def _save_product(msg, uid, state, desc):
    d = await state.get_data()
    await db_insert(
        "INSERT INTO products(shop_id,name,price,unit,description) VALUES(?,?,?,?,?)",
        (d["shop_id"], d["prod_name"], d["prod_price"], d["prod_unit"], desc)
    )
    await state.clear()
    await msg.answer(f"u2705 *{d['prod_name']}* qo'shildi!\nud83dudcb0 {d['prod_price']:,.0f} so'm/{d['prod_unit']}")

@router.callback_query(F.data.startswith("delprod_"))
async def del_product_list(call: CallbackQuery):
    shop_id  = int(call.data[8:])
    products = await db_all("SELECT * FROM products WHERE shop_id=?", (shop_id,))
    if not products:
        await call.answer("Mahsulotlar yo'q", show_alert=True); return
    rows = [[ib(f"ud83duddd1 {p['name']}", f"delp_{p['id']}")] for p in products]
    await call.message.answer("Qaysi mahsulotni o'chirmoqchisiz?",
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()

@router.callback_query(F.data.startswith("delp_"))
async def del_product(call: CallbackQuery):
    pid = int(call.data[5:])
    p   = await db_get("SELECT name FROM products WHERE id=?", (pid,))
    await db_run("DELETE FROM products WHERE id=?", (pid,))
    await call.message.edit_text(f"ud83duddd1 *{p['name']}* o'chirildi.", reply_markup=None)
    await call.answer("u2705")

# u2500u2500 SOTUVCHI: EHTIYOJLAR u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500
@router.message(F.text.in_(["🔔 Yangi ehtiyojlar", "🔔 Новые заявки"]))
async def seller_feed(msg: Message):
    lg    = await lang(msg.from_user.id)
    needs = await db_all(
        "SELECT n.*,u.region,u.address,u.clinic_name,r.room_code "
        "FROM needs n JOIN users u ON n.owner_id=u.id JOIN rooms r ON n.room_id=r.id "
        "WHERE n.status='active' ORDER BY n.created_at DESC LIMIT 20"
    )
    if not needs: await msg.answer(t(lg,"no_feed")); return
    await msg.answer(t(lg,"feed_title", count=len(needs)))
    for n in needs:
        b = f"\nud83dudcb0 Budjet: {n['budget']:,.0f} so'm" if n["budget"] else ""
        await msg.answer(
            f"ud83euddb7 *{n['product_name']}*\nud83dudce6 {n['quantity']} {n['unit']}\n"
            f"u23f1 {n['deadline_hours']} soat{b}\nud83dudccd {n['region'] or ''} u2014 {n['address'] or ''}",
            reply_markup=ik([ib(t(lg,"btn_make_offer"), f"offer_{n['id']}_{n['unit']}")])
        )

@router.callback_query(F.data.startswith("offer_"))
async def start_offer(call: CallbackQuery, state: FSMContext):
    lg    = await lang(call.from_user.id)
    parts = call.data.split("_")
    nid, unit = int(parts[1]), parts[2]
    existing = await db_get("SELECT id FROM offers WHERE need_id=? AND seller_id=?", (nid, call.from_user.id))
    if existing:
        await call.answer(t(lg,"already_offered"), show_alert=True); return
    nd = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
    await state.update_data(need_id=nid, need_unit=unit, req_product=nd["product_name"])
    await state.set_state(OS.product)
    await call.message.answer(t(lg,"ask_offer_product", req=nd["product_name"]))
    await call.answer()

@router.message(OS.product)
async def os_product(msg: Message, state: FSMContext):
    await state.update_data(offer_prod=msg.text)
    d  = await state.get_data()
    lg = await lang(msg.from_user.id)
    await state.set_state(OS.price)
    await msg.answer(t(lg,"ask_offer_price", unit=d["need_unit"]))

@router.message(OS.price)
async def os_price(msg: Message, state: FSMContext):
    lg = await lang(msg.from_user.id)
    try:
        price = float(msg.text.replace(" ","").replace(",",""))
        await state.update_data(price=price)
        await state.set_state(OS.delivery)
        await msg.answer(t(lg,"ask_delivery"), reply_markup=kb_delivery(lg))
    except: await msg.answer("u274c Faqat raqam!")

@router.callback_query(F.data.startswith("del_"), OS.delivery)
async def os_delivery(call: CallbackQuery, state: FSMContext):
    lg    = await lang(call.from_user.id)
    hours = int(call.data[4:])
    d     = await state.get_data()
    u     = await get_user(call.from_user.id)
    await db_insert(
        "INSERT INTO offers(need_id,seller_id,product_name,price,delivery_hours) VALUES(?,?,?,?,?)",
        (d["need_id"], call.from_user.id, d["offer_prod"], d["price"], hours)
    )
    nd = await db_get(
        "SELECT n.*,u2.id as cid,u2.lang as clang FROM needs n JOIN users u2 ON n.owner_id=u2.id WHERE n.id=?",
        (d["need_id"],)
    )
    seller_name = u["clinic_name"] or u["full_name"] or "Sotuvchi"
    clang = nd["clang"] or "uz"
    try:
        last_offer = await db_get(
            "SELECT id FROM offers WHERE need_id=? AND seller_id=? ORDER BY id DESC LIMIT 1",
            (d["need_id"], call.from_user.id)
        )
        await bot.send_message(nd["cid"],
            t(clang,"new_offer_notify",
              product=nd["product_name"], offer_prod=d["offer_prod"],
              price=d["price"], unit=d["need_unit"], delivery=hours,
              seller=seller_name, phone=u["phone"] or "u2014"),
            reply_markup=kb_offer_action(last_offer["id"], clang) if last_offer else None
        )
    except Exception as e: log.error(e)
    await state.clear()
    await call.message.answer(t(lg,"offer_sent"))
    await call.answer("u2705")

# u2500u2500 STATISTIKA (FIX 8) u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500
@router.callback_query(F.data=="my_stats")
async def my_stats(call: CallbackQuery):
    uid = call.from_user.id
    u   = await get_user(uid)

    if u["role"] == "clinic":
        total_n  = (await db_get("SELECT COUNT(*) as c FROM needs WHERE owner_id=?", (uid,)))["c"]
        active_n = (await db_get("SELECT COUNT(*) as c FROM needs WHERE owner_id=? AND status='active'", (uid,)))["c"]
        done_n   = (await db_get("SELECT COUNT(*) as c FROM needs WHERE owner_id=? AND status='done'", (uid,)))["c"]
        total_o  = (await db_get("SELECT COUNT(*) as c FROM offers o JOIN needs n ON o.need_id=n.id WHERE n.owner_id=?", (uid,)))["c"]
        acc_o    = (await db_get("SELECT COUNT(*) as c FROM offers o JOIN needs n ON o.need_id=n.id WHERE n.owner_id=? AND o.status='accepted'", (uid,)))["c"]
        await call.message.answer(
            f"ud83dudcca *Sizning statistikangiz*\n\n"
            f"ud83dudccb Jami e'lonlar: *{total_n}*\n"
            f"ud83dudfe2 Aktiv: *{active_n}*\n"
            f"u2705 Yakunlangan: *{done_n}*\n\n"
            f"ud83dudce9 Kelgan takliflar: *{total_o}*\n"
            f"ud83eudd1d Qabul qilingan: *{acc_o}*"
        )
    elif u["role"] == "seller":
        shop   = await db_get("SELECT * FROM shops WHERE owner_id=?", (uid,))
        total_o = (await db_get("SELECT COUNT(*) as c FROM offers WHERE seller_id=?", (uid,)))["c"]
        acc_o   = (await db_get("SELECT COUNT(*) as c FROM offers WHERE seller_id=? AND status='accepted'", (uid,)))["c"]
        rej_o   = (await db_get("SELECT COUNT(*) as c FROM offers WHERE seller_id=? AND status='rejected'", (uid,)))["c"]
        deals   = shop["total_deals"] if shop else 0
        await call.message.answer(
            f"ud83dudcca *Do'kon statistikasi*\n\n"
            f"ud83cudfea {shop['shop_name'] if shop else 'u2014'}\n\n"
            f"ud83dudce4 Yuborilgan takliflar: *{total_o}*\n"
            f"u2705 Qabul qilingan: *{acc_o}*\n"
            f"u274c Rad etilgan: *{rej_o}*\n"
            f"ud83eudd1d Yakunlangan xaridlar: *{deals}*"
        )
    await call.answer()

# u2500u2500 ADMIN DASHBOARD (FIX 4) u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500
@router.message(Command("testchannel"))
async def test_channel(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    await msg.answer(f"🔍 CHANNEL_ID = `{CHANNEL_ID}`\nTest yuborilmoqda...")
    try:
        m = await bot.send_message(CHANNEL_ID, "✅ *Test* — bot kanalga yoza oladi!")
        await msg.answer(f"✅ Muvaffaqiyat! msg_id=`{m.message_id}`")
    except Exception as e:
        await msg.answer(f"❌ Xato:\n`{e}`\n\nYechim: CHANNEL_ID = @kanalusername")

@router.message(Command("admin"))
async def admin_panel(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("u26d4ufe0f Ruxsat yo'q."); return
    total_u   = (await db_get("SELECT COUNT(*) as c FROM users", ()))["c"]
    clinics   = (await db_get("SELECT COUNT(*) as c FROM users WHERE role='clinic'", ()))["c"]
    sellers   = (await db_get("SELECT COUNT(*) as c FROM users WHERE role='seller'", ()))["c"]
    active_n  = (await db_get("SELECT COUNT(*) as c FROM needs WHERE status='active'", ()))["c"]
    total_n   = (await db_get("SELECT COUNT(*) as c FROM needs", ()))["c"]
    pending_t = (await db_get("SELECT COUNT(*) as c FROM transactions WHERE status='pending'", ()))["c"]
    pending_s = (await db_get("SELECT COUNT(*) as c FROM shops WHERE status='pending'", ()))["c"]
    total_off = (await db_get("SELECT COUNT(*) as c FROM offers", ()))["c"]
    acc_off   = (await db_get("SELECT COUNT(*) as c FROM offers WHERE status='accepted'", ()))["c"]
    rev_row   = await db_get("SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE status='confirmed'", ())
    revenue   = rev_row["s"] if rev_row else 0

    await msg.answer(
        f"ud83dudc68u200dud83dudcbc *XAZDENT Admin*\n"
        f"_{datetime.now().strftime('%d.%m.%Y %H:%M')}_\n\n"
        f"ud83dudc65 Foydalanuvchilar: *{total_u}*\n"
        f"  u251c ud83cudfe5 Klinikalar: {clinics}\n"
        f"  u2514 ud83duded2 Sotuvchilar: {sellers}\n\n"
        f"ud83dudccb E'lonlar: *{total_n}* (ud83dudfe2 aktiv: {active_n})\n"
        f"ud83dudce9 Takliflar: *{total_off}* (u2705 qabul: {acc_off})\n\n"
        f"u23f3 Kutmoqda: ud83dudcb3 {pending_t} chek | ud83cudfea {pending_s} do'kon\n\n"
        f"ud83dudcb0 Jami daromad: *{revenue:,.0f} so'm*",
        reply_markup=ik(
            [ib("ud83dudcb3 Kutayotgan cheklar","adm_pending_tx")],
            [ib("ud83cudfea Kutayotgan do'konlar","adm_pending_shops")],
            [ib("u2699ufe0f Sozlamalar","adm_settings")],
        )
    )

@router.callback_query(F.data=="adm_pending_tx")
async def adm_pending_tx(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    txs = await db_all(
        "SELECT t.*,u.full_name,u.clinic_name FROM transactions t "
        "JOIN users u ON t.user_id=u.id WHERE t.status='pending' ORDER BY t.created_at DESC LIMIT 10"
    )
    if not txs: await call.message.answer("u2705 Kutayotgan cheklar yo'q."); await call.answer(); return
    for tx in txs:
        name = tx["clinic_name"] or tx["full_name"] or str(tx["user_id"])
        if tx["receipt_file_id"]:
            try:
                await call.message.answer_photo(tx["receipt_file_id"],
                    caption=f"ud83dudcb3 *Chek #{tx['id']}*\nud83dudc64 {name}\nud83dudcb0 {tx['amount']:,.0f} so'm u2192 {tx['balls']:.1f} ball",
                    reply_markup=ik(
                        [ib("u2705 Tasdiqlash",f"adm_ok_{tx['id']}_{tx['user_id']}_{tx['balls']}"),
                         ib("u274c Rad",        f"adm_rej_{tx['id']}_{tx['user_id']}")]
                    )
                )
            except: pass
    await call.answer()

@router.callback_query(F.data=="adm_pending_shops")
async def adm_pending_shops(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    shops = await db_all(
        "SELECT s.*,u.full_name,u.phone FROM shops s JOIN users u ON s.owner_id=u.id WHERE s.status='pending'"
    )
    if not shops: await call.message.answer("u2705 Kutayotgan do'konlar yo'q."); await call.answer(); return
    for s in shops:
        await call.message.answer(
            f"ud83cudfea *{s['shop_name']}*\nud83dudc64 {s['full_name']}\nud83dudcde {s['phone']}\nud83dudcc2 {s['category']}",
            reply_markup=ik([ib("u2705 Tasdiqlash",f"shopok_{s['owner_id']}"),
                              ib("u274c Rad",       f"shoprej_{s['owner_id']}")])
        )
    await call.answer()

@router.callback_query(F.data=="adm_settings")
async def adm_settings(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    ball_price = await get_setting("ball_price") or "1000"
    elon_price = await get_setting("elon_price") or "0.5"
    await call.message.answer(
        f"u2699ufe0f *Sozlamalar*\n\n"
        f"ud83dudcb0 1 ball = *{ball_price} so'm*\n"
        f"ud83dudccb 1 e'lon = *{elon_price} ball*\n"
        f"ud83dudcb3 Karta: `{CARD_NUM}`\n\n"
        f"O'zgartirish:\n"
        f"`/setball 2000` u2014 ball narxi\n"
        f"`/setelon 1` u2014 e'lon narxi"
    )
    await call.answer()

@router.message(Command("setball"))
async def set_ball(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    try:
        val = msg.text.split()[1]
        await update_setting("ball_price", val)
        await msg.answer(f"u2705 Ball narxi: *{val} so'm*")
    except: await msg.answer("u274c To'g'ri: /setball 2000")

@router.message(Command("setelon"))
async def set_elon(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    try:
        val = msg.text.split()[1]
        await update_setting("elon_price", val)
        await msg.answer(f"u2705 E'lon narxi: *{val} ball*")
    except: await msg.answer("u274c To'g'ri: /setelon 0.5")

# u2500u2500 MAIN u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500
async def main():
    await init_db()
    dp.include_router(router)
    log.info("ud83euddb7 XAZDENT Bot ishga tushdi!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
