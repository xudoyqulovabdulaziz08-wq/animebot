from telegram import Update
from telegram.ext import ContextTypes
from database.db import async_session
from services.user_service import register_user, get_user_status
from keyboard.default import get_main_kb # Menyuni import qilamiz
from config import MAIN_ADMIN_ID # Adminni tekshirish uchun

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    tg_user = update.effective_user
    
    async with async_session() as session:
        try:
            user, is_new = await register_user(session, tg_user)
            status = await get_user_status(session, tg_user.id, MAIN_ADMIN_ID)
            reply_markup = get_main_kb(status)

            # HTML formatiga o'tkazdik (Xavfsizroq)
            if is_new:
                text = (
                    f"👋 Xush kelibsiz, <b>{tg_user.full_name}</b>!\n"
                    f"Siz muvaffaqiyatli ro'yxatdan o'tdingiz.\n\n"
                    f"🆔 ID: <code>{user.user_id}</code>\n"
                    f"🏆 Ballar: <b>{user.points}</b>\n"
                    f"✨ Status: <b>{status.upper()}</b>"
                )
            else:
                text = (
                    f"Sizni yana ko'rib turganimizdan xursandmiz, <b>{tg_user.full_name}</b>! ✨\n\n"
                    f"📊 <b>Status:</b> {status.upper()}\n"
                    f"💰 <b>Ballar:</b> {user.points}\n"
                    f"📅 <b>A'zo bo'lgan sana:</b> {user.joined_at.strftime('%d.%m.%Y')}"
                )
            
            await update.message.reply_text(
                text, 
                reply_markup=reply_markup, 
                parse_mode="HTML" # HTML ga o'zgartirildi
            )
            
        except Exception as e:
            print(f"❌ Xatolik: {e}")
            await update.message.reply_text("Tizimda texnik xatolik yuz berdi.")

async def cabinet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    async with async_session() as session:
        user, _ = await register_user(session, update.effective_user)
        status = await get_user_status(session, user_id, MAIN_ADMIN_ID)
        
        text = (
            f"👤 <b>Shaxsiy Kabinet</b>\n\n"
            f"🆔 ID: <code>{user.user_id}</code>\n"
            f"🎭 Status: <b>{status.upper()}</b>\n"
            f"💰 Ballar: <b>{user.points}</b>\n"
            f"👥 Takliflar: <b>{user.referral_count}</b> ta\n"
            f"📅 Qo'shilgan sana: {user.joined_at.strftime('%d.%m.%Y')}\n"
        )
        
        if user.status == 'vip' and user.vip_expire_date:
            text += f"💎 VIP muddati: <b>{user.vip_expire_date.strftime('%d.%m.%Y')}</b>"

        # BU YERDA HAM HTML BO'LISHI SHART!
        await update.message.reply_text(text, parse_mode='HTML')









