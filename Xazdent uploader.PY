"""
Hamkor bot — XazDentga yuklash moduli
bot.py ga qo'shiladi yoki alohida fayl sifatida import qilinadi
"""

import os
import aiohttp
import logging

logger = logging.getLogger(__name__)

XAZDENT_API_URL = os.getenv("XAZDENT_API_URL", "")   # https://your-railway-url.up.railway.app
PARTNER_TOKEN   = os.getenv("PARTNER_TOKEN", "")      # Railway da bir xil bo'lishi kerak!
SELLER_UID      = os.getenv("SELLER_UID", "")         # Sizning Telegram ID ingiz


async def upload_to_xazdent(product_data: dict) -> dict:
    """
    Tayyor kartochkani XazDentga yuboradi.
    
    product_data — scraper.py dan kelgan dict:
      title, price_uzs, price_usd, description,
      images (URL list), variants, min_order, product_id
    
    Qaytaradi:
      {"ok": True, "article_code": "XZ00123", "product_id": 456}
      {"ok": False, "error": "..."}
    """
    if not XAZDENT_API_URL or not PARTNER_TOKEN or not SELLER_UID:
        return {"ok": False, "error": "XAZDENT_API_URL, PARTNER_TOKEN yoki SELLER_UID sozlanmagan"}

    # Variantlarni XazDent formatiga o'tkazish
    xazdent_variants = []
    for v in product_data.get("variants", []):
        for val in v.get("values", []):
            xazdent_variants.append({
                "size_name": f"{v.get('name', '')}: {val}",
                "article":   f"AE-{product_data.get('product_id', '')}-{val}",
                "stock":     999,
                "price":     float(product_data.get("price_uzs", 0))
            })

    payload = {
        "uid":          int(SELLER_UID),
        "name":         product_data.get("title", "")[:200],
        "price":        float(product_data.get("price_uzs", 0)),
        "unit":         "dona",
        "description":  product_data.get("description", "")[:1000],
        "images":       product_data.get("images", [])[:5],
        "variants":     xazdent_variants[:10],
        "delivery_type":"global",
        "delivery_days":"15-30",
        "installment":  0,
        "source_url":   f"https://www.aliexpress.com/item/{product_data.get('product_id', '')}.html"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{XAZDENT_API_URL}/api/partner/add_product",
                json=payload,
                headers={
                    "X-Partner-Token": PARTNER_TOKEN,
                    "Content-Type":    "application/json"
                },
                timeout=aiohttp.ClientTimeout(total=30),
                ssl=False
            ) as resp:
                result = await resp.json()
                return result

    except Exception as e:
        logger.error(f"XazDent yuklash xatolik: {e}")
        return {"ok": False, "error": str(e)}
