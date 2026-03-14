import asyncio
import os
import logging
from datetime import datetime

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage

from database import init_db, get_user, db_get, db_all, db_run, get_setting, update_setting, add_balance

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_IDS       = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

bot    = Bot(token=ADMIN_BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp     = Dispatcher(storage=MemoryStorage())
router = Router()

def ik(*rows):
    return InlineKeyboardMarkup(inline_keyboard=list(rows))

def ib(text, data):
    return InlineKeyboardButton(text=text, callback_data=data)

def is_admin(uid):
    return uid in ADMIN_IDS

# ── /start ────────────────────────────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(msg: Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("⛔️ Ruxsat yo'q.")
        return
    await show_dashboard(msg)

async def show_dashboard(msg: Message):
    now       = datetime.now().strftime("%d.%m.%Y %H:%M")
    total_u   = (await db_get("SELECT COUNT(*) as c FROM users", ()))["c"]
    clinics   = (await db_get("SELECT COUNT(*) as c FROM users WHERE role='clinic'", ()))["c"]
    sellers   = (await db_get("SELECT COUNT(*) as c FROM users WHERE role='seller'", ()))["c"]
    active_n  = (await db_get("SELECT COUNT(*) as c FROM needs WHERE status='active'", ()))["c"]
    total_n   = (await db_get("SELECT COUNT(*) as c FROM needs", ()))["c"]
    pending_t = (await db_get("SELECT COUNT(*) as c FROM transactions WHERE status='pending'", ()))["c"]
    pending_s = (await db_get("SELECT COUNT(*) as c FROM shops WHERE status='pending'", ()))["c"]
    acc_off   = (await db_get("SELECT COUNT(*) as c FROM offers WHERE status='accepted'", ()))["c"]
    rev       = await db_get("SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE status='confirmed'", ())
    revenue   = rev["s"] if rev else 0

    await msg.answer(
        f"👨‍💼 *XAZDENT Admin*\n_{now}_\n\n"
        f"👥 Foydalanuvchilar: *{total_u}*\n"
        f"  ├ 🏥 Klinikalar: {clinics}\n"
        f"  └ 🛒 Sotuvchilar: {sellers}\n\n"
        f"📋 E'lonlar: *{total_n}* (🟢 {active_n} aktiv)\n"
        f"✅ Qabul qilingan takliflar: *{acc_off}*\n\n"
        f"⏳ Kutmoqda: 💳 {pending_t} chek | 🏪 {pending_s} do'kon\n\n"
        f"💰 Jami daromad: *{revenue:,.0f} so'm*",
        reply_markup=ik(
            [ib("💳 Kutayotgan cheklar", "pending_tx")],
            [ib("🏪 Kutayotgan do'konlar", "pending_shops")],
            [ib("👥 Foydalanuvchilar", "users_list")],
            [ib("⚙️ Sozlamalar", "settings")],
            [ib("📊 Batafsil statistika", "full_stats")],
        ),
    )

@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await show_dashboard(msg)

# ── KUTAYOTGAN CHEKLAR ─────────────────────────────────────────────────────────
@router.callback_query(F.data == "pending_tx")
async def pending_tx(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    txs = await db_all(
        "SELECT t.*, u.full_name, u.clinic_name FROM transactions t "
        "JOIN users u ON t.user_id=u.id WHERE t.status='pending' ORDER BY t.created_at DESC LIMIT 10"
    )
    if not txs:
        await call.message.answer("✅ Kutayotgan cheklar yo'q.")
        await call.answer()
        return
    for tx in txs:
        name = tx["clinic_name"] or tx["full_name"] or str(tx["user_id"])
        if tx["receipt_file_id"]:
            try:
                await call.message.answer_photo(
                    tx["receipt_file_id"],
                    caption=(
                        f"💳 *Chek #{tx['id']}*\n\n"
                        f"👤 {name}\n"
                        f"💰 {tx['amount']:,.0f} so'm → {tx['balls']:.1f} ball\n"
                        f"🕐 {tx['created_at'][:16]}"
                    ),
                    reply_markup=ik(
                        [ib("✅ Tasdiqlash", f"adm_ok_{tx['id']}_{tx['user_id']}_{tx['balls']}"),
                         ib("❌ Rad etish", f"adm_rej_{tx['id']}_{tx['user_id']}")],
                    ),
                )
            except Exception:
                pass
    await call.answer()

@router.callback_query(F.data.startswith("adm_ok_"))
async def adm_ok(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    parts = call.data.split("_")
    tid, uid, balls = int(parts[2]), int(parts[3]), float(parts[4])
    await db_run("UPDATE transactions SET status='confirmed',confirmed_by=? WHERE id=?", (call.from_user.id, tid))
    await add_balance(uid, balls)
    # Asosiy botdan xabar yuborib bo'lmaydi (token boshqa) — faqat log
    log.info(f"✅ Tasdiqlandi: tx={tid} uid={uid} balls={balls}")
    await call.message.edit_caption(call.message.caption + "\n\n✅ TASDIQLANDI", reply_markup=None)
    await call.answer("✅ Tasdiqlandi")

@router.callback_query(F.data.startswith("adm_rej_"))
async def adm_rej(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    parts = call.data.split("_")
    tid = int(parts[2])
    await db_run("UPDATE transactions SET status='rejected' WHERE id=?", (tid,))
    await call.message.edit_caption(call.message.caption + "\n\n❌ RAD ETILDI", reply_markup=None)
    await call.answer("❌ Rad etildi")

# ── KUTAYOTGAN DO'KONLAR ───────────────────────────────────────────────────────
@router.callback_query(F.data == "pending_shops")
async def pending_shops(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    shops = await db_all(
        "SELECT s.*, u.full_name, u.phone FROM shops s "
        "JOIN users u ON s.owner_id=u.id WHERE s.status='pending'"
    )
    if not shops:
        await call.message.answer("✅ Kutayotgan do'konlar yo'q.")
        await call.answer()
        return
    for s in shops:
        await call.message.answer(
            f"🏪 *{s['shop_name']}*\n"
            f"📂 {s['category']}\n"
            f"👤 {s['full_name']}\n"
            f"📞 {s['phone']}",
            reply_markup=ik(
                [ib("✅ Tasdiqlash", f"shopok_{s['owner_id']}"),
                 ib("❌ Rad", f"shoprej_{s['owner_id']}")],
            ),
        )
    await call.answer()

@router.callback_query(F.data.startswith("shopok_"))
async def shop_ok(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    uid = int(call.data[7:])
    await db_run("UPDATE shops SET status='active' WHERE owner_id=?", (uid,))
    await call.message.edit_text(call.message.text + "\n\n✅ TASDIQLANDI", reply_markup=None)
    await call.answer("✅")

@router.callback_query(F.data.startswith("shoprej_"))
async def shop_rej(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    uid = int(call.data[8:])
    await db_run("UPDATE shops SET status='rejected' WHERE owner_id=?", (uid,))
    await call.message.edit_text(call.message.text + "\n\n❌ RAD ETILDI", reply_markup=None)
    await call.answer("❌")

# ── FOYDALANUVCHILAR ──────────────────────────────────────────────────────────
@router.callback_query(F.data == "users_list")
async def users_list(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    users = await db_all(
        "SELECT * FROM users ORDER BY created_at DESC LIMIT 20"
    )
    txt = f"👥 *So'nggi 20 foydalanuvchi:*\n\n"
    for u in users:
        role  = {"clinic": "🏥", "seller": "🛒"}.get(u["role"], "👤")
        name  = u["clinic_name"] or u["full_name"] or "—"
        phone = u["phone"] or "—"
        txt  += f"{role} {name} | {phone}\n"
    await call.message.answer(txt)
    await call.answer()

# ── SOZLAMALAR ─────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "settings")
async def settings_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    ball_price = await get_setting("ball_price") or "1000"
    card       = await get_setting("card_number") or "—"
    await call.message.answer(
        f"⚙️ *Sozlamalar*\n\n"
        f"💰 1 ball = *{ball_price} so'm*\n"
        f"💳 Karta: `{card}`\n\n"
        f"Buyruqlar:\n"
        f"`/setball 2000` — ball narxini o'zgartirish\n"
        f"`/setcard 9860...` — karta raqamini o'zgartirish"
    )
    await call.answer()

@router.message(Command("setball"))
async def set_ball(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    try:
        val = msg.text.split()[1]
        await update_setting("ball_price", val)
        await msg.answer(f"✅ 1 ball = *{val} so'm*")
    except Exception:
        await msg.answer("❌ Format: `/setball 2000`")

@router.message(Command("setcard"))
async def set_card(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    try:
        val = msg.text.split()[1]
        await update_setting("card_number", val)
        await msg.answer(f"✅ Karta: `{val}`")
    except Exception:
        await msg.answer("❌ Format: `/setcard 9860020138100068`")

# ── BATAFSIL STATISTIKA ───────────────────────────────────────────────────────
@router.callback_query(F.data == "full_stats")
async def full_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    now   = datetime.now()
    month = now.strftime("%Y-%m")

    month_u = (await db_get(
        "SELECT COUNT(*) as c FROM users WHERE strftime('%Y-%m',created_at)=?", (month,)
    ))["c"]
    month_n = (await db_get(
        "SELECT COUNT(*) as c FROM needs WHERE strftime('%Y-%m',created_at)=?", (month,)
    ))["c"]
    month_o = (await db_get(
        "SELECT COUNT(*) as c FROM offers WHERE status='accepted' AND strftime('%Y-%m',created_at)=?", (month,)
    ))["c"]
    month_r = await db_get(
        "SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE status='confirmed' AND strftime('%Y-%m',created_at)=?",
        (month,)
    )

    top_needs = await db_all(
        "SELECT product_name, COUNT(*) as cnt FROM needs "
        "GROUP BY product_name ORDER BY cnt DESC LIMIT 5"
    )
    top_txt = "\n".join([f"  {i+1}. {n['product_name']} ({n['cnt']} ta)" for i, n in enumerate(top_needs)])

    await call.message.answer(
        f"📊 *Bu oy ({now.strftime('%B %Y')}):*\n\n"
        f"👥 Yangi: *{month_u}* foydalanuvchi\n"
        f"📋 E'lonlar: *{month_n}*\n"
        f"✅ Bitimlar: *{month_o}*\n"
        f"💰 Daromad: *{(month_r['s'] if month_r else 0):,.0f} so'm*\n\n"
        f"🔥 *Top 5 so'ralgan mahsulot:*\n{top_txt}"
    )
    await call.answer()

# ── BROADCAST ─────────────────────────────────────────────────────────────────
@router.message(Command("broadcast"))
async def broadcast(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    text = msg.text.split(maxsplit=1)
    if len(text) < 2:
        await msg.answer("❌ Format: `/broadcast Xabar matni`")
        return
    message = text[1]
    users   = await db_all("SELECT id FROM users WHERE is_blocked=0")
    sent, fail = 0, 0
    for u in users:
        try:
            await bot.send_message(u["id"], message)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail += 1
    await msg.answer(f"📢 Yuborildi: *{sent}* | Xato: *{fail}*")

# ── MAIN ─────────────────────────────────────────────────────────────────────
async def main():
    await init_db()
    dp.include_router(router)
    log.info("🔑 XAZDENT Admin Bot ishga tushdi!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
