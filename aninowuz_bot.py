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

# Conversation States
(
    A_ADD_CH, A_REM_CH, A_ADD_ADM, A_REM_ADM, 
    A_ADD_VIP, A_REM_VIP, A_ADD_ANI_POSTER, A_ADD_ANI_DATA,
    A_SEND_ADS_PASS, A_SEND_ADS_MSG, A_SEARCH_NAME
) = range(11)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
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
        return
    
    cur = conn.cursor()
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY, 
            joined_at DATETIME, 
            bonus INT DEFAULT 0,
            status VARCHAR(20) DEFAULT 'user'
        )""")

        cur.execute("""CREATE TABLE IF NOT EXISTS anime_list (
            anime_id VARCHAR(50) PRIMARY KEY, 
            name VARCHAR(255), 
            poster_id TEXT
        )""")

        cur.execute("""CREATE TABLE IF NOT EXISTS anime_episodes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            anime_id VARCHAR(50),
            episode INT,
            lang VARCHAR(50),
            file_id TEXT,
            FOREIGN KEY (anime_id) REFERENCES anime_list(anime_id) ON DELETE CASCADE
        )""")

        cur.execute("CREATE TABLE IF NOT EXISTS admins (user_id BIGINT PRIMARY KEY)")
        cur.execute("CREATE TABLE IF NOT EXISTS channels (id INT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(255))")
        
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
    if uid == MAIN_ADMIN_ID: return "main_admin"
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT status FROM users WHERE user_id=%s", (uid,))
    res = cur.fetchone()
    cur.close(); conn.close()
    return res[0] if res else "user"

async def check_sub(uid, bot):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT username FROM channels")
    channels = cur.fetchall(); cur.close(); conn.close()
    not_joined = []
    for (ch,) in channels:
        try:
            member = await bot.get_chat_member(ch if ch.startswith('@') else f"@{ch}", uid)
            if member.status not in ['member', 'administrator', 'creator']: not_joined.append(ch)
        except: not_joined.append(ch)
    return not_joined

# ====================== KLAVIATURALAR ======================
async def get_main_kb(uid):
    status = await get_user_status(uid)
    kb = [
        [KeyboardButton("🔍 Anime qidirish 🎬")],
        [KeyboardButton("🎁 Bonus ballarim 💰"), KeyboardButton("💎 VIP bo'lish ⭐")],
        [KeyboardButton("📜 Barcha anime ro'yxati 📂"), KeyboardButton("📖 Qo'llanma ❓")]
    ]
    if status in ["main_admin", "admin"]:
        kb.append([KeyboardButton("🛠 ADMIN PANEL")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def get_admin_kb(is_main=False):
    buttons = [
        [InlineKeyboardButton("📢 Kanallar", callback_data="adm_ch"), InlineKeyboardButton("🎬 Anime Qo'shish", callback_data="adm_ani_add")],
        [InlineKeyboardButton("💎 VIP Qo'shish", callback_data="adm_vip_add"), InlineKeyboardButton("❌ VIP Bekor qilish", callback_data="adm_vip_rem")],
        [InlineKeyboardButton("📊 Statistika", callback_data="adm_stats"), InlineKeyboardButton("🚀 Reklama", callback_data="adm_ads_start")],
        [InlineKeyboardButton("📤 DB Export (JSON)", callback_data="adm_export")]
    ]
    if is_main:
        buttons.append([InlineKeyboardButton("👮 Admin Qo'shish", callback_data="adm_user_add"), InlineKeyboardButton("🗑 Admin O'chirish", callback_data="adm_user_rem")])
    return InlineKeyboardMarkup(buttons)

# ====================== ASOSIY ISHLOVCHILAR ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT IGNORE INTO users (user_id, joined_at, status) VALUES (%s, %s, 'user')", (uid, datetime.datetime.now()))
    conn.commit(); cur.close(); conn.close()
    
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

    if data == "recheck":
        if not await check_sub(uid, context.bot):
            await query.message.delete()
            await context.bot.send_message(uid, "Tabriklaymiz! ✅ Obuna tasdiqlandi.", reply_markup=await get_main_kb(uid))
        else:
            await query.answer("❌ Hali hamma kanallarga a'zo emassiz!", show_alert=True)

    # Admin funksiyalari
    if status not in ["main_admin", "admin"]: return

    if data == "adm_ch":
        kb = [[InlineKeyboardButton("➕ Qo'shish", callback_data="add_channel"), InlineKeyboardButton("❌ O'chirish", callback_data="rem_channel")]]
        await query.edit_message_text("📢 Majburiy obuna kanallarini boshqarish:", reply_markup=InlineKeyboardMarkup(kb))

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
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users"); u_data = cur.fetchall()
        cur.execute("SELECT * FROM anime_list"); a_data = cur.fetchall()
        full_data = {"backup_date": str(datetime.datetime.now()), "users": u_data, "anime": a_data}
        with open("full_db_export.json", "w") as f: json.dump(full_data, f, default=str, indent=4)
        await query.message.reply_document(open("full_db_export.json", "rb"), caption="📦 Barcha ma'lumotlar JSON shaklida.")
        cur.close(); conn.close()

    elif data == "adm_ads_start":
        await query.message.reply_text("🔐 Reklama paneliga kirish uchun parolni kiriting:")
        return A_SEND_ADS_PASS

# ====================== ANIME QIDIRISH VA PAGINATION ======================
async def search_anime_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    
    conn = get_db(); cur = conn.cursor(dictionary=True)
    # Nomi yoki ID bo'yicha qidirish
    cur.execute("SELECT * FROM anime_list WHERE anime_id=%s OR name LIKE %s", (text, f"%{text}%"))
    anime = cur.fetchone()
    
    if not anime:
        await update.message.reply_text("😔 Kechirasiz, bunday anime topilmadi.")
        return

    # Qismlarni olish
    cur.execute("SELECT episode FROM anime_episodes WHERE anime_id=%s ORDER BY episode ASC", (anime['anime_id'],))
    episodes = cur.fetchall()
    cur.close(); conn.close()

    if not episodes:
        await update.message.reply_text("Bu animega hali qismlar joylanmagan.")
        return

    # Pagination Keyboard (1-10 qismlar)
    keyboard = []
    row = []
    for i, ep in enumerate(episodes[:10]):
        row.append(InlineKeyboardButton(str(ep['episode']), callback_data=f"get_ep_{anime['anime_id']}_{ep['episode']}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    
    if len(episodes) > 10:
        keyboard.append([InlineKeyboardButton("Keyingi ➡️", callback_data=f"page_{anime['anime_id']}_10")])

    await update.message.reply_photo(
        photo=anime['poster_id'],
        caption=f"🎬 **{anime['name']}**\n🆔 ID: {anime['anime_id']}\n\nQismni tanlang 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def get_episode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    # Format: get_ep_{anime_id}_{episode}
    _, _, aid, ep_num = query.data.split("_")
    
    status = await get_user_status(uid)
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM anime_episodes WHERE anime_id=%s AND episode=%s", (aid, ep_num))
    ep_data = cur.fetchone()
    
    if not ep_data:
        await query.answer("Qism topilmadi.")
        return

    # Bonus ball berish
    bonus_add = 2 if status == 'vip' else 1
    cur.execute("UPDATE users SET bonus = bonus + %s WHERE user_id=%s", (bonus_add, uid))
    
    # Yuklab olish tugmasi faqat VIP/Admin uchun
    kb = None
    if status in ['vip', 'admin', 'main_admin']:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📥 Qurilmaga yuklab olish", callback_data=f"download_{ep_data['id']}")]])

    # Oddiy user uchun protect_content=True (Saqlash taqiqlangan)
    is_protected = False if status in ['vip', 'admin', 'main_admin'] else True

    await context.bot.send_video(
        chat_id=uid,
        video=ep_data['file_id'],
        caption=f"🎬 {aid} | {ep_num}-qism\n🌐 Til: {ep_data['lang']}\n\n🎁 Bonus: +{bonus_add}",
        protect_content=is_protected,
        reply_markup=kb
    )
    cur.close(); conn.close()

# ====================== CONVERSATION STEPS ======================
async def add_ani_poster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['poster'] = update.message.photo[-1].file_id
    await update.message.reply_text("✅ Poster qabul qilindi.\n\nEndi ma'lumotni formatda yuboring:\n`ID | Nomi | Tili | Qismi`\n\nMisol: `101 | Naruto | O'zb | 1`", parse_mode="Markdown")
    return A_ADD_ANI_DATA

async def add_ani_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        raw_data = update.message.text.split("|")
        aid, name, lang, ep = [i.strip() for i in raw_data]
        
        await update.message.reply_text(f"Oxirgi qadam: {aid} uchun VIDEONI yuboring:")
        context.user_data['tmp_ani'] = {"id": aid, "name": name, "lang": lang, "ep": ep}
        return A_ADD_ANI_DATA # Video kutamiz
    except:
        if update.message.video:
            v_id = update.message.video.file_id
            d = context.user_data['tmp_ani']
            conn = get_db(); cur = conn.cursor()
            # Anime ro'yxatiga qo'shish (agar bo'lmasa)
            cur.execute("INSERT IGNORE INTO anime_list (anime_id, name, poster_id) VALUES (%s, %s, %s)", (d['id'], d['name'], context.user_data['poster']))
            # Qismni qo'shish
            cur.execute("INSERT INTO anime_episodes (anime_id, episode, lang, file_id) VALUES (%s, %s, %s, %s)", (d['id'], d['ep'], d['lang'], v_id))
            conn.commit(); cur.close(); conn.close()
            await update.message.reply_text("✅ Anime/Qism muvaffaqiyatli qo'shildi!", reply_markup=await get_main_kb(update.effective_user.id))
            return ConversationHandler.END
        await update.message.reply_text("Xatolik! Formatni tekshiring.")
        return A_ADD_ANI_DATA

# ====================== MAIN FUNKSIYA (RENDER.COM WEB SERVICE UCHUN) ======================
def main():
    # Ma'lumotlar bazasini yaratish/tekshirish
    init_db()

    # ApplicationBuilder orqali botni qurish
    app_bot = ApplicationBuilder().token(TOKEN).build()

    # 1. Conversation Handler - Murakkab bosqichli jarayonlar uchun
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_callback, pattern="^(adm_ani_add|adm_ads_start|adm_vip_add)$")
        ],
        states={
            A_ADD_ANI_POSTER: [MessageHandler(filters.PHOTO, add_ani_poster)],
            A_ADD_ANI_DATA: [MessageHandler(filters.TEXT | filters.VIDEO, add_ani_data)],
            A_SEND_ADS_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, 
                lambda u, c: A_SEND_ADS_MSG if u.message.text == ADVERTISING_PASSWORD else ConversationHandler.END)],
            A_SEND_ADS_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, ads_send_finish)],
            A_ADD_VIP: [MessageHandler(filters.TEXT & ~filters.COMMAND, exec_vip_add)],
        },
        fallbacks=[CommandHandler("cancel", start), CommandHandler("start", start)],
    )

    # 2. Asosiy buyruqlar va xabarlar
    app_bot.add_handler(CommandHandler("start", start))
    
    # Admin Panel tugmasi
    app_bot.add_handler(MessageHandler(
        filters.Regex("^🛠 ADMIN PANEL$"), 
        lambda u, c: u.message.reply_text("Boshqaruv paneli:", 
        reply_markup=get_admin_kb(u.effective_user.id == MAIN_ADMIN_ID))
    ))

    # Bonus ballar tugmasi
    app_bot.add_handler(MessageHandler(filters.Regex("^🎁 Bonus ballarim 💰$"), show_bonus))
    
    # VIP bo'lish va Qo'llanma tugmalari
    app_bot.add_handler(MessageHandler(filters.Regex("^💎 VIP bo'lish ⭐$"), 
        lambda u, c: u.message.reply_text(f"💎 VIP status olish uchun admin bilan bog'laning: @Admin_Username")))
    
    app_bot.add_handler(MessageHandler(filters.Regex("^📖 Qo'llanma ❓$"), 
        lambda u, c: u.message.reply_text("📖 *Botdan foydalanish:*\n1. Anime nomini yozing.\n2. Chiqqan qismlardan birini tanlang.", parse_mode="Markdown")))

    # 3. Callback Query Handlers (Tugmalar uchun)
    app_bot.add_handler(conv_handler) # Conversation birinchi bo'lishi kerak
    app_bot.add_handler(CallbackQueryHandler(get_episode_handler, pattern="^get_ep_"))
    app_bot.add_handler(CallbackQueryHandler(handle_callback)) # Qolgan barcha tugmalar uchun

    # 4. Global matnli qidiruv (Anime qidirish mantiqi)
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_anime_logic))

    # Render uchun Web Serverni alohida oqimda ishga tushirish
    print("🌐 Web Server 8080-portda ishga tushmoqda...")
    keep_alive()

    # Botni ishga tushirish
    print("🤖 Bot polling rejimida ishlamoqda...")
    app_bot.run_polling()

# ====================== QO'SHIMCHA FUNKSIYALAR ======================

async def ads_send_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reklamani barcha foydalanuvchilarga yuborish funksiyasi"""
    msg = update.message
    conn = get_db()
    if not conn:
        await update.message.reply_text("❌ Bazaga ulanib bo'lmadi.")
        return ConversationHandler.END
        
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()
    cur.close()
    conn.close()

    count = 0
    status_msg = await update.message.reply_text(f"🚀 Reklama yuborish boshlandi (0/{len(users)})...")

    for user in users:
        try:
            # Reklamani hamma foydalanuvchilarga nusxalash
            await context.bot.copy_message(
                chat_id=user[0],
                from_chat_id=update.effective_chat.id,
                message_id=msg.message_id
            )
            count += 1
            if count % 50 == 0:
                await status_msg.edit_text(f"🚀 Reklama yuborilmoqda ({count}/{len(users)})...")
        except Exception:
            continue

    await update.message.reply_text(f"✅ Reklama yakunlandi. {count} ta foydalanuvchiga yuborildi.")
    return ConversationHandler.END

async def show_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT bonus, status FROM users WHERE user_id=%s", (uid,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    
    if res:
        bonus, status = res
        text = f"👤 **Sizning ma'lumotlaringiz:**\n\n💰 Bonus ballar: `{bonus}` ball\n🌟 Status: `{status.upper()}`"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text("Ma'lumot topilmadi. /start bosing.")

async def exec_vip_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin tomonidan foydalanuvchini VIP qilish funksiyasi"""
    text = update.message.text
    # Kutilayotgan format: "user_id" yoki "user_id kun"
    parts = text.split()
    
    if not parts:
        await update.message.reply_text("❌ Iltimos, User ID kiriting.")
        return A_ADD_VIP

    try:
        target_id = int(parts[0])
        # Agar kun ko'rsatilmagan bo'lsa, standart 30 kun
        days = int(parts[1]) if len(parts) > 1 else 30
        
        conn = get_db()
        cur = conn.cursor()
        # Foydalanuvchi statusini VIP-ga o'zgartirish
        cur.execute("UPDATE users SET status = 'vip' WHERE user_id = %s", (target_id,))
        conn.commit()
        cur.close()
        conn.close()

        await update.message.reply_text(f"✅ Foydalanuvchi {target_id} muvaffaqiyatli VIP qilindi ({days} kun).")
    except ValueError:
        await update.message.reply_text("❌ Xato! User ID faqat raqamlardan iborat bo'lishi kerak.")
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik yuz berdi: {e}")

    return ConversationHandler.END

# ====================== MAIN FUNKSIYA ======================
def main():
    init_db()

    app_bot = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_callback, pattern="^(adm_ani_add|adm_ads_start|adm_vip_add)$")
        ],
        states={
            A_ADD_ANI_POSTER: [MessageHandler(filters.PHOTO, add_ani_poster)],
            A_ADD_ANI_DATA: [MessageHandler(filters.TEXT | filters.VIDEO, add_ani_data)],
            A_SEND_ADS_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, 
                lambda u, c: A_SEND_ADS_MSG if u.message.text == ADVERTISING_PASSWORD else ConversationHandler.END)],
            A_SEND_ADS_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, ads_send_finish)],
            A_ADD_VIP: [MessageHandler(filters.TEXT & ~filters.COMMAND, exec_vip_add)],
        },
        fallbacks=[CommandHandler("cancel", start), CommandHandler("start", start)],
    )

    app_bot.add_handler(CommandHandler("start", start))
    
    app_bot.add_handler(MessageHandler(
        filters.Regex("^🛠 ADMIN PANEL$"), 
        lambda u, c: u.message.reply_text("Boshqaruv paneli:", 
        reply_markup=get_admin_kb(u.effective_user.id == MAIN_ADMIN_ID))
    ))

    app_bot.add_handler(MessageHandler(filters.Regex("^🎁 Bonus ballarim 💰$"), show_bonus))
    app_bot.add_handler(MessageHandler(filters.Regex("^💎 VIP bo'lish ⭐$"), 
        lambda u, c: u.message.reply_text(f"💎 VIP status olish uchun admin bilan bog'laning: @Admin_Username")))
    
    app_bot.add_handler(MessageHandler(filters.Regex("^📖 Qo'llanma ❓$"), 
        lambda u, c: u.message.reply_text("📖 *Botdan foydalanish:*\n1. Anime nomini yozing.\n2. Chiqqan qismlardan birini tanlang.", parse_mode="Markdown")))

    app_bot.add_handler(conv_handler)
    app_bot.add_handler(CallbackQueryHandler(get_episode_handler, pattern="^get_ep_"))
    app_bot.add_handler(CallbackQueryHandler(handle_callback))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_anime_logic))

    keep_alive()
    print("🤖 Bot polling rejimida ishlamoqda...")
    app_bot.run_polling()

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Bot to'xtatildi!")

