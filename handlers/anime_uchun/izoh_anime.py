import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from config import config

logger = logging.getLogger("izohlarim")
router = Router()
CREATOR_ID = config.CREATOR_ID


@router.callback_query(F.data.startswith("anime_comment:"))
async def anime_comment_handler(callback: CallbackQuery):
    # 🔒 Oddiy foydalanuvchilar kira olmaydi
    if callback.from_user.id != CREATOR_ID:
        await callback.answer(
            text="🛑 Izohlar funksiya tez orada ishga tushadi.",
            show_alert=True
        )
        return

    # Qolgan mantiq (keyinchalik yoziladi)...