from telegram.ext import ContextTypes
from services.user_service import get_user_status
from keyboard.admin_kb import get_admin_kb
from telegram import Update
from config import MAIN_ADMIN_ID
from database.db import async_session


# ===================================================================================


async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = update.callback_query # Tugma bosilganini tekshirish
    
    async with async_session() as session:
        status = await get_user_status(session, user_id, MAIN_ADMIN_ID)
    
        if status in ["main_admin", "admin"]:
            is_main = (status == "main_admin")
            admin_info = "👑 <b>Bosh Admin Paneli</b>" if is_main else "👨‍💻 <b>Admin Paneli</b>"
            
            text = (
                f"{admin_info}\n\n"
                "Botni boshqarish va statistika bilan tanishish uchun quyidagi bo'limlardan birini tanlang:\n\n"
                "   <i>Eslatma: Tizim barqaror ishlamoqda.</i>"
            )
            
            keyboard = get_admin_kb(is_main)

            if query:
                # 1. Agar "Orqaga" tugmasi orqali kelgan bo'lsa - tahrirlaymiz
                await query.answer() # "Soat"ni to'xtatish
                await query.edit_message_text(
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            else:
                # 2. Agar /admin komandasi bo'lsa - yangi xabar yuboramiz
                await update.effective_message.reply_text(
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
        else:
            # Ruxsat bo'lmasa
            message = "❌ <b>Sizda ushbu bo'limga kirish huquqi yo'q!</b>"
            if query:
                await query.answer(text=message, show_alert=True)
            else:
                await update.effective_message.reply_text(text=message, parse_mode="HTML")







