import logging
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession
from services.favorite_service import FavoriteService
from config import config

logger = logging.getLogger("Cabinetanimelarim")
router = Router()

CREATOR_ID = config.CREATOR_ID

@router.callback_query(F.data == "animelarim_cabinet")
async def animelarim_menu(callback: CallbackQuery, session: AsyncSession):
    # 🔒 Oddiy foydalanuvchilar uchun cheklov
    if callback.from_user.id != CREATOR_ID:
        await callback.answer(
            text="📩 Bu funksiya tez orada ishga tushadi.",
            show_alert=True
        )
        return

    # 📊 Foydalanuvchining sevimlilari sonini olish
    user_id = callback.from_user.id
    fav_count = 0
    
    try:
        fav_service = FavoriteService(session=session)
        fav_count = await fav_service.get_user_favorites_count(user_id)
        if not fav_count: 
            fav_count = 0
    except Exception as err:
        logger.error(f"❌ Sevimlilar sonini olishda xato: {err}")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📜 Ko'rish tarixi",
                    callback_data="cabinet_history",
                    style="primary"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⭐ Baholarim",
                    callback_data="cabinet_ratings",
                    style="primary"
                ),
                InlineKeyboardButton(
                    text=f"❤️ Sevimlilarim ({fav_count})",
                    callback_data="cabinet_favorite",
                    style="primary"
                )
            ],
            
            [
                InlineKeyboardButton(
                    text="💬 Izohlarim",
                    callback_data="cabinet_comments",
                    style="primary"
                ),
                InlineKeyboardButton(
                    text="🔔 Obunalarim",
                    callback_data="cabinet_subscriptions",
                    style="primary"
                )
            ],
        
            [
                InlineKeyboardButton(
                    text="⬅️ Orqaga",
                    callback_data="cabinet",
                    style="danger"
                    
                )
            ]
        ]
    )

    caption_text = (
        "🎬 <b>Animelarim</b>\n\n"
        "Bu bo'lim orqali o'zingizga tegishli ma'lumotlarni boshqarishingiz mumkin.\n\n"
        "Kerakli bo'limni tanlang."
    )

    try:
        # 🖼 Agar xabar Media bo'lsa
        if callback.message.photo or callback.message.video or callback.message.document:
            await callback.message.edit_caption(
                caption=caption_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        # 📝 Faqat Matn bo'lsa
        else:
            await callback.message.edit_text(
                text=caption_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
    except TelegramBadRequest as e:
        logger.warning(f"Xabarni tahrirlashda xatolik: {e}")
        await callback.message.answer(
            text=caption_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )

    await callback.answer()