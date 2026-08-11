

from asyncio.log import logger
from aiogram.exceptions import TelegramBadRequest

from aiogram.exceptions import TelegramBadRequest
from aiogram import Router, html, types, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message

from config import config




router = Router()
CREATOR_ID = config.CREATOR_ID

@router.message(lambda message: message.text == "⚙️ Creator Paneli")
@router.callback_query(lambda c: c.data == "creator_panel")
async def creator_menu(event: Message | CallbackQuery, user: dict):
    """
    Asoschi (Creator) uchun maxsus universal boshqaruv paneli.
    Faqat va faqat CREATOR_ID egalari kira oladi.
    """
    # 1. Kelgan obyekt turiga qarab ma'lumotlarni ajratamiz
    if isinstance(event, CallbackQuery):
        message = event.message
        user_id = event.from_user.id
        username = event.from_user.username or "BOSS"
        await event.answer()  # Soat belgisini o'chirish
    else:
        message = event
        user_id = event.from_user.id
        username = event.from_user.username or "BOSS"

    # 2. Faqat eng yuqori huquq egasini (Asoschini) tekshiramiz
    if user_id == CREATOR_ID:
        
        creator_inline_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="👑 Adminlarni boshqarish", callback_data="admin_creator")],
                [
                    InlineKeyboardButton(text="📊 To'liq statistika", callback_data="creator_statistics"),
                    InlineKeyboardButton(text="🗄️ Baza control", callback_data="creator_db_panel", style="danger")
                ]
            ]
        )
        
        text = (
            f"👑 {html.bold('Creator Paneliga')} xush kelibsiz, BOSS {html.bold(username)}!\n\n"
            f"Tizimni to'liq nazorat qilish uchun quyidagi tugmalardan foydalaning:"
        )

        try:
            # 3. Callback bo'lsa edit, xabar bo'lsa yangi text yuboramiz
            if isinstance(event, CallbackQuery):
                await message.edit_text(text=text, reply_markup=creator_inline_kb, parse_mode="HTML")
            else:
                await message.answer(text=text, reply_markup=creator_inline_kb, parse_mode="HTML")
        
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                pass
            else:
                logger.error(f"❌ Creator panelda Telegram xatoligi: {e}")
        except Exception as e:
            logger.error(f"❌ Creator panelda umumiy xatolik: {e}")
        
    else:
        # Huquqi bo'lmagan g'irromlar uchun
        await message.answer("❌ Sizda ushbu yuqori boshqaruv paneliga kirish huquqi yo'q.")