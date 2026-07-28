import logging
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from config import config

logger = logging.getLogger("Cabinetanimelarim")
router = Router()

CREATOR_ID = config.CREATOR_ID


@router.callback_query(F.data == "animelarim_cabinet")
async def animelarim_menu(callback: CallbackQuery):
    # 🔒 Oddiy foydalanuvchilar kira olmaydi
    if callback.from_user.id != CREATOR_ID:
        await callback.answer(
            text="📩 Bu funksiya tez orada ishga tushadi.",
            show_alert=True
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📜 Ko'rish tarixi",
                    callback_data="cabinet_history"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⭐ Baholar",
                    callback_data="cabinet_ratings"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Izohlar",
                    callback_data="cabinet_comments"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔔 Obunalar",
                    callback_data="cabinet_subscriptions"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Orqaga",
                    callback_data="back_cabinet"
                )
            ]
        ]
    )

    await callback.message.edit_text(
        text=(
            "🎬 <b>Animelarim</b>\n\n"
            "Bu bo'lim orqali o'zingizga tegishli ma'lumotlarni boshqarishingiz mumkin.\n\n"
            "Kerakli bo'limni tanlang."
        ),
        parse_mode="HTML",
        reply_markup=keyboard
    )

    await callback.answer()