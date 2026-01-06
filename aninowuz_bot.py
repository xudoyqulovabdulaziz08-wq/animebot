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
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
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
        return mysql.connector.connect(**DB_CONFIG)
    except Exception as e:
        logger.error(f"MySQL ulanish xatosi: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn: return
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, joined_at DATETIME)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS anime (
            id VARCHAR(50), name VARCHAR(255), lang VARCHAR(50), episode VARCHAR(50),
            video_file_id TEXT, photo_file_id TEXT, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id, episode)
        )
    """)
    cur.execute("CREATE TABLE IF NOT EXISTS vip_users (user_id BIGINT PRIMARY KEY, expires_at DATETIME)")
    cur.execute("CREATE TABLE IF NOT EXISTS admins (user_id BIGINT PRIMARY KEY)")
    cur.execute("CREATE TABLE IF NOT EXISTS required_channels (id INT AUTO_INCREMENT PRIMARY KEY, channel_username VARCHAR(255))")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS watched_anime (
            user_id BIGINT, anime_id VARCHAR(50), watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, anime_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bonuses (
            user_id BIGINT PRIMARY KEY, bonus_points INT DEFAULT 0,
            last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)
    conn.commit(); cur.close(); conn.close()

# ====================== YORDAMCHI FUNKSIYALAR ======================
async def check_subscription(user_id, bot):
    conn = get_db_connection()
    if not conn: return []
    cur = conn.cursor()
    cur.execute("SELECT channel_username FROM required_channels")
    channels = cur.fetchall(); cur.close(); conn.close()
    not_joined = []
    for (ch,) in channels:
        try:
            m = await bot.get_chat_member(ch, user_id)
            if m.status not in ["member", "creator", "administrator"]: not_joined.append(ch)
        except: not_joined.append(ch)
    return not_joined

async def is_user_admin(user_id):
    if user_id == MAIN_ADMIN_ID: return True
    conn = get_db_connection()
    if not conn: return False
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins WHERE user_id=%s", (user_id,))
    res = cur.fetchone(); cur.close(); conn.close()
    return bool(res)

async def mark_as_watched(user_id, anime_id):
    conn = get_db_connection()
    if not conn: return False
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM watched_anime WHERE user_id=%s AND anime_id=%s", (user_id, anime_id))
        if not cur.fetchone():
            cur.execute("INSERT INTO watched_anime (user_id, anime_id) VALUES (%s, %s)", (user_id, anime_id))
            cur.execute("INSERT INTO bonuses (user_id, bonus_points) VALUES (%s, 1) ON DUPLICATE KEY UPDATE bonus_points = bonus_points + 1", (user_id,))
            conn.commit(); return True
        return False
    finally: cur.close(); conn.close()

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
                animes = cur.fetchall(); cur.close(); conn.close()
                with open("animeroyhat.txt", "w", encoding="utf-8") as f:
                    f.write(f"--- BARCHA ANIMELER RO'YXATI ({datetime.datetime.now()}) ---\n\n")
                    for a in animes:
                        f.write(f"🎬 Nomi: {a['name']}\n🆔 ID: {a['id']}\n🌐 Til: {a['lang']}\n🔢 Qismlar: {a['total_eps']}\n" + "-"*30 + "\n")
        except: pass
        await asyncio.sleep(6 * 3600)

# ====================== START COMMAND ======================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.first_name
    conn = get_db_connection()
    if conn:
        cur = conn.cursor(); cur.execute("SELECT user_id FROM users WHERE user_id=%s", (uid,))
        if not cur.fetchone():
            cur.execute("INSERT INTO users (user_id, joined_at) VALUES (%s, %s)", (uid, datetime.datetime.now()))
            conn.commit()
            try:
                username = f"@{update.effective_user.username}" if update.effective_user.username else "yo'q"
                await context.bot.send_message(MAIN_ADMIN_ID, f"🆕 Yangi user: {name}\n🆔 ID: {uid}\n🌐 Username: {username}")
            except: pass
        cur.close(); conn.close()
    
    context.user_data.clear()
    not_joined = await check_subscription(uid, context.bot)
    if not_joined:
        btns = [[InlineKeyboardButton(f"Obuna bo'lish: {c}", url=f"https://t.me/{c.replace('@','')}")] for c in not_joined]
        btns.append([InlineKeyboardButton("Tekshirish 🔄", callback_data="check_subs")])
        await update.message.reply_text(f"Salom {name}! 👋\nBotdan foydalanish uchun kanallarga a'zo bo'ling:", reply_markup=InlineKeyboardMarkup(btns))
        return
    await update.message.reply_text(f"Xush kelibsiz, {name}!", reply_markup=await main_menu_keyboard(uid))

# ====================== CALLBACK HANDLER ======================
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    await query.answer()
    admin = await is_user_admin(uid)

    if data == "check_subs":
        not_joined = await check_subscription(uid, context.bot)
        if not not_joined:
            try: await query.message.delete()
            except: pass
            await context.bot.send_message(uid, "✅ Obuna tasdiqlandi!", reply_markup=await main_menu_keyboard(uid))
        else: await query.answer("Hali a'zo emassiz!", show_alert=True)

    elif data.startswith("send_vid_"):
        parts = data.split("_"); aid, ep = parts[2], parts[3]
        conn = get_db_connection(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM anime WHERE id=%s AND episode=%s", (aid, ep))
        anime = cur.fetchone(); cur.close(); conn.close()
        if anime:
            kb = [[InlineKeyboardButton("✅ Ko'rdim", callback_data=f"watch_{aid}")]]
            await context.bot.send_video(uid, anime['video_file_id'], caption=f"🎬 {anime['name']} - {anime['episode']}-qism", protect_content=True, reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("watch_"):
        aid = data.split("_")[1]
        if await mark_as_watched(uid, aid): await query.message.reply_text("✅ Ko'rildi deb belgilandi! +1 bonus.")
        else: await query.answer("Allaqachon ko'rilgan.", show_alert=True)

    elif data == "mode_name": context.user_data["search_mode"] = "name"; await query.message.reply_text("📝 Anime nomini yuboring:")
    elif data == "mode_id": context.user_data["search_mode"] = "id"; await query.message.reply_text("🆔 Anime ID raqamini yuboring:")

    elif data == "add_anime" and admin:
        context.user_data["step"] = "wait_photo"
        await query.message.reply_text("1️⃣ Poster (rasm) yuboring:")

    elif data == "bot_stats" and admin:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users"); u = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM anime"); a = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM vip_users"); v = cur.fetchone()[0]
        cur.close(); conn.close()
        await query.message.reply_text(f"📊 STATISTIKA:\n👤 Foydalanuvchilar: {u}\n🎬 Jami qismlar: {a}\n💎 VIP: {v}")

    elif data == "broadcast" and admin:
        context.user_data["step"] = "wait_broadcast"; await query.message.reply_text("📢 Reklama xabarini yuboring:")

    elif data == "manage_admins" and uid == MAIN_ADMIN_ID:
        context.user_data["step"] = "wait_admin_id"; await query.message.reply_text("👤 Yangi admin ID raqamini yuboring:")

    elif data == "manage_channels" and admin:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT id, channel_username FROM required_channels"); chs = cur.fetchall()
        cur.close(); conn.close()
        msg = "📢 Kanallar:\n"
        kb = []
        for cid, cname in chs:
            msg += f"🔹 {cname}\n"
            kb.append([InlineKeyboardButton(f"❌ {cname}", callback_data=f"del_ch_{cid}")])
        kb.append([InlineKeyboardButton("➕ Kanal qo'shish", callback_data="add_channel")])
        kb.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_admin")])
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "add_channel" and admin:
        context.user_data["step"] = "wait_channel_name"; await query.message.reply_text("Kanal username kiriting (@kanal):")

    elif data.startswith("del_ch_") and admin:
        cid = data.split("_")[2]
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM required_channels WHERE id=%s", (cid,)); conn.commit()
        cur.close(); conn.close(); await query.answer("Kanal o'chirildi."); await handle_callbacks(update, context)

    elif data == "export_db" and admin:
        conn = get_db_connection(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM anime"); a_data = cur.fetchall()
        cur.execute("SELECT * FROM users"); u_data = cur.fetchall()
        cur.close(); conn.close()
        with open("backup.json", "w") as f: json.dump({"anime": a_data, "users": u_data}, f, default=str)
        await context.bot.send_document(uid, open("backup.json", "rb"), caption="📦 DB Export")

    elif data == "back_to_admin" and admin:
        kb = [[InlineKeyboardButton("➕ Anime", callback_data="add_anime"), InlineKeyboardButton("👥 Admin", callback_data="manage_admins")],
              [InlineKeyboardButton("📢 Kanallar", callback_data="manage_channels"), InlineKeyboardButton("📊 Stat", callback_data="bot_stats")],
              [InlineKeyboardButton("📢 Reklama", callback_data="broadcast"), InlineKeyboardButton("💾 Export", callback_data="export_db")]]
        await query.edit_message_text("🛡 Admin Panel:", reply_markup=InlineKeyboardMarkup(kb))

# ====================== MESSAGE HANDLER ======================
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; text = update.message.text; admin = await is_user_admin(uid)
    step = context.user_data.get("step"); mode = context.user_data.get("search_mode")

    if text == "🔍 Anime qidirish":
        kb = [[InlineKeyboardButton("📝 Nomi orqali", callback_data="mode_name")], [InlineKeyboardButton("🆔 ID orqali", callback_data="mode_id")]]
        await update.message.reply_text("Qidiruv turi:", reply_markup=InlineKeyboardMarkup(kb))
    elif text == "🛠 ADMIN PANEL" and admin:
        kb = [[InlineKeyboardButton("➕ Anime", callback_data="add_anime"), InlineKeyboardButton("👥 Admin", callback_data="manage_admins")],
              [InlineKeyboardButton("📢 Kanallar", callback_data="manage_channels"), InlineKeyboardButton("📊 Stat", callback_data="bot_stats")],
              [InlineKeyboardButton("📢 Reklama", callback_data="broadcast"), InlineKeyboardButton("💾 Export", callback_data="export_db")]]
        await update.message.reply_text("🛡 Admin Panel:", reply_markup=InlineKeyboardMarkup(kb))
    elif text == "📜 Barcha animelar":
        if os.path.exists("animeroyhat.txt"): await update.message.reply_document(open("animeroyhat.txt", "rb"))
    elif text == "🎁 Mening bonuslarim":
        conn = get_db_connection(); cur = conn.cursor(); cur.execute("SELECT bonus_points FROM bonuses WHERE user_id=%s", (uid,))
        res = cur.fetchone(); cur.close(); conn.close()
        await update.message.reply_text(f"💰 Bonuslaringiz: {res[0] if res else 0} ball")

    # --- ADMIN BOSQICHLARI ---
    if step == "wait_channel_name" and admin:
        if text.startswith("@"):
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO required_channels (channel_username) VALUES (%s)", (text,)); conn.commit()
            cur.close(); conn.close(); await update.message.reply_text("✅ Kanal qo'shildi.")
        context.user_data.clear()
    elif step == "wait_admin_id" and uid == MAIN_ADMIN_ID:
        try:
            aid = int(text); conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT IGNORE INTO admins (user_id) VALUES (%s)", (aid,)); conn.commit()
            cur.close(); conn.close(); await update.message.reply_text(f"✅ {aid} admin bo'ldi.")
        except: await update.message.reply_text("ID raqam bo'lishi kerak.")
        context.user_data.clear()
    elif step == "wait_broadcast" and admin:
        conn = get_db_connection(); cur = conn.cursor(); cur.execute("SELECT user_id FROM users"); users = cur.fetchall()
        cur.close(); conn.close(); count = 0
        for (u,) in users:
            try: await update.message.copy(u); count += 1; await asyncio.sleep(0.1)
            except: pass
        await update.message.reply_text(f"✅ {count} kishiga yuborildi."); context.user_data.clear()
    elif step == "wait_photo" and update.message.photo and admin:
        context.user_data["tmp_photo"] = update.message.photo[-1].file_id
        context.user_data["step"] = "wait_video"
        await update.message.reply_text("2️⃣ Video va caption (ID|Nomi|Til|Qism) yuboring:")
    elif step == "wait_video" and update.message.video and admin:
        try:
            p = [x.strip() for x in update.message.caption.split("|")]
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO anime (id, name, lang, episode, video_file_id, photo_file_id) VALUES (%s,%s,%s,%s,%s,%s)",
                        (p[0], p[1], p[2], p[3], update.message.video.file_id, context.user_data["tmp_photo"]))
            conn.commit(); cur.close(); conn.close()
            await update.message.reply_text(f"✅ {p[3]}-qism qo'shildi! Keyingisini yuboring...")
        except: await update.message.reply_text("❌ Xato! Format: ID|Nomi|Til|Qism")

    # --- QIDIRUV (GURUHLASH) ---
    elif mode and text:
        conn = get_db_connection(); cur = conn.cursor(dictionary=True)
        if mode == "name": cur.execute("SELECT * FROM anime WHERE name LIKE %s ORDER BY CAST(episode AS UNSIGNED) ASC", (f"%{text}%",))
        else: cur.execute("SELECT * FROM anime WHERE id=%s ORDER BY CAST(episode AS UNSIGNED) ASC", (text,))
        res = cur.fetchall(); cur.close(); conn.close()
        if not res: await update.message.reply_text("Topilmadi."); return
        grouped = {}
        for a in res:
            if a['id'] not in grouped: grouped[a['id']] = {"n": a['name'], "p": a['photo_file_id'], "l": a['lang'], "e": []}
            grouped[a['id']]["e"].append(a['episode'])
        for aid, d in grouped.items():
            kb = []; row = []
            for ep in d["e"]:
                row.append(InlineKeyboardButton(str(ep), callback_data=f"send_vid_{aid}_{ep}"))
                if len(row) == 4: kb.append(row); row = []
            if row: kb.append(row)
            await update.message.reply_photo(d['p'], caption=f"🎬 **{d['n']}**\n🌐 Til: {d['l']}\n🆔 ID: {aid}\n\nQismni tanlang:", reply_markup=InlineKeyboardMarkup(kb))
        context.user_data.clear()

# ====================== ASOSIY ISHGA TUSHIRISH ======================
async def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_messages))
    asyncio.create_task(update_anime_list_file())
    await app.initialize(); await app.start()
    await app.updater.start_polling()
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try: asyncio.run(main())
    except: pass
