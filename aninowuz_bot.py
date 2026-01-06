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
TOKEN = "TOKENINGIZNI_BUYERGA_QO'YING"
MAIN_ADMIN_ID = 8244870375

DB_CONFIG = {
    "host": os.getenv("MYSQLHOST", "mysql.railway.internal"),
    "user": os.getenv("MYSQLUSER", "root"),
    "password": os.getenv("MYSQLPASSWORD", ""),
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

# ====================== SUBSCRIPTION CHECK ======================
async def check_subscription(user_id, bot):
    conn = get_db_connection()
    if not conn:
        return []
    cur = conn.cursor()
    cur.execute("SELECT channel_username FROM required_channels")
    channels = cur.fetchall()
    cur.close()
    conn.close()
    not_joined = []
    for (ch,) in channels:
        try:
            m = await bot.get_chat_member(ch, user_id)
            if m.status not in ["member", "creator", "administrator"]:
                not_joined.append(ch)
        except:
            not_joined.append(ch)
    return not_joined

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

    not_joined = await check_subscription(uid, context.bot)
    if not_joined:
        buttons = [[InlineKeyboardButton(f"Obuna bo'lish: {c}", url=f"https://t.me/{c.replace('@','')}")] for c in not_joined]
        buttons.append([InlineKeyboardButton("Tekshirish 🔄", callback_data="check_subs")])
        await update.message.reply_text(f"Salom {name}! 👋\nBotdan foydalanish uchun kanallarga a'zo bo'ling:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    await update.message.reply_text(
        f"Xush kelibsiz, {name}!",
        reply_markup=await main_menu_keyboard(uid)
    )

# ====================== WATCHED & BONUS ======================
async def mark_as_watched(user_id, anime_id):
    conn = get_db_connection()
    if not conn:
        return False
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM watched_anime WHERE user_id=%s AND anime_id=%s", (user_id, anime_id))
        if not cur.fetchone():
            cur.execute("INSERT INTO watched_anime (user_id, anime_id) VALUES (%s, %s)", (user_id, anime_id))
            cur.execute("INSERT INTO bonuses (user_id, bonus_points) VALUES (%s, 1) ON DUPLICATE KEY UPDATE bonus_points = bonus_points + 1", (user_id,))
            conn.commit()
            return True
        return False
    finally:
        cur.close()
        conn.close()

# ====================== ANIME LIST FILE ======================
async def update_anime_list_file():
    while True:
        try:
            conn = get_db_connection()
            if conn:
                cur = conn.cursor(dictionary=True)
                cur.execute("SELECT id, name, lang, COUNT(episode) as total_eps FROM anime GROUP BY id, name, lang")
                animes = cur.fetchall()
                cur.close()
                conn.close()
                with open("animeroyhat.txt", "w", encoding="utf-8") as f:
                    f.write(f"--- BARCHA ANIMELER RO'YXATI ({datetime.datetime.now()}) ---\n\n")
                    for a in animes:
                        f.write(f"🎬 Nomi: {a['name']}\n🆔 ID: {a['id']}\n🌐 Til: {a['lang']}\n🔢 Qismlar: {a['total_eps']}\n" + "-"*30 + "\n")
        except:
            pass
        await asyncio.sleep(6*3600)

# ====================== CALLBACKS ======================
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    await query.answer()

    admin = await is_user_admin(uid)

    if data == "check_subs":
        not_joined = await check_subscription(uid, context.bot)
        if not not_joined:
            await query.message.delete()
            await context.bot.send_message(uid, "✅ Obuna tasdiqlandi!", reply_markup=await main_menu_keyboard(uid))
        else:
            await query.answer("Hali a'zo emassiz!", show_alert=True)

    elif data.startswith("watch_"):
        anime_id = data.split("_")[1]
        if await mark_as_watched(uid, anime_id):
            await query.message.reply_text("✅ Ko'rildi deb belgilandi! +1 bonus.")
        else:
            await query.answer("Allaqachon ko'rilgan.", show_alert=True)

# ====================== MESSAGE HANDLER ======================
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    admin = await is_user_admin(uid)
    step = context.user_data.get("step")

    if text == "🎁 Mening bonuslarim":
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT bonus_points FROM bonuses WHERE user_id=%s", (uid,))
        r = cur.fetchone()
        cur.close()
        conn.close()
        await update.message.reply_text(f"🎁 Bonuslaringiz: {r[0] if r else 0}")

    elif text == "📜 Barcha animelar":
        if os.path.exists("animeroyhat.txt"):
            await update.message.reply_document(open("animeroyhat.txt", "rb"))

# ====================== MAIN ======================
async def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_messages))

    asyncio.create_task(update_anime_list_file())

    await app.initialize()
    await app.start()
    await app.run_polling()

if __name__ == "__main__":
    try:
        asyncio.run(main())  # EHTIYOT: main() chaqirilgan
    except (KeyboardInterrupt, SystemExit):
        print("Bot to‘xtatildi.")

# ======= [ KOD TUGADI ] =======
