import asyncio, os, logging, io
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    BufferedInputFile
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from database import (init_db, get_user, db_run, db_get, db_all, db_insert,
                      get_setting, update_setting, add_balance, get_next_room_code)
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
class Reg(StatesGroup):
    name = State()
    phone = State()
    region = State()
    address = State()
    location = State()
    role = State()

class BulkAdd(StatesGroup):     # Ko'p ehtiyoj birdaniga
    items = State()
    deadline = State()
    confirm = State()

class StepAdd(StatesGroup):     # Tartibli ehtiyoj
    product = State()
    qty_unit = State()
    more = State()
    deadline = State()
    confirm = State()

class OfferState(StatesGroup):
    batch_select = State()
    price = State()
    delivery = State()

class Topup(StatesGroup):
    amount = State()
    receipt = State()

class ShopReg(StatesGroup):
    cat = State()
    name = State()

class AddProd(StatesGroup):
    name = State()
    price = State()
    unit = State()

# ── KEYBOARDS ─────────────────────────────────────────────
def ik(*rows): return InlineKeyboardMarkup(inline_keyboard=list(rows))
def ib(text, data): return [InlineKeyboardButton(text=text, callback_data=data)]
def ib1(text, data): return InlineKeyboardButton(text=text, callback_data=data)
def rk(*rows): return ReplyKeyboardMarkup(keyboard=list(rows), resize_keyboard=True)

def kb_main_clinic():
    return rk(
        [KeyboardButton(text="📋 Ehtiyojlarim"),   KeyboardButton(text="➕ Ehtiyoj yozish")],
        [KeyboardButton(text="📊 Jadval & Takliflar"), KeyboardButton(text="💰 Hisob")],
        [KeyboardButton(text="⚙️ Profil")]
    )

def kb_main_seller():
    return rk(
        [KeyboardButton(text="🔔 Ehtiyojlar lenti"), KeyboardButton(text="📤 Takliflarim")],
        [KeyboardButton(text="🏪 Do'konim"),          KeyboardButton(text="💰 Hisob")],
        [KeyboardButton(text="⚙️ Profil")]
    )

def kb_roles():
    return ik(ib("🏥 Stomatolog / Klinika", "role_clinic"),
              ib("🔬 Zubo texnik (Lab)",     "role_lab"),
              ib("🛒 Sotuvchi",              "role_seller"))

def kb_regions():
    rows = []
    for i in range(0, len(REGIONS), 2):
        row = [ib1(REGIONS[i], f"reg_{i}")]
        if i+1 < len(REGIONS): row.append(ib1(REGIONS[i+1], f"reg_{i+1}"))
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_deadline():
    return ik(ib("⚡️ 2 soat","dl_2"),  ib("🕐 24 soat","dl_24"),
              ib("📅 3 kun","dl_72"),   ib("🗓 1 hafta","dl_168"))

def kb_units():
    return ik(ib("📌 dona","u_dona"), ib("⚖️ kg","u_kg"), ib("💧 litr","u_litr"))

def kb_yes_no():
    return ik(ib("✅ Ha, yana qo'shaman","more_yes"),
              ib("📋 Yo'q, tayyor","more_no"))

def kb_shop_cats():
    return ik(ib("🦷 Terapevtik material","sc_1"),
              ib("⚙️ Jarrohlik & Implant","sc_2"),
              ib("🔬 Zubo texnik ashyolar","sc_3"),
              ib("🧪 Dezinfeksiya","sc_4"),
              ib("💡 Asbob-uskunalar","sc_5"))

# ── HELPERS ───────────────────────────────────────────────
def parse_bulk_text(text: str):
    """
    '5 dona Fuji IX' yoki 'Fuji IX 5 dona' formatlarini parse qiladi
    """
    lines   = [l.strip() for l in text.strip().split("\n") if l.strip()]
    parsed  = []
    errors  = []
    units   = {"dona","kg","litr","gr","ml","box","quti","pachka","set","ta"}
    for line in lines:
        parts = line.split()
        if len(parts) < 2:
            errors.append(line); continue
        qty, unit, name = None, "dona", []
        for i, p in enumerate(parts):
            try:
                qty = float(p.replace(",","."))
                # keyingi so'z birlik bo'lishi mumkin
                if i+1 < len(parts) and parts[i+1].lower() in units:
                    unit = parts[i+1].lower()
                    name = parts[:i] + parts[i+2:]
                else:
                    name = parts[:i] + parts[i+1:]
                break
            except: pass
        if qty is None or not name:
            errors.append(line); continue
        parsed.append({"qty": qty, "unit": unit, "name": " ".join(name)})
    return parsed, errors

async def post_to_channel(need: dict, owner: dict):
    dl_map = {2:"2 soat", 24:"24 soat", 72:"3 kun", 168:"1 hafta"}
    dl_txt = dl_map.get(need["deadline_hours"], f"{need['deadline_hours']} soat")
    words  = need["product_name"].split()
    tags   = " ".join(f"#{w.lower()}" for w in words[:3] if len(w) > 2)
    txt = (
        f"📋 *BUYURTMA*\n\n"
        f"🦷 {need['product_name']}\n"
        f"📦 {need['quantity']} {need['unit']}\n"
        f"⏱ {dl_txt} ichida\n\n"
        f"📍 {owner.get('region','')}\n\n"
        f"{tags}\n💬 @XazdentBot"
    )
    try:
        m = await bot.send_message(CHANNEL_ID, txt)
        return m.message_id
    except Exception as e:
        log.error(f"Kanal xato: {e}"); return None

async def build_comparison_table(batch_id: int):
    """
    Bir to'plamning barcha ehtiyojlari va takliflari uchun
    solishtirma jadval (botda + Excel) yaratadi
    """
    needs = await db_all("SELECT * FROM needs WHERE batch_id=? ORDER BY id", (batch_id,))
    if not needs:
        return None, None

    # Barcha sotuvchilarni yig'amiz
    sellers_raw = await db_all(
        "SELECT DISTINCT o.seller_id, COALESCE(s.shop_name, u.full_name, u.clinic_name) as name "
        "FROM offers o "
        "JOIN users u ON o.seller_id=u.id "
        "LEFT JOIN shops s ON s.owner_id=o.seller_id "
        "WHERE o.batch_id=? AND o.status='pending'",
        (batch_id,)
    )
    if not sellers_raw:
        return None, None

    sellers = [{"id": s["seller_id"], "name": s["name"]} for s in sellers_raw]

    # Har bir need + har bir seller uchun narx
    table = []
    col_totals = {s["id"]: 0.0 for s in sellers}
    col_missing = {s["id"]: False for s in sellers}

    for nd in needs:
        row = {"name": nd["product_name"], "qty": nd["quantity"], "unit": nd["unit"],
               "need_id": nd["id"], "prices": {}}
        for sel in sellers:
            offer = await db_get(
                "SELECT price FROM offers WHERE need_id=? AND seller_id=? AND status='pending' ORDER BY price LIMIT 1",
                (nd["id"], sel["id"])
            )
            if offer:
                row["prices"][sel["id"]] = offer["price"]
                col_totals[sel["id"]] += offer["price"] * nd["quantity"]
            else:
                row["prices"][sel["id"]] = None
                col_missing[sel["id"]] = True
        table.append(row)

    return sellers, table, col_totals, col_missing

def format_table_text(sellers, table, col_totals, col_missing):
    """Telegram uchun monospace jadval"""
    lines = ["```"]
    # Header
    header = f"{'Mahsulot':<18} {'Miqdor':>6}"
    for s in sellers:
        header += f" {s['name'][:8]:>9}"
    lines.append(header)
    lines.append("─" * (26 + len(sellers)*10))

    # Rows
    for row in table:
        prices = []
        min_price = None
        for s in sellers:
            p = row["prices"].get(s["id"])
            if p is not None:
                if min_price is None or p < min_price:
                    min_price = p
            prices.append(p)

        line = f"{row['name'][:18]:<18} {str(row['qty'])+row['unit']:>6}"
        for i, s in enumerate(sellers):
            p = prices[i]
            if p is None:
                cell = "    —    "
            elif p == min_price:
                cell = f"✅{p/1000:.0f}k   "
            else:
                cell = f" {p/1000:.0f}k    "
            line += f" {cell[:9]:>9}"
        lines.append(line)

    lines.append("─" * (26 + len(sellers)*10))
    # Totals
    total_line = f"{'JAMI':<18} {'':>6}"
    best_total = min((v for k,v in col_totals.items() if not col_missing[k]), default=None)
    for s in sellers:
        total = col_totals[s["id"]]
        miss  = col_missing[s["id"]]
        if miss:
            cell = "  to'liq emas"[:9]
        elif best_total and total == best_total:
            cell = f"✅{total/1000:.0f}k"[:9]
        else:
            cell = f" {total/1000:.0f}k"[:9]
        total_line += f" {cell:>9}"
    lines.append(total_line)
    lines.append("```")
    return "\n".join(lines)

def build_excel(sellers, table, col_totals, col_missing):
    """Excel fayl yaratish (openpyxl)"""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        return None

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Narx jadvali"

    # Ranglar
    green_fill = PatternFill("solid", fgColor="C6EFCE")
    header_fill = PatternFill("solid", fgColor="1F4E79")
    sub_fill    = PatternFill("solid", fgColor="BDD7EE")
    total_fill  = PatternFill("solid", fgColor="DDEBF7")
    red_fill    = PatternFill("solid", fgColor="FFCCCC")

    thin = Side(style='thin')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    white_font  = Font(name="Calibri", color="FFFFFF", bold=True, size=11)
    bold_font   = Font(name="Calibri", bold=True, size=11)
    normal_font = Font(name="Calibri", size=11)
    center      = Alignment(horizontal="center", vertical="center")
    left_al     = Alignment(horizontal="left",   vertical="center")

    # Sarlavha
    ws.merge_cells(f"A1:{get_column_letter(3+len(sellers))}1")
    title_cell = ws["A1"]
    title_cell.value = f"XAZDENT — Narx Jadvali   {datetime.now().strftime('%d.%m.%Y')}"
    title_cell.font  = Font(name="Calibri", bold=True, size=14, color="FFFFFF")
    title_cell.fill  = header_fill
    title_cell.alignment = center
    ws.row_dimensions[1].height = 28

    # Header qator
    ws["A2"] = "Mahsulot"
    ws["B2"] = "Miqdor"
    ws["C2"] = "Birlik"
    for i, s in enumerate(sellers):
        cell = ws.cell(row=2, column=4+i, value=s["name"])
        cell.fill      = sub_fill
        cell.font      = bold_font
        cell.alignment = center
        cell.border    = border
    for col in ["A","B","C"]:
        c = ws[f"{col}2"]
        c.fill = sub_fill; c.font = bold_font
        c.alignment = center; c.border = border
    ws.row_dimensions[2].height = 22

    # Ma'lumot qatorlari
    for r, row in enumerate(table):
        excel_row = 3 + r
        prices_for_row = [row["prices"].get(s["id"]) for s in sellers]
        valid_prices   = [p for p in prices_for_row if p is not None]
        min_p          = min(valid_prices) if valid_prices else None

        ws.cell(excel_row, 1, row["name"]).alignment = left_al
        ws.cell(excel_row, 2, row["qty"]).alignment  = center
        ws.cell(excel_row, 3, row["unit"]).alignment = center

        for i, s in enumerate(sellers):
            p    = row["prices"].get(s["id"])
            cell = ws.cell(excel_row, 4+i)
            if p is None:
                cell.value = "—"
                cell.fill  = red_fill
            else:
                cell.value = p
                cell.number_format = '#,##0 "so\'m"'
                if p == min_p:
                    cell.fill = green_fill
                    cell.font = Font(name="Calibri", bold=True, color="006100", size=11)
            cell.alignment = center
            cell.border    = border

        for col_idx in range(1, 4):
            c = ws.cell(excel_row, col_idx)
            c.font = normal_font; c.border = border
        ws.row_dimensions[excel_row].height = 20

    # Jami qatori
    total_row = 3 + len(table)
    ws.cell(total_row, 1, "JAMI").font = bold_font
    ws.cell(total_row, 1).fill        = total_fill
    ws.cell(total_row, 2, "").fill    = total_fill
    ws.cell(total_row, 3, "").fill    = total_fill

    best_total = min((v for k,v in col_totals.items() if not col_missing[k]), default=None)
    for i, s in enumerate(sellers):
        total = col_totals[s["id"]]
        cell  = ws.cell(total_row, 4+i)
        cell.border    = border
        cell.alignment = center
        if col_missing[s["id"]]:
            cell.value = "To'liq emas"
            cell.fill  = red_fill
            cell.font  = normal_font
        else:
            cell.value = total
            cell.number_format = '#,##0 "so\'m"'
            if best_total and total == best_total:
                cell.fill = green_fill
                cell.font = Font(name="Calibri", bold=True, color="006100", size=12)
            else:
                cell.fill = total_fill
                cell.font = bold_font
    ws.row_dimensions[total_row].height = 24

    # Ustun kengligi
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 8
    for i in range(len(sellers)):
        ws.column_dimensions[get_column_letter(4+i)].width = 18

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()

# ── START & REGISTRATSIYA ─────────────────────────────────
@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    u = await get_user(msg.from_user.id)

    if u and u["role"] not in (None, "none"):
        kb = kb_main_clinic() if u["role"] in ("clinic","lab") else kb_main_seller()
        txt = "🏥 *Klinika paneli*" if u["role"] in ("clinic","lab") else "🛒 *Sotuvchi paneli*"
        await msg.answer(txt, reply_markup=kb); return

    await db_run("INSERT OR IGNORE INTO users(id,username,full_name) VALUES(?,?,?)",
                 (msg.from_user.id, msg.from_user.username, msg.from_user.full_name))
    await state.set_state(Reg.name)
    await msg.answer(
        "👋 *XAZDENT*ga xush kelibsiz!\n\n"
        "🦷 Stomatologik materiallar bozori\n\n"
        "Ro'yxatdan o'tish boshlaylik.\n\n"
        "📝 Ism-familiya yoki klinika nomingiz?",
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(Reg.name)
async def reg_name(msg: Message, state: FSMContext):
    await state.update_data(clinic_name=msg.text)
    await state.set_state(Reg.phone)
    await msg.answer(
        "📞 Telefon raqamingiz?",
        reply_markup=rk([KeyboardButton(text="📞 Raqamni yuborish", request_contact=True)])
    )

@router.message(Reg.phone, F.contact)
async def reg_phone(msg: Message, state: FSMContext):
    await state.update_data(phone=msg.contact.phone_number)
    await state.set_state(Reg.region)
    await msg.answer("📍 Viloyatingizni tanlang:", reply_markup=kb_regions())

@router.message(Reg.phone)
async def reg_phone_text(msg: Message, state: FSMContext):
    # Agar tugma bosmasdan yozsa
    p = msg.text.replace(" ","").replace("-","").replace("+","")
    if p.isdigit() and len(p) >= 9:
        await state.update_data(phone=msg.text)
        await state.set_state(Reg.region)
        await msg.answer("📍 Viloyatingizni tanlang:", reply_markup=kb_regions())
    else:
        await msg.answer("❌ Telefon raqam noto'g'ri. Qaytadan yuboring.")

@router.callback_query(F.data.startswith("reg_"), Reg.region)
async def reg_region(call: CallbackQuery, state: FSMContext):
    idx    = int(call.data[4:])
    region = REGIONS[idx].split(" ",1)[1] if " " in REGIONS[idx] else REGIONS[idx]
    await state.update_data(region=region)
    await state.set_state(Reg.address)
    await call.message.answer("🏠 Aniq manzilingiz?\n_(Ko'cha, uy raqami)_",
                               reply_markup=ReplyKeyboardRemove())
    await call.answer()

@router.message(Reg.address)
async def reg_address(msg: Message, state: FSMContext):
    await state.update_data(address=msg.text)
    await state.set_state(Reg.location)
    await msg.answer(
        "📍 Lokatsiyangizni yuboring?\n_(ixtiyoriy — tezroq yetkazib berish uchun)_",
        reply_markup=rk(
            [KeyboardButton(text="📍 Lokatsiyani yuborish", request_location=True)],
            [KeyboardButton(text="⏭ O'tkazish")]
        )
    )

@router.message(Reg.location, F.location)
async def reg_location(msg: Message, state: FSMContext):
    await state.update_data(lat=msg.location.latitude, lon=msg.location.longitude)
    await _finish_reg_go_role(msg, state)

@router.message(Reg.location, F.text == "⏭ O'tkazish")
async def reg_location_skip(msg: Message, state: FSMContext):
    await _finish_reg_go_role(msg, state)

async def _finish_reg_go_role(msg: Message, state: FSMContext):
    await state.set_state(Reg.role)
    await msg.answer("✅ Deyarli tayyor!\n\nSiz kimسیز?",
                     reply_markup=kb_roles())

@router.callback_query(F.data.startswith("role_"), Reg.role)
async def reg_role(call: CallbackQuery, state: FSMContext):
    role = call.data[5:]
    d    = await state.get_data()
    await db_run(
        "UPDATE users SET clinic_name=?,phone=?,region=?,address=?,latitude=?,longitude=?,role=? WHERE id=?",
        (d.get("clinic_name"), d.get("phone"), d.get("region"), d.get("address"),
         d.get("lat"), d.get("lon"), role, call.from_user.id)
    )
    await state.clear()
    kb  = kb_main_clinic() if role in ("clinic","lab") else kb_main_seller()
    txt = {
        "clinic": "🏥 *Klinika paneli*\n\nEhtiyoj yozish va takliflarni jadvalda ko'rish mumkin!",
        "lab":    "🔬 *Zubo texnik paneli*\n\nEhtiyoj yozish va takliflarni jadvalda ko'rish mumkin!",
        "seller": "🛒 *Sotuvchi paneli*\n\nEhtiyojlar lentini ko'rib taklif yuboring!"
    }.get(role, "Xush kelibsiz!")
    await call.message.answer(txt, reply_markup=kb)
    await call.answer()

# ── PROFIL ─────────────────────────────────────────────────
@router.message(F.text == "⚙️ Profil")
async def show_profile(msg: Message):
    u = await get_user(msg.from_user.id)
    role_label = {"clinic":"🏥 Klinika","lab":"🔬 Zubo texnik","seller":"🛒 Sotuvchi"}.get(u["role"],"—")
    await msg.answer(
        f"⚙️ *Profil*\n\n"
        f"👤 {u['clinic_name'] or '—'}\n"
        f"📞 {u['phone'] or '—'}\n"
        f"📍 {u['region'] or '—'}\n"
        f"🏠 {u['address'] or '—'}\n"
        f"🔖 Rol: {role_label}\n"
        f"💰 Balans: {u['balance'] or 0:.1f} ball",
        reply_markup=ik(ib("✏️ Profilni yangilash","edit_profile"))
    )

@router.callback_query(F.data=="edit_profile")
async def edit_profile(call: CallbackQuery, state: FSMContext):
    await state.set_state(Reg.name)
    await call.message.answer("📝 Yangi ism/klinika nomingiz:", reply_markup=ReplyKeyboardRemove())
    await call.answer()

# ── EHTIYOJ YOZISH ─────────────────────────────────────────
@router.message(F.text == "➕ Ehtiyoj yozish")
async def need_menu(msg: Message):
    await msg.answer(
        "📝 *Ehtiyoj yozish usulini tanlang:*\n\n"
        "📦 *Ko'p ehtiyoj* — ro'yxatni bir yozing\n"
        "📋 *Tartibli* — savol-javob bilan",
        reply_markup=ik(
            ib("📦 Ko'p ehtiyoj (tezkor)","bulk_start"),
            ib("📋 Tartibli (savol-javob)","step_start")
        )
    )

# ── BULK EHTIYOJ ───────────────────────────────────────────
@router.callback_query(F.data=="bulk_start")
async def bulk_start(call: CallbackQuery, state: FSMContext):
    u = await get_user(call.from_user.id)
    if not u or not u["clinic_name"]:
        await call.message.answer("⚠️ Avval profilni to'ldiring.",
                                  reply_markup=ik(ib("✏️ Profilni to'ldirish","edit_profile")))
        await call.answer(); return
    await state.set_state(BulkAdd.items)
    await call.message.answer(
        "📦 *Ko'p ehtiyoj*\n\n"
        "Har bir mahsulotni yangi qatorda yozing:\n\n"
        "```\n5 dona Fuji IX\n3 dona Xarizma A2\n2 kg Endomotor igna\n1 dona Ultratone\n```\n\n"
        "_Format: miqdor + birlik + nom_\n"
        "_Birliklar: dona, kg, litr, gr, ml, box, quti_",
        reply_markup=ReplyKeyboardRemove()
    )
    await call.answer()

@router.message(BulkAdd.items)
async def bulk_items(msg: Message, state: FSMContext):
    parsed, errors = parse_bulk_text(msg.text)
    if not parsed:
        await msg.answer(
            "❌ Format xato!\n\n"
            "To'g'ri format:\n"
            "```\n5 dona Fuji IX\n3 dona Xarizma A2\n```"
        ); return
    await state.update_data(items=parsed)
    preview = "\n".join([f"• {p['qty']} {p['unit']} — *{p['name']}*" for p in parsed])
    err_txt = f"\n\n⚠️ _Qabul qilinmadi: {', '.join(errors)}_" if errors else ""
    await state.set_state(BulkAdd.deadline)
    await msg.answer(
        f"✅ *{len(parsed)} ta mahsulot:*\n\n{preview}{err_txt}\n\n⏱ Qachongacha kerak?",
        reply_markup=kb_deadline()
    )

@router.callback_query(F.data.startswith("dl_"), BulkAdd.deadline)
async def bulk_deadline(call: CallbackQuery, state: FSMContext):
    await state.update_data(dl=int(call.data[3:]))
    d = await state.get_data()
    await state.set_state(BulkAdd.confirm)
    preview = "\n".join([f"• {p['qty']} {p['unit']} — *{p['name']}*" for p in d["items"]])
    dl_map = {2:"2 soat",24:"24 soat",72:"3 kun",168:"1 hafta"}
    await call.message.answer(
        f"📋 *Tasdiqlang:*\n\n{preview}\n\n⏱ {dl_map.get(d['dl'],'?')} ichida",
        reply_markup=ik(ib("✅ Joylash","bulk_confirm"), ib("❌ Bekor","cancel"))
    )
    await call.answer()

@router.callback_query(F.data=="bulk_confirm")
async def bulk_confirm(call: CallbackQuery, state: FSMContext):
    d       = await state.get_data()
    items   = d["items"]
    dl      = d["dl"]
    owner   = await get_user(call.from_user.id)
    expires = (datetime.now()+timedelta(hours=dl)).isoformat()
    
    # Batch yaratish
    batch_id = await db_insert(
        "INSERT INTO batches(owner_id,deadline_hours,expires_at) VALUES(?,?,?)",
        (call.from_user.id, dl, expires)
    )
    # Har bir ehtiyoj
    room = await db_get("SELECT * FROM rooms WHERE owner_id=? AND status='active' LIMIT 1",
                        (call.from_user.id,))
    if not room:
        code = await get_next_room_code("standard")
        room_id = await db_insert("INSERT INTO rooms(room_code,room_type,owner_id,max_needs) VALUES(?,?,?,?)",
                                  (code, "standard", call.from_user.id, 25))
    else:
        room_id = room["id"]

    count = 0
    for item in items:
        nid = await db_insert(
            "INSERT INTO needs(batch_id,room_id,owner_id,product_name,quantity,unit,deadline_hours,expires_at) VALUES(?,?,?,?,?,?,?,?)",
            (batch_id, room_id, call.from_user.id, item["name"], item["qty"], item["unit"], dl, expires)
        )
        nd  = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
        mid = await post_to_channel(dict(nd), dict(owner))
        if mid:
            await db_run("UPDATE needs SET channel_message_id=? WHERE id=?", (mid, nid))
        count += 1
    
    await state.clear()
    chan = CHANNEL_ID.lstrip("@")
    await call.message.edit_text(
        f"✅ *{count} ta ehtiyoj joylashtirildi!*\n\n"
        f"📦 To'plam #{batch_id}\n\n"
        f"Sotuvchilar taklif yuboradi. Takliflar kelgach:\n"
        f"📊 *Jadval & Takliflar* → solishtiring → eng yaxshisini tanlang!"
    )
    await call.answer()

# ── TARTIBLI EHTIYOJ ───────────────────────────────────────
@router.callback_query(F.data=="step_start")
async def step_start(call: CallbackQuery, state: FSMContext):
    u = await get_user(call.from_user.id)
    if not u or not u["clinic_name"]:
        await call.message.answer("⚠️ Avval profilni to'ldiring.",
                                  reply_markup=ik(ib("✏️ Profilni to'ldirish","edit_profile")))
        await call.answer(); return
    await state.update_data(step_items=[])
    await state.set_state(StepAdd.product)
    await call.message.answer("🦷 *1-ehtiyoj*\n\nMahsulot nomi?",
                              reply_markup=ReplyKeyboardRemove())
    await call.answer()

@router.message(StepAdd.product)
async def step_product(msg: Message, state: FSMContext):
    await state.update_data(cur_product=msg.text)
    await state.set_state(StepAdd.qty_unit)
    await msg.answer(
        f"📦 *{msg.text}* — miqdori?\n\n"
        "_Masalan: `5 dona` yoki `2 kg`_",
        reply_markup=ik(ib("📌 1 dona","sq_1_dona"), ib("📌 2 dona","sq_2_dona"),
                        ib("📌 5 dona","sq_5_dona"), ib("📌 10 dona","sq_10_dona"))
    )

@router.callback_query(F.data.startswith("sq_"), StepAdd.qty_unit)
async def step_qty_btn(call: CallbackQuery, state: FSMContext):
    parts = call.data[3:].split("_")
    await _step_save_item(call.message, call.from_user.id, state, float(parts[0]), parts[1])
    await call.answer()

@router.message(StepAdd.qty_unit)
async def step_qty_text(msg: Message, state: FSMContext):
    parsed, _ = parse_bulk_text(f"{msg.text} placeholder")
    # faqat son + birlik
    parts = msg.text.strip().split()
    try:
        qty  = float(parts[0].replace(",","."))
        unit = parts[1].lower() if len(parts) > 1 else "dona"
        await _step_save_item(msg, msg.from_user.id, state, qty, unit)
    except:
        await msg.answer("❌ Masalan: `5 dona` yoki `2 kg`")

async def _step_save_item(msg, uid, state, qty, unit):
    d    = await state.get_data()
    cur  = d.get("cur_product","?")
    items= d.get("step_items",[])
    items.append({"qty": qty, "unit": unit, "name": cur})
    await state.update_data(step_items=items, cur_product=None)
    await state.set_state(StepAdd.more)
    preview = "\n".join([f"• {p['qty']} {p['unit']} — *{p['name']}*" for p in items])
    await msg.answer(
        f"✅ Qo'shildi!\n\n*Hozirgi ro'yxat:*\n{preview}\n\nYana qo'shamizmi?",
        reply_markup=kb_yes_no()
    )

@router.callback_query(F.data=="more_yes", StepAdd.more)
async def step_more_yes(call: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    n = len(d.get("step_items",[])) + 1
    await state.set_state(StepAdd.product)
    await call.message.answer(f"🦷 *{n}-ehtiyoj*\n\nMahsulot nomi?")
    await call.answer()

@router.callback_query(F.data=="more_no", StepAdd.more)
async def step_more_no(call: CallbackQuery, state: FSMContext):
    await state.set_state(StepAdd.deadline)
    await call.message.answer("⏱ Qachongacha kerak?", reply_markup=kb_deadline())
    await call.answer()

@router.callback_query(F.data.startswith("dl_"), StepAdd.deadline)
async def step_deadline(call: CallbackQuery, state: FSMContext):
    await state.update_data(dl=int(call.data[3:]))
    d = await state.get_data()
    await state.set_state(StepAdd.confirm)
    preview = "\n".join([f"• {p['qty']} {p['unit']} — *{p['name']}*" for p in d["step_items"]])
    dl_map = {2:"2 soat",24:"24 soat",72:"3 kun",168:"1 hafta"}
    await call.message.answer(
        f"📋 *Tasdiqlang:*\n\n{preview}\n\n⏱ {dl_map.get(d['dl'],'?')} ichida",
        reply_markup=ik(ib("✅ Joylash","step_confirm"), ib("❌ Bekor","cancel"))
    )
    await call.answer()

@router.callback_query(F.data=="step_confirm")
async def step_confirm(call: CallbackQuery, state: FSMContext):
    d       = await state.get_data()
    items   = d["step_items"]
    dl      = d["dl"]
    owner   = await get_user(call.from_user.id)
    expires = (datetime.now()+timedelta(hours=dl)).isoformat()
    batch_id= await db_insert(
        "INSERT INTO batches(owner_id,deadline_hours,expires_at) VALUES(?,?,?)",
        (call.from_user.id, dl, expires)
    )
    room = await db_get("SELECT * FROM rooms WHERE owner_id=? AND status='active' LIMIT 1",
                        (call.from_user.id,))
    room_id = room["id"] if room else await db_insert(
        "INSERT INTO rooms(room_code,room_type,owner_id,max_needs) VALUES(?,?,?,?)",
        (await get_next_room_code("standard"), "standard", call.from_user.id, 25)
    )
    for item in items:
        nid = await db_insert(
            "INSERT INTO needs(batch_id,room_id,owner_id,product_name,quantity,unit,deadline_hours,expires_at) VALUES(?,?,?,?,?,?,?,?)",
            (batch_id, room_id, call.from_user.id, item["name"], item["qty"], item["unit"], dl, expires)
        )
        nd  = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
        mid = await post_to_channel(dict(nd), dict(owner))
        if mid:
            await db_run("UPDATE needs SET channel_message_id=? WHERE id=?", (mid, nid))
    await state.clear()
    await call.message.edit_text(
        f"✅ *{len(items)} ta ehtiyoj joylashtirildi!*\n\n"
        f"📦 To'plam #{batch_id}\n\n"
        f"📊 *Jadval & Takliflar* tugmasida solishtiring!"
    )
    await call.answer()

# ── EHTIYOJLARIM ───────────────────────────────────────────
@router.message(F.text == "📋 Ehtiyojlarim")
async def my_needs(msg: Message):
    needs = await db_all(
        "SELECT n.*, (SELECT COUNT(*) FROM offers o WHERE o.need_id=n.id AND o.status='pending') as offer_cnt "
        "FROM needs n WHERE n.owner_id=? ORDER BY n.created_at DESC LIMIT 20",
        (msg.from_user.id,)
    )
    if not needs:
        await msg.answer("📭 Hali ehtiyoj yo'q.",
                         reply_markup=ik(ib("➕ Ehtiyoj yozish","need_menu_btn"))); return
    await msg.answer(f"📋 *Ehtiyojlarim:* {len(needs)} ta")
    for n in needs:
        st    = {"active":"🟢","paused":"⏸","done":"✅"}.get(n["status"],"📋")
        badge = f" │ 📩*{n['offer_cnt']}*" if n["offer_cnt"] else ""
        await msg.answer(
            f"{st} *{n['product_name']}* — {n['quantity']} {n['unit']}{badge}",
            reply_markup=ik(
                [ib1("♻️ Qayta post","rp_"+str(n["id"])), ib1("⏸","pause_"+str(n["id"])), ib1("✅","done_"+str(n["id"]))],
            )
        )

@router.callback_query(F.data=="need_menu_btn")
async def need_menu_btn(call: CallbackQuery):
    await call.answer()
    await need_menu(call.message)

@router.callback_query(F.data.startswith("rp_"))
async def repost_need(call: CallbackQuery):
    nid  = int(call.data[3:])
    nd   = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
    owner= await get_user(call.from_user.id)
    new_exp = (datetime.now()+timedelta(hours=nd["deadline_hours"])).isoformat()
    await db_run("UPDATE needs SET status='active',expires_at=? WHERE id=?", (new_exp, nid))
    mid = await post_to_channel(dict(nd), dict(owner))
    if mid:
        await db_run("UPDATE needs SET channel_message_id=? WHERE id=?", (mid, nid))
    chan = CHANNEL_ID.lstrip("@")
    link = f"[Kanalda](https://t.me/{chan}/{mid})" if mid else ""
    await call.message.answer(f"♻️ Qayta joylashtirildi! {link}")
    await call.answer("✅")

@router.callback_query(F.data.startswith("pause_"))
async def cb_pause(call: CallbackQuery):
    await db_run("UPDATE needs SET status='paused' WHERE id=?", (int(call.data[6:]),))
    await call.answer("⏸ Pauza")

@router.callback_query(F.data.startswith("done_"))
async def cb_done(call: CallbackQuery):
    await db_run("UPDATE needs SET status='done' WHERE id=?", (int(call.data[5:]),))
    await call.answer("✅ Yakunlandi")

@router.callback_query(F.data=="cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await call.message.delete()
    except: pass
    await call.answer("Bekor qilindi")

# ── JADVAL & TAKLIFLAR ─────────────────────────────────────
@router.message(F.text == "📊 Jadval & Takliflar")
async def jadval_menu(msg: Message):
    batches = await db_all(
        "SELECT b.*, (SELECT COUNT(*) FROM needs n WHERE n.batch_id=b.id) as need_cnt, "
        "(SELECT COUNT(DISTINCT o.seller_id) FROM offers o JOIN needs n ON o.need_id=n.id WHERE n.batch_id=b.id AND o.status='pending') as seller_cnt "
        "FROM batches b WHERE b.owner_id=? ORDER BY b.created_at DESC LIMIT 10",
        (msg.from_user.id,)
    )
    if not batches:
        await msg.answer("📭 Hali to'plam yo'q. Ehtiyoj yozing!",
                         reply_markup=ik(ib("➕ Ehtiyoj yozish","need_menu_btn"))); return

    await msg.answer("📊 *To'plamlaringiz:*")
    for b in batches:
        date  = b["created_at"][:10]
        st    = "🟢" if b["status"]=="active" else "✅"
        shops = b["seller_cnt"] or 0
        rows  = []
        if shops > 0:
            rows.append(ib(f"📊 Jadval ko'rish ({shops} do'kon)", f"tbl_{b['id']}"))
        rows.append(ib("📩 Takliflar",f"off_batch_{b['id']}"))
        await msg.answer(
            f"{st} *To'plam #{b['id']}* — {date}\n"
            f"📦 {b['need_cnt']} ta ehtiyoj | 🏪 {shops} ta taklif bergan",
            reply_markup=ik(*[r if isinstance(r, list) else [r] for r in rows])
        )

@router.callback_query(F.data.startswith("tbl_"))
async def show_table(call: CallbackQuery):
    batch_id = int(call.data[4:])
    await call.message.answer("⏳ Jadval tayyorlanmoqda...")
    
    result = await build_comparison_table(batch_id)
    if result is None or result[0] is None:
        await call.message.answer("📭 Hali taklif yo'q."); await call.answer(); return
    
    sellers, table, col_totals, col_missing = result

    # 1. Botda tekst jadval
    txt = format_table_text(sellers, table, col_totals, col_missing)
    
    # Qabul tugmalari — har seller uchun
    best_total = min((v for k,v in col_totals.items() if not col_missing[k]), default=None)
    rows = []
    for s in sellers:
        total = col_totals[s["id"]]
        miss  = col_missing[s["id"]]
        if not miss and best_total and total == best_total:
            label = f"✅ {s['name']} — {total:,.0f} so'm (eng arzon)"
        elif miss:
            label = f"⚠️ {s['name']} — to'liq emas"
        else:
            label = f"🏪 {s['name']} — {total:,.0f} so'm"
        rows.append(ib(label, f"acc_batch_{batch_id}_{s['id']}"))

    rows.append(ib("📥 Excel yuklab olish", f"excel_{batch_id}"))

    await call.message.answer(
        f"📊 *Narx jadvali — To'plam #{batch_id}*\n\n{txt}",
        reply_markup=ik(*rows)
    )
    await call.answer()

@router.callback_query(F.data.startswith("excel_"))
async def send_excel(call: CallbackQuery):
    batch_id = int(call.data[6:])
    await call.message.answer("⏳ Excel fayl tayyorlanmoqda...")
    result = await build_comparison_table(batch_id)
    if result is None or result[0] is None:
        await call.message.answer("📭 Ma'lumot yo'q."); await call.answer(); return
    sellers, table, col_totals, col_missing = result
    xlsx_bytes = build_excel(sellers, table, col_totals, col_missing)
    if xlsx_bytes:
        fname = f"xazdent_jadval_{batch_id}_{datetime.now().strftime('%d%m%Y')}.xlsx"
        await call.message.answer_document(
            BufferedInputFile(xlsx_bytes, filename=fname),
            caption=f"📊 *Narx jadvali* — To'plam #{batch_id}\n_{datetime.now().strftime('%d.%m.%Y')}_"
        )
    else:
        await call.message.answer("❌ Excel yaratishda xato. `openpyxl` o'rnatilmagan bo'lishi mumkin.")
    await call.answer()

@router.callback_query(F.data.startswith("acc_batch_"))
async def accept_batch_seller(call: CallbackQuery):
    """Bir butun do'kondan hammani qabul qilish"""
    parts     = call.data.split("_")
    batch_id  = int(parts[2])
    seller_id = int(parts[3])
    
    # Shu seller ning barcha takliflarini qabul qilish
    offers = await db_all(
        "SELECT o.* FROM offers o JOIN needs n ON o.need_id=n.id "
        "WHERE n.batch_id=? AND o.seller_id=? AND o.status='pending'",
        (batch_id, seller_id)
    )
    for o in offers:
        await db_run("UPDATE offers SET status='accepted' WHERE id=?", (o["id"],))
        await db_run("UPDATE needs SET status='paused' WHERE id=?",    (o["need_id"],))
    await db_run("UPDATE shops SET total_deals=total_deals+? WHERE owner_id=?",
                 (len(offers), seller_id))

    seller = await get_user(seller_id)
    shop   = await db_get("SELECT * FROM shops WHERE owner_id=?", (seller_id,))
    clinic = await get_user(call.from_user.id)
    name   = shop["shop_name"] if shop else (seller["full_name"] or "Sotuvchi")

    # Sotuvchiga klinika ma'lumotlari
    try:
        await bot.send_message(seller_id,
            f"🎉 *{len(offers)} ta taklifingiz qabul qilindi!*\n\n"
            f"🏥 {clinic['clinic_name'] or clinic['full_name']}\n"
            f"📞 {clinic['phone'] or '—'}\n"
            f"📍 {clinic['region'] or '—'}\n"
            f"🏠 {clinic['address'] or '—'}"
        )
        if clinic["latitude"]:
            await bot.send_location(seller_id, clinic["latitude"], clinic["longitude"])
    except Exception as e: log.error(e)

    await call.message.answer(
        f"✅ *{name}* dan *{len(offers)} ta mahsulot* qabul qilindi!\n\n"
        f"📞 {seller['phone'] or '—'}\n"
        f"Do'kon siz bilan bog'lanadi."
    )
    await call.answer("✅")

@router.callback_query(F.data.startswith("off_batch_"))
async def offers_by_batch(call: CallbackQuery):
    batch_id = int(call.data[10:])
    needs    = await db_all("SELECT * FROM needs WHERE batch_id=? ORDER BY id", (batch_id,))
    if not needs:
        await call.answer("Bo'sh to'plam", show_alert=True); return
    
    await call.message.answer(f"📩 *To'plam #{batch_id} takliflari:*")
    for nd in needs:
        offs = await db_all(
            "SELECT o.*,COALESCE(s.shop_name,u.full_name,u.clinic_name,'?') as shop_name,u.phone "
            "FROM offers o JOIN users u ON o.seller_id=u.id "
            "LEFT JOIN shops s ON s.owner_id=o.seller_id "
            "WHERE o.need_id=? AND o.status='pending' ORDER BY o.price",
            (nd["id"],)
        )
        if not offs:
            await call.message.answer(f"🦷 *{nd['product_name']}* — taklif yo'q"); continue
        
        txt  = f"🦷 *{nd['product_name']}* ({nd['quantity']} {nd['unit']}):\n"
        rows = []
        for i, o in enumerate(offs, 1):
            medal = ["🥇","🥈","🥉"][i-1] if i <= 3 else f"{i}."
            txt  += f"{medal} {o['shop_name']} — {o['price']:,.0f} so'm ({o['delivery_hours']}s)\n"
            rows.append([ib1(f"✅ {medal} {o['shop_name']} qabul", f"acc1_{o['id']}")])
        await call.message.answer(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()

@router.callback_query(F.data.startswith("acc1_"))
async def accept_one_offer(call: CallbackQuery):
    oid = int(call.data[5:])
    o   = await db_get(
        "SELECT o.*,u.full_name,u.phone,COALESCE(s.shop_name,u.clinic_name,u.full_name,'Sotuvchi') as shop_name "
        "FROM offers o JOIN users u ON o.seller_id=u.id "
        "LEFT JOIN shops s ON s.owner_id=o.seller_id WHERE o.id=?", (oid,)
    )
    if not o: await call.answer("Topilmadi", show_alert=True); return
    await db_run("UPDATE offers SET status='accepted' WHERE id=?", (oid,))
    await db_run("UPDATE needs SET status='paused' WHERE id=?", (o["need_id"],))
    await db_run("UPDATE shops SET total_deals=total_deals+1 WHERE owner_id=?", (o["seller_id"],))
    clinic = await get_user(call.from_user.id)
    try:
        await bot.send_message(o["seller_id"],
            f"🎉 *Taklifingiz qabul qilindi!*\n\n"
            f"🏥 {clinic['clinic_name'] or clinic['full_name']}\n"
            f"📞 {clinic['phone'] or '—'}\n"
            f"📍 {clinic['region'] or '—'}\n"
            f"🏠 {clinic['address'] or '—'}"
        )
        if clinic["latitude"]:
            await bot.send_location(o["seller_id"], clinic["latitude"], clinic["longitude"])
    except Exception as e: log.error(e)
    await call.message.answer(f"✅ *{o['shop_name']}* qabul qilindi!\n📞 {o['phone'] or '—'}")
    await call.answer("✅")

# ── BALANS ─────────────────────────────────────────────────
@router.message(F.text == "💰 Hisob")
async def show_balance(msg: Message):
    u          = await get_user(msg.from_user.id)
    balls      = u["balance"] or 0
    elon_price = float(await get_setting("elon_price") or 0)
    possible   = int(balls / elon_price) if elon_price > 0 else "∞"
    await msg.answer(
        f"💰 *Hisobingiz*\n\n"
        f"⚡️ Ball: *{balls:.1f}*\n"
        f"📋 Joylashtira olasiz: *{possible} ta e'lon*",
        reply_markup=ik(ib("➕ Hisob to'ldirish","topup"),
                        ib("📊 Statistika","stat_menu"))
    )

@router.callback_query(F.data=="topup")
async def topup_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(Topup.amount)
    await call.message.answer(
        f"💳 *Hisob to'ldirish*\n\n⚡️ 1 ball = 1 000 so'm\n\nQancha so'm?"
    )
    await call.answer()

@router.message(Topup.amount)
async def topup_amount(msg: Message, state: FSMContext):
    try:
        amount = float(msg.text.replace(" ","").replace(",",""))
        balls  = amount / float(await get_setting("ball_price") or 1000)
        await state.update_data(amount=amount, balls=balls)
        await state.set_state(Topup.receipt)
        await msg.answer(
            f"✅ *{amount:,.0f} so'm → {balls:.1f} ball*\n\n"
            f"💳 Kartaga o'tkazing:\n\n`{CARD_NUM}`\n_Komilova M_\n\n"
            f"📸 Screenshotni yuboring:"
        )
    except: await msg.answer("❌ Faqat raqam!")

@router.message(Topup.receipt, F.photo)
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
                caption=f"💳 *Chek #{tid}*\n👤 {name}\n💰 {d['amount']:,.0f} so'm → {d['balls']:.1f} ball",
                reply_markup=ik(
                    ib(f"✅ Tasdiqlash", f"adm_ok_{tid}_{msg.from_user.id}_{d['balls']}"),
                    ib(f"❌ Rad",         f"adm_rej_{tid}_{msg.from_user.id}")
                )
            )
        except: pass
    await state.clear()
    await msg.answer("✅ Chek yuborildi! Admin 15-30 daqiqada tasdiqlaydi.")

@router.callback_query(F.data.startswith("adm_ok_"))
async def adm_ok(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    p = call.data.split("_")
    tid, uid, balls = p[2], p[3], p[4]
    await db_run("UPDATE transactions SET status='confirmed',confirmed_by=? WHERE id=?",
                 (call.from_user.id, int(tid)))
    await add_balance(int(uid), float(balls))
    try: await bot.send_message(int(uid), f"🎉 *+{float(balls):.1f} ball qo'shildi!*")
    except: pass
    await call.message.edit_caption(call.message.caption+"\n✅ TASDIQLANDI", reply_markup=None)
    await call.answer("✅")

@router.callback_query(F.data.startswith("adm_rej_"))
async def adm_rej(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    p = call.data.split("_")
    await db_run("UPDATE transactions SET status='rejected' WHERE id=?", (int(p[2]),))
    try: await bot.send_message(int(p[3]), "❌ Chekingiz rad etildi.")
    except: pass
    await call.message.edit_caption(call.message.caption+"\n❌ RAD ETILDI", reply_markup=None)
    await call.answer("❌")

# ── STATISTIKA ─────────────────────────────────────────────
@router.callback_query(F.data=="stat_menu")
async def stat_menu(call: CallbackQuery):
    await call.message.answer("📊 *Davr:*",
        reply_markup=ik(ib("📅 Bu oy","stat_month"),
                        ib("📆 Bu yil","stat_year"),
                        ib("🗓 Hammasi","stat_all")))
    await call.answer()

@router.callback_query(F.data.startswith("stat_"))
async def show_stats(call: CallbackQuery):
    uid    = call.from_user.id
    period = call.data[5:]
    now    = datetime.now()
    u      = await get_user(uid)
    if period == "month":
        df    = f"AND strftime('%Y-%m',created_at)='{now.strftime('%Y-%m')}'"
        label = f"Bu oy ({now.strftime('%B %Y')})"
    elif period == "year":
        df    = f"AND strftime('%Y',created_at)='{now.strftime('%Y')}'"
        label = f"Bu yil {now.year}"
    else:
        df, label = "", "Butun vaqt"

    if u["role"] in ("clinic","lab"):
        tn = (await db_get(f"SELECT COUNT(*) c FROM needs WHERE owner_id=? {df}",(uid,)))["c"]
        dn = (await db_get(f"SELECT COUNT(*) c FROM needs WHERE owner_id=? AND status='done' {df}",(uid,)))["c"]
        ta = (await db_get(
            f"SELECT COUNT(*) c FROM offers o JOIN needs n ON o.need_id=n.id WHERE n.owner_id=? AND o.status='accepted' {df.replace('created_at','n.created_at')}",
            (uid,)
        ))["c"]
        spent_r = await db_get(
            f"SELECT COALESCE(SUM(o.price*n.quantity),0) s FROM offers o JOIN needs n ON o.need_id=n.id "
            f"WHERE n.owner_id=? AND o.status='accepted' {df.replace('created_at','o.created_at')}", (uid,)
        )
        spent = spent_r["s"] if spent_r else 0
        cats  = await db_all(
            f"SELECT o.product_name, COUNT(*) cnt, SUM(o.price) tot FROM offers o "
            f"JOIN needs n ON o.need_id=n.id WHERE n.owner_id=? AND o.status='accepted' "
            f"{df.replace('created_at','o.created_at')} GROUP BY o.product_name ORDER BY tot DESC LIMIT 5", (uid,)
        )
        cat_txt = ""
        if cats:
            cat_txt = "\n\n💡 *Eng ko'p xaridlar:*\n" + "\n".join(
                [f"• {c['product_name']}: {c['tot']:,.0f} so'm ({c['cnt']}x)" for c in cats]
            )
        await call.message.answer(
            f"📊 *{label}*\n\n"
            f"📋 E'lonlar: *{tn}* | ✅ Yakunlangan: *{dn}*\n"
            f"🤝 Qabul qilingan: *{ta}*\n"
            f"💰 Taxminiy xarajat: *{spent:,.0f} so'm*{cat_txt}"
        )
    else:
        to = (await db_get(f"SELECT COUNT(*) c FROM offers WHERE seller_id=? {df}",(uid,)))["c"]
        ao = (await db_get(f"SELECT COUNT(*) c FROM offers WHERE seller_id=? AND status='accepted' {df}",(uid,)))["c"]
        ro = (await db_get(f"SELECT COUNT(*) c FROM offers WHERE seller_id=? AND status='rejected' {df}",(uid,)))["c"]
        sh = await db_get("SELECT total_deals FROM shops WHERE owner_id=?", (uid,))
        await call.message.answer(
            f"📊 *{label}*\n\n"
            f"📤 Takliflar: *{to}* | ✅ Qabul: *{ao}* | ❌ Rad: *{ro}*\n"
            f"🤝 Jami xaridlar: *{sh['total_deals'] if sh else 0}*"
        )
    await call.answer()

# ── SOTUVCHI ───────────────────────────────────────────────
@router.message(F.text == "🔔 Ehtiyojlar lenti")
async def seller_feed(msg: Message):
    needs = await db_all(
        "SELECT n.*,u.region,u.clinic_name FROM needs n JOIN users u ON n.owner_id=u.id "
        "WHERE n.status='active' ORDER BY n.created_at DESC LIMIT 20"
    )
    if not needs: await msg.answer("📭 Aktiv ehtiyoj yo'q."); return
    await msg.answer(f"🔔 *Aktiv ehtiyojlar:* {len(needs)} ta")
    for n in needs:
        await msg.answer(
            f"🦷 *{n['product_name']}*\n📦 {n['quantity']} {n['unit']}\n"
            f"⏱ {n['deadline_hours']} soat\n📍 {n['region'] or ''}",
            reply_markup=ik(ib("📤 Taklif yuborish", f"make_offer_{n['id']}_{n['unit']}"))
        )

@router.message(F.text == "📤 Takliflarim")
async def my_offers_seller(msg: Message):
    offs = await db_all(
        "SELECT o.*,n.product_name as np FROM offers o JOIN needs n ON o.need_id=n.id "
        "WHERE o.seller_id=? ORDER BY o.created_at DESC LIMIT 20", (msg.from_user.id,)
    )
    if not offs: await msg.answer("📭 Hali taklif yo'q."); return
    await msg.answer(f"📤 *Takliflarim:* {len(offs)} ta")
    for o in offs:
        st = {"pending":"⏳","accepted":"✅","rejected":"❌"}.get(o["status"],"📤")
        await msg.answer(f"{st} *{o['np']}* — {o['price']:,.0f} so'm, {o['delivery_hours']}s")

@router.callback_query(F.data.startswith("make_offer_"))
async def make_offer_start(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    nid, unit = int(parts[2]), parts[3]
    exists = await db_get("SELECT id FROM offers WHERE need_id=? AND seller_id=?",
                          (nid, call.from_user.id))
    if exists: await call.answer("⚠️ Bu ehtiyojga taklif yubordingiz!", show_alert=True); return
    nd = await db_get("SELECT * FROM needs WHERE id=?", (nid,))
    await state.update_data(need_id=nid, need_unit=unit, need_name=nd["product_name"],
                            batch_id=nd["batch_id"])
    await state.set_state(OfferState.price)
    await call.message.answer(
        f"💰 *{nd['product_name']}* uchun narx?\n_(1 {unit} uchun, so'mda)_"
    )
    await call.answer()

@router.message(OfferState.price)
async def offer_price(msg: Message, state: FSMContext):
    try:
        price = float(msg.text.replace(" ","").replace(",",""))
        await state.update_data(price=price)
        await state.set_state(OfferState.delivery)
        await msg.answer("🚚 Yetkazib berish muddati:",
                         reply_markup=ik(ib("⚡️ 2 soat","del_2"), ib("🕐 24 soat","del_24"),
                                         ib("📅 2 kun","del_48"), ib("🗓 1 hafta","del_168")))
    except: await msg.answer("❌ Faqat raqam!")

@router.callback_query(F.data.startswith("del_"), OfferState.delivery)
async def offer_delivery(call: CallbackQuery, state: FSMContext):
    hours = int(call.data[4:])
    d     = await state.get_data()
    u     = await get_user(call.from_user.id)
    await db_insert(
        "INSERT INTO offers(need_id,batch_id,seller_id,product_name,price,unit,delivery_hours) VALUES(?,?,?,?,?,?,?)",
        (d["need_id"], d.get("batch_id"), call.from_user.id, d["need_name"], d["price"], d["need_unit"], hours)
    )
    # Klinikaga xabar
    nd = await db_get("SELECT n.*,u2.id cid FROM needs n JOIN users u2 ON n.owner_id=u2.id WHERE n.id=?",
                      (d["need_id"],))
    shop = await db_get("SELECT shop_name FROM shops WHERE owner_id=?", (call.from_user.id,))
    sname= shop["shop_name"] if shop else (u["clinic_name"] or u["full_name"] or "Sotuvchi")
    try:
        await bot.send_message(nd["cid"],
            f"📩 *Yangi taklif!*\n\n"
            f"🦷 {d['need_name']}\n💰 {d['price']:,.0f} so'm/{d['need_unit']}\n"
            f"🚚 {hours} soat | 🏪 {sname}",
            reply_markup=ik(ib("📊 Jadval ko'rish", f"tbl_{d.get('batch_id','0')}"))
        )
    except Exception as e: log.error(e)
    await state.clear()
    await call.message.answer("✅ Taklif yuborildi!")
    await call.answer("✅")

# ── DO'KON ─────────────────────────────────────────────────
@router.message(F.text == "🏪 Do'konim")
async def my_shop(msg: Message):
    shop = await db_get("SELECT * FROM shops WHERE owner_id=? AND status='active'", (msg.from_user.id,))
    if not shop:
        await msg.answer("🏪 Do'koningiz yo'q.",
                         reply_markup=ik(ib("➕ Do'kon ochish","open_shop"))); return
    prods = await db_all("SELECT * FROM products WHERE shop_id=? AND is_active=1", (shop["id"],))
    ptxt  = "\n" + "\n".join(f"• {p['name']} — {p['price']:,.0f}/{p['unit']}" for p in prods) if prods else "\n_Mahsulot yo'q_"
    await msg.answer(
        f"🏪 *{shop['shop_name']}*\n📂 {shop['category']}\n"
        f"🤝 Xaridlar: {shop['total_deals'] or 0}\n\n📦*Mahsulotlar:*{ptxt}",
        reply_markup=ik(ib("➕ Mahsulot qo'shish",f"ap_{shop['id']}"),
                        ib("🗑 O'chirish",          f"dp_{shop['id']}"))
    )

@router.callback_query(F.data=="open_shop")
async def open_shop(call: CallbackQuery, state: FSMContext):
    await state.set_state(ShopReg.cat)
    await call.message.answer("📂 Kategoriya:", reply_markup=kb_shop_cats())
    await call.answer()

@router.callback_query(F.data.startswith("sc_"), ShopReg.cat)
async def shop_cat(call: CallbackQuery, state: FSMContext):
    await state.update_data(cat=call.data)
    await state.set_state(ShopReg.name)
    await call.message.answer("🏪 Do'kon nomi:")
    await call.answer()

@router.message(ShopReg.name)
async def shop_name(msg: Message, state: FSMContext):
    d = await state.get_data()
    u = await get_user(msg.from_user.id)
    await db_insert("INSERT INTO shops(owner_id,shop_name,category,phone,region) VALUES(?,?,?,?,?)",
                    (msg.from_user.id, msg.text, d["cat"], u["phone"], u["region"]))
    await state.clear()
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid,
                f"🏪 *Yangi do'kon!*\n{msg.text}\n{u['clinic_name']}\n{u['phone']}",
                reply_markup=ik(ib("✅ Tasdiqlash",f"shopok_{msg.from_user.id}"),
                                ib("❌ Rad",       f"shoprej_{msg.from_user.id}")))
        except: pass
    await msg.answer("⏳ Admin tasdiqlashini kutmoqda.")

@router.callback_query(F.data.startswith("shopok_"))
async def shop_ok(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    uid = int(call.data[7:])
    await db_run("UPDATE shops SET status='active' WHERE owner_id=?", (uid,))
    try: await bot.send_message(uid, "✅ Do'koningiz faollashdi!")
    except: pass
    await call.message.edit_text(call.message.text+"\n✅", reply_markup=None)
    await call.answer()

@router.callback_query(F.data.startswith("shoprej_"))
async def shop_rej(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    uid = int(call.data[8:])
    await db_run("UPDATE shops SET status='rejected' WHERE owner_id=?", (uid,))
    await call.message.edit_text(call.message.text+"\n❌", reply_markup=None)
    await call.answer()

@router.callback_query(F.data.startswith("ap_"))
async def add_prod_start(call: CallbackQuery, state: FSMContext):
    await state.update_data(shop_id=int(call.data[3:]))
    await state.set_state(AddProd.name)
    await call.message.answer("📦 Mahsulot nomi:")
    await call.answer()

@router.message(AddProd.name)
async def ap_name(msg: Message, state: FSMContext):
    await state.update_data(pname=msg.text)
    await state.set_state(AddProd.price)
    await msg.answer("💰 Narxi (so'mda):")

@router.message(AddProd.price)
async def ap_price(msg: Message, state: FSMContext):
    try:
        await state.update_data(pprice=float(msg.text.replace(" ","").replace(",","")))
        await state.set_state(AddProd.unit)
        await msg.answer("⚖️ Birlik:", reply_markup=ik(
            ib("📌 dona","pu_dona"), ib("⚖️ kg","pu_kg"), ib("💧 litr","pu_litr")
        ))
    except: await msg.answer("❌ Faqat raqam!")

@router.callback_query(F.data.startswith("pu_"), AddProd.unit)
async def ap_unit(call: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    await db_insert("INSERT INTO products(shop_id,name,price,unit) VALUES(?,?,?,?)",
                    (d["shop_id"], d["pname"], d["pprice"], call.data[3:]))
    await state.clear()
    await call.message.answer(f"✅ *{d['pname']}* qo'shildi!")
    await call.answer()

@router.callback_query(F.data.startswith("dp_"))
async def del_prod(call: CallbackQuery):
    prods = await db_all("SELECT * FROM products WHERE shop_id=? AND is_active=1", (int(call.data[3:]),))
    if not prods: await call.answer("Mahsulot yo'q", show_alert=True); return
    rows  = [[ib1(f"🗑 {p['name']}", f"delp_{p['id']}")] for p in prods]
    await call.message.answer("O'chirish:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()

@router.callback_query(F.data.startswith("delp_"))
async def del_prod_one(call: CallbackQuery):
    pid = int(call.data[5:])
    p   = await db_get("SELECT name FROM products WHERE id=?", (pid,))
    await db_run("UPDATE products SET is_active=0 WHERE id=?", (pid,))
    await call.message.edit_text(f"🗑 *{p['name']}* o'chirildi.", reply_markup=None)
    await call.answer()

# ── ADMIN ──────────────────────────────────────────────────
@router.message(Command("admin"))
async def admin_cmd(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    tu = (await db_get("SELECT COUNT(*) c FROM users", ()))["c"]
    cl = (await db_get("SELECT COUNT(*) c FROM users WHERE role IN ('clinic','lab')", ()))["c"]
    sl = (await db_get("SELECT COUNT(*) c FROM users WHERE role='seller'", ()))["c"]
    an = (await db_get("SELECT COUNT(*) c FROM needs WHERE status='active'", ()))["c"]
    pt = (await db_get("SELECT COUNT(*) c FROM transactions WHERE status='pending'", ()))["c"]
    ps = (await db_get("SELECT COUNT(*) c FROM shops WHERE status='pending'", ()))["c"]
    rv = (await db_get("SELECT COALESCE(SUM(amount),0) s FROM transactions WHERE status='confirmed'",()))["s"]
    await msg.answer(
        f"👨‍💼 *XAZDENT Admin*\n_{datetime.now().strftime('%d.%m.%Y %H:%M')}_\n\n"
        f"👥 Foydalanuvchilar: *{tu}*\n  🏥 Klinika/Lab: {cl} | 🛒 Sotuvchi: {sl}\n\n"
        f"📋 Aktiv ehtiyojlar: *{an}*\n\n"
        f"⏳ Kutmoqda: 💳 {pt} chek | 🏪 {ps} do'kon\n\n"
        f"💰 Jami daromad: *{rv:,.0f} so'm*",
        reply_markup=ik(ib("💳 Cheklar","adm_tx"), ib("🏪 Do'konlar","adm_shops"),
                        ib("⚙️ Sozlamalar","adm_set"))
    )

@router.callback_query(F.data=="adm_tx")
async def adm_tx(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    txs = await db_all(
        "SELECT t.*,COALESCE(u.clinic_name,u.full_name) nm FROM transactions t "
        "JOIN users u ON t.user_id=u.id WHERE t.status='pending' LIMIT 10"
    )
    if not txs: await call.message.answer("✅ Kutayotgan yo'q."); await call.answer(); return
    for tx in txs:
        if tx["receipt_file_id"]:
            await call.message.answer_photo(tx["receipt_file_id"],
                caption=f"💳 #{tx['id']} | {tx['nm']}\n{tx['amount']:,.0f} so'm → {tx['balls']:.1f} ball",
                reply_markup=ik(ib(f"✅ Tasdiqlash",f"adm_ok_{tx['id']}_{tx['user_id']}_{tx['balls']}"),
                                ib(f"❌ Rad",        f"adm_rej_{tx['id']}_{tx['user_id']}")))
    await call.answer()

@router.callback_query(F.data=="adm_shops")
async def adm_shops(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    shops = await db_all("SELECT s.*,u.phone FROM shops s JOIN users u ON s.owner_id=u.id WHERE s.status='pending'")
    if not shops: await call.message.answer("✅ Kutayotgan yo'q."); await call.answer(); return
    for s in shops:
        await call.message.answer(f"🏪 *{s['shop_name']}* | {s['phone']}",
            reply_markup=ik(ib("✅",f"shopok_{s['owner_id']}"), ib("❌",f"shoprej_{s['owner_id']}")))
    await call.answer()

@router.callback_query(F.data=="adm_set")
async def adm_set(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    bp = await get_setting("ball_price") or "1000"
    ep = await get_setting("elon_price") or "0"
    await call.message.answer(
        f"⚙️ *Sozlamalar*\n\n💰 1 ball = {bp} so'm\n📋 1 e'lon = {ep} ball\n\n"
        f"`/setball 2000` | `/setelon 0.5`"
    )
    await call.answer()

@router.message(Command("setball"))
async def set_ball(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    try:
        v = msg.text.split()[1]; await update_setting("ball_price", v)
        await msg.answer(f"✅ 1 ball = *{v} so'm*")
    except: await msg.answer("❌ /setball 2000")

@router.message(Command("setelon"))
async def set_elon(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    try:
        v = msg.text.split()[1]; await update_setting("elon_price", v)
        await msg.answer(f"✅ 1 e'lon = *{v} ball*")
    except: await msg.answer("❌ /setelon 0.5")

# ── MAIN ──────────────────────────────────────────────────
async def main():
    await init_db()
    dp.include_router(router)
    log.info("🦷 XAZDENT Bot ishga tushdi!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
