import logging
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.exceptions import TelegramBadRequest
from config import config
logger = logging.getLogger("obunalarim")
router = Router()


CREATOR_ID = config.CREATOR_ID


@router.callback_query(F.data.startswith("anime_subscription:"))
async def anime_subscription_handler(callback: CallbackQuery):
    # 🔒 Oddiy foydalanuvchilar kira olmaydi
    if callback.from_user.id != CREATOR_ID:
        await callback.answer(
            text="🛑 Obunalarim funksiya tez orada ishga tushadi.",
            show_alert=True
        )
        return