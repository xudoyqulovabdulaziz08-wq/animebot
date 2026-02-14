from telegram import Update
from telegram.ext import ContextTypes
from database.db import async_session
from services.user_service import register_user, get_user_status
from keyboards.default import get_main_kb # Menyuni import qilamiz
from config import MAIN_ADMIN_ID # Adminni tekshirish uchun

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    tg_user = update.effective_user
    
    async with async_session() as session:
        try:
            # 1. Foydalanuvchini ro'yxatdan o'tkazish yoki ma'lumotni yangilash
            user, is_new = await register_user(session, tg_user)
            
            # 2. Statusni aniqlash (Menyu tugmalari uchun)
            status = await get_user_status(session, tg_user.id, MAIN_ADMIN_ID)
            
            # 3. Statusga mos menyuni olish
            reply_markup = get_main_kb(status)

            if is_new:
                text = (
                    f"👋 Xush kelibsiz, {tg_user.full_name}!\n"
                    f"Siz muvaffaqiyatli ro'yxatdan o'tdingiz.\n\n"
                    f"🆔 ID: `{user.user_id}`\n"
                    f"🏆 Ballar: {user.points}\n"
                    f"✨ Status: {status.upper()}"
                )
            else:
                text = (
                    f"Sizni yana ko'rib turganimizdan xursandmiz, {tg_user.full_name}! ✨\n\n"
                    f"📊 **Status:** {status.upper()}\n"
                    f"💰 **Ballar:** {user.points}\n"
                    f"📅 **A'zo bo'lgan sana:** {user.joined_at.strftime('%d.%m.%Y')}"
                )
            
            # 4. Xabarni menyu bilan birga yuborish
            await update.message.reply_text(
                text, 
                reply_markup=reply_markup, 
                parse_mode="Markdown"
            )
            
        except Exception as e:
            print(f"❌ Xatolik: {e}")
            await update.message.reply_text("Tizimda texnik xatolik yuz berdi.")



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





