from aiogram import Router, html, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from dotenv.main import logger
from aiogram.fsm.context import FSMContext
from services.navigation import NavigationManager
router = Router()


@router.callback_query(lambda c: c.data == "guide")
async def guide_menu(callback: CallbackQuery, state: FSMContext):
    await NavigationManager(state).push("guide")
    await callback.answer()
    
    
    
    welcome_text = (
        "<b>📖 Foydalanish qo'llanmasi</b>\n\n"
        "<b>🔍 Qidiruv</b>\n"
        "<blockquote expandable>Anime nomi, ID yoki janr orqali qidiring. </blockquote>\n"
        "<b>🔔 Obunalar</b>"
        "<blockquote expandable>Sevimli animelaringiz yangilanganda xabar oling. </blockquote>\n"
        "<b>👤 Kabinet</b>"
        "<blockquote expandable>Profil, VIP va sozlamalarni boshqaring. </blockquote>\n"
        "<b>📢 Reklama</b>"
        "<blockquote expandable>Reklamangizni joylashtirmoqchi bo'lsangiz admin bilan bo'g'lanish </blockquote>\n"
        "<b>💬 Yordam</b>"
        "<blockquote expandable>Muammo yuzaga kelsa support bilan bog'laning. </blockquote>\n"
    )
    
    guide_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                
                InlineKeyboardButton(text="💬 Aloqa", callback_data="support", style="success")
            ],
            [
                InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_global", style="danger")
            ]
        ]
    )
    
    try:
        await callback.message.edit_caption(
            caption=welcome_text,
            parse_mode="HTML",
            reply_markup=guide_keyboard
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