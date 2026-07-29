import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from services.favorite_service import FavoriteService
from config import config

logger = logging.getLogger("sevimli")
router = Router()

CREATOR_ID = config.CREATOR_ID


@router.callback_query(F.data.startswith("anime_favorite:"))
async def anime_favorite_handler(callback: CallbackQuery, session: AsyncSession):
    # 🔒 Oddiy foydalanuvchilar uchun vaqtincha cheklov
    if callback.from_user.id != CREATOR_ID:
        await callback.answer(
            text="🛑 Sevimlilar funksiyasi tez orada ishga tushadi.",
            show_alert=True
        )
        return

    anime_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    # 1. Sevimliga qo'shish yoki o'chirish
    success, action = await FavoriteService.toggle_favorite(session, user_id, anime_id)

    if not success:
        await callback.answer(
            text="❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.",
            show_alert=True
        )
        return

    # 2. Xabar matnini va yangi tugma nomini tayyorlash
    if action == "added":
        msg_text = "❤️ Ushbu anime sevimlilaringiz ro'yxatiga qo'shildi!"
        new_fav_text = "❤️ Sevimlida ✓"
        
    else:
        msg_text = "💔 Ushbu anime sevimlilaringiz ro'yxatidan olib tashlandi."
        new_fav_text = "🤍 Sevimli"
        
    # 3. 🪄 TUGMALARNI EKRONDA DARHOL r54t54gYANGILASH (EDIT REPLY MARKUP)
    if callback.message and callback.message.reply_markup:
        current_markup = callback.message.reply_markup
        new_inline_keyboard = []

        # Xabardagi barcha tugmalarni ko'rib chiqamiz
        for row in current_markup.inline_keyboard:
            new_row = []
            for button in row:
                # Aynan shu Sevimli tugmasini topsak, matnini yangilaymiz
                if button.callback_data == callback.data:
                    new_row.append(
                        InlineKeyboardButton(
                            text=new_fav_text,
                            callback_data=button.callback_data,
                            style="primary"
                        )
                    )
                else:
                    new_row.append(button)
            new_inline_keyboard.append(new_row)

        # Klaviaturani almashtiramiz
        try:
            await callback.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(inline_keyboard=new_inline_keyboard)
            )
        except Exception as edit_err:
            logger.error(f"❌ Tugmani yangilashda xato: {edit_err}")

    # 4. Pop-up alert chiqarish
    await callback.answer(
        text=msg_text,
        show_alert=True
    )