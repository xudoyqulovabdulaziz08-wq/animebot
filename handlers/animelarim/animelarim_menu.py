import logging
import asyncio
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto
)
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession
from services.favorite_service import FavoriteService
from services.rating_service import RatingService
from services.comment_service import CommentService
from services.subscription_service import SubscriptionService
from services.navigation import NavigationManager
from aiogram.fsm.context import FSMContext
from config import config

POSTER_ID = config.RASM_ID
logger = logging.getLogger("Cabinetanimelarim")
router = Router()

CREATOR_ID = config.CREATOR_ID

ANIME_COVER = POSTER_ID



@router.callback_query(F.data == "animelarim_cabinet")
async def animelarim_menu(
    callback: CallbackQuery, 
    session: AsyncSession, 
    state: FSMContext  # 👈 1. STATE PARAMETRI QO'SHILDI
):
    # 🔒 Oddiy foydalanuvchilar uchun cheklov
    if callback.from_user.id != CREATOR_ID:
        await callback.answer(
            text="📩 Bu funksiya tez orada ishga tushadi.",
            show_alert=True
        )
        return

    # 📌 NAVIGATSIYA TARIXIGA QO'SHAMIZ
    nav = NavigationManager(state)
    await nav.push("animelarim_cabinet")  # 👈 2. SHU SAHIFA STACK'GA TUSHADI

    # 📊 Foydalanuvchining sevimlilari sonini olish
    user_id = callback.from_user.id
    rat_count = 0
    fav_count = 0
    com_count = 0
    sub_count = 0

    try:
        rat_service = RatingService(session=session)
        fav_service = FavoriteService(session=session)
        com_service = CommentService(session=session)
        sub_service = SubscriptionService(session=session)

        # Ikkala keshlangan query'ni bir vaqtda parallel bajarish
        rat_count, fav_count, com_count, sub_count = await asyncio.gather(
            rat_service.get_user_ratings_count(user_id),
            fav_service.get_user_favorites_count(user_id),
            com_service.get_user_commented_anime_count(user_id),
            sub_service.get_user_subscription_anime_count(user_id),
            return_exceptions=False
        )
    except Exception as err:
        logger.error(f"❌ Kabinet statistikasini olishda xato: {err}")

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
                    text=f"⭐ Baholarim ({rat_count})",
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
                    text=f"💬 Izohlarim ({com_count})",
                    callback_data="cabinet_comments",
                    style="primary"
                ),
                InlineKeyboardButton(
                    text="🔔 Obunalarim ({sub_count})",
                    callback_data="cabinet_subscriptions",
                    style="primary"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Orqaga",
                    callback_data="cabinet",  # 👈 HAR DOIM UNIVERSAL "back_global" ISHLATILADI
                    style="danger"
                )
            ]
        ]
    )

    caption_text = (
        f"🎬 <b>Animelarim</b>\n\n"
        f"<blockquote expandable>Bu bo'lim orqali o'zingizga tegishli ma'lumotlarni boshqarishingiz mumkin.</blockquote>\n\n"
        f"Kerakli bo'limni tanlang."
    )

    try:
        media_obj = InputMediaPhoto(
            media=ANIME_COVER,
            caption=caption_text,
            parse_mode="HTML"
        )
        
        await callback.message.edit_media(
            media=media_obj,
            reply_markup=keyboard
        )

    except TelegramBadRequest as e:
        err_str = str(e).lower()
        if "message is not modified" in err_str:
            await callback.answer()
            return

        logger.warning(f"⚠️ edit_media bajarishda xatolik (Fallback rejimiga o'tilmoqda): {e}")
        
        try:
            await callback.message.delete()
        except Exception:
            pass

        await callback.message.answer_photo(
            photo=ANIME_COVER,
            caption=caption_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )

    await callback.answer()