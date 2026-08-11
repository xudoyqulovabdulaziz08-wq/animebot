

from asyncio.log import logger
from aiogram.exceptions import TelegramBadRequest

from aiogram.exceptions import TelegramBadRequest
from aiogram import Router, html, types, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message

from config import config




router = Router()
CREATOR_ID = config.CREATOR_ID




@router.message(lambda message: message.text == "🛠 Admin Paneli")
@router.callback_query(lambda c: c.data == "admin_panel")
async def admin_menu(event: Message | CallbackQuery, user: dict):
    """
    Ushbu handler ham matnli xabarni (Message), ham inline tugmani (CallbackQuery) 
    bitta joyda qabul qilib, unga mos ravishda javob qaytaradi.
    """
    # 1. Kelgan obyekt turiga qarab xabar va foydalanuvchi ma'lumotlarini ajratib olamiz
    if isinstance(event, CallbackQuery):
        message = event.message
        user_id = event.from_user.id
        username = event.from_user.username or "do'stim"
        await event.answer()  # Soat belgisini o'chirish
    else:
        message = event
        user_id = event.from_user.id
        username = event.from_user.username or "do'stim"

    # 2. Statusni xavfsiz formatga o'tkazamiz
    user_status = str(user.get('status', 'user')).lower()
    
    # 3. Huquqni tekshiramiz
    if user_id == CREATOR_ID or "admin" in user_status or "creator" in user_status:
        
        admin_inline_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Anime bo'limi 📚", callback_data="admin_anime", style="primary")],
                [
                    InlineKeyboardButton(text="Channel 📢", callback_data="admin_channel_menu", style="primary"),
                    InlineKeyboardButton(text="📣 Reklama", callback_data="admin_advertisement", style="primary")
                ],
                [
                    InlineKeyboardButton(text="📊 Statistika", callback_data="admin_statistics", style="primary"),
                    InlineKeyboardButton(text="Vip 💎", callback_data="admin_vip_panel", style="primary")
                ]
                
            ]
        )
        
        text = (
            f"🛡 {html.bold('Admin Paneliga')} xush kelibsiz, {html.bold(username)}!\n\n"
            f"Boshqarish uchun quyidagi ichki tugmalardan foydalaning:"
        )

        # 🎯 MANA SHU YERDA TRY-EXCEPT BLOKI OCHILDI
        try:
            # 4. Agar tugma bosilgan bo'lsa edit_text, aks holda yangi xabar
            if isinstance(event, CallbackQuery):
                await message.edit_text(text=text, reply_markup=admin_inline_kb, parse_mode="HTML")
            else:
                await message.answer(text=text, reply_markup=admin_inline_kb, parse_mode="HTML")
        
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                # Ketma-ket tugma bosilganda o'zgarmadi xatosini indamay o'tkazib yuboramiz
                pass
            else:
                logger.error(f"❌ Kutilmagan Telegram xatoligi: {e}")
        except Exception as e:
            logger.error(f"❌ Xabarni yuborishda umumiy xatolik: {e}")
        
    else:
        # Huquqi bo'lmaganlar uchun
        await message.answer("❌ Sizda admin panelga kirish huquqi yo'q.")