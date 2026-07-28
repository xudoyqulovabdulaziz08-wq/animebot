import logging
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.exceptions import TelegramBadRequest
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
                    callback_data="cabinet_history",
                    style="primary"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⭐ Baholarim",
                    callback_data="cabinet_ratings",
                    style="success"
                ),
                InlineKeyboardButton(
                    text="❤️ Sevimlilarim",
                    callback_data="cabinet_favorite",
                    style="success"
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
        # 🖼 Agar xabar Rasm yoki Video bo'lsa (Media) -> Caption va Keyboard o'zgaradi
        if callback.message.photo or callback.message.video or callback.message.document:
            await callback.message.edit_caption(
                caption=caption_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        # 📝 Agar xabar faqat Matndan iborat bo'lsa
        else:
            await callback.message.edit_text(
                text=caption_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
    except TelegramBadRequest as e:
        # Agar xabar o'zgarmas darajada eski bo'lsa yoki boshqa xato bersa, xabarni o'chirib qayta yuboradi
        logger.warning(f"Xabarni tahrirlashda xatolik: {e}")
        await callback.message.answer(
            text=caption_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )

    await callback.answer()