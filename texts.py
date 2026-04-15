REGIONS = [
    "🌍 O'zbekiston bo'ylab",
    "🏙 Toshkent shahri", "🌆 Toshkent viloyati", "🏛 Samarqand",
    "🕌 Buxoro", "🌸 Farg'ona", "🏔 Andijon", "🌿 Namangan",
    "🌊 Xorazm", "🌵 Qashqadaryo", "🏜 Surxondaryo",
    "🌾 Jizzax", "🌱 Sirdaryo", "💎 Navoiy", "🏝 Qoraqalpog'iston"
]

REGIONS_RU = [
    "🌍 По всему Узбекистану",
    "🏙 г.Ташкент", "🌆 Ташкентская обл.", "🏛 Самарканд",
    "🕌 Бухара", "🌸 Фергана", "🏔 Андижан", "🌿 Наманган",
    "🌊 Хорезм", "🌵 Кашкадарья", "🏜 Сурхандарья",
    "🌾 Джизак", "🌱 Сырдарья", "💎 Навои", "🏝 Каракалпакстан"
]

T = {
    "uz": {
        "welcome": "🦷 *XAZDENT*ga xush kelibsiz!\n\nStomatologik materiallar bozori\n\n🌐 Tilni tanlang:",
        "choose_role": "Siz kimسیز?",
        "role_clinic": "🏥 Vrach / Klinika",
        "role_seller": "🛒 Sotuvchi",
        "back": "⬅️ Orqaga",
        "cancel": "❌ Bekor",
        "confirm": "✅ Tasdiqlash",
        "skip": "⏭ O'tkazish",
        "edit": "✏️ Tahrirlash",
        "error": "❌ Xatolik. Qaytadan urinib ko'ring.",

        # Klinika
        "clinic_menu": "🏥 *Klinika paneli*",
        "btn_my_needs": "📋 Ehtiyojlarim",
        "btn_offers": "📩 Takliflar",
        "btn_my_rooms": "🏠 Omborxonalarim",
        "btn_new_room": "➕ Yangi omborxona",
        "btn_balance": "💰 Hisobim",
        "btn_profile": "⚙️ Profil",

        # Sotuvchi
        "seller_menu": "🛒 *Sotuvchi paneli*",
        "btn_feed": "🔔 Yangi ehtiyojlar",
        "btn_my_offers": "📤 Takliflarim",
        "btn_my_shop": "🏪 Do'konim",
        "btn_new_shop": "➕ Do'kon ochish",

        # Profil
        "ask_clinic_name": "🏥 Klinika yoki ism-familiyangizni kiriting:\n\n_Masalan: Sadaf Dental_",
        "ask_phone": "📞 Telefon raqamingizni yuboring:\n_(Pastdagi tugmani bosing)_",
        "btn_send_phone": "📞 Raqamni yuborish",
        "ask_region": "📍 Viloyatingizni tanlang:",
        "ask_address": "🏠 Aniq manzilingizni kiriting:\n\n_Masalan: Chilonzor 15/6, 2-qavat_",
        "profile_saved": "✅ Profil saqlandi! Endi omborxona oching.",
        "profile_first": "⚠️ Avval profilingizni to'ldiring!",

        # Omborxona
        "ask_room_type": "📦 *Omborxona turini tanlang:*\n\nHar birining imkoniyatlari farqli",
        "btn_small": "🔹 Kichik — 10 ehtiyoj (BEPUL)",
        "btn_standard": "🔷 Standart — 25 ehtiyoj (BEPUL)",
        "btn_premium": "💎 Premium — 150 ehtiyoj (BEPUL)",
        "room_created": "✅ *Omborxona yaratildi!*\n\n🏠 Xona raqami: `{code}`\n\nEndi ehtiyoj qo'shing!",
        "no_rooms": "📭 Omborxona yo'q. Yangi ochish uchun ➕ tugmasini bosing.",
        "rooms_list": "🏠 *Omborxonalarim:*",

        # Ehtiyoj
        "ask_product": "🦷 Qaysi mahsulot kerak?\n\n_Masalan: Xarizma plomba A2, GC Fuji IX_",
        "ask_qty": "📦 Miqdorini kiriting:\n\n_Faqat raqam. Masalan: 2_",
        "ask_unit": "⚖️ O'lchov birligini tanlang:",
        "btn_dona": "📌 Dona",
        "btn_kg": "⚖️ Kg",
        "btn_litr": "💧 Litr",
        "ask_budget": "💰 Taxminiy byudjet? (so'mda)\n\n_Bilmasangiz — O'tkazish tugmasini bosing_",
        "ask_deadline": "⏱ Qachongacha kerak?",
        "btn_2h": "⚡️ 2 soat",
        "btn_24h": "🕐 24 soat",
        "btn_3d": "📅 3 kun",
        "btn_1w": "🗓 1 hafta",
        "ask_note": "📝 Qo'shimcha izoh? (ixtiyoriy)\n\n_Masalan: Original bo'lsin, sertifikat kerak_",
        "need_preview": "📋 *E'lon ko'rinishi:*\n\n{preview}\n\nJoylashtiramizmi?",
        "need_posted": "✅ *E'lon joylashtirildi!*\n\n🏠 Xona: `{room}`\n📢 Kanal: {link}",
        "no_needs": "📭 Ehtiyojlar yo'q.",

        # Taklif
        "no_offers": "📭 Hali taklif kelmagan. Sotuvchilar ko'rib chiqmoqda...",
        "offers_title": "📩 *Takliflar:* {count} ta",
        "btn_accept": "✅ Qabul qilish",
        "btn_reject": "❌ Rad etish",
        "offer_accepted": "✅ *Qabul qilindi!*\n\nSotuvchi: {name}\n📞 Tel: {phone}",

        # Balans
        "balance_info": "💰 *Hisobingiz:*\n\nBall: *{balls:.1f}*\n\n_(1-bosqichda e'lon bepul)_",
        "btn_topup": "➕ Hisob to'ldirish",
        "topup_ask_amount": "💰 Qancha so'm o'tkazasiz?\n\n_Faqat raqam kiriting_",
        "topup_send_card": "💳 Ushbu kartaga o'tkazing:\n\n`{card}`\n\nSo'ng chek rasmini yuboring 📸",
        "receipt_sent": "✅ Chek yuborildi! Admin 15-30 daqiqada tasdiqlaydi.",
        "balance_added": "🎉 *Hisobingiz to'ldirildi!*\n\n+{balls:.1f} ball qo'shildi",

        # Sotuvchi
        "ask_shop_cat": "📂 Do'kon kategoriyasini tanlang:",
        "cat_1": "🦷 Terapevtik materiallar",
        "cat_2": "⚙️ Jarrohlik & Implantlar",
        "cat_3": "🔬 Zubtexnik ashyolar",
        "cat_4": "🧪 Dezinfeksiya",
        "cat_5": "💡 Asbob-uskunalar",
        "ask_shop_name": "🏪 Do'kon nomini kiriting:\n\n_Masalan: DentalPlus Toshkent_",
        "shop_pending": "⏳ Do'kon admin tasdiqlashini kutmoqda.",
        "shop_approved": "✅ Do'koningiz faollashdi!",
        "feed_title": "🔔 *Aktiv ehtiyojlar:* {count} ta",
        "no_feed": "📭 Hozircha aktiv ehtiyoj yo'q.",
        "btn_make_offer": "📤 Taklif yuborish",
        "ask_offer_product": "🦷 Qaysi mahsulot taklif qilasiz?\n\n_So'rov: {req}_",
        "ask_offer_price": "💰 Narxini kiriting (so'mda, 1 {unit} uchun):",
        "ask_delivery": "🚚 Yetkazib berish muddati:",
        "btn_del_2h": "⚡️ 2 soat",
        "btn_del_24h": "🕐 24 soat",
        "btn_del_2d": "📅 2 kun",
        "btn_del_1w": "🗓 1 hafta",
        "offer_sent": "✅ Taklif yuborildi! Klinika ko'rib chiqadi.",
        "already_offered": "⚠️ Bu e'longa allaqachon taklif yuborgansiz!",
        "new_offer_notify": "📩 *Yangi taklif!*\n\n🦷 {product}\n💡 {offer_prod}\n💰 {price:,.0f} so'm/{unit}\n🚚 {delivery} soat\n👤 {seller}\n📞 {phone}",
    }
}

# Rus tili — asosiy kalitlar
T["ru"] = {
    "welcome": "🦷 Добро пожаловать в *XAZDENT*!\n\nРынок стоматологических материалов\n\n🌐 Выберите язык:",
    "choose_role": "Кто вы?",
    "role_clinic": "🏥 Врач / Клиника",
    "role_seller": "🛒 Продавец",
    "back": "⬅️ Назад", "cancel": "❌ Отмена",
    "confirm": "✅ Подтвердить", "skip": "⏭ Пропустить", "edit": "✏️ Изменить",
    "error": "❌ Ошибка. Попробуйте снова.",
    "clinic_menu": "🏥 *Панель клиники*",
    "btn_my_needs": "📋 Мои заявки", "btn_offers": "📩 Предложения",
    "btn_my_rooms": "🏠 Мои склады", "btn_new_room": "➕ Новый склад",
    "btn_balance": "💰 Мой счёт", "btn_profile": "⚙️ Профиль",
    "seller_menu": "🛒 *Панель продавца*",
    "btn_feed": "🔔 Новые заявки", "btn_my_offers": "📤 Мои предложения",
    "btn_my_shop": "🏪 Мой магазин", "btn_new_shop": "➕ Открыть магазин",
    "ask_clinic_name": "🏥 Введите название клиники или ФИО:\n\n_Пример: Sadaf Dental_",
    "ask_phone": "📞 Отправьте номер телефона:\n_(Нажмите кнопку ниже)_",
    "btn_send_phone": "📞 Отправить номер",
    "ask_region": "📍 Выберите регион:",
    "ask_address": "🏠 Введите точный адрес:\n\n_Пример: Чиланзар 15/6, 2 этаж_",
    "profile_saved": "✅ Профиль сохранён!",
    "profile_first": "⚠️ Сначала заполните профиль!",
    "ask_room_type": "📦 *Выберите тип склада:*",
    "btn_small": "🔹 Малый — 10 заявок (БЕСПЛАТНО)",
    "btn_standard": "🔷 Стандарт — 25 заявок (БЕСПЛАТНО)",
    "btn_premium": "💎 Премиум — 150 заявок (БЕСПЛАТНО)",
    "room_created": "✅ *Склад создан!*\n\n🏠 Номер комнаты: `{code}`",
    "no_rooms": "📭 Нет складов. Нажмите ➕",
    "rooms_list": "🏠 *Мои склады:*",
    "ask_product": "🦷 Какой материал нужен?\n\n_Пример: Xarizma пломба A2_",
    "ask_qty": "📦 Введите количество:\n\n_Только цифра. Пример: 2_",
    "ask_unit": "⚖️ Единица измерения:",
    "btn_dona": "📌 Штук", "btn_kg": "⚖️ Кг", "btn_litr": "💧 Литр",
    "ask_budget": "💰 Примерный бюджет? (в сумах)\n\n_Не знаете — нажмите Пропустить_",
    "ask_deadline": "⏱ Когда нужно?",
    "btn_2h": "⚡️ 2 часа", "btn_24h": "🕐 24 часа",
    "btn_3d": "📅 3 дня", "btn_1w": "🗓 1 неделя",
    "ask_note": "📝 Доп. примечание? (необязательно)",
    "need_preview": "📋 *Предпросмотр:*\n\n{preview}\n\nРазместить?",
    "need_posted": "✅ *Объявление размещено!*\n\n🏠 Комната: `{room}`\n📢 Канал: {link}",
    "no_needs": "📭 Нет заявок.",
    "no_offers": "📭 Предложений пока нет.",
    "offers_title": "📩 *Предложения:* {count} шт",
    "btn_accept": "✅ Принять", "btn_reject": "❌ Отклонить",
    "offer_accepted": "✅ *Принято!*\n\nПродавец: {name}\n📞 Тел: {phone}",
    "balance_info": "💰 *Ваш счёт:*\n\nБаллы: *{balls:.1f}*",
    "btn_topup": "➕ Пополнить",
    "topup_ask_amount": "💰 Сколько сум переводите?\n\n_Только цифра_",
    "topup_send_card": "💳 Переведите на карту:\n\n`{card}`\n\nЗатем отправьте чек 📸",
    "receipt_sent": "✅ Чек отправлен! Администратор подтвердит за 15-30 минут.",
    "balance_added": "🎉 *Счёт пополнен!*\n\n+{balls:.1f} баллов добавлено",
    "ask_shop_cat": "📂 Выберите категорию магазина:",
    "cat_1": "🦷 Терапевтические материалы",
    "cat_2": "⚙️ Хирургия & Имплантаты",
    "cat_3": "🔬 Зуботехника",
    "cat_4": "🧪 Дезинфекция",
    "cat_5": "💡 Оборудование",
    "ask_shop_name": "🏪 Введите название магазина:",
    "shop_pending": "⏳ Магазин ожидает проверки администратора.",
    "shop_approved": "✅ Ваш магазин активирован!",
    "feed_title": "🔔 *Активные заявки:* {count} шт",
    "no_feed": "📭 Активных заявок нет.",
    "btn_make_offer": "📤 Отправить предложение",
    "ask_offer_product": "🦷 Какой товар предлагаете?\n\n_Запрос: {req}_",
    "ask_offer_price": "💰 Введите цену (в сумах, за 1 {unit}):",
    "ask_delivery": "🚚 Срок доставки:",
    "btn_del_2h": "⚡️ 2 часа", "btn_del_24h": "🕐 24 часа",
    "btn_del_2d": "📅 2 дня", "btn_del_1w": "🗓 1 неделя",
    "offer_sent": "✅ Предложение отправлено!",
    "already_offered": "⚠️ Вы уже отправили предложение на эту заявку!",
    "new_offer_notify": "📩 *Новое предложение!*\n\n🦷 {product}\n💡 {offer_prod}\n💰 {price:,.0f} сум/{unit}\n🚚 {delivery} ч\n👤 {seller}\n📞 {phone}",
}


def t(lang: str, key: str, **kw) -> str:
    lang = lang if lang in T else "uz"
    text = T[lang].get(key) or T["uz"].get(key, key)
    try:
        return text.format(**kw) if kw else text
    except:
        return text
