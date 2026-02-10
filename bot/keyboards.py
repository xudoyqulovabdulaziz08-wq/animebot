from telegram.ext import ConversationHandler, ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, Update
from db import db_pool # Pagination bazadan ma'lumot olishi uchun kerak
from config import logger
from handlers.common import get_user_status


# ===================================================================================


def get_main_kb(status):
    kb = [
        [KeyboardButton("🔍 Anime qidirish 🎬"), KeyboardButton("🔥 Trenddagilar")],
        [KeyboardButton("👤 Shaxsiy Kabinet"), KeyboardButton("🎁 Ballar & VIP")],
        [KeyboardButton("🤝 Muxlislar Klubi"), KeyboardButton("📂 Barcha animelar")],
        [KeyboardButton("✍️ Murojaat & Shikoyat"), KeyboardButton("📖 Qo'llanma ❓")]
    ]
    if status in ["main_admin", "admin"]:
        kb.append([KeyboardButton("🛠 ADMIN PANEL")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def get_admin_kb(is_main=False):
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

def get_cancel_kb():
    return ReplyKeyboardMarkup([[KeyboardButton("⬅️ Orqaga")]], resize_keyboard=True)

async def get_pagination_keyboard(table_name, page=0, per_page=15, prefix="selani_", extra_callback=""):
    # Siz yuborgan pagination kodi (tepada yozilganidek o'zgarishsiz qoladi)
    # Faqat global db_pool o'rniga db.py dan import qilinganidan foydalanadi
    pass 


# ===================================================================================

async def get_pagination_keyboard(table_name, page=0, per_page=15, prefix="selani_", extra_callback=""):
    """
    Bazadagi ma'lumotlarni sahifalab (pagination) ko'rsatish uchun klaviatura.
    SQL darajasida OFFSET va LIMIT ishlatilgani uchun tez ishlaydi.
    """
    offset = page * per_page
    base_prefix = prefix.rstrip('_') + "_"

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Faqat joriy sahifa uchun kerakli ma'lumotlarni olish
                await cur.execute(
                    f"SELECT anime_id, name FROM {table_name} ORDER BY anime_id DESC LIMIT %s OFFSET %s",
                    (per_page, offset)
                )
                current_items = await cur.fetchall()

                # 2. Umumiy elementlar sonini aniqlash (Keyingi tugmasi uchun)
                await cur.execute(f"SELECT COUNT(*) FROM {table_name}")
                res = await cur.fetchone()
                total_count = res[0] if isinstance(res, tuple) else res['COUNT(*)']

        buttons = []
        for item in current_items:
            # item[0] -> id, item[1] -> name
            a_id = item['anime_id'] if isinstance(item, dict) else item[0]
            a_name = item['name'] if isinstance(item, dict) else item[1]
            
            btn_text = f"🎬 {a_name} [ID: {a_id}]"
            buttons.append([InlineKeyboardButton(btn_text, callback_data=f"{base_prefix}{a_id}")])

        # 3. Navigatsiya tugmalari
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"pg_{base_prefix}{page-1}"))
        
        # Hozirgi sahifa ma'lumoti
        total_pages = (total_count + per_page - 1) // per_page
        nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="none"))

        if offset + per_page < total_count:
            nav_buttons.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"pg_{base_prefix}{page+1}"))
        
        if nav_buttons:
            buttons.append(nav_buttons)

        # Orqaga qaytish
        back_call = extra_callback if extra_callback else "back_to_ctrl"
        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data=back_call)])
        
        return InlineKeyboardMarkup(buttons)

    except Exception as e:
        logger.error(f"Pagination error: {e}")
        return None


# ===================================================================================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha jarayonlarni to'xtatadi, ma'lumotlarni tozalaydi va menyuga qaytaradi"""
    user_id = update.effective_user.id
    
    # 1. Foydalanuvchining ushbu sessiyadagi vaqtinchalik ma'lumotlarini o'chirish
    # Bu juda muhim: anime_id yoki reklama targeti kabi ma'lumotlar saqlanib qolmasligi kerak
    context.user_data.clear()

    # 2. Foydalanuvchi statusini aniqlash
    status = await get_user_status(user_id)

    # 3. Javob xabari
    text = "🔙 <b>Jarayon bekor qilindi.</b>\n\nSiz asosiy menyuga qaytdingiz. Davom etish uchun kerakli bo'limni tanlang."
    
    # Agar xabar callback orqali kelsa (tugma bosilsa)
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text, reply_markup=get_main_kb(status), parse_mode="HTML")
    else:
        # Agar foydalanuvchi /cancel komandasini yozsa
        await update.message.reply_text(text, reply_markup=get_main_kb(status), parse_mode="HTML")

    # 4. ConversationHandler'dan butunlay chiqish
    return ConversationHandler.END

#===================================================================================


async def show_donate_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Donat qilish menyusi va tanlovni qayd etish"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # 1. Matnni HTML formatda boyitish
    text = (
        "❤️ <b>BOT RIVOJIGA HISSA QO'SHING!</b>\n\n"
        "Sizning xayriyangiz bizga server xarajatlarini qoplash va "
        "yangi animelarni sifatli formatda yuklashga yordam beradi. "
        "Har bir donat uchun <b>eksklyuziv</b> sovg'alarimiz bor! ✨\n\n"
        "💎 <b>Paketni tanlang:</b>"
    )
    
    # 2. Tugmalarni shakllantirish
    keyboard = [
        [InlineKeyboardButton("💳 5 000 so'm (500 ball)", callback_data="don_5000")],
        [InlineKeyboardButton("💎 20 000 so'm (VIP 1 oy + 1000 ball)", callback_data="don_20000")],
        [InlineKeyboardButton("👑 100 000 so'm (Cheksiz VIP + Homiy)", callback_data="don_100000")],
        [InlineKeyboardButton("🌟 400 000 so'm (Oltin Homiy)", callback_data="don_400000")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        # 3. Xabarni yuborish yoki yangilash
        if query:
            await query.answer()
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Donate menu error: {e}")
        await update.message.reply_text("🛑 To'lov menyusini yuklashda xatolik yuz berdi.")


#===================================================================================

async def show_redeem_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ballarni xizmatlarga ayirboshlash menyusi"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    try:
        # 1. Asinxron bazadan joriy ballarni olish
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                await cur.execute("SELECT bonus FROM users WHERE user_id = %s", (uid,))
                user = await cur.fetchone()

        # Agar foydalanuvchi topilmasa (kamdan-kam holat), 0 ball beramiz
        points = user['bonus'] if user else 0
        
        # 2. Matnni shakllantirish (HTML orqali vizual boyitilgan)
        text = (
            f"💰 <b>SIZNING HISOBINGIZ:</b> <code>{points}</code> ball\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Ballaringizni bot imtiyozlariga almashtiring:\n\n"
            f"<i>Eslatma: VIP status reklamalarni o'chiradi va eksklyuziv animelarga yo'l ochadi.</i>"
        )
        
        # 3. Ayirboshlash tugmalari
        keyboard = [
            [InlineKeyboardButton("📢 1 kun Reklama (250 ball)", callback_data="redeem_ad_1")],
            [InlineKeyboardButton("📢 3 kun Reklama (500 ball)", callback_data="redeem_ad_3")],
            [InlineKeyboardButton("💎 1 oy VIP (1000 ball)", callback_data="redeem_vip_1")],
            [InlineKeyboardButton("💎 3 oy VIP (2500 ball)", callback_data="redeem_vip_3")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)

        # 4. Xabarni chiqarish (Callback yoki Oddiy xabar)
        if query:
            await query.answer()
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Redeem menu error: {e}")
        error_text = "🛑 Hisob ma'lumotlarini yuklashda xatolik yuz berdi."
        if query:
            await query.answer(error_text, show_alert=True)
        else:
            await update.message.reply_text(error_text)


#===================================================================================


async def rate_anime_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchiga reyting berish tugmalarini ko'rsatish"""
    query = update.callback_query
    # Callback format: rate_ani_123
    anime_id = query.data.split("_")[-1]
    
    # 5 ballik tizim (Telegram interfeysi uchun qulayroq)
    stars = [InlineKeyboardButton(f"{i} ⭐", callback_data=f"rate_set_{anime_id}_{i}") for i in range(1, 6)]
    keyboard = [stars, [InlineKeyboardButton("🔙 Orqaga", callback_data=f"show_ani_{anime_id}")]]
    
    await query.answer()
    await query.edit_message_caption(
        caption=(
            "⭐ <b>REYTING BERISH</b>\n\n"
            "Ushbu anime sizga yoqdimi? O'z bahoingizni bering. "
            "Sizning ovozingiz boshqa foydalanuvchilarga tanlov qilishda yordam beradi!"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
# ----------------- CALLBACK HANDLER (MUHIM QISM) -----------------