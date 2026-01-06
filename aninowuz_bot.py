# ======= [ KOD BOSHLANISHI ] =======

import os
import logging
import mysql.connector
import asyncio
import datetime
import json
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# ====================== LOG ======================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====================== CONFIG ======================
TOKEN = "8258233749:AAHdFklNhjGlE7pK0026vJrMYJaK8iiddXo"
MAIN_ADMIN_ID = 8244870375

DB_CONFIG = {
    "host": os.getenv("MYSQLHOST", "mysql.railway.internal"),
    "user": os.getenv("MYSQLUSER", "root"),
    "password": os.getenv("MYSQLPASSWORD", "CIbKpeQrFVJosmzyKZwJiQoTkJxoeBjP"),
    "database": os.getenv("MYSQLDATABASE", "railway"),
    "port": int(os.getenv("MYSQLPORT", 3306)),
    "connect_timeout": 20,
    "autocommit": True
}

# ====================== DB ======================
def get_db_connection():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Exception as e:
        logger.error(e)
        return None

def init_db():
    conn = get_db_connection()
    if not conn:
        return
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, joined_at DATETIME)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS anime (
            id VARCHAR(50),
            name VARCHAR(255),
            lang VARCHAR(50),
            episode VARCHAR(50),
            video_file_id TEXT,
            photo_file_id TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id, episode)
        )
    """)
    cur.execute("CREATE TABLE IF NOT EXISTS vip_users (user_id BIGINT PRIMARY KEY, expires_at DATETIME)")
    cur.execute("CREATE TABLE IF NOT EXISTS admins (user_id BIGINT PRIMARY KEY)")
    cur.execute("CREATE TABLE IF NOT EXISTS required_channels (id INT AUTO_INCREMENT PRIMARY KEY, channel_username VARCHAR(255))")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS watched_anime (
            user_id BIGINT,
            anime_id VARCHAR(50),
            watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, anime_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bonuses (
            user_id BIGINT PRIMARY KEY,
            bonus_points INT DEFAULT 0,
            last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

# ====================== SECURITY ======================
async def is_user_admin(user_id):
    if user_id == MAIN_ADMIN_ID:
        return True
    conn = get_db_connection()
    if not conn:
        return False
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM admins WHERE user_id=%s", (user_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return bool(res)

# ====================== MAIN MENU ======================
async def main_menu_keyboard(user_id):
    keyboard = [
        [KeyboardButton("🔍 Anime qidirish")],
        [KeyboardButton("🎁 Mening bonuslarim"), KeyboardButton("📖 Ko'rilganlar")],
        [KeyboardButton("📜 Barcha animelar"), KeyboardButton("💎 VIP sotib olish")]
    ]
    if await is_user_admin(user_id):
        keyboard.append([KeyboardButton("🛠 ADMIN PANEL")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ====================== START ======================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.first_name

    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE user_id=%s", (uid,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO users (user_id, joined_at) VALUES (%s,%s)",
                (uid, datetime.datetime.now())
            )
            conn.commit()
        cur.close()
        conn.close()

    await update.message.reply_text(
        f"Xush kelibsiz, {name}!",
        reply_markup=await main_menu_keyboard(uid)
    )

# ====================== CALLBACK ======================
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    await query.answer()

    admin = await is_user_admin(uid)

    # ❌ ADMIN EMASLAR BLOKI
    ADMIN_ACTIONS = [
        "add_anime", "broadcast", "manage_admins",
        "manage_channels", "export_db", "bot_stats",
        "add_channel"
    ]
    if any(data.startswith(a) for a in ADMIN_ACTIONS) and not admin:
        await query.answer("⛔ Ruxsat yo‘q!", show_alert=True)
        return

    # ===== ADMIN PANEL =====
    if data == "admin_panel" and admin:
        kb = [
            [InlineKeyboardButton("➕ Anime", callback_data="add_anime")],
            [InlineKeyboardButton("👥 Adminlar", callback_data="manage_admins")],
            [InlineKeyboardButton("📢 Kanallar", callback_data="manage_channels")],
            [InlineKeyboardButton("📊 Stat", callback_data="bot_stats")],
            [InlineKeyboardButton("📢 Reklama", callback_data="broadcast")],
            [InlineKeyboardButton("💾 Export", callback_data="export_db")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_main")]
        ]
        await query.edit_message_text("🛡 ADMIN PANEL", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "back_main":
        await context.bot.send_message(
            uid,
            "Asosiy menyu",
            reply_markup=await main_menu_keyboard(uid)
        )

# ====================== MESSAGE HANDLER ======================
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    admin = await is_user_admin(uid)
    step = context.user_data.get("step")

    if text == "🛠 ADMIN PANEL":
        if not admin:
            await update.message.reply_text("⛔ Siz admin emassiz.")
            return
        kb = [[InlineKeyboardButton("ADMIN PANEL", callback_data="admin_panel")]]
        await update.message.reply_text("Admin boshqaruv:", reply_markup=InlineKeyboardMarkup(kb))

    elif text == "🎁 Mening bonuslarim":
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT bonus_points FROM bonuses WHERE user_id=%s", (uid,))
        r = cur.fetchone()
        cur.close()
        conn.close()
        await update.message.reply_text(f"🎁 Bonuslar: {r[0] if r else 0}")

# =# ====================== MAIN ======================
async def main():
    # Bazani tayyorlash
    init_db()

    # Bot ilovasini yaratish
    app = ApplicationBuilder().token(TOKEN).build()

    # Handlerlar qo'shish
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_messages))

    # Automatik anime ro'yxatini yangilash taskini ishga tushirish
    asyncio.create_task(update_anime_list_file())

    # Botni ishga tushirish
    await app.initialize()
    await app.start()

    # Zamonaviy PTB da run_polling ishlatish kifoya
    await app.run_polling()

if __name__ == "__main__":
    try:
        asyncio.run(main())  # <-- BU YERDA () BO’LMASA XATO
    except (KeyboardInterrupt, SystemExit):
        print("Bot to‘xtatildi.")


