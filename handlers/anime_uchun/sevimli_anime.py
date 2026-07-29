import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from services.favorite_service import FavoriteService
from config import config


logger = logging.getLogger("sevimlilarim")
router = Router()

CREATOR_ID = config.CREATOR_ID


@router.callback_query(F.data.startswith("anime_favorite:"))
async def anime_favorite_handler(callback: CallbackQuery, session: AsyncSession):
    # 🔒 Oddiy foydalanuvchilar uchun vaqtincha cheklov
    if callback.from_user.id != CREATOR_ID:
        await callback.answer(
            text="🛑 Sevimlilar funksiyasi tez orada ishga tushadi.",
            show_alert=True  # Markazda modal oyna chiqaradi
        )
        return

    anime_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    # Sevimliga qo'shish yoki o'chirish mantiqi
    success, action = await FavoriteService.toggle_favorite(session, user_id, anime_id)

    if not success:
        await callback.answer(
            text="❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.",
            show_alert=True
        )
        return

    # Muvaffaqiyatli bajarilganda chiquvchi modal xabar
    if action == "added":
        msg_text = "❤️ Ushbu anime sevimlilaringiz ro'yxatiga qo'shildi!"
    else:
        msg_text = "💔 Ushbu anime sevimlilaringiz ro'yxatidan olib tashlandi."

    # Faqat markaziy popup Alert xabarini chiqaradi
    await callback.answer(
        text=msg_text,
        show_alert=True
    )