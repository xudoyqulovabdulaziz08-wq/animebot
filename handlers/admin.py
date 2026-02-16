from telegram.ext import ContextTypes
from services.user_service import get_user_status
from keyboard.admin_kb import get_admin_kb
from telegram import Update
from config import MAIN_ADMIN_ID
from database.db import async_session



# ===================================================================================


async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = update.callback_query
    
    async with async_session() as session:
        status = await get_user_status(session, user_id, MAIN_ADMIN_ID)
    
        if status in ["main_admin", "admin"]:
            is_main = (status == "main_admin")
            admin_info = "👑 <b>Bosh Admin Paneli</b>" if is_main else "👨‍💻 <b>Admin Paneli</b>"
            
            # Har safar matn ozgina farq qilishi uchun vaqt qo'shamiz (Message is not modified xatosini oldini oladi)
            now = datetime.now().strftime("%H:%M:%S")
            text = (
                f"{admin_info}\n\n"
                f"Bo'limni tanlang:\n"
                f"🕒 Yangilandi: {now}"
            )
            
            keyboard = get_admin_kb(is_main)

            try:
                if query:
                    await query.answer()
                    await query.edit_message_text(
                        text=text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                else:
                    await update.effective_message.reply_text(
                        text=text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
            except Exception as e:
                # AGAR XATO BERSA, SHU YERDA ANIQLAYMIZ
                error_msg = str(e)
                print(f"❌ Telegram xatosi: {error_msg}")
                
                # Agar HTMLdan bo'lsa, oddiy matnda yuboramiz
                if "Can't parse entities" in error_msg:
                    safe_text = "👑 Admin Paneli (Formatlash xatosi bor)"
                    if query:
                        await query.edit_message_text(text=safe_text, reply_markup=keyboard)
                    else:
                        await update.effective_message.reply_text(text=safe_text, reply_markup=keyboard)
                
                # Agar matn o'zgarmagan bo'lsa, foydalanuvchiga bildirishnoma ko'rsatamiz
                elif "Message is not modified" in error_msg:
                    if query:
                        await query.answer("Siz allaqachon shu bo'limdasiz.")





