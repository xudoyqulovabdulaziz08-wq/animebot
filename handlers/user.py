from telegram import Update
from telegram.ext import ContextTypes
from database.db import async_session   # db.py-dagi sessiya fabrikasi
from services.user_service import register_user

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    tg_user = update.effective_user
    
    async with async_session() as session:
        try:
            # register_user funksiyasi bazadan foydalanuvchi obyektini qaytaradi
            user, is_new = await register_user(session, tg_user)
            
            if is_new:
                # Yangi foydalanuvchi uchun xabar
                text = (
                    f"👋 Xush kelibsiz, {tg_user.full_name}!\n"
                    f"Siz muvaffaqiyatli ro'yxatdan o'tdingiz.\n\n"
                    f"🆔 Sizning bazadagi ID: `{user.user_id}`\n"
                    f"🏆 Ballaringiz: {user.points}"
                )
            else:
                # Bazada mavjud foydalanuvchi uchun xabar
                # Bu yerda biz bazadan kelgan 'points' va 'status'ni ko'rsatamiz
                text = (
                    f"Sizni yana ko'rib turganimizdan xursandmiz, {tg_user.full_name}! ✨\n\n"
                    f"📊 **Sizning statusingiz:** {user.status.upper()}\n"
                    f"💰 **Joriy ballaringiz:** {user.points}\n"
                    f"📅 **A'zo bo'lgan sana:** {user.joined_at.strftime('%d.%m.%Y')}"
                )
            
            await update.message.reply_text(text, parse_mode="Markdown")
            
        except Exception as e:
            print(f"❌ DB ulanish xatosi: {e}")
            await update.message.reply_text("Bazaga ulanishda muammo yuz berdi. Iltimos, config va db.py ni tekshiring.")


