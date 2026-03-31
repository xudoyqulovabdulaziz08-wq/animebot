
import logging
logger = logging.getLogger(__name__)
from sqlalchemy import select, text, update
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from core import SessionLocal, sync_user
from models import Channel, DBUser
from utils import check_subscription, get_or_create_user, increment_referral
from html import escape


#=======================================================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    if not tg_user:
        return

    message = update.message or (update.callback_query.message if update.callback_query else None)
    if not message:
        return

    if not await enforce_subscription(update, context):
        return

    user, is_new = await get_or_create_user(tg_user.id, tg_user.username)
    if not user:
        return

    if is_new and context.args and context.args[0].isdigit():
        referrer_id = int(context.args[0])

        if referrer_id != tg_user.id:
            async with SessionLocal() as session:
                success = await increment_referral(session, referrer_id, 100)

                if isinstance(success, dict):
                    try:
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text="🎉 <b>Yangi referal!</b>\nSizga 100 ball qo'shildi."
                        )
                    except:
                        pass

    text = (
        f"💫 Salom, {tg_user.mention_html()}!\n"
        f"🆔 ID: <code>{tg_user.id}</code>\n"
        f"🚀 Status: <b>{user['st']}</b>\n"
        f"💰 Ball: <b>{user['pts']}</b>\n\n"
        f"Kerakli bo'limni tanlang:"
    )

    try:
        if update.callback_query:
            await message.edit_text(text, reply_markup=menu_keyboard(user["st"]))
        else:
            await message.reply_text(text, reply_markup=menu_keyboard(user["st"]))
    except:
        await message.reply_text(text, reply_markup=menu_keyboard(user["st"]))
  
#=======================================================================================================

async def enforce_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    if not tg_user:
        return False

    # ================= DB =================
    async with SessionLocal() as session:
        result = await session.execute(
            select(Channel).where(Channel.is_active.is_(True))
        )
        active_channels = result.scalars().all()

    # Agar majburiy kanal bo'lmasa
    if not active_channels:
        return True

    # ================= CHECK =================
    is_subscribed = await check_subscription(
        tg_user.id,
        active_channels,
        context.bot
    )

    if is_subscribed:
        return True

    # ================= UI =================
    keyboard = [
        [InlineKeyboardButton(text=ch.title, url=ch.url)]
        for ch in active_channels
    ]
    keyboard.append([
        InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")
    ])

    text = "<b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:</b>"

    msg = update.message or update.callback_query.message

    try:
        if update.callback_query:
            await update.callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await msg.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        logger.warning(f"Subscription message error: {e}")

    return False
#=======================================================================================================

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Tekshirilmoqda...", show_alert=False) # "Clock" belgisini yo'qotadi
    
    # Startni qayta chaqiramiz, u o'zi obunani tekshirib ketaveradi
    await start(update, context)

#=======================================================================================================

ADMIN_STATUSES = {"main_admin", "admin"}
VIP_STATUS = "vip"

def menu_keyboard(status: str):
    status = status or "user"

    kb = [
        [KeyboardButton("🔍 Anime qidirish 🎬"), KeyboardButton("🔥 Trenddagilar")],
        [KeyboardButton("👤 Shaxsiy Kabinet"), KeyboardButton("🎁 Ballar & VIP")],
        [KeyboardButton("🤝 Muxlislar Klubi"), KeyboardButton("📂 Barcha animelar")],
        [KeyboardButton("✍️ Murojaat & Shikoyat"), KeyboardButton("📖 Qo'llanma ❓")]
    ]

    # ================= ADMIN =================
    if status in ADMIN_STATUSES:
        kb.insert(0, [KeyboardButton("🛠 ADMIN PANEL")])

    # ================= VIP =================
    if status == VIP_STATUS:
        kb.insert(1, [KeyboardButton("🌟 VIP IMKONIYATLAR 🌟")])

    return ReplyKeyboardMarkup(
        kb,
        resize_keyboard=True,
        input_field_placeholder="Kerakli bo'limni tanlang..."
    )
#=======================================================================================================

async def health_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("OK")


#=======================================================================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"❌ Xatolik: {context.error}", exc_info=context.error)
    # Agar foydalanuvchiga xabar yuborish kerak bo'lsa:
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("Kutilmagan xatolik yuz berdi. Birozdan so'ng urinib ko'ring.")


#=======================================================================================================

async def pre_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha xabarlardan oldin ishlaydigan mantiq"""
    if update.effective_user:
        # Userni bazaga yozish/yangilash (utils orqali)
        await sync_user(update.effective_user.id)


#=======================================================================================================

