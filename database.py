import aiosqlite
import os
import random

DB_PATH = "xazdent.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                role TEXT DEFAULT 'none',
                lang TEXT DEFAULT 'uz',
                clinic_name TEXT,
                region TEXT,
                address TEXT,
                balance REAL DEFAULT 0,
                is_blocked INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_code TEXT UNIQUE NOT NULL,
                room_type TEXT NOT NULL,
                owner_id INTEGER,
                status TEXT DEFAULT 'active',
                max_needs INTEGER NOT NULL,
                monthly_price INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS needs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER,
                owner_id INTEGER,
                product_name TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit TEXT NOT NULL,
                budget REAL,
                deadline_hours INTEGER NOT NULL,
                extra_note TEXT,
                status TEXT DEFAULT 'active',
                channel_message_id INTEGER,
                created_at TEXT DEFAULT (datetime('now')),
                expires_at TEXT
            );

            CREATE TABLE IF NOT EXISTS offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                need_id INTEGER,
                seller_id INTEGER,
                product_name TEXT NOT NULL,
                price REAL NOT NULL,
                currency TEXT DEFAULT 'uzs',
                delivery_hours INTEGER NOT NULL,
                note TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS shops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                shop_name TEXT NOT NULL,
                category TEXT NOT NULL,
                phone TEXT,
                region TEXT,
                status TEXT DEFAULT 'pending',
                rating REAL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL NOT NULL,
                balls REAL NOT NULL,
                type TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                receipt_file_id TEXT,
                confirmed_by INTEGER,
                note TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            INSERT OR IGNORE INTO settings VALUES ('ball_price', '1000');
            INSERT OR IGNORE INTO settings VALUES ('elon_price', '0.5');
            INSERT OR IGNORE INTO settings VALUES ('card_number', '8600 0000 0000 0000');
            INSERT OR IGNORE INTO settings VALUES ('small_room_price', '0');
            INSERT OR IGNORE INTO settings VALUES ('standard_room_price', '0');
            INSERT OR IGNORE INTO settings VALUES ('premium_room_price', '0');
        """)
        await db.commit()
    print("✅ Database tayyor!")


async def db_get(query: str, params=()):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cursor:
            return await cursor.fetchone()


async def db_all(query: str, params=()):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cursor:
            return await cursor.fetchall()


async def db_run(query: str, params=()):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(query, params)
        await db.commit()


async def db_insert(query: str, params=()):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(query, params)
        await db.commit()
        return cursor.lastrowid


async def get_user(uid: int):
    return await db_get("SELECT * FROM users WHERE id=?", (uid,))


async def get_setting(key: str):
    row = await db_get("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row else None


async def update_setting(key: str, value: str):
    await db_run("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, value))


async def add_balance(user_id: int, balls: float):
    await db_run("UPDATE users SET balance=balance+? WHERE id=?", (balls, user_id))


async def deduct_balance(user_id: int, balls: float) -> bool:
    user = await get_user(user_id)
    if not user or user["balance"] < balls:
        return False
    await db_run("UPDATE users SET balance=balance-? WHERE id=?", (balls, user_id))
    return True


async def get_next_room_code(room_type: str) -> str:
    rows = await db_all("SELECT room_code FROM rooms")
    existing = {r["room_code"] for r in rows}

    for building in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        for _ in range(300):
            if room_type == "small":
                digits = random.sample(range(1, 10), 3)
            elif room_type == "standard":
                d1 = random.randint(1, 9)
                d2 = random.randint(1, 9)
                while d2 == d1:
                    d2 = random.randint(1, 9)
                digits = random.choice([[d1, d1, d2], [d1, d2, d2], [d2, d1, d2]])
            else:
                d = random.randint(1, 9)
                digits = [d, d, d]

            code = f"{building}-{''.join(map(str, digits))}"
            if code not in existing:
                return code
    return None
