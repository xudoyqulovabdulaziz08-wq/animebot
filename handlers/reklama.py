from aiogram import Router, html, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from dotenv.main import logger

router = Router()

@router.callback_query(lambda c: c.data == "advertise")
async def advertise_menu(callback: CallbackQuery):
    await callback.answer()
    
    
    
    text = (
        "<b>📢 Reklama</b>\n\n"
        "Aninovuz orqali reklamangizni anime ixlosmandlariga yetkazing.\n\n"
        "<b>📌 Xizmatlar</b>\n"
        "• Telegram bot reklamasi\n"
        "• Anime loyihalari reklamasi\n"
        "• Hamkorlik takliflari\n\n"
        "<b>ℹ️ Muhim</b>\n"
        "Narxlar va reklama shartlari administrator tomonidan taqdim etiladi.\n\n"
        "Quyidagi tugmani bosib reklama so'rovini yuboring."
    )
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Reklama berish", callback_data="advertise_submit", style="success")],
            
            # ⬇️ "Orqaga" tugmasi start.py faylidagi 'back_to_start' handleriga ulandi!
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_start", style="danger")]
        ]
    )
    
    try:
        # Matn o'rniga Media va Klaviatura birga chiroyli edit bo'ladi
        await callback.message.edit_caption(
            caption=text,
            parse_mode="HTML",
            reply_markup=kb
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
        # Agar xabar allaqachon o'zgargan bo'lsa, xato bermaymiz, shunchaki o'tkazib yuboramiz
            pass
        else:
            # Boshqa jiddiy xatolik bo'lsa logga yozamiz
            logger.error(f"❌ Kutilmagan xatolik: {e}")
    except Exception as e:
        logger.error(f"❌ Tizimda xatolik yuz berdi: {e}")








@router.callback_query(lambda c: c.data == "advertise_submit")
async def advertise_submit(callback: CallbackQuery):
    await callback.answer()
    advertise_image_file_id = "AgACAgIAAxkBAAI8rWo2yOOJrbYjf6oN-0buXgcqrr91AAJqGWsbZ6WxSdfP89-yJYeKAQADAgADdwADPAQ"

    text = (
        
        "📢 Reklama berish\n\n"
        "Botimiz orqali reklama joylashtirmoqchimisiz❓\n\n"
        "<blockquote expandable>⚠️ Quyidagi tugma orqali administrator bilan bog'laning. Reklama mazmuni avval ko'rib chiqiladi. </blockquote>\n"
        "<b>🛑 Reklama shartlari</b>\n"
        "<blockquote expandable> 1️⃣ 18+ kontent qabul qilinmaydi.</blockquote>\n"
        "<blockquote expandable> 2️⃣ Qimor, noqonuniy faoliyat yoki zararli dasturlar reklamasi taqiqlanadi.</blockquote>\n"
        "<blockquote expandable> 3️⃣ Yolg'on yoki foydalanuvchini chalg'ituvchi reklama qabul qilinmaydi.</blockquote>\n"
        "<blockquote expandable> 4️⃣ Telegram qoidalariga zid reklama joylashtirilmaydi.</blockquote>\n"
        "<blockquote expandable> 5️⃣ Tahqirlovchi yoki kamsituvchi mazmundagi reklama qabul qilinmaydi.</blockquote>\n"
    )

    url_admin = "https://t.me/Khudoyqulov_pg"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗Bog'lanish", url=url_admin, style="success")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="advertise", style="danger")]
        ]

    )
    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=advertise_image_file_id,
                caption=text,
                parse_mode="HTML"
            ),
            reply_markup=kb
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
        # Agar xabar allaqachon o'zgargan bo'lsa, xato bermaymiz, shunchaki o'tkazib yuboramiz
            pass
        else:
            # Boshqa jiddiy xatolik bo'lsa logga yozamiz
            logger.error(f"❌ Kutilmagan xatolik: {e}")
