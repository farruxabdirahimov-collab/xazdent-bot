# ── XAZDENT Versiya Boshqaruvi ────────────────────────────
# 
# breaking=True  → foydalanuvchilarga xabar yuboriladi (stop bo'ladigan yangilanish)
# breaking=False → jim yangilanadi (foydalanuvchi sezmaydigan fix)
#
# QOIDASI:
#   - Tugma matni o'zgardi      → breaking=True
#   - Yangi sahifa/bo'lim       → breaking=True  
#   - DB jadval o'zgardi        → breaking=True
#   - Bug fix, kichik tuzatish  → breaking=False
#   - Matn/emoji o'zgardi       → breaking=False

VERSION = "1.3"

BREAKING = True   # ← False qilsang xabar yuborilmaydi

CHANGELOG = """✨ Yangi imkoniyatlar:
• Sotuvchi taklif berish yangilandi
• Kanal postida to'g'ridan taklif tugmasi
• Barcha sotuvchilarga lichkada xabar
• Jadval + Excel yuklab olish"""

# Motivatsion xabarlar (har deployda tasodifiy tanlanadi)
HYPE_MESSAGES = [
    "🚀 *Biz o'sib bormoqdamiz!*\nHar yangilanish sizga yanada qulay xizmat.",
    "🎉 *Yangi versiya — yangi imkoniyat!*\nJamoa siz uchun tinimsiz ishlayapti.",
    "💪 *XAZDENT kuchaymoqda!*\nSotib olish va sotish endi yanada tezroq.",
    "🌟 *Yangilanish = yaxshilanish!*\nHar versiyada siz uchun biror yangilik.",
    "🦷 *Stomatologiya bozori rivojlanmoqda!*\nBiz shu yo'lda birgamiz.",
]
