from telegram import Update
from telegram.ext import ContextTypes
from database.db import async_session
from services.user_service import register_user

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    tg_user = update.effective_user
    
    # Har bir start buyrug'i uchun alohida sessiya
    async with async_session() as session:
        try:
            user, is_new = await register_user(session, tg_user)
            
            if is_new:
                text = (
                    f"👋 Xush kelibsiz, {tg_user.full_name}!\n\n"
                    f"🎬 Bizning bot orqali eng sara animelarni "
                    f"o'zbek tilida tomosha qilishingiz mumkin."
                )
            else:
                text = f"Qayta ko'rishganimizdan xursandmiz, {tg_user.full_name}! ✨"
            
            await update.message.reply_text(text)
            
        except Exception as e:
            # Xatolik yuz bersa logga yozamiz (bu o'rgimchak to'rini oldini oladi)
            print(f"Start Error: {e}")
            await update.message.reply_text("Tizimda kichik xatolik yuz berdi. Birozdan so'ng urinib ko'ring.")
