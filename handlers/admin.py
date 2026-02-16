import html
from datetime import datetime
from services.user_service import get_user_status
from telegram import  InlineKeyboardButton, InlineKeyboardMarkup, Update
from config import MAIN_ADMIN_ID
from database.db import async_session
from telegram.ext import ContextTypes



# ===================================================================================





# 1. Keyboard funksiyasi (shu fayl ichida bo'lgani xavfsizroq)
def get_admin_kb(is_main=False):
    """Admin panel ichidagi inline tugmalar"""
    buttons = [
        [
            InlineKeyboardButton("📢 Kanallar", callback_data="adm_ch"), 
            InlineKeyboardButton("🎬 Anime control", callback_data="adm_ani_ctrl")
        ],
        [
            InlineKeyboardButton("💎 VIP CONTROL", callback_data="adm_vip_add"), 
            InlineKeyboardButton("📊 Statistika", callback_data="adm_stats")
        ],
        [
            InlineKeyboardButton("🚀 Reklama", callback_data="adm_ads_start"), 
            InlineKeyboardButton("📤 DB Export (JSON)", callback_data="adm_export")
        ]
    ]
    
    if is_main:
        buttons.append([InlineKeyboardButton("👮 Adminlarni boshqarish", callback_data="manage_admins")])
        
    return InlineKeyboardMarkup(buttons)



# ===================================================================================



# 2. Asosiy Handler
async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = update.callback_query # Tugma bosilganini tekshirish
    
    async with async_session() as session:
        # Foydalanuvchi statusini tekshiramiz
        status = await get_user_status(session, user_id, MAIN_ADMIN_ID)
    
        if status in ["main_admin", "admin"]:
            is_main = (status == "main_admin")
            admin_info = "👑 <b>Bosh Admin Paneli</b>" if is_main else "👨‍💻 <b>Admin Paneli</b>"
            
            # Message is not modified xatosini oldini olish uchun vaqt qo'shamiz
            now = datetime.now().strftime("%H:%M:%S")
            
            text = (
                f"{admin_info}\n\n"
                "Botni boshqarish va statistika bilan tanishish uchun quyidagi bo'limlardan birini tanlang:\n\n"
                f"🕒 <i>Oxirgi yangilanish: {now}</i>\n"
                "   <i>Eslatma: Tizim barqaror ishlamoqda.</i>"
            )
            
            keyboard = get_admin_kb(is_main)

            try:
                if query:
                    # 1. "Orqaga" tugmasi orqali kelsa - tahrirlaymiz
                    await query.answer() 
                    await query.edit_message_text(
                        text=text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                else:
                    # 2. /admin komandasi orqali kelsa - yangi xabar
                    await update.effective_message.reply_text(
                        text=text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
            except Exception as e:
                # Agar matn o'zgarmagan bo'lsa (ba'zida milisekundlar farq qilmay qolsa)
                if "Message is not modified" not in str(e):
                    print(f"⚠️ Admin panel xatosi: {e}")
        else:
            # Ruxsat bo'lmasa
            message = "❌ <b>Sizda ushbu bo'limga kirish huquqi yo'q!</b>"
            if query:
                await query.answer(text=message, show_alert=True)
            else:
                await update.effective_message.reply_text(text=message, parse_mode="HTML")







