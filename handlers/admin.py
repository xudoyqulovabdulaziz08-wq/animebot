from telegram.ext import ContextTypes
from services.user_service import get_user_status
from keyboard.admin_kb import get_admin_kb
from telegram import Update


async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Foydalanuvchi statusini tekshiramiz
    status = await get_user_status(user_id)
    
    if status in ["main_admin", "admin"]:
        is_main = (status == "main_admin")
        
        # Log yozish qismi (INSERT INTO admin_logs) butunlay olib tashlandi 🚀
        
        admin_info = "👑 <b>Bosh Admin Paneli</b>" if is_main else "👨‍💻 <b>Admin Paneli</b>"
        text = (
            f"{admin_info}\n\n"
            "Botni boshqarish va statistika bilan tanishish uchun quyidagi bo'limlardan birini tanlang:\n\n"
            "<i>Eslatma: Tizim barqaror ishlamoqda.</i>"
        )
        
        await update.message.reply_text(
            text=text,
            reply_markup=get_admin_kb(is_main),
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("❌ <b>Sizda ushbu bo'limga kirish huquqi yo'q!</b>", parse_mode="HTML")
