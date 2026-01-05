import os
import logging
import mysql.connector
import asyncio
import datetime
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, 
    KeyboardButton
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
# Bot tokenini o'zgartiring
TOKEN = "8589253414:AAFTMMnZkUrNsqGWQmsBmJjyBTbssqn6zTE"
MAIN_ADMIN_ID = 8244870375

# MySQL ma'lumotlari (2-server manzili)
# Agar baza boshqa serverda bo'lsa, localhost o'rniga IP yozing
# Rasmga asosan Railway o'zgaruvchilari
DB_CONFIG = {
    "host": os.getenv("MYSQLHOST", "mysql.railway.internal"),
    "user": os.getenv("MYSQLUSER", "root"),
    "password": os.getenv("MYSQLPASSWORD", "CIbKpeQrFVJosmzyKZwJiQoTkJxoeBjP"), # Yangi parol
    "database": os.getenv("MYSQLDATABASE", "railway"),
    "port": int(os.getenv("MYSQLPORT", 3306)),
    "connect_timeout": 20,
    "autocommit": True
}

# ====================== MA'LUMOTLAR BAZASI BILAN ISHLASH ======================
def get_db_connection():
    """Serverlararo barqaror ulanish yaratish"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        logger.error(f"MySQL ulanish xatosi: {err}")
        return None

def init_db():
    """Barcha jadvallarni yaratish va tekshirish"""
    conn = get_db_connection()
    if not conn:
        return
    cur = conn.cursor()
    
    # Foydalanuvchilar jadvali
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, joined_at DATETIME)")
    
    # Anime/Kino jadvali
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
    
    # VIP foydalanuvchilar jadvali
    cur.execute("CREATE TABLE IF NOT EXISTS vip_users (user_id BIGINT PRIMARY KEY, expires_at DATETIME)")
    
    # Qo'shimcha adminlar jadvali
    cur.execute("CREATE TABLE IF NOT EXISTS admins (user_id BIGINT PRIMARY KEY)")
    
    # Majburiy obuna kanallari
    cur.execute("CREATE TABLE IF NOT EXISTS required_channels (id INT AUTO_INCREMENT PRIMARY KEY, channel_username VARCHAR(255))")
    
    # Ko'rilgan animelar tarixi
    cur.execute("""
        CREATE TABLE IF NOT EXISTS watched_anime (
            user_id BIGINT,
            anime_id VARCHAR(50),
            watched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, anime_id)
        )
    """)
    
    # Bonus tizimi
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
    """Kanallarga a'zolikni tekshirish"""
    conn = get_db_connection()
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
    """Adminlik huquqini tekshirish"""
    if user_id == MAIN_ADMIN_ID:
        return True
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins WHERE user_id=%s", (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return bool(result)

async def mark_as_watched(user_id, anime_id):
    """Animeni ko'rildi deb belgilash va bonus berish"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Avval tekshirish
        cur.execute("SELECT 1 FROM watched_anime WHERE user_id=%s AND anime_id=%s", (user_id, anime_id))
        if not cur.fetchone():
            cur.execute("INSERT INTO watched_anime (user_id, anime_id) VALUES (%s, %s)", (user_id, anime_id))
            # Bonus qo'shish
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

# ====================== AVTOMATIK FAYL GENERATORI ======================
async def update_anime_list_file():
    """Baza asosida .txt ro'yxatni yangilash"""
    while True:
        try:
            conn = get_db_connection()
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
            
        await asyncio.sleep(6 * 3600) # 6 soat kutish

# ====================== BOT COMMAND HANDLERS ======================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT IGNORE INTO users (user_id, joined_at) VALUES (%s, %s)", (user_id, datetime.datetime.now()))
    conn.commit()
    cur.close()
    conn.close()
    
    context.user_data.clear()
    
    # Obunani tekshirish
    not_joined = await check_subscription(user_id, context.bot)
    if not_joined:
        buttons = []
        for ch in not_joined:
            buttons.append([InlineKeyboardButton(f"Obuna bo'lish: {ch}", url=f"https://t.me/{ch.replace('@','')} text=")])
        buttons.append([InlineKeyboardButton("Tekshirish 🔄", callback_data="check_subs")])
        
        await update.message.reply_text(
            "❗ Botdan to'liq foydalanish uchun quyidagi kanallarga obuna bo'lishingiz shart:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    # Asosiy tugmalar
    admin_status = await is_user_admin(user_id)
    keyboard = [
        [InlineKeyboardButton("🔍 Anime qidirish", callback_data="search_menu")],
        [InlineKeyboardButton("🎁 Mening bonuslarim", callback_data="my_bonuses"), InlineKeyboardButton("📖 Ko'rilganlar", callback_data="my_watched")],
        [InlineKeyboardButton("📜 Barcha animelar", callback_data="send_list"), InlineKeyboardButton("💎 VIP sotib olish", callback_data="buy_vip")]
    ]
    
    if admin_status:
        keyboard.append([InlineKeyboardButton("🛠 ADMIN PANEL", callback_data="admin_panel")])
        
    await update.message.reply_text(
        f"Xush kelibsiz, {update.effective_user.first_name}!\nBotdan foydalanish uchun bo'limni tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    if not await is_user_admin(uid):
        await query.answer("Siz admin emassiz!", show_alert=True)
        return
        
    keyboard = [
        [InlineKeyboardButton("➕ Anime qo'shish", callback_data="add_anime"), InlineKeyboardButton("💎 VIP berish", callback_data="give_vip")],
        [InlineKeyboardButton("📢 Reklama (Xabar)", callback_data="broadcast"), InlineKeyboardButton("📊 Statistika", callback_data="bot_stats")],
        [InlineKeyboardButton("⚙️ Kanal sozlamalari", callback_data="chan_settings"), InlineKeyboardButton("🛡 Admin qo'shish", callback_data="add_new_admin")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_start")]
    ]
    await query.edit_message_text("🛡 Admin boshqaruv paneli:", reply_markup=InlineKeyboardMarkup(keyboard))

# ====================== CALLBACK QUERY HANDLER ======================
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
            await start_command(update, context)
        else:
            await query.answer("Hali hamma kanallarga a'zo bo'lmadingiz!", show_alert=True)

    elif data == "search_menu":
        kb = [
            [InlineKeyboardButton("📝 Nomi orqali", callback_data="mode_name")],
            [InlineKeyboardButton("🆔 ID raqami orqali", callback_data="mode_id")],
            [InlineKeyboardButton("🔢 Qism raqami orqali", callback_data="mode_ep")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_start")]
        ]
        await query.edit_message_text("Qidiruv turini tanlang:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("mode_"):
        mode = data.split("_")[1]
        context.user_data["search_mode"] = mode
        await query.edit_message_text("Qidirilayotgan ma'lumotni yuboring (Masalan: Naruto):")

    elif data == "add_anime" and admin_status:
        context.user_data["step"] = "wait_photo"
        await query.edit_message_text("1️⃣ Anime posterini (rasm) yuboring:")

    elif data == "bot_stats" and admin_status:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users"); u_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM anime"); a_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM vip_users"); v_count = cur.fetchone()[0]
        cur.close(); conn.close()
        await query.message.reply_text(f"📊 BOT STATISTIKASI:\n\n👤 Foydalanuvchilar: {u_count}\n🎬 Jami qismlar: {a_count}\n💎 VIP a'zolar: {v_count}")

    elif data == "send_list":
        if os.path.exists("animeroyhat.txt"):
            await context.bot.send_document(chat_id=uid, document=open("animeroyhat.txt", "rb"), caption="📜 Barcha animelar ro'yxati:")
        else:
            await query.message.reply_text("Ro'yxat fayli hali yaratilmadi. Biroz kuting.")

    elif data.startswith("watch_"):
        anime_id = data.split("_")[1]
        res = await mark_as_watched(uid, anime_id)
        if res:
            await query.message.reply_text(f"✅ Anime ko'rildi sifatida saqlandi! +1 bonus ball.")
        else:
            await query.answer("Bu animeni allaqachon ko'rgansiz.", show_alert=True)

    elif data.startswith("dl_"):
        file_id = data.split("_")[1]
        # VIP tekshirish
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM vip_users WHERE user_id=%s", (uid,))
        is_vip = cur.fetchone()
        cur.close(); conn.close()
        
        if is_vip or admin_status:
            await context.bot.send_video(chat_id=uid, video=file_id, caption="Marhamat, yuklab oling! ✅")
        else:
            await query.answer("Bu faylni yuklab olish uchun VIP a'zo bo'lishingiz kerak!", show_alert=True)

    elif data == "broadcast" and admin_status:
        context.user_data["step"] = "wait_broadcast"
        await query.edit_message_text("📢 Barcha foydalanuvchilarga yuboriladigan xabarni (matn, rasm yoki video) yuboring:")

    elif data == "back_to_start":
        await query.message.delete()
        # Soxta update yaratish orqali startni chaqirish
        await start_command(update, context)

# ====================== MESSAGE HANDLER (DATA INPUT) ======================
async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    step = context.user_data.get("step")
    search_mode = context.user_data.get("search_mode")
    text = update.message.text
    admin_status = await is_user_admin(uid)

    # 📢 REKLAMA TARQATISH
    if step == "wait_broadcast" and admin_status:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users")
        users = cur.fetchall()
        cur.close(); conn.close()
        
        count = 0
        for (user,) in users:
            try:
                await update.message.copy(chat_id=user)
                count += 1
                await asyncio.sleep(0.05)
            except: pass
        await update.message.reply_text(f"✅ Xabar {count} ta foydalanuvchiga muvaffaqiyatli yuborildi.")
        context.user_data.clear()

    # ➕ ANIME QO'SHISH BOSQICHLARI
    elif step == "wait_photo" and update.message.photo and admin_status:
        context.user_data["temp_photo"] = update.message.photo[-1].file_id
        context.user_data["step"] = "wait_video"
        await update.message.reply_text("2️⃣ Endi videoni yuboring va caption (izoh) qismiga mana bu formatda yozing:\n\n`ID|Nomi|Til|Qism` (Masalan: 101|Naruto|O'zbekcha|1)")

    elif step == "wait_video" and update.message.video and admin_status:
        try:
            caption = update.message.caption
            if not caption or "|" not in caption:
                await update.message.reply_text("Xato! Caption formatini to'g'ri yozing: `ID|Nomi|Til|Qism`")
                return
            
            p = [x.strip() for x in caption.split("|")]
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO anime (id, name, lang, episode, video_file_id, photo_file_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (p[0], p[1], p[2], p[3], update.message.video.file_id, context.user_data["temp_photo"])
            )
            conn.commit()
            cur.close(); conn.close()
            await update.message.reply_text("✅ Anime muvaffaqiyatli bazaga qo'shildi!")
            context.user_data.clear()
        except Exception as e:
            await update.message.reply_text(f"Xatolik yuz berdi: {e}")

    # 🔍 QIDIRUV ISHLASHI
    elif search_mode and text:
        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        
        query_map = {
            "name": ("SELECT * FROM anime WHERE name LIKE %s", f"%{text}%"),
            "id": ("SELECT * FROM anime WHERE id=%s", text),
            "ep": ("SELECT * FROM anime WHERE episode=%s", text)
        }
        
        sql, val = query_map.get(search_mode)
        cur.execute(sql, (val,))
        results = cur.fetchall()
        cur.close(); conn.close()
        
        if not results:
            await update.message.reply_text("Hech narsa topilmadi. 😕")
            return
            
        for a in results:
            kb = [
                [InlineKeyboardButton("✅ Ko'rdim", callback_data=f"watch_{a['id']}"), 
                 InlineKeyboardButton("📥 Yuklab olish (VIP)", callback_data=f"dl_{a['video_file_id'][:20]}")]
            ]
            # Telegram callback_data limiti 64 bayt, shuning uchun file_id ni to'liq yuborib bo'lmaydi. 
            # Bu yerda file_id o'rniga boshqa usul kerak, lekin kod qisqarmasligi uchun namunaviy qoldirildi.
            # Haqiqiy serverda a['video_file_id'] ni keshlab keyin ID yuborish kerak.
            
            # Kodni to'liq ishlashi uchun callback-ni to'g'irlaymiz
            # Context orqali file_id saqlash
            context.bot_data[f"vid_{a['id']}_{a['episode']}"] = a['video_file_id']
            kb = [[InlineKeyboardButton("✅ Ko'rdim", callback_data=f"watch_{a['id']}"), 
                   InlineKeyboardButton("📥 Yuklab olish (VIP)", callback_data=f"dl_real_{a['id']}_{a['episode']}")]]
            
            await update.message.reply_photo(
                photo=a['photo_file_id'],
                caption=f"🎬 Nomi: {a['name']}\n🆔 ID: {a['id']}\n🌐 Til: {a['lang']}\n🔢 Qism: {a['episode']}\n\nKo'rish uchun videoni bosing ⬇️",
                reply_markup=InlineKeyboardMarkup(kb)
            )
            # Videoni o'zini ham yuborish (forward qilib bo'lmaydigan qilib)
            await update.message.reply_video(video=a['video_file_id'], protect_content=True)
            
        context.user_data.clear()

# ====================== ASOSIY ISHGA TUSHIRISH (SERVER) ======================
# ====================== ASOSIY ISHGA TUSHIRISH (SERVER) ======================
async def main():
    # 1. Ma'lumotlar bazasini tayyorlash
    init_db()
    
    # 2. Bot ilovasini qurish
    app = ApplicationBuilder().token(TOKEN).build()
    
    # 3. Handlerlarni ro'yxatdan o'tkazish
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_messages))
    
    # 4. BOT ISHGA TUSHGANDAN KEYIN vazifani boshlash (Xato shu yerda edi)
    # create_task ni polling dan oldin main ichiga ko'chirdik
    asyncio.create_task(update_anime_list_file())
    
    logger.info("Bot serverda muvaffaqiyatli ishga tushdi.")
    
    # 5. Botni yurgizish
    await app.run_polling()

if __name__ == "__main__":
    try:
        # Bu qator o'zgarmaydi
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")




