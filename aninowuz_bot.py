import os
import logging
import mysql.connector
import asyncio
import datetime
import json
from flask import Flask
from threading import Thread
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes, ConversationHandler
)

# ====================== WEB SERVICE (RENDER UCHUN) ======================
app = Flask('')

@app.route('/')
def home():
    return "Bot is running..."

def run():
    # Render avtomatik beradigan PORT-ni oladi, bo'lmasa 8080 ishlatadi
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

# ====================== XAVFSIZ KONFIGURATSIYA ======================
# Token va parollar kod ichidan olib tashlandi. 
# Ularni Render Dashboard -> Settings -> Environment Variables qismiga qo'shing.

TOKEN = os.getenv("TOKEN") 
MAIN_ADMIN_ID = int(os.getenv("ADMIN_ID", 8244870375))
ADVERTISING_PASSWORD = os.getenv("ADS_PASS", "2009")

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", 27624)), # Port bo'sh bo'lsa standart 27624 ni oladi
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "database": os.getenv("DB_NAME"),
    "autocommit": True,
    "ssl_disabled": False,
    "ssl_mode": "REQUIRED" # SSL ulanishni majburiy qilish
}

# ====================== CONVERSATION STATES ======================
# Yangi professional qidiruv mantiqi uchun holatlar yangilandi
(
    A_ADD_CH,            # 0: Kanal qo'shish
    A_REM_CH,            # 1: Kanal o'chirish
    A_ADD_ADM,           # 2: Yangi admin ID sini qabul qilish
    A_CONFIRM_REM_ADM,   # 3: Adminni o'chirishni tasdiqlash
    A_ADD_VIP,           # 4: VIP foydalanuvchi qo'shish
    A_REM_VIP,           # 5: VIP-ni bekor qilish
    A_ADD_ANI_POSTER,    # 6: Anime posterini qabul qilish
    A_ADD_ANI_DATA,      # 7: Anime ma'lumotlarini qabul qilish
    A_SEND_ADS_PASS,     # 8: Reklama parolini tekshirish
    A_SEND_ADS_MSG,      # 9: Reklama xabarini tarqatish
    A_SEARCH_BY_ID,      # 10: ID orqali qidirish (YANGI)
    A_SEARCH_BY_NAME     # 11: Nomi orqali qidirish (YANGI)
) = range(12)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ====================== MA'LUMOTLAR BAZASI ======================
def get_db():
    try:
        # Tizim o'zgaruvchilaridan olingan ma'lumotlar bilan ulanish
        conn = mysql.connector.connect(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            ssl_disabled=False  # Aiven SSL talab qiladi
        )
        return conn
    except mysql.connector.Error as err:
        logger.error(f"❌ Ma'lumotlar bazasiga ulanishda xato: {err}")
        return None

def init_db():
    conn = get_db()
    if not conn:
        logger.error("❌ Ma'lumotlar bazasiga ulanish imkonsiz!")
        return
    
    cur = conn.cursor()
    try:
        # Foydalanuvchilar jadvali
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY, 
            joined_at DATETIME, 
            bonus INT DEFAULT 0,
            status VARCHAR(20) DEFAULT 'user'
        )""")

        # Animelar asosiy jadvali
        cur.execute("""CREATE TABLE IF NOT EXISTS anime_list (
            anime_id VARCHAR(50) PRIMARY KEY, 
            name VARCHAR(255), 
            poster_id TEXT
        )""")

        # Anime qismlari jadvali
        cur.execute("""CREATE TABLE IF NOT EXISTS anime_episodes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            anime_id VARCHAR(50),
            episode INT,
            lang VARCHAR(50),
            file_id TEXT,
            FOREIGN KEY (anime_id) REFERENCES anime_list(anime_id) ON DELETE CASCADE
        )""")

        # Adminlar jadvali (Qo'shimcha adminlar uchun)
        cur.execute("""CREATE TABLE IF NOT EXISTS admins (
            user_id BIGINT PRIMARY KEY,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")

        # Majburiy obuna kanallari jadvali
        cur.execute("""CREATE TABLE IF NOT EXISTS channels (
            id INT AUTO_INCREMENT PRIMARY KEY, 
            username VARCHAR(255)
        )""")
        
        conn.commit()
        print("✅ Ma'lumotlar bazasi jadvallari tayyor.")
    except mysql.connector.Error as err:
        print(f"❌ Jadvallarni yaratishda xato: {err}")
    finally:
        cur.close()
        conn.close()
        

# ... (Bu yerda handle_callback, start va boshqa funksiyalar davom etadi)

# ====================== YORDAMCHI FUNKSIYALAR ======================
async def get_user_status(uid):
    """Foydalanuvchi statusini aniqlash (Main Admin, Admin, VIP yoki Oddiy foydalanuvchi)"""
    if uid == MAIN_ADMIN_ID: 
        return "main_admin"
    
    conn = get_db()
    if not conn: return "user"
    
    cur = conn.cursor()
    try:
        # 1. Avval 'admins' jadvalini tekshiramiz
        cur.execute("SELECT user_id FROM admins WHERE user_id=%s", (uid,))
        if cur.fetchone():
            return "admin"
            
        # 2. Keyin 'users' jadvalidagi umumiy statusni (vip/user) tekshiramiz
        cur.execute("SELECT status FROM users WHERE user_id=%s", (uid,))
        res = cur.fetchone()
        return res[0] if res else "user"
    except Exception as e:
        logger.error(f"Status aniqlashda xato: {e}")
        return "user"
    finally:
        cur.close()
        conn.close()

async def check_sub(uid, bot):
    """Majburiy obunani tekshirish"""
    conn = get_db()
    if not conn: return []
    
    cur = conn.cursor()
    cur.execute("SELECT username FROM channels")
    channels = cur.fetchall()
    cur.close()
    conn.close()
    
    not_joined = []
    for (ch,) in channels:
        try:
            # Username formatini to'g'irlash (@ belgisini tekshirish)
            target = ch if ch.startswith('@') or ch.startswith('-100') else f"@{ch}"
            member = await bot.get_chat_member(target, uid)
            if member.status not in ['member', 'administrator', 'creator']: 
                not_joined.append(ch)
        except Exception: 
            not_joined.append(ch)
    return not_joined

# ====================== KLAVIATURALAR ======================
async def get_main_kb(uid):
    """Asosiy menyu klaviaturasi"""
    status = await get_user_status(uid)
    kb = [
        [KeyboardButton("🔍 Anime qidirish 🎬")],
        [KeyboardButton("🎁 Bonus ballarim 💰"), KeyboardButton("💎 VIP bo'lish ⭐")],
        [KeyboardButton("📜 Barcha anime ro'yxati 📂"), KeyboardButton("📖 Qo'llanma ❓")]
    ]
    # Agar foydalanuvchi admin bo'lsa, admin panel tugmasi qo'shiladi
    if status in ["main_admin", "admin"]:
        kb.append([KeyboardButton("🛠 ADMIN PANEL")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def get_admin_kb(is_main=False):
    """Admin panel ichidagi inline tugmalar"""
    buttons = [
        [
            InlineKeyboardButton("📢 Kanallar", callback_data="adm_ch"), 
            InlineKeyboardButton("🎬 Anime Qo'shish", callback_data="adm_ani_add")
        ],
        [
            InlineKeyboardButton("💎 VIP Qo'shish", callback_data="adm_vip_add"), 
            InlineKeyboardButton("📊 Statistika", callback_data="adm_stats")
        ],
        [
            InlineKeyboardButton("🚀 Reklama", callback_data="adm_ads_start"), 
            InlineKeyboardButton("📤 DB Export (JSON)", callback_data="adm_export")
        ]
    ]
    
    # Faqat MAIN_ADMIN uchun adminlarni boshqarish menyusi ko'rinadi
    if is_main:
        buttons.append([InlineKeyboardButton("👮 Adminlarni boshqarish", callback_data="manage_admins")])
        
    return InlineKeyboardMarkup(buttons)
    
    
# ====================== ASOSIY ISHLOVCHILAR ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = get_db()
    if conn:
        cur = conn.cursor()
        # Foydalanuvchini bazaga qo'shish
        cur.execute("INSERT IGNORE INTO users (user_id, joined_at, status) VALUES (%s, %s, 'user')", 
                    (uid, datetime.datetime.now()))
        conn.commit(); cur.close(); conn.close()
    
    # Majburiy obunani tekshirish
    not_joined = await check_sub(uid, context.bot)
    if not_joined:
        btn = [[InlineKeyboardButton(f"Obuna bo'lish ➕", url=f"https://t.me/{c.replace('@','')}") ] for c in not_joined]
        btn.append([InlineKeyboardButton("Tekshirish ✅", callback_data="recheck")])
        return await update.message.reply_text("👋 Botdan foydalanish uchun kanallarga a'zo bo'ling:", reply_markup=InlineKeyboardMarkup(btn))
    
    await update.message.reply_text("✨ Xush kelibsiz! Anime olamiga marhamat.", reply_markup=await get_main_kb(uid))

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    status = await get_user_status(uid)
    await query.answer()

    # --- OBUNANI QAYTA TEKSHIRISH ---
    if data == "recheck":
        if not await check_sub(uid, context.bot):
            await query.message.delete()
            await context.bot.send_message(uid, "Tabriklaymiz! ✅ Obuna tasdiqlandi.", reply_markup=await get_main_kb(uid))
        else:
            await query.answer("❌ Hali hamma kanallarga a'zo emassiz!", show_alert=True)
        return

    # --- PRO QIDIRUV TIZIMI MANTIQI ---
    if data == "search_type_id":
        kb = [[InlineKeyboardButton("❌ Qidirishni bekor qilish", callback_data="cancel_search")]]
        await query.edit_message_text("🆔 **Anime kodini (ID) yuboring:**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return A_SEARCH_BY_ID

    elif data == "search_type_name":
        kb = [[InlineKeyboardButton("❌ Qidirishni bekor qilish", callback_data="cancel_search")]]
        await query.edit_message_text("🔎 **Anime nomini kiriting (masalan: Naruto):**", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return A_SEARCH_BY_NAME

    elif data == "cancel_search":
        await query.message.delete()
        await context.bot.send_message(uid, "❌ Qidiruv bekor qilindi.", reply_markup=await get_main_kb(uid))
        return ConversationHandler.END

    # Admin bo'lmaganlar uchun pastki qismlarni yopish
    if status not in ["main_admin", "admin"]: 
        return

    # --- KANALLARNI BOSHQARISH ---
    if data == "adm_ch":
        kb = [[InlineKeyboardButton("➕ Qo'shish", callback_data="add_channel_start"), 
               InlineKeyboardButton("❌ O'chirish", callback_data="rem_channel_start")]]
        await query.edit_message_text("📢 Majburiy obuna kanallarini boshqarish:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "add_channel_start":
        await query.message.reply_text("➕ Yangi kanal username-ini yuboring (masalan: @kanal_nomi):")
        return A_ADD_CH

    elif data == "rem_channel_start":
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT id, username FROM channels")
        chs = cur.fetchall(); cur.close(); conn.close()
        if not chs:
            await query.message.reply_text("❌ Hozircha kanallar yo'q.")
            return
        kb = [[InlineKeyboardButton(f"🗑 {c[1]}", callback_data=f"final_rem_ch_{c[0]}")] for c in chs]
        await query.edit_message_text("O'chirmoqchi bo'lgan kanalni tanlang:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("final_rem_ch_"):
        cid = data.replace("final_rem_ch_", "")
        conn = get_db(); cur = conn.cursor()
        cur.execute("DELETE FROM channels WHERE id=%s", (cid,))
        conn.commit(); cur.close(); conn.close()
        await query.edit_message_text("✅ Kanal ro'yxatdan o'chirildi!")

    # --- ADMINLARNI BOSHQARISH (FAQAT MAIN ADMIN) ---
    elif data == "manage_admins":
        if status != "main_admin":
            await query.answer("❌ Bu bo'lim faqat asosiy admin uchun!", show_alert=True)
            return
        kb = [
            [InlineKeyboardButton("➕ Admin Qo'shish", callback_data="add_admin_start")],
            [InlineKeyboardButton("📜 Adminlar ro'yxati", callback_data="list_admins")],
            [InlineKeyboardButton("🗑 Admin O'chirish", callback_data="rem_admin_start")]
        ]
        await query.edit_message_text("👮 Adminlarni boshqarish paneli:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "add_admin_start":
        await query.message.reply_text("🆔 Yangi admin bo'ladigan foydalanuvchi ID raqamini yuboring:")
        return A_ADD_ADM

    elif data == "list_admins":
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT user_id FROM admins")
        admins = cur.fetchall(); cur.close(); conn.close()
        text = "👮 **Adminlar ro'yxati:**\n\n"
        text += "\n".join([f"• `{a[0]}`" for a in admins]) if admins else "Hozircha qo'shimcha adminlar yo'q."
        await query.message.reply_text(text, parse_mode="Markdown")

    elif data == "rem_admin_start":
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT user_id FROM admins")
        admins = cur.fetchall(); cur.close(); conn.close()
        if not admins:
            await query.message.reply_text("O'chirish uchun adminlar yo'q.")
            return
        kb = [[InlineKeyboardButton(f"🗑 {a[0]}", callback_data=f"pre_rem_adm_{a[0]}")] for a in admins]
        await query.edit_message_text("🗑 O'chirmoqchi bo'lgan adminni tanlang:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("pre_rem_adm_"):
        aid = data.replace("pre_rem_adm_", "")
        kb = [[InlineKeyboardButton("✅ Ha, o'chirilsin", callback_data=f"final_rem_adm_{aid}"),
               InlineKeyboardButton("❌ Yo'q", callback_data="manage_admins")]]
        await query.edit_message_text(f"❓ {aid} ni admindan bo'shatmoqchimisiz?", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("final_rem_adm_"):
        aid = data.replace("final_rem_adm_", "")
        conn = get_db(); cur = conn.cursor()
        cur.execute("DELETE FROM admins WHERE user_id=%s", (aid,))
        conn.commit(); cur.close(); conn.close()
        await query.edit_message_text("✅ Admin o'chirildi!")

    # --- BOSHQA ADMIN TUGMALARI ---
    elif data == "adm_ani_add":
        await query.message.reply_text("1️⃣ Anime uchun POSTER (rasm) yuboring:")
        return A_ADD_ANI_POSTER

    elif data == "adm_stats":
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        u_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE status='vip'")
        v_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM admins")
        a_count = cur.fetchone()[0]
        cur.close(); conn.close()
        text = f"📊 **Bot Statistikasi:**\n\n👤 Foydalanuvchilar: {u_count}\n💎 VIP a'zolar: {v_count}\n👮 Adminlar: {a_count + 1}"
        await query.message.reply_text(text, parse_mode="Markdown")

    elif data == "adm_vip_add":
        await query.message.reply_text("💎 VIP qilmoqchi bo'lgan foydalanuvchi ID sini yuboring:")
        return A_ADD_VIP

    elif data == "adm_export":
        return await export_all_anime(update, context)

    elif data == "adm_ads_start":
        await query.message.reply_text("🔐 Reklama paneliga kirish uchun parolni kiriting:")
        return A_SEND_ADS_PASS
        
    
# ====================== ANIME QIDIRISH VA PAGINATION (TUZATILDI) ======================

async def search_anime_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anime nomi yoki ID bo'yicha qidirish mantiqi"""
    text = update.message.text.strip()
    uid = update.effective_user.id
    
    conn = get_db()
    if not conn:
        await update.message.reply_text("❌ Bazaga ulanishda xato.")
        return ConversationHandler.END

    cur = conn.cursor(dictionary=True)
    
    # ID yoki Nom bo'yicha qidirish
    if text.isdigit():
        cur.execute("SELECT * FROM anime_list WHERE anime_id=%s", (text,))
    else:
        cur.execute("SELECT * FROM anime_list WHERE name LIKE %s", (f"%{text}%",))
    
    anime = cur.fetchone()
    
    if not anime:
        await update.message.reply_text(
            "😔 Kechirasiz, bunday anime topilmadi.\n\n"
            "Iltimos, nomini to'g'ri yozganingizni yoki ID raqam xato emasligini tekshiring.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Qidirishni to'xtatish", callback_data="cancel_search")]])
        )
        return # User yana urinib ko'rishi uchun state saqlanib qoladi

    cur.execute("SELECT episode FROM anime_episodes WHERE anime_id=%s ORDER BY episode ASC", (anime['anime_id'],))
    episodes = cur.fetchall()
    cur.close(); conn.close()

    if not episodes:
        # get_main_kb funksiyasi async emas, shuning uchun await olib tashlandi
        await update.message.reply_text("Bu animega hali qismlar joylanmagan.", reply_markup=get_main_kb(uid))
        return ConversationHandler.END

    # Pagination Keyboard (Dastlabki 10 qism)
    keyboard = []
    row = []
    for ep in episodes[:10]:
        row.append(InlineKeyboardButton(str(ep['episode']), callback_data=f"get_ep_{anime['anime_id']}_{ep['episode']}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    
    if len(episodes) > 10:
        keyboard.append([InlineKeyboardButton("Keyingi ➡️", callback_data=f"page_{anime['anime_id']}_10")])

    await update.message.reply_photo(
        photo=anime['poster_id'],
        caption=f"🎬 **{anime['name']}**\n🆔 ID: `{anime['anime_id']}`\n\nQismni tanlang 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def get_episode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qism tugmasi bosilganda videoni yuborish"""
    query = update.callback_query
    uid = query.from_user.id
    
    # pagination callbacklarini (page_) bu funksiya o'tkazib yuborishi kerak
    if query.data.startswith("page_"):
        await handle_pagination(update, context)
        return

    try:
        parts = query.data.split("_")
        aid = parts[2]
        ep_num = parts[3]
    except:
        await query.answer("Ma'lumotda xatolik yuz berdi.")
        return

    status = await get_user_status(uid)
    conn = get_db(); cur = conn.cursor(dictionary=True)
    
    cur.execute("SELECT * FROM anime_episodes WHERE anime_id=%s AND episode=%s", (aid, ep_num))
    ep_data = cur.fetchone()
    
    if not ep_data:
        await query.answer("Kechirasiz, bu qism topilmadi.")
        cur.close(); conn.close()
        return

    # Bonus ball berish
    bonus_add = 2 if status == 'vip' else 1
    cur.execute("UPDATE users SET bonus = bonus + %s WHERE user_id=%s", (bonus_add, uid))
    conn.commit()
    
    is_protected = False if status in ['vip', 'admin', 'main_admin'] else True

    kb_list = []
    # Agar orqaga qaytish tugmasi bo'lsa, foydalanuvchi boshqa qismlarni ham ko'ra oladi
    kb_list.append([InlineKeyboardButton("⬅️ Boshqa qismlar", callback_data=f"page_{aid}_0")])

    await context.bot.send_video(
        chat_id=uid,
        video=ep_data['file_id'],
        caption=f"🎬 **ID: {aid}** | **{ep_num}-qism**\n🌐 Til: {ep_data['lang']}\n\n🎁 Bonus ball: +{bonus_add}",
        protect_content=is_protected,
        reply_markup=InlineKeyboardMarkup(kb_list),
        parse_mode="Markdown"
    )
    
    cur.close(); conn.close()
    await query.answer(f"+{bonus_add} bonus berildi!")

async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Keyingi/Oldingi qismlar ro'yxatini ko'rsatish"""
    query = update.callback_query
    _, aid, offset = query.data.split("_")
    offset = int(offset)
    
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT episode FROM anime_episodes WHERE anime_id=%s ORDER BY episode ASC", (aid,))
    episodes = cur.fetchall()
    cur.close(); conn.close()

    keyboard = []
    row = []
    # Offsetdan boshlab 10 ta qismni kesib olish
    display_eps = episodes[offset:offset+10]
    
    for ep in display_eps:
        row.append(InlineKeyboardButton(str(ep['episode']), callback_data=f"get_ep_{aid}_{ep['episode']}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)

    nav_buttons = []
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"page_{aid}_{offset-10}"))
    if offset + 10 < len(episodes):
        nav_buttons.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"page_{aid}_{offset+10}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)

    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
    await query.answer()
    
    

# ====================== CONVERSATION STEPS ======================
async def add_ani_poster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anime posterini qabul qilish"""
    context.user_data['poster'] = update.message.photo[-1].file_id
    await update.message.reply_text(
        "✅ Poster qabul qilindi.\n\nEndi ma'lumotni quyidagi formatda yuboring:\n"
        "`ID | Nomi | Tili | Qismi`\n\n"
        "Misol: `101 | Naruto | O'zb | 1`", 
        parse_mode="Markdown"
    )
    return A_ADD_ANI_DATA

async def add_ani_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anime ma'lumotlarini yoki videoni qabul qilish"""
    uid = update.effective_user.id
    
    # 1. Agar matn kelsa (Anime ma'lumotlari)
    if update.message.text:
        try:
            raw_data = update.message.text.split("|")
            if len(raw_data) < 4:
                raise ValueError
            
            aid, name, lang, ep = [i.strip() for i in raw_data]
            
            # Qism raqami butun son ekanini tekshirish
            if not ep.isdigit():
                await update.message.reply_text("❌ Qism faqat raqam bo'lishi kerak!")
                return A_ADD_ANI_DATA

            context.user_data['tmp_ani'] = {
                "id": aid, 
                "name": name, 
                "lang": lang, 
                "ep": int(ep)
            }
            
            await update.message.reply_text(
                f"🎬 **Ma'lumotlar saqlandi.**\n\n"
                f"🆔 ID: {aid}\n"
                f"📺 Nomi: {name}\n"
                f"🔢 Qism: {ep}\n\n"
                f"Endi ushbu qism uchun **VIDEONI** yuboring:",
                parse_mode="Markdown"
            )
            return A_ADD_ANI_DATA
        except ValueError:
            await update.message.reply_text("❌ Xato! Iltimos formatni tekshiring:\n`ID | Nomi | Tili | Qismi`")
            return A_ADD_ANI_DATA

    # 2. Agar video kelsa
    elif update.message.video:
        if 'tmp_ani' not in context.user_data:
            await update.message.reply_text("❌ Avval anime ma'lumotlarini matn shaklida yuboring!")
            return A_ADD_ANI_DATA
            
        if 'poster' not in context.user_data:
            await update.message.reply_text("❌ Xatolik: Poster topilmadi. Qayta /start bosing.")
            return ConversationHandler.END

        v_id = update.message.video.file_id
        d = context.user_data['tmp_ani']
        p_id = context.user_data['poster']

        conn = get_db()
        if not conn:
            await update.message.reply_text("❌ Bazaga ulanishda xato.")
            return ConversationHandler.END

        try:
            cur = conn.cursor()
            
            # 1. Anime listini yangilash yoki qo'shish (Poster yangilanishi uchun)
            cur.execute("""
                INSERT INTO anime_list (anime_id, name, poster_id) 
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE name=%s, poster_id=%s
            """, (d['id'], d['name'], p_id, d['name'], p_id))
            
            # 2. Qismni qo'shish (Agar bu qism bo'lsa yangilaydi)
            cur.execute("""
                INSERT INTO anime_episodes (anime_id, episode, lang, file_id) 
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE file_id=%s, lang=%s
            """, (d['id'], d['ep'], d['lang'], v_id, v_id, d['lang']))
            
            conn.commit()
            await update.message.reply_text(
                f"✅ Muvaffaqiyatli saqlandi!\n\n"
                f"📺 {d['name']}\n"
                f"🔢 {d['ep']}-qism tayyor.", 
                reply_markup=await get_main_kb(uid)
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Xatolik yuz berdi: {e}")
        finally:
            cur.close()
            conn.close()
            # Vaqtinchalik ma'lumotlarni tozalash
            context.user_data.pop('tmp_ani', None)
            context.user_data.pop('poster', None)
            
        return ConversationHandler.END

    else:
        await update.message.reply_text("Iltimos, video yoki ma'lumotni matn shaklida yuboring.")
        return A_ADD_ANI_DATA
    
            

# ====================== QO'SHIMCHA FUNKSIYALAR (TUZATILGAN) ======================

async def check_ads_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reklama parolini tekshirish va xabar so'rash"""
    if update.message.text == ADVERTISING_PASSWORD:
        await update.message.reply_text("✅ Parol tasdiqlandi! \n\nEndi barcha foydalanuvchilarga yubormoqchi bo'lgan **reklama xabaringizni** yuboring (Rasm, Video, Matn yoki Post):")
        return A_SEND_ADS_MSG
    else:
        await update.message.reply_text("❌ Parol noto'g'ri! Reklama paneli yopildi.")
        return ConversationHandler.END

async def ads_send_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reklamani barcha foydalanuvchilarga tarqatish"""
    msg = update.message
    conn = get_db()
    if not conn:
        await update.message.reply_text("❌ Bazaga ulanib bo'lmadi.")
        return ConversationHandler.END
        
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()
    cur.close(); conn.close()

    count = 0
    status_msg = await update.message.reply_text(f"🚀 Reklama yuborish boshlandi (0/{len(users)})...")

    for user in users:
        try:
            # copy_message - bu eng xavfsiz usul (caption va tugmalar bilan ko'chiradi)
            await context.bot.copy_message(
                chat_id=user[0],
                from_chat_id=update.effective_chat.id,
                message_id=msg.message_id
            )
            count += 1
            await asyncio.sleep(0.05) # Telegram limitlaridan oshib ketmaslik uchun

            if count % 50 == 0:
                await status_msg.edit_text(f"🚀 Reklama yuborilmoqda ({count}/{len(users)})...")
        except Exception:
            continue

    await update.message.reply_text(f"✅ Reklama yakunlandi. {count} ta foydalanuvchiga yuborildi.")
    return ConversationHandler.END

async def export_all_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha animelar ro'yxatini JSON fayl qilib yuborish (TUZATILDI)"""
    # CallbackQuery yoki Message ekanini aniqlash
    msg = update.effective_message
    
    conn = get_db()
    if not conn:
        await msg.reply_text("❌ Bazaga ulanishda xato.")
        return

    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM anime_list")
    animes = cur.fetchall()
    cur.close(); conn.close()
    
    file_name = "anime_list.json"
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(animes, f, indent=4, default=str, ensure_ascii=False)
    
    # reply_document ishlatishda faylni 'rb' rejimida ochish
    with open(file_name, "rb") as doc:
        await msg.reply_document(document=doc, caption="🎬 Barcha animelar bazasi (JSON).")

async def exec_vip_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchini VIP qilish ijrosi"""
    if not update.message.text:
        return A_ADD_VIP
        
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ Xato! Iltimos, faqat foydalanuvchi ID raqamini yuboring.")
        return A_ADD_VIP

    try:
        target_id = int(text)
        conn = get_db(); cur = conn.cursor()
        # Avval foydalanuvchi bazada borligini tekshirish foydali bo'lardi, 
        # lekin UPDATE ham yetarli
        cur.execute("UPDATE users SET status = 'vip' WHERE user_id = %s", (target_id,))
        conn.commit(); cur.close(); conn.close()
        
        await update.message.reply_text(f"✅ Foydalanuvchi {target_id} muvaffaqiyatli VIP qilindi.")
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik yuz berdi: {e}")
    
    return ConversationHandler.END

# Qolgan funksiyalar (exec_add_admin, exec_add_channel, exec_rem_channel, show_bonus) 
# o'z holicha qolsa bo'ladi, ular to'g'ri yozilgan.


# ====================== MAIN FUNKSIYA (TUZATILGAN VA TO'LIQ) ======================

async def search_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anime qidirish menyusini chiqarish uchun alohida funksiya"""
    kb = [
        [
            InlineKeyboardButton("🆔 ID bo'yicha", callback_data="search_type_id"),
            InlineKeyboardButton("🔎 Nomi bo'yicha", callback_data="search_type_name")
        ]
    ]
    await update.message.reply_text(
        "🔍 **Qidirish turini tanlang** 👇",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

def main():
    # Ma'lumotlar bazasini tayyorlash
    init_db()

    # Botni qurish
    app_bot = ApplicationBuilder().token(TOKEN).build()

    # 1. Conversation Handler - Faqat ma'lumot kiritish jarayonlari uchun
    conv_handler = ConversationHandler(
        entry_points=[
            # Inline tugmalar orqali kirish (Search, Ads, Admin qo'shish va h.k)
            CallbackQueryHandler(handle_callback, pattern="^(adm_ani_add|adm_ads_start|adm_vip_add|add_channel_start|rem_channel_start|add_admin_start|manage_admins|search_type_id|search_type_name)$"),
        ],
        states={
            # Qidiruv holatlari
            A_SEARCH_BY_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_anime_logic)],
            A_SEARCH_BY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_anime_logic)],
            
            # Admin holatlari
            A_ADD_CH: [MessageHandler(filters.TEXT & ~filters.COMMAND, exec_add_channel)],
            A_REM_CH: [MessageHandler(filters.TEXT & ~filters.COMMAND, exec_rem_channel)],
            A_ADD_ANI_POSTER: [MessageHandler(filters.PHOTO, add_ani_poster)],
            A_ADD_ANI_DATA: [MessageHandler(filters.TEXT | filters.VIDEO, add_ani_data)],
            A_SEND_ADS_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_ads_pass)],
            A_SEND_ADS_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, ads_send_finish)],
            A_ADD_VIP: [MessageHandler(filters.TEXT & ~filters.COMMAND, exec_vip_add)],
            A_ADD_ADM: [MessageHandler(filters.TEXT & ~filters.COMMAND, exec_add_admin)],
        },
        fallbacks=[
            CommandHandler("start", start),
            CallbackQueryHandler(handle_callback, pattern="^cancel_search$"),
            MessageHandler(filters.Regex("^⬅️ Orqaga$"), start)
        ],
        allow_reentry=True
    )

    # 2. Asosiy buyruqlar va xabarlar (Tartib muhim!)
    
    # Start buyrug'i
    app_bot.add_handler(CommandHandler("start", start))

    # Anime qidirish tugmasi (Asosiy menyudan keladigan matn)
    app_bot.add_handler(MessageHandler(filters.Regex("^🔍 Anime qidirish 🎬$"), search_menu_cmd))

    # Admin Panel tugmasi
    app_bot.add_handler(MessageHandler(
        filters.Regex("^🛠 ADMIN PANEL$"), 
        lambda u, c: u.message.reply_text(
            "🛠 Boshqaruv paneli:", 
            reply_markup=get_admin_kb(u.effective_user.id == MAIN_ADMIN_ID)
        )
    ))

    # DB Export (Xatolik tuzatildi: endi ham matnli, ham inline tugma orqali ishlaydi)
    app_bot.add_handler(MessageHandler(filters.Regex("^📜 Barcha anime ro'yxati 📂$"), export_all_anime))
    app_bot.add_handler(CallbackQueryHandler(export_all_anime, pattern="^adm_export$"))

    # Boshqa menyu tugmalari
    app_bot.add_handler(MessageHandler(filters.Regex("^🎁 Bonus ballarim 💰$"), show_bonus))
    app_bot.add_handler(MessageHandler(filters.Regex("^💎 VIP bo'lish ⭐$"), 
        lambda u, c: u.message.reply_text("💎 VIP status olish uchun admin bilan bog'laning: @Admin_Username")))
    app_bot.add_handler(MessageHandler(filters.Regex("^📖 Qo'llanma ❓$"), 
        lambda u, c: u.message.reply_text("📖 *Qo'llanma:*\nID yoki Nomi orqali animelarni topishingiz mumkin.", parse_mode="Markdown")))

    # 3. Handlerlarni ulash (ConvHandler eng muhimi)
    app_bot.add_handler(conv_handler)
    app_bot.add_handler(CallbackQueryHandler(get_episode_handler, pattern="^get_ep_"))
    
    # Umumiy Callback Handler (Tepada tutib olinmagan barcha callbacklar uchun)
    app_bot.add_handler(CallbackQueryHandler(handle_callback))
    
    # Hech qanday jarayonda bo'lmagan foydalanuvchi matn yozsa qidiruv deb hisoblash
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_anime_logic))

    # Web serverni yuritish (Keep alive)
    keep_alive()

    # Botni ishga tushirish
    print("🤖 Bot muvaffaqiyatli ishga tushdi...")
    app_bot.run_polling()

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Bot to'xtatildi!")
        







