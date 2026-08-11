import logging
from typing import Any
from aiogram import html
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from config import config


logger = logging.getLogger("StartHelpers")
POSTER_ID = config.RASM_ID



async def send_or_edit_start_menu(
    target: Message | CallbackQuery, 
    user_id: int, 
    username: str,
    session: Any = None  # 🔥 Admin/VIP statusini tekshirish uchun session
):
    """
    Ushbu funksiya start menyusini ko'rsatadi.
    VIP va Adminlar uchun protect_content = False,
    Oddiy foydalanuvchilar uchun protect_content = True bo'ladi.
    """
    start_image_file_id = POSTER_ID 
    sayt_url = "https://aninov.uz"
    
    # 🛡️ 1. USER STATUSINI TEKSHIRISH (VIP/ADMIN)
    is_vip_or_admin = False
    if session:
        try:
            from services.user_service import UserService
            from config import config
            
            user_service = UserService(session=session)
            user_data = await user_service.get_user(user_id)
            creator_id = getattr(config, "CREATOR_ID", None)

            if user_data:
                is_vip_or_admin = (
                    user_data.get("is_vip", False) or 
                    user_data.get("status") == "admin" or 
                    user_id == creator_id
                )
            else:
                is_vip_or_admin = user_id == creator_id
        except Exception as e:
            logger.error(f"❌ User statusini tekshirishda xato: {e}")

    # Mualliflik huquqi himoyasi: Oddiy userlarga True, VIP/Adminlarga False
    should_protect = not is_vip_or_admin

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

    # 🔄 2. CALLBACK QUERY (Inline tugma bosilganda)
    if isinstance(target, CallbackQuery):
        try:
            # Silliq media edit qilish
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
            logger.warning(f"⚠️ Edit media bajarilmadi, yangi xabar yuborilmoqda: {edit_err}")
            # Agar edit xato bersa (mualliflik huquqi yoki media tipi to'g'ri kelmasa),
            # eski xabarni o'chirib yangisini protect statusi bilan yuboramiz
            try:
                await target.message.delete()
            except Exception:
                pass

            await target.message.answer_photo(
                photo=start_image_file_id,
                caption=welcome_text,
                reply_markup=start_keyboard,
                parse_mode="HTML",
                protect_content=should_protect  # 🔥 Mualliflik huquqi sozlamasi
            )
            await target.answer()

    # 📩 3. MESSAGE (/start yuborilganda)
    elif isinstance(target, Message):
        try:
            await target.delete()  # User yozgan /start buyrug'ini o'chirish
        except Exception:
            pass
            
        await target.answer_photo(
            photo=start_image_file_id,
            caption=welcome_text,
            reply_markup=start_keyboard,
            parse_mode="HTML",
            protect_content=should_protect  # 🔥 Mualliflik huquqi sozlamasi
        )