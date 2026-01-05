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

# ====================== LOGLASHNI SOZLASH ======================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====================== KONFIGURATSIYA ======================
TOKEN = "8589253414:AAFTMMnZkUrNsqGWQmsBmJjyBTbssqn6zTE"
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

# ====================== MA'LUMOTLAR BAZASI BILAN ISHLASH ======================
def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        logger.error(f"MySQL ulanish xatosi: {err}")
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
    logger.info("Ma'lumotlar bazasi jadvallari tayyor.")

# ====================== YORDAMCHI FUNKSIYALAR ======================
async def check_subscription(user_id, bot):
    conn = get_db_connection()
    if not conn: return []
    cur = conn.cursor()
    cur.execute("SELECT channel_username FROM required_channels")
    channels = cur.fetchall()
    cur.close()
    conn.close()
    
    not_joined = []
    for (channel,) in channels:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status not in ["member", "creator", "administrator"]:
                not_joined.append(channel)
        except Exception:
            not_joined.append(channel)
    return not_joined

async def is_user_admin(user_id):
    if user_id == MAIN_ADMIN_ID:
        return True
    conn = get_db_connection()
    if not conn: return False
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins WHERE user_id=%s", (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return bool(result)

async def mark_as_watched(user_id, anime_id):
    conn = get_db_connection()
    if not conn: return False
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM watched_anime WHERE user_id=%s AND anime_id=%s", (user_id, anime_id))
        if not cur.fetchone():
            cur.execute("INSERT INTO watched_anime (user_id, anime_id) VALUES (%s, %s)", (user_id, anime_id))
            cur.execute("""
                INSERT INTO bonuses (user_id, bonus_points) VALUES (%s, 1) 
                ON DUPLICATE KEY UPDATE bonus_points = bonus_points + 1
            """, (user_id,))
            conn.commit()
            return True
        return False
    finally:
        cur.close()
        conn.close()

# ====================== KLAVIATURALAR ======================
async def main_menu_keyboard(user_id):
    keyboard = [
        [KeyboardButton("🔍 Anime qidirish")],
        [KeyboardButton("🎁 Mening bonuslarim"), KeyboardButton("📖 Ko'rilganlar")],
        [KeyboardButton("📜 Barcha animelar"), KeyboardButton("💎 VIP sotib olish")]
    ]
    if await is_user_admin(user_id):
        keyboard.append([KeyboardButton("🛠 ADMIN PANEL")])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ====================== AVTOMATIK FAYL GENERATORI ======================
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
                    f.write(f"--- BARCHA ANIMELER RO'YXATI ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}) ---\n\n")
                    if not animes:
                        f.write("Hozircha animelar yo'q.")
                    for a in animes:
                        f.write(f"🎬 Nomi: {a['name']}\n🆔 ID: {a['id']}\n🌐 Til: {a['lang']}\n🔢 Qismlar: {a['total_eps']}\n")
                        f.write("-" * 30 + "\n")
                logger.info("animeroyhat.txt muvaffaqiyatli yangilandi.")
        except Exception as e:
            logger.error(f"Fayl yangilashda xato: {e}")
        await asyncio.sleep(6 * 3600)

# ====================== BOT COMMAND HANDLERS ======================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("INSERT IGNORE INTO users (user_id, joined_at) VALUES (%s, %s)", (user_id, datetime.datetime.now()))
        conn.commit()
        cur.close()
        conn.close()
    
    context.user_data.clear()
    not_joined = await check_subscription(user_id, context.bot)
    
    if not_joined:
        buttons = []
        for ch in not_joined:
            buttons.append([InlineKeyboardButton(f"Obuna bo'lish: {ch}", url=f"https://t.me/{ch.replace('@','')}")])
        buttons.append([InlineKeyboardButton("Tekshirish 🔄", callback_data="check_subs")])
        await update.message.reply_text(
            "❗ Botdan to'liq foydalanish uchun quyidagi kanallarga obuna bo'lishingiz shart:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    await update.message.reply_text(
        f"Xush kelibsiz, {update.effective_user.first_name}!\nBotdan foydalanish uchun quyidagi menyudan foydalaning:",
        reply_markup=await main_menu_keyboard(user_id)
    )

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    await query.answer()
    admin_status = await is_user_admin(uid)

    if data == "check_subs":
        not_joined = await check_subscription(uid, context.bot)
        if not not_joined:
            await query.message.delete()
            await query.message.reply_text("✅ Obuna tasdiqlandi!", reply_markup=await main_menu_keyboard(uid))
        else:
            await query.answer("Hali hamma kanallarga a'zo bo'lmadingiz!", show_alert=True)

    elif data == "mode_name":
        context.user_data["search_mode"] = "name"
        await query.message.reply_text("📝 Anime nomini yuboring (Masalan: Naruto):")
    
    elif data == "mode_id":
        context.user_data["search_mode"] = "id"
        await query.message.reply_text("🆔 Anime ID raqamini yuboring:")

    elif data == "mode_ep":
        context.user_data["search_mode"] = "ep"
        await query.message.reply_text("🔢 Qism raqamini yuboring:")

    elif data == "add_anime" and admin_status:
        context.user_data["step"] = "wait_photo"
        await query.message.reply_text("1️⃣ Anime posterini (rasm) yuboring:")

    elif data == "bot_stats" and admin_status:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users"); u_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM anime"); a_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM vip_users"); v_count = cur.fetchone()[0]
            cur.close(); conn.close()
            await query.message.reply_text(f"📊 STATISTIKA:\n👤 Foydalanuvchilar: {u_count}\n🎬 Jami qismlar: {a_count}\n💎 VIP: {v_count}")

    elif data.startswith("watch_"):
        anime_id = data.split("_")[1]
        res = await mark_as_watched(uid, anime_id)
        if res: await query.message.reply_text("✅ Ko'rildi deb belgilandi! +1 bonus.")
        else: await query.answer("Allaqachon ko'rilgan.", show_alert=True)

    elif data.startswith("dl_real_"):
        p = data.split("_")
        anime_id = p[2]
        ep = p[3]
        file_id = context.bot_data.get(f"vid_{anime_id}_{ep}")
        if file_id:
            await context.bot.send_video(chat_id=uid, video=file_id, caption="Marhamat! ✅")
        else:
            await query.answer("Fayl topilmadi.", show_alert=True)

    elif data == "broadcast" and admin_status:
        context.user_data["step"] = "wait_broadcast"
        await query.message.reply_text("📢 Xabarni yuboring:")

    # --- YANGI QO'SHILGAN CALLBACK'LAR ---
    elif data == "manage_admins" and admin_status:
        kb = [
            [InlineKeyboardButton("➕ Yangi admin qo'shish", callback_data="add_new_admin")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_admin")]
        ]
        await query.edit_message_text("👥 Adminlarni boshqarish bo'limi:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "add_new_admin" and uid == MAIN_ADMIN_ID:
        context.user_data["step"] = "wait_admin_id"
        await query.message.reply_text("👤 Yangi admin qilmoqchi bo'lgan foydalanuvchi ID raqamini yuboring:")

    elif data == "back_to_admin" and admin_status:
        keyboard = [
            [InlineKeyboardButton("➕ Anime qo'shish", callback_data="add_anime"), InlineKeyboardButton("👥 Adminlar", callback_data="manage_admins")],
            [InlineKeyboardButton("📢 Reklama (Xabar)", callback_data="broadcast"), InlineKeyboardButton("📊 Statistika", callback_data="bot_stats")],
            [InlineKeyboardButton("💾 DB Export", callback_data="export_db")]
        ]
        await query.edit_message_text("🛡 Admin boshqaruv paneli:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "export_db" and admin_status:
        conn = get_db_connection()
        if conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM anime"); animes = cur.fetchall()
            cur.execute("SELECT * FROM users"); users = cur.fetchall()
            cur.close(); conn.close()
            backup = {"anime": animes, "users": users, "date": str(datetime.datetime.now())}
            with open("backup.json", "w", encoding="utf-8") as f:
                json.dump(backup, f, ensure_ascii=False, indent=4, default=str)
            await context.bot.send_document(chat_id=uid, document=open("backup.json", "rb"), caption="📦 Railway DB Backup")

# ====================== MESSAGE HANDLER (DATA INPUT) ======================
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    step = context.user_data.get("step")
    search_mode = context.user_data.get("search_mode")
    text = update.message.text
    admin_status = await is_user_admin(uid)

    # RE REPLY MENU CLICK HANDLING
    if text == "🔍 Anime qidirish":
        kb = [
            [InlineKeyboardButton("📝 Nomi orqali", callback_data="mode_name")],
            [InlineKeyboardButton("🆔 ID raqami orqali", callback_data="mode_id")],
            [InlineKeyboardButton("🔢 Qism raqami orqali", callback_data="mode_ep")]
        ]
        await update.message.reply_text("Qidiruv turini tanlang:", reply_markup=InlineKeyboardMarkup(kb))
        return

    elif text == "🛠 ADMIN PANEL" and admin_status:
        keyboard = [
            [InlineKeyboardButton("➕ Anime qo'shish", callback_data="add_anime"), InlineKeyboardButton("👥 Adminlar", callback_data="manage_admins")],
            [InlineKeyboardButton("📢 Reklama (Xabar)", callback_data="broadcast"), InlineKeyboardButton("📊 Statistika", callback_data="bot_stats")],
            [InlineKeyboardButton("💾 DB Export", callback_data="export_db")]
        ]
        await update.message.reply_text("🛡 Admin boshqaruv paneli:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif text == "📜 Barcha animelar":
        if os.path.exists("animeroyhat.txt"):
            await update.message.reply_document(document=open("animeroyhat.txt", "rb"), caption="📜 Barcha animelar ro'yxati:")
        else:
            await update.message.reply_text("Ro'yxat hali tayyor emas.")
        return

    # REKLAMA TARQATISH
    if step == "wait_broadcast" and admin_status:
        conn = get_db_connection()
        cur = conn.cursor(); cur.execute("SELECT user_id FROM users"); users = cur.fetchall()
        cur.close(); conn.close()
        count = 0
        for (user,) in users:
            try:
                await update.message.copy(chat_id=user)
                count += 1
                await asyncio.sleep(0.05)
            except: pass
        await update.message.reply_text(f"✅ {count} ta foydalanuvchiga yuborildi.")
        context.user_data.clear()

    # YANGI ADMIN ID QABUL QILISH
    elif step == "wait_admin_id" and uid == MAIN_ADMIN_ID:
        try:
            new_admin = int(text)
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT IGNORE INTO admins (user_id) VALUES (%s)", (new_admin,))
            conn.commit(); cur.close(); conn.close()
            await update.message.reply_text(f"✅ {new_admin} muvaffaqiyatli admin qilindi.")
        except:
            await update.message.reply_text("❌ Xato ID.")
        context.user_data.clear()

    # ANIME QO'SHISH BOSQICHLARI
    elif step == "wait_photo" and update.message.photo and admin_status:
        context.user_data["temp_photo"] = update.message.photo[-1].file_id
        context.user_data["step"] = "wait_video"
        await update.message.reply_text("2️⃣ Videoni yuboring: `ID|Nomi|Til|Qism` formatda")

    elif step == "wait_video" and update.message.video and admin_status:
        try:
            p = [x.strip() for x in update.message.caption.split("|")]
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO anime (id, name, lang, episode, video_file_id, photo_file_id) VALUES (%s, %s, %s, %s, %s, %s)",
                        (p[0], p[1], p[2], p[3], update.message.video.file_id, context.user_data["temp_photo"]))
            conn.commit(); cur.close(); conn.close()
            await update.message.reply_text("✅ Bazaga qo'shildi!")
            context.user_data.clear()
        except: await update.message.reply_text("Xato format! Captionga ID|Nomi|Til|Qism yozing.")

    # QIDIRUV ISHLASHI
    elif search_mode and text:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        if search_mode == "name":
            cur.execute("SELECT * FROM anime WHERE name LIKE %s", (f"%{text}%",))
        elif search_mode == "id":
            cur.execute("SELECT * FROM anime WHERE id=%s", (text,))
        else:
            cur.execute("SELECT * FROM anime WHERE episode=%s", (text,))
        results = cur.fetchall()
        cur.close(); conn.close()

        if not results:
            await update.message.reply_text("Hech narsa topilmadi. 😕")
            return

        for a in results:
            context.bot_data[f"vid_{a['id']}_{a['episode']}"] = a['video_file_id']
            kb = [[InlineKeyboardButton("✅ Ko'rdim", callback_data=f"watch_{a['id']}"), 
                   InlineKeyboardButton("📥 Yuklab olish (VIP)", callback_data=f"dl_real_{a['id']}_{a['episode']}")]]
            await update.message.reply_photo(
                photo=a['photo_file_id'],
                caption=f"🎬 Nomi: {a['name']}\n🆔 ID: {a['id']}\n🌐 Til: {a['lang']}\n🔢 Qism: {a['episode']}",
                reply_markup=InlineKeyboardMarkup(kb)
            )
            await update.message.reply_video(video=a['video_file_id'], protect_content=True)
        context.user_data.clear()

# ====================== ASOSIY ISHGA TUSHIRISH ======================
async def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_messages))
    
    await app.initialize()
    await app.start()
    
    asyncio.create_task(update_anime_list_file())
    
    logger.info("Bot ishga tushdi.")
    await app.updater.start_polling()
    
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
