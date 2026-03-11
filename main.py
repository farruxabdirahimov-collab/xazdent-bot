import asyncio, os, logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from database import init_db, get_user, db_run, db_get, db_all, db_insert
from database import get_setting, update_setting, add_balance, deduct_balance, get_next_room_code
from texts import t, REGIONS, REGIONS_RU

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN   = os.getenv("BOT_TOKEN")
CHANNEL_ID  = os.getenv("CHANNEL_ID", "@xazdent")
ADMIN_IDS   = [int(x) for x in os.getenv("ADMIN_IDS","").split(",") if x.strip()]

bot = Bot(token=BOT_TOKEN, parse_mode="Markdown")
dp  = Dispatcher(storage=MemoryStorage())
router = Router()

# ── STATES ───────────────────────────────────────────────
class PS(StatesGroup):           # Profile
    name = State(); phone = State(); region = State(); address = State()

class NS(StatesGroup):           # Need
    product = State(); qty = State(); unit = State()
    budget = State(); deadline = State(); note = State(); confirm = State()
    room = State()

class TS(StatesGroup):           # Topup
    amount = State(); receipt = State()

class OS(StatesGroup):           # Offer
    product = State(); price = State(); delivery = State()

class SS(StatesGroup):           # Shop
    cat = State(); name = State()

# ── KEYBOARDS ────────────────────────────────────────────
def ik(*rows): return InlineKeyboardMarkup(inline_keyboard=list(rows))
def ib(text, data): return InlineKeyboardButton(text=text, callback_data=data)
def rk(*rows, resize=True, one_time=False):
    return ReplyKeyboardMarkup(keyboard=list(rows), resize_keyboard=resize, one_time_keyboard=one_time)

def kb_lang():
    return ik([ib("🇺🇿 O'zbekcha","lang_uz"), ib("🇷🇺 Русский","lang_ru")])

def kb_role(lang):
    return ik([ib(t(lang,"role_clinic"),"role_clinic")],
              [ib(t(lang,"role_seller"),"role_seller")])

def kb_clinic(lang):
    return rk(
        [KeyboardButton(text=t(lang,"btn_my_needs")), KeyboardButton(text=t(lang,"btn_offers"))],
        [KeyboardButton(text=t(lang,"btn_my_rooms")), KeyboardButton(text=t(lang,"btn_new_room"))],
        [KeyboardButton(text=t(lang,"btn_balance")),  KeyboardButton(text=t(lang,"btn_profile"))],
    )

def kb_seller(lang):
    return rk(
        [KeyboardButton(text=t(lang,"btn_feed")),     KeyboardButton(text=t(lang,"btn_my_offers"))],
        [KeyboardButton(text=t(lang,"btn_my_shop")),  KeyboardButton(text=t(lang,"btn_new_shop"))],
        [KeyboardButton(text=t(lang,"btn_balance")),  KeyboardButton(text=t(lang,"btn_profile"))],
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
              [ib(t(lang,"edit"),   "edit"),
               ib(t(lang,"cancel"),"cancel")])

def kb_offer_action(offer_id, lang):
    return ik([ib(t(lang,"btn_accept"),f"acc_{offer_id}"),
               ib(t(lang,"btn_reject"),f"rej_{offer_id}")])

def kb_shop_cats(lang):
    return ik([ib(t(lang,"cat_1"),"cat_1")],[ib(t(lang,"cat_2"),"cat_2")],
              [ib(t(lang,"cat_3"),"cat_3")],[ib(t(lang,"cat_4"),"cat_4")],
              [ib(t(lang,"cat_5"),"cat_5")])

# ── HELPERS ──────────────────────────────────────────────
async def lang(uid): 
    u = await get_user(uid)
    return u["lang"] if u else "uz"

async def has_profile(uid):
    u = await get_user(uid)
    return u and u["clinic_name"] and u["phone"] and u["region"]

def need_preview_text(d, lg):
    dl = {2:"2 soat",24:"24 soat",72:"3 kun",168:"1 hafta"}.get(d.get("dl",24),"?")
    if lg == "ru":
        dl = {2:"2 часа",24:"24 часа",72:"3 дня",168:"1 неделя"}.get(d.get("dl",24),"?")
    b = f"\n💰 Byudjet: {d['budget']:,.0f} so'm" if d.get("budget") else ""
    n = f"\n📝 {d['note']}" if d.get("note") else ""
    return f"🦷 *{d['product']}*\n📦 {d['qty']} {d['unit']}\n⏱ {dl}{b}{n}"

async def post_channel(need_id, room_code, user, d):
    dl_txt = {2:"2 soat",24:"24 soat",72:"3 kun",168:"1 hafta"}.get(d.get("dl",24),"?")
    budget_txt = f"\n💰 Budjet: {d['budget']:,.0f} so'm gacha" if d.get("budget") else ""
    note_txt   = f"\n📝 {d['note']}" if d.get("note") else ""
    words = d["product"].split()
    tags  = " ".join(f"#{w.lower()}" for w in words[:3] if len(w)>2)
    reg   = f"#{(user['region'] or '').replace(' ','').lower()}"
    txt = (
        f"📋 *BUYURTMA*\n\n"
        f"🦷 {d['product']}\n"
        f"📦 {d['qty']} {d['unit']}\n"
        f"⏱ {dl_txt} ichida"
        f"{budget_txt}{note_txt}\n\n"
        f"📍 {user['region'] or ''}\n"
        f"🏠 {user['address'] or ''}\n\n"
        f"{tags} {reg}\n\n"
        f"💬 @XazdentBot | 🏠 {room_code}"
    )
    try:
        msg = await bot.send_message(CHANNEL_ID, txt)
        return msg.message_id
    except Exception as e:
        log.error(f"Kanal xato: {e}")
        return None

# ── START ────────────────────────────────────────────────
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

    # deep-link (sotuvchi xona linkidan kelsa)
    args = msg.text.split()
    if len(args) > 1:
        await state.update_data(from_room=args[1])

    if u and u["role"] not in (None, "none"):
        lg = u["lang"] or "uz"
        kb = kb_clinic(lg) if u["role"]=="clinic" else kb_seller(lg)
        menu_txt = t(lg,"clinic_menu") if u["role"]=="clinic" else t(lg,"seller_menu")
        await msg.answer(menu_txt, reply_markup=kb)
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
    lg = await lang(call.from_user.id)
    kb  = kb_clinic(lg) if role=="clinic" else kb_seller(lg)
    txt = t(lg,"clinic_menu") if role=="clinic" else t(lg,"seller_menu")
    await call.message.delete()
    await call.message.answer(txt, reply_markup=kb)
    await call.answer()

# ── PROFIL ───────────────────────────────────────────────
@router.message(F.text.in_(["⚙️ Profil","⚙️ Профиль"]))
async def show_profile(msg: Message, state: FSMContext):
    lg = await lang(msg.from_user.id)
    u  = await get_user(msg.from_user.id)
    txt = (
        f"⚙️ *Profil*\n\n"
        f"👤 {u['clinic_name'] or '—'}\n"
        f"📞 {u['phone'] or '—'}\n"
        f"📍 {u['region'] or '—'}\n"
        f"🏠 {u['address'] or '—'}\n"
        f"💰 Balans: {u['balance']:.1f} ball"
    )
    await msg.answer(txt, reply_markup=ik([ib("✏️ Tahrirlash","edit_profile")]))

@router.callback_query(F.data == "edit_profile")
async def start_profile(call: CallbackQuery, state: FSMContext):
    lg = await lang(call.from_user.id)
    await state.set_state(PS.name)
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
    lg = await lang(call.from_user.id)
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
    await msg.answer(t(lg,"profile_saved"), reply_markup=kb)

# ── OMBORXONA ────────────────────────────────────────────
@router.message(F.text.in_(["➕ Yangi omborxona","➕ Новый склад"]))
async def new_room(msg: Message):
    lg = await lang(msg.from_user.id)
    if not await has_profile(msg.from_user.id):
        await msg.answer(t(lg,"profile_first"))
        return
    await msg.answer(t(lg,"ask_room_type"), reply_markup=kb_room_types(lg))

@router.callback_query(F.data.startswith("room_"))
async def cb_room(call: CallbackQuery):
    lg = await lang(call.from_user.id)
    rtype = call.data[5:]
    max_n = {"small":10,"standard":25,"premium":150}[rtype]
    code  = await get_next_room_code(rtype)
    if not code:
        await call.message.answer("❌ Xona topilmadi. Admin bilan bog'laning.")
        return
    await db_insert(
        "INSERT INTO rooms(room_code,room_type,owner_id,max_needs) VALUES(?,?,?,?)",
        (code, rtype, call.from_user.id, max_n)
    )
    await call.message.edit_text(t(lg,"room_created",code=code))
    await call.answer("✅")

@router.message(F.text.in_(["🏠 Omborxonalarim","🏠 Мои склады"]))
async def my_rooms(msg: Message):
    lg = await lang(msg.from_user.id)
    rooms = await db_all("SELECT * FROM rooms WHERE owner_id=? AND status='active'", (msg.from_user.id,))
    if not rooms:
        await msg.answer(t(lg,"no_rooms")); return
    await msg.answer(t(lg,"rooms_list"))
    for r in rooms:
        cnt = (await db_get("SELECT COUNT(*) as c FROM needs WHERE room_id=? AND status='active'",(r["id"],)))["c"]
        emoji = {"small":"🔹","standard":"🔷","premium":"💎"}.get(r["room_type"],"📦")
        await msg.answer(
            f"{emoji} `{r['room_code']}` — {cnt}/{r['max_needs']} ehtiyoj",
            reply_markup=ik([ib("➕ Ehtiyoj qo'shish", f"addneed_{r['id']}_{r['room_code']}")])
        )

# ── EHTIYOJ ──────────────────────────────────────────────
@router.callback_query(F.data.startswith("addneed_"))
async def start_need(call: CallbackQuery, state: FSMContext):
    lg = await lang(call.from_user.id)
    _, rid, rcode = call.data.split("_", 2)
    await state.update_data(room_id=int(rid), room_code=rcode)
    await state.set_state(NS.product)
    await call.message.answer(t(lg,"ask_product"))
    await call.answer()

@router.message(F.text.in_(["📋 Ehtiyojlarim","📋 Мои заявки"]))
async def my_needs_menu(msg: Message):
    lg = await lang(msg.from_user.id)
    needs = await db_all(
        "SELECT n.*,r.room_code FROM needs n JOIN rooms r ON n.room_id=r.id WHERE n.owner_id=? ORDER BY n.created_at DESC LIMIT 15",
        (msg.from_user.id,)
    )
    if not needs: await msg.answer(t(lg,"no_needs")); return
    await msg.answer(f"📋 *Ehtiyojlarim:* {len(needs)} ta")
    for n in needs:
        st = {"active":"🟢","paused":"⏸","done":"✅","cancelled":"❌"}.get(n["status"],"📋")
        await msg.answer(
            f"{st} *{n['product_name']}* — {n['quantity']} {n['unit']}\n🏠 `{n['room_code']}`",
            reply_markup=ik(
                [ib("📩 Takliflar",f"offers_{n['id']}"),  ib("⏸",f"pause_{n['id']}")],
                [ib("✅ Yakunlash", f"done_{n['id']}")]
            )
        )

@router.message(NS.product)
async def ns_product(msg: Message, state: FSMContext):
    lg = await lang(msg.from_user.id)
    await state.update_data(product=msg.text)
    await state.set_state(NS.qty)
    await msg.answer(t(lg,"ask_qty"))

@router.message(NS.qty)
async def ns_qty(msg: Message, state: FSMContext):
    lg = await lang(msg.from_user.id)
    try:
        await state.update_data(qty=float(msg.text.replace(",",".")))
        await state.set_state(NS.unit)
        await msg.answer(t(lg,"ask_unit"), reply_markup=kb_units(lg))
    except: await msg.answer("❌ Faqat raqam!")

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
    await call.answer("✅")

@router.callback_query(F.data=="cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await call.answer("Bekor qilindi")

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

# ── TAKLIFLAR (klinika) ───────────────────────────────────
@router.message(F.text.in_(["📩 Takliflar","📩 Предложения"]))
async def my_offers_page(msg: Message):
    lg = await lang(msg.from_user.id)
    needs = await db_all(
        "SELECT id,product_name FROM needs WHERE owner_id=? AND status='active'", (msg.from_user.id,)
    )
    if not needs: await msg.answer(t(lg,"no_needs")); return
    rows = [[ib(n["product_name"], f"offers_{n['id']}")] for n in needs]
    await msg.answer("📩 Qaysi e'lonning takliflarini ko'rmoqchisiz?",
                     reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@router.callback_query(F.data.startswith("offers_"))
async def show_offers(call: CallbackQuery):
    lg = await lang(call.from_user.id)
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
            f"{i}. *{shop}*\n🦷 {o['product_name']}\n💰 {o['price']:,.0f} so'm/{nd['unit']}\n🚚 {o['delivery_hours']} soat",
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
    name  = o["shop_name"] or o["full_name"] or "Sotuvchi"
    phone = o["phone"] or "—"
    await call.message.edit_text(t(lg,"offer_accepted", name=name, phone=phone))
    # Sotuvchiga xabar
    clinic = await get_user(call.from_user.id)
    try:
        await bot.send_message(o["seller_id"],
            f"🎉 *Taklifingiz qabul qilindi!*\n\n"
            f"🏥 {clinic['clinic_name'] or clinic['full_name'] or 'Klinika'}\n"
            f"📞 {clinic['phone'] or '—'}")
    except: pass
    await call.answer("✅")

@router.callback_query(F.data.startswith("rej_"))
async def reject_offer(call: CallbackQuery):
    oid = int(call.data[4:])
    await db_run("UPDATE offers SET status='rejected' WHERE id=?", (oid,))
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("❌ Rad etildi")

# ── BALANS ───────────────────────────────────────────────
@router.message(F.text.in_(["💰 Hisobim","💰 Мой счёт"]))
async def show_balance(msg: Message):
    lg = await lang(msg.from_user.id)
    u  = await get_user(msg.from_user.id)
    await msg.answer(t(lg,"balance_info", balls=u["balance"] or 0),
                     reply_markup=ik([ib(t(lg,"btn_topup"),"topup")]))

@router.callback_query(F.data=="topup")
async def topup_start(call: CallbackQuery, state: FSMContext):
    lg   = await lang(call.from_user.id)
    card = await get_setting("card_number") or "8600 0000 0000 0000"
    await state.set_state(TS.amount)
    await call.message.answer(t(lg,"topup_send_card", card=card))
    await call.answer()

@router.message(TS.amount)
async def topup_amount(msg: Message, state: FSMContext):
    lg = await lang(msg.from_user.id)
    try:
        amount     = float(msg.text.replace(" ","").replace(",",""))
        ball_price = float(await get_setting("ball_price") or 1000)
        balls      = amount / ball_price
        await state.update_data(amount=amount, balls=balls)
        await state.set_state(TS.receipt)
        await msg.answer(f"💰 {amount:,.0f} so'm → {balls:.1f} ball\n\n📸 Chek rasmini yuboring:")
    except: await msg.answer("❌ Faqat raqam!")

@router.message(TS.receipt, F.photo)
async def topup_receipt(msg: Message, state: FSMContext):
    lg   = await lang(msg.from_user.id)
    d    = await state.get_data()
    fid  = msg.photo[-1].file_id
    tid  = await db_insert(
        "INSERT INTO transactions(user_id,amount,balls,type,receipt_file_id) VALUES(?,?,?,'topup',?)",
        (msg.from_user.id, d["amount"], d["balls"], fid)
    )
    # Adminlarga xabar
    u = await get_user(msg.from_user.id)
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
    await msg.answer(t(lg,"receipt_sent"))

# Admin tasdiqlash (asosiy botdan ham ishlaydi)
@router.callback_query(F.data.startswith("adm_ok_"))
async def adm_confirm(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    _, _, tid, uid, balls = call.data.split("_")
    await db_run("UPDATE transactions SET status='confirmed',confirmed_by=? WHERE id=?",
                 (call.from_user.id, int(tid)))
    await add_balance(int(uid), float(balls))
    lg = await lang(int(uid))
    try: await bot.send_message(int(uid), t(lg,"balance_added", balls=float(balls)))
    except: pass
    await call.message.edit_caption(call.message.caption + "\n\n✅ TASDIQLANDI", reply_markup=None)
    await call.answer("✅")

@router.callback_query(F.data.startswith("adm_rej_"))
async def adm_reject(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    _, _, tid, uid = call.data.split("_")
    await db_run("UPDATE transactions SET status='rejected' WHERE id=?", (int(tid),))
    try: await bot.send_message(int(uid), "❌ Chekingiz rad etildi. Admin bilan bog'laning.")
    except: pass
    await call.message.edit_caption(call.message.caption + "\n\n❌ RAD ETILDI", reply_markup=None)
    await call.answer("❌")

# ── SOTUVCHI: DO'KON ─────────────────────────────────────
@router.message(F.text.in_(["➕ Do'kon ochish","➕ Открыть магазин"]))
async def new_shop(msg: Message, state: FSMContext):
    lg = await lang(msg.from_user.id)
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
    # Adminlarga xabar
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid,
                f"🏪 *Yangi do'kon tasdiqlash kerak!*\n\n"
                f"📛 {msg.text}\n👤 {u['clinic_name'] or u['full_name']}\n📞 {u['phone']}",
                reply_markup=ik([ib("✅ Tasdiqlash",f"shopok_{msg.from_user.id}"),
                                  ib("❌ Rad",       f"shoprej_{msg.from_user.id}")])
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
    await call.message.edit_text(call.message.text + "\n\n✅ TASDIQLANDI", reply_markup=None)
    await call.answer("✅")

@router.callback_query(F.data.startswith("shoprej_"))
async def shop_rej(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    uid = int(call.data[8:])
    await db_run("UPDATE shops SET status='rejected' WHERE owner_id=?", (uid,))
    await call.message.edit_text(call.message.text + "\n\n❌ RAD ETILDI", reply_markup=None)
    await call.answer("❌")

# ── SOTUVCHI: EHTIYOJ TEZKOR ─────────────────────────────
@router.message(F.text.in_(["🔔 Yangi ehtiyojlar","🔔 Новые заявки"]))
async def seller_feed(msg: Message):
    lg = await lang(msg.from_user.id)
    needs = await db_all(
        "SELECT n.*,u.region,u.address,u.clinic_name,r.room_code "
        "FROM needs n JOIN users u ON n.owner_id=u.id JOIN rooms r ON n.room_id=r.id "
        "WHERE n.status='active' ORDER BY n.created_at DESC LIMIT 20"
    )
    if not needs: await msg.answer(t(lg,"no_feed")); return
    await msg.answer(t(lg,"feed_title", count=len(needs)))
    for n in needs:
        b = f"\n💰 Budjet: {n['budget']:,.0f} so'm" if n["budget"] else ""
        await msg.answer(
            f"🦷 *{n['product_name']}*\n📦 {n['quantity']} {n['unit']}\n"
            f"⏱ {n['deadline_hours']} soat{b}\n📍 {n['region'] or ''} — {n['address'] or ''}\n🏠 `{n['room_code']}`",
            reply_markup=ik([ib(t(lg,"btn_make_offer"), f"offer_{n['id']}_{n['unit']}")])
        )

@router.callback_query(F.data.startswith("offer_"))
async def start_offer(call: CallbackQuery, state: FSMContext):
    lg = await lang(call.from_user.id)
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
    lg = await lang(msg.from_user.id)
    await state.update_data(offer_prod=msg.text)
    d  = await state.get_data()
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
    except: await msg.answer("❌ Faqat raqam!")

@router.callback_query(F.data.startswith("del_"), OS.delivery)
async def os_delivery(call: CallbackQuery, state: FSMContext):
    lg   = await lang(call.from_user.id)
    hours= int(call.data[4:])
    d    = await state.get_data()
    u    = await get_user(call.from_user.id)
    await db_insert(
        "INSERT INTO offers(need_id,seller_id,product_name,price,delivery_hours) VALUES(?,?,?,?,?)",
        (d["need_id"], call.from_user.id, d["offer_prod"], d["price"], hours)
    )
    # Klinikaga xabar
    nd = await db_get(
        "SELECT n.*,u2.id as cid,u2.lang as clang FROM needs n JOIN users u2 ON n.owner_id=u2.id WHERE n.id=?",
        (d["need_id"],)
    )
    seller_name = u["clinic_name"] or u["full_name"] or "Sotuvchi"
    clang = nd["clang"] or "uz"
    try:
        # Offer ID ni olish
        last_offer = await db_get(
            "SELECT id FROM offers WHERE need_id=? AND seller_id=? ORDER BY id DESC LIMIT 1",
            (d["need_id"], call.from_user.id)
        )
        await bot.send_message(nd["cid"],
            t(clang,"new_offer_notify",
              product=nd["product_name"], offer_prod=d["offer_prod"],
              price=d["price"], unit=d["need_unit"], delivery=hours,
              seller=seller_name, phone=u["phone"] or "—"),
            reply_markup=kb_offer_action(last_offer["id"], clang) if last_offer else None
        )
    except Exception as e: log.error(e)
    await state.clear()
    await call.message.answer(t(lg,"offer_sent"))
    await call.answer("✅")

# ── MAIN ─────────────────────────────────────────────────
async def main():
    await init_db()
    dp.include_router(router)
    log.info("🦷 XAZDENT Bot ishga tushdi!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
