import os
import random
import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL", "")
_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    return _pool

class Row(dict):
    pass

def _row(r):
    return Row(dict(r)) if r else None

def _rows(rs):
    return [Row(dict(r)) for r in rs]

def _q(query):
    out, n, i = [], 0, 0
    while i < len(query):
        if query[i] == '?':
            n += 1
            out.append(f"${n}")
        else:
            out.append(query[i])
        i += 1
    q = "".join(out)
    q = q.replace("INSERT OR IGNORE INTO", "INSERT INTO")
    q = q.replace("INSERT OR REPLACE INTO", "INSERT INTO")
    q = q.replace("datetime('now')", "to_char(now(),'YYYY-MM-DD HH24:MI:SS')")
    return q

async def init_db():
    pool = await get_pool()
    async with pool.acquire() as c:
        # users
        await c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT PRIMARY KEY, username TEXT, full_name TEXT, phone TEXT,
            role TEXT DEFAULT 'none', lang TEXT DEFAULT 'uz', clinic_name TEXT,
            region TEXT, address TEXT, latitude REAL, longitude REAL,
            balance REAL DEFAULT 0, is_blocked INTEGER DEFAULT 0,
            payment_methods TEXT DEFAULT NULL,
            created_at TEXT DEFAULT to_char(now(),'YYYY-MM-DD HH24:MI:SS')
        )""")
        await c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS payment_methods TEXT")

        # settings
        await c.execute("""
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)""")

        # rooms
        await c.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id SERIAL PRIMARY KEY, room_code TEXT UNIQUE NOT NULL,
            room_type TEXT NOT NULL, owner_id BIGINT, status TEXT DEFAULT 'active',
            max_needs INTEGER NOT NULL,
            created_at TEXT DEFAULT to_char(now(),'YYYY-MM-DD HH24:MI:SS')
        )""")

        # batches
        await c.execute("""
        CREATE TABLE IF NOT EXISTS batches (
            id SERIAL PRIMARY KEY, owner_id BIGINT NOT NULL,
            status TEXT DEFAULT 'active', deadline_hours INTEGER DEFAULT 24,
            created_at TEXT DEFAULT to_char(now(),'YYYY-MM-DD HH24:MI:SS'),
            expires_at TEXT
        )""")

        # needs
        await c.execute("""
        CREATE TABLE IF NOT EXISTS needs (
            id SERIAL PRIMARY KEY, batch_id INTEGER, room_id INTEGER,
            owner_id BIGINT, product_name TEXT NOT NULL, quantity REAL NOT NULL,
            unit TEXT NOT NULL DEFAULT 'dona', budget REAL,
            deadline_hours INTEGER NOT NULL DEFAULT 24, extra_note TEXT,
            status TEXT DEFAULT 'active', channel_message_id BIGINT,
            payment_methods TEXT DEFAULT NULL,
            photo_file_id TEXT DEFAULT NULL,
            created_at TEXT DEFAULT to_char(now(),'YYYY-MM-DD HH24:MI:SS'),
            expires_at TEXT
        )""")
        await c.execute("ALTER TABLE needs ADD COLUMN IF NOT EXISTS payment_methods TEXT")
        await c.execute("ALTER TABLE needs ADD COLUMN IF NOT EXISTS photo_file_id TEXT")

        # offers
        await c.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            id SERIAL PRIMARY KEY, need_id INTEGER, batch_id INTEGER,
            seller_id BIGINT, product_name TEXT NOT NULL, price REAL NOT NULL,
            unit TEXT DEFAULT 'dona', delivery_hours INTEGER NOT NULL,
            note TEXT, status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT to_char(now(),'YYYY-MM-DD HH24:MI:SS')
        )""")

        # shops
        await c.execute("""
        CREATE TABLE IF NOT EXISTS shops (
            id SERIAL PRIMARY KEY, owner_id BIGINT, shop_name TEXT NOT NULL,
            category TEXT NOT NULL, phone TEXT, region TEXT,
            status TEXT DEFAULT 'pending', rating REAL DEFAULT 0,
            total_deals INTEGER DEFAULT 0,
            created_at TEXT DEFAULT to_char(now(),'YYYY-MM-DD HH24:MI:SS')
        )""")

        # products — avval CREATE, keyin ALTER
        await c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY, shop_id INTEGER NOT NULL,
            name TEXT NOT NULL, price REAL NOT NULL, unit TEXT NOT NULL,
            description TEXT, is_active INTEGER DEFAULT 1,
            photo_file_id TEXT DEFAULT NULL,
            stock INTEGER DEFAULT 0,
            category_id INTEGER DEFAULT 1,
            created_at TEXT DEFAULT to_char(now(),'YYYY-MM-DD HH24:MI:SS')
        )""")
        await c.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS photo_file_id TEXT")
        await c.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS stock INTEGER DEFAULT 0")
        await c.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS category_id INTEGER DEFAULT 1")

        # transactions
        await c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY, user_id BIGINT, amount REAL NOT NULL,
            balls REAL NOT NULL, type TEXT NOT NULL, status TEXT DEFAULT 'pending',
            receipt_file_id TEXT, confirmed_by BIGINT, note TEXT,
            created_at TEXT DEFAULT to_char(now(),'YYYY-MM-DD HH24:MI:SS')
        )""")

        # clinic_products
        await c.execute("""
        CREATE TABLE IF NOT EXISTS clinic_products (
            id SERIAL PRIMARY KEY, owner_id BIGINT NOT NULL,
            name TEXT NOT NULL, unit TEXT DEFAULT 'dona',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT to_char(now(),'YYYY-MM-DD HH24:MI:SS')
        )""")

        # support_messages
        await c.execute("""
        CREATE TABLE IF NOT EXISTS support_messages (
            id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL,
            message TEXT NOT NULL, admin_reply TEXT,
            status TEXT DEFAULT 'new', admin_id BIGINT,
            created_at TEXT DEFAULT to_char(now(),'YYYY-MM-DD HH24:MI:SS'),
            replied_at TEXT
        )""")
        await c.execute("ALTER TABLE support_messages ADD COLUMN IF NOT EXISTS admin_id BIGINT")

        # product_variants — razmer, artikul, miqdor
        await c.execute("""
        CREATE TABLE IF NOT EXISTS product_variants (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL,
            size_name TEXT,
            article TEXT,
            stock INTEGER DEFAULT 0,
            extra_price REAL DEFAULT 0,
            created_at TEXT DEFAULT to_char(now(),\'YYYY-MM-DD HH24:MI:SS\')
        )""")

        # product_photos — bir mahsulot uchun ko'p rasm
        await c.execute("""
        CREATE TABLE IF NOT EXISTS product_photos (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL,
            file_id TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT to_char(now(),\'YYYY-MM-DD HH24:MI:SS\')
        )""")

        # product_views — ko'rishlar soni
        await c.execute("""
        CREATE TABLE IF NOT EXISTS product_views (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL,
            user_id BIGINT,
            created_at TEXT DEFAULT to_char(now(),'YYYY-MM-DD HH24:MI:SS')
        )""")

        # complaints — shikoyatlar
        await c.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id SERIAL PRIMARY KEY,
            from_user_id BIGINT NOT NULL,
            against_user_id BIGINT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT DEFAULT 'new',
            admin_note TEXT,
            created_at TEXT DEFAULT to_char(now(),'YYYY-MM-DD HH24:MI:SS')
        )""")

        # subscriptions — obuna
        await c.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY,
            user_id BIGINT UNIQUE NOT NULL,
            status TEXT DEFAULT 'trial',
            trial_ends_at TEXT,
            paid_until TEXT,
            amount REAL DEFAULT 300000,
            created_at TEXT DEFAULT to_char(now(),'YYYY-MM-DD HH24:MI:SS')
        )""")

        # search_logs — qidiruvlar
        await c.execute("""
        CREATE TABLE IF NOT EXISTS search_logs (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            query TEXT NOT NULL,
            results_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT to_char(now(),'YYYY-MM-DD HH24:MI:SS')
        )""")

        # catalog_orders — savat buyurtmalari tracking
        await c.execute("""
        CREATE TABLE IF NOT EXISTS catalog_orders (
            id SERIAL PRIMARY KEY,
            buyer_id BIGINT NOT NULL,
            seller_id BIGINT NOT NULL,
            products_json TEXT NOT NULL,
            total_amount REAL DEFAULT 0,
            status TEXT DEFAULT 'pending',
            confirmed_at TEXT,
            delivered_at TEXT,
            notify_sent INTEGER DEFAULT 0,
            created_at TEXT DEFAULT to_char(now(),'YYYY-MM-DD HH24:MI:SS')
        )""")

        # reviews — baholar
        await c.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id SERIAL PRIMARY KEY,
            order_id INTEGER NOT NULL,
            buyer_id BIGINT NOT NULL,
            seller_id BIGINT NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            created_at TEXT DEFAULT to_char(now(),'YYYY-MM-DD HH24:MI:SS')
        )""")

        # default settings
        await c.execute("""
        INSERT INTO settings(key,value) VALUES
            ('ball_price','1000'),('elon_price','0'),('card_number','9860020138100068')
        ON CONFLICT(key) DO NOTHING""")

    print("✅ Database tayyor!")


async def db_get(query, params=()):
    pool = await get_pool()
    async with pool.acquire() as c:
        return _row(await c.fetchrow(_q(query), *params))

async def db_all(query, params=()):
    pool = await get_pool()
    async with pool.acquire() as c:
        return _rows(await c.fetch(_q(query), *params))

async def db_run(query, params=()):
    pool = await get_pool()
    async with pool.acquire() as c:
        await c.execute(_q(query), *params)

async def db_insert(query, params=()):
    q = _q(query)
    if "RETURNING" not in q.upper():
        q = q.rstrip(";") + " RETURNING id"
    pool = await get_pool()
    async with pool.acquire() as c:
        row = await c.fetchrow(q, *params)
        return row["id"] if row else None

async def get_user(uid):
    return await db_get("SELECT * FROM users WHERE id=?", (uid,))

async def get_setting(key):
    row = await db_get("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row else None

async def update_setting(key, value):
    pool = await get_pool()
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO settings(key,value) VALUES($1,$2) ON CONFLICT(key) DO UPDATE SET value=$2",
            key, value)

async def add_balance(user_id, balls):
    await db_run("UPDATE users SET balance=balance+? WHERE id=?", (balls, user_id))

async def get_next_room_code(room_type):
    rows = await db_all("SELECT room_code FROM rooms")
    existing = {r["room_code"] for r in rows}
    for building in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        for _ in range(300):
            if room_type == "small":
                digits = random.sample(range(1,10), 3)
            elif room_type == "standard":
                d1 = random.randint(1,9)
                d2 = random.randint(1,9)
                while d2 == d1: d2 = random.randint(1,9)
                digits = random.choice([[d1,d1,d2],[d1,d2,d2]])
            else:
                d = random.randint(1,9)
                digits = [d,d,d]
            code = f"{building}-{''.join(map(str,digits))}"
            if code not in existing:
                return code
    return None
