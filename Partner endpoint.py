# ============================================================
# XAZDENT — HAMKOR BOT ENDPOINT
# main.py ga qo'shiladi
# ============================================================
#
# 1. IMPORT qo'shish (main.py boshiga, agar yo'q bo'lsa):
#    import aiohttp
#
# 2. ENV ga qo'shish (Railway Variables):
#    PARTNER_TOKEN=o'zingiz_o'ylab_topgan_uzun_parol
#
# 3. Bu funksiyani main.py ga ko'chirish
#
# 4. app.router ga qo'shish (boshqa add_post qatorlar yoniga):
#    app.router.add_post('/api/partner/add_product', api_partner_add_product)
#
# ============================================================

import os
import aiohttp

PARTNER_TOKEN = os.getenv("PARTNER_TOKEN", "")

async def api_partner_add_product(request):
    """
    Hamkor bot (AliExpress scraper) dan mahsulot qabul qiladi.
    
    POST /api/partner/add_product
    Headers:
        X-Partner-Token: <PARTNER_TOKEN>
    Body (JSON):
        {
          "uid":          123456789,        # sotuvchi Telegram ID
          "name":         "Dental turbina", # mahsulot nomi
          "price":        150000,           # narx (UZS)
          "unit":         "dona",           # birlik
          "description":  "...",            # tavsif
          "images":       ["https://..."],  # rasm URL lar (max 5)
          "variants":     [                 # ixtiyoriy
            {"size_name": "S", "article": "ART-001", "stock": 99, "price": 150000}
          ],
          "delivery_type": "global",        # "local" yoki "global"
          "delivery_days": "15-30",         # yetkazish muddati
          "installment":   0,               # muddatli to'lov: 0 yoki 1
          "source_url":    "https://aliexpress.com/item/..." # manba havola
        }
    
    Response:
        { "ok": true, "product_id": 123, "article_code": "XZ00123" }
        { "ok": false, "error": "..." }
    """
    
    # 1. TOKEN TEKSHIRISH
    token = request.headers.get("X-Partner-Token", "")
    if not PARTNER_TOKEN or token != PARTNER_TOKEN:
        return web.json_response({"ok": False, "error": "Ruxsat yo'q"}, status=403)

    # 2. JSON OLISH
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "JSON noto'g'ri"}, status=400)

    # 3. MAJBURIY MAYDONLAR
    uid          = data.get("uid")
    name         = data.get("name", "").strip()
    price        = data.get("price", 0)
    unit         = data.get("unit", "dona")
    description  = data.get("description", "")
    images       = data.get("images", [])[:5]       # max 5 ta
    variants     = data.get("variants", [])
    delivery_type= data.get("delivery_type", "global")
    delivery_days= data.get("delivery_days", "15-30")
    installment  = data.get("installment", 0)
    source_url   = data.get("source_url", "")

    if not uid or not name or not price:
        return web.json_response(
            {"ok": False, "error": "uid, name, price majburiy"},
            status=400
        )

    try:
        async with request.app['db'].acquire() as conn:

            # 4. DO'KON TEKSHIRISH / YARATISH
            shop = await conn.fetchrow(
                "SELECT id FROM shops WHERE user_id = $1", uid
            )
            if not shop:
                # Do'kon yo'q — avtomatik yaratamiz
                shop_id = await conn.fetchval("""
                    INSERT INTO shops (user_id, name, category, delivery_type)
                    VALUES ($1, $2, 'Stomatologiya', 'global')
                    RETURNING id
                """, uid, f"Do'kon #{uid}")
            else:
                shop_id = shop['id']

            # 5. ARTIKUL KODI GENERATSIYA (XZ00001 format)
            last_id = await conn.fetchval(
                "SELECT MAX(id) FROM products"
            ) or 0
            article_code = f"XZ{(last_id + 1):05d}"

            # 6. MAHSULOT INSERT
            product_id = await conn.fetchval("""
                INSERT INTO products
                    (shop_id, name, price, unit, description,
                     is_active, stock, category_id, article_code,
                     delivery_type, delivery_days, installment)
                VALUES
                    ($1, $2, $3, $4, $5,
                     1, 999, 1, $6,
                     $7, $8, $9)
                RETURNING id
            """,
                shop_id, name, float(price), unit, description,
                article_code,
                delivery_type, delivery_days, int(installment)
            )

            # 7. RASMLARNI TELEGRAM GA YUBORISH → file_id OLISH
            photo_file_ids = []
            async with aiohttp.ClientSession() as session:
                for img_url in images:
                    try:
                        file_id = await _url_to_telegram_file_id(
                            session, img_url, bot
                        )
                        if file_id:
                            photo_file_ids.append(file_id)
                    except Exception as e:
                        print(f"[PARTNER] Rasm xatolik: {img_url} — {e}")

            # 8. RASMLARNI SAQLASH (product_photos jadvali)
            for i, file_id in enumerate(photo_file_ids):
                await conn.execute("""
                    INSERT INTO product_photos (product_id, file_id, sort_order)
                    VALUES ($1, $2, $3)
                    ON CONFLICT DO NOTHING
                """, product_id, file_id, i)

            # Birinchi rasmni products jadvaliga ham yozamiz
            if photo_file_ids:
                await conn.execute("""
                    UPDATE products SET photo_file_id = $1 WHERE id = $2
                """, photo_file_ids[0], product_id)

            # 9. VARIANTLARNI SAQLASH
            for v in variants:
                await conn.execute("""
                    INSERT INTO product_variants
                        (product_id, size_name, article, stock, price)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT DO NOTHING
                """,
                    product_id,
                    v.get("size_name", ""),
                    v.get("article", article_code),
                    int(v.get("stock", 999)),
                    float(v.get("price", price))
                )

            # 10. MANBA URL SAQLASH (agar source_url ustuni bo'lsa)
            # Agar jadvalda source_url ustuni yo'q bo'lsa bu qatorni o'chiring
            if source_url:
                try:
                    await conn.execute("""
                        ALTER TABLE products
                        ADD COLUMN IF NOT EXISTS source_url TEXT
                    """)
                    await conn.execute("""
                        UPDATE products SET source_url = $1 WHERE id = $2
                    """, source_url, product_id)
                except Exception:
                    pass  # Ustun qo'shib bo'lmasa o'tkazib yuboramiz

            # 11. KANALGA POST (ixtiyoriy — xohlasangiz o'chiring)
            # await _post_to_channel(product_id, name, price, photo_file_ids)

        print(f"[PARTNER] Yangi mahsulot: {article_code} — {name} (shop_id={shop_id})")

        return web.json_response({
            "ok": True,
            "product_id": product_id,
            "article_code": article_code,
            "shop_id": shop_id,
        })

    except Exception as e:
        print(f"[PARTNER] Xatolik: {e}")
        return web.json_response(
            {"ok": False, "error": str(e)},
            status=500
        )


async def _url_to_telegram_file_id(session, url: str, bot) -> str | None:
    """
    URL dan rasm yuklab, Telegram ga yuboradi va file_id qaytaradi.
    Bot obyekti — main.py dagi global `bot` o'zgaruvchisi.
    """
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=15),
            ssl=False,
            headers={"User-Agent": "Mozilla/5.0"}
        ) as resp:
            if resp.status != 200:
                return None
            image_bytes = await resp.read()

        # Telegram ga yuborish — maxfiy chat (bot o'ziga)
        # ADMIN_ID — main.py dagi admin Telegram ID si
        from aiogram.types import BufferedInputFile
        import hashlib
        filename = hashlib.md5(url.encode()).hexdigest()[:8] + ".jpg"

        msg = await bot.send_photo(
            chat_id=ADMIN_ID,   # main.py dagi ADMIN_ID ishlatiladi
            photo=BufferedInputFile(image_bytes, filename=filename)
        )
        await bot.delete_message(chat_id=ADMIN_ID, message_id=msg.message_id)
        return msg.photo[-1].file_id

    except Exception as e:
        print(f"[PARTNER] _url_to_telegram_file_id xatolik: {e}")
        return None
