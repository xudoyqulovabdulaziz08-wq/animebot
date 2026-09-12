import logging
from typing import Any
from aiogram import html
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from config import config

logger = logging.getLogger("StartHelpers")
POSTER_ID = config.RASM_ID
CREATOR_ID = config.CREATOR_ID


# handlers/start/helpers.py

async def send_or_edit_start_menu(
    target: Message | CallbackQuery, 
    user_id: int, 
    username: str,
    session: Any = None,        # 🔥 Eski chaqiruvlar uchun
    user_data: dict = None,      # 🔥 Middleware'dan kelgan foydalanuvchi ma'lumoti
    **kwargs                     # 🔥 Kutilmagan boshqa argumentlarni ushlab qolish uchun
):
    start_image_file_id = POSTER_ID 
    sayt_url = "https://aninov.uz"
    
    # 🛡️ Statusni tekshirish
    is_privileged = (user_id == CREATOR_ID)
    
    if not is_privileged and user_data:
        user_status = str(user_data.get("status", "")).lower()
        is_vip = user_data.get("is_vip", False)
        
        if is_vip or user_status == "admin":
            is_privileged = True

    should_protect = not is_privileged

    welcome_text = (
        f"👋 Xush kelibsiz, {html.bold(username)}!\n\n"
        f"🎬 {html.bold('AniNovuz')} — siz qidirgan eng sara, sifatli va sevimli animelar makoniga qadam qo‘ydingiz.\n\n"
        f"⚡️ Quyidagi menyudan foydalanib, darhol tomosha qilishni boshlashingiz mumkin:"
    )
    
    start_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Qidiruv", callback_data="search_menu", style="primary")],
            [
                InlineKeyboardButton(text="👤 Kabinet", callback_data="cabinet", style="primary"),
                InlineKeyboardButton(text="🌐 Sayt", url=sayt_url, style="primary")
            ],
            [
                InlineKeyboardButton(text="📖 Qo'llanma", callback_data="guide", style="success"),
                InlineKeyboardButton(text="💬 Yordam", callback_data="support", style="success")
            ],
            [InlineKeyboardButton(text="📢 Reklama", callback_data="advertise", style="primary")]
        ]
    )

    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_media(
                media=InputMediaPhoto(
                    media=start_image_file_id,
                    caption=welcome_text,
                    parse_mode="HTML"
                ),
                reply_markup=start_keyboard
            )
            await target.answer()
        except Exception as edit_err:
            logger.warning(f"⚠️ Edit media bajarilmadi: {edit_err}")
            try:
                await target.message.delete()
            except Exception:
                pass

            await target.message.answer_photo(
                photo=start_image_file_id,
                caption=welcome_text,
                reply_markup=start_keyboard,
                parse_mode="HTML",
                protect_content=should_protect
            )
            await target.answer()

    elif isinstance(target, Message):
        try:
            await target.delete() 
        except Exception:
            pass
            
        await target.answer_photo(
            photo=start_image_file_id,
            caption=welcome_text,
            reply_markup=start_keyboard,
            parse_mode="HTML",
            protect_content=should_protect
        )