from telegram import Update
from telegram.ext import ContextTypes
from database.db import async_session   # db.py-dagi sessiya fabrikasi
from services.user_service import register_user, get_user_status
from keyboards.default import get_main_kb
from config import MAIN_ADMIN_ID


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



async def cabinet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    async with async_session() as session:
        # Foydalanuvchi ma'lumotlarini bazadan olamiz
        user, _ = await register_user(session, update.effective_user)
        status = await get_user_status(session, user_id, MAIN_ADMIN_ID)
        
        text = (
            f"👤 **Sizning Kabinetingiz**\n\n"
            f"🆔 ID: `{user.user_id}`\n"
            f"🎭 Status: **{status.upper()}**\n"
            f"💰 Ballar: `{user.points}`\n"
            f"👥 Takliflar: `{user.referral_count}` ta\n"
            f"📅 Ro'yxatdan o'tdingiz: {user.joined_at.strftime('%d.%m.%Y')}\n"
        )
        
        if user.status == 'vip' and user.vip_expire_date:
            text += f"💎 VIP muddati: {user.vip_expire_date.strftime('%d.%m.%Y')}"

        await update.message.reply_text(text, parse_mode='Markdown')




