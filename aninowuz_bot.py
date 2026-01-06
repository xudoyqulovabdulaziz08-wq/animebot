import os
import logging
import mysql.connector
import asyncio
import datetime
import json
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes, ConversationType
)

# ====================== KONFIGURATSIYA ======================
TOKEN = "8258233749:AAHdFklNhjGlE7pK0026vJrMYJaK8iiddXo"
MAIN_ADMIN_ID = 8244870375
ADVERTISING_PASSWORD = "2009"  # Reklama uchun parol

DB_CONFIG = {
    "host": "mysql.railway.internal",
    "user": "root",
    "password": "CIbKpeQrFVJosmzyKZwJiQoTkJxoeBjP",
    "database": "railway",
    "port": 3306,
    "autocommit": True
}

# Holatlar (Conversation States)
(
    A_ADD_CH, A_REM_CH, A_ADD_ADM, A_REM_ADM, 
    A_ADD_VIP, A_REM_VIP, A_ADD_ANI_ID, A_ADD_ANI_NAME,
    A_ADD_ANI_LANG, A_ADD_ANI_EP, A_ADD_ANI_FILE,
    A_SEND_ADS_PASS, A_SEND_ADS_MSG, A_SEARCH_NAME
) = range(14)

# ====================== LOGGING ======================
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ====================== MA'LUMOTLAR BAZASI ======================
def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, joined_at DATETIME, bonus INT DEFAULT 0)")
    cur.execute("CREATE TABLE IF NOT EXISTS anime (id VARCHAR(50), name VARCHAR(255), lang VARCHAR(50), ep VARCHAR(50), file_id TEXT, PRIMARY KEY(id, ep))")
    cur.execute("CREATE TABLE IF NOT EXISTS admins (user_id BIGINT PRIMARY KEY)")
    cur.execute("CREATE TABLE IF NOT EXISTS vip_users (user_id BIGINT PRIMARY KEY, expires DATETIME)")
    cur.execute("CREATE TABLE IF NOT EXISTS channels (id INT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(255))")
    conn.commit()
    cur.close()
    conn.close()

# ====================== TEKSHIRUV FUNKSIYALARI ======================
async def is_admin(uid):
    if uid == MAIN_ADMIN_ID: return True
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT 1 FROM admins WHERE user_id=%s", (uid,))
    res = cur.fetchone(); cur.close(); conn.close()
    return bool(res)

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
    kb = [
        [KeyboardButton("🔍 Anime qidirish")],
        [KeyboardButton("🎁 Bonus ballarim"), KeyboardButton("💎 VIP bo'lish")],
        [KeyboardButton("📜 Barcha anime ro'yxati"), KeyboardButton("📖 Qo'llanma")]
    ]
    if await is_admin(uid): kb.append([KeyboardButton("🛠 ADMIN PANEL")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def get_admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Kanallar", callback_data="adm_ch"), InlineKeyboardButton("👮 Adminlar", callback_data="adm_manage")],
        [InlineKeyboardButton("💎 VIP boshqarish", callback_data="adm_vip"), InlineKeyboardButton("🎬 Anime boshqarish", callback_data="adm_anime")],
        [InlineKeyboardButton("📤 DB Export", callback_data="adm_export"), InlineKeyboardButton("🚀 Reklama", callback_data="adm_ads")]
    ])

# ====================== ASOSIY KOMANDALAR ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT IGNORE INTO users (user_id, joined_at) VALUES (%s, %s)", (uid, datetime.datetime.now()))
    conn.commit(); cur.close(); conn.close()
    
    not_joined = await check_sub(uid, context.bot)
    if not_joined:
        btn = [[InlineKeyboardButton(f"Obuna bo'lish", url=f"https://t.me/{c.replace('@','')}") ] for c in not_joined]
        btn.append([InlineKeyboardButton("Tekshirish ✅", callback_data="recheck")])
        return await update.message.reply_text("Botdan foydalanish uchun kanallarga a'zo bo'ling:", reply_markup=InlineKeyboardMarkup(btn))
    
    await update.message.reply_text("Xush kelibsiz!", reply_markup=await get_main_kb(uid))

# ====================== ADMIN PANEL MANTIQI ======================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update.effective_user.id):
        await update.message.reply_text("Boshqaruv paneli:", reply_markup=get_admin_kb())

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    await query.answer()

    if data == "recheck":
        if not await check_sub(uid, context.bot):
            await query.message.delete()
            await context.bot.send_message(uid, "Obuna tasdiqlandi!", reply_markup=await get_main_kb(uid))
        else: await query.answer("Hali hamma kanallarga a'zo emassiz!", show_alert=True)

    if not await is_admin(uid): return

    if data == "adm_ch":
        kb = [[InlineKeyboardButton("➕ Kanal qo'shish", callback_data="add_ch")],
              [InlineKeyboardButton("❌ Kanal o'chirish", callback_data="rem_ch")],
              [InlineKeyboardButton("📜 Ro'yxat", callback_data="list_ch")]]
        await query.edit_message_text("Kanal boshqarish:", reply_markup=InlineKeyboardMarkup(kb))
    
    elif data == "add_ch":
        await query.message.reply_text("Kanal usernameni yuboring (masalan: @kanal):")
        return A_ADD_CH
    
    elif data == "list_ch":
        conn = get_db(); cur = conn.cursor(); cur.execute("SELECT username FROM channels")
        res = cur.fetchall(); cur.close(); conn.close()
        text = "Majburiy kanallar:\n" + "\n".join([f"- {r[0]}" for r in res])
        await query.message.reply_text(text)

    elif data == "adm_manage" and uid == MAIN_ADMIN_ID:
        kb = [[InlineKeyboardButton("➕ Admin qo'shish", callback_data="add_adm")],
              [InlineKeyboardButton("❌ Admin o'chirish", callback_data="rem_adm")],
              [InlineKeyboardButton("📜 Adminlar", callback_data="list_adm")]]
        await query.edit_message_text("Admin boshqarish:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "adm_export":
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users"); u_data = cur.fetchall()
        cur.execute("SELECT * FROM anime"); a_data = cur.fetchall()
        full_data = {"users": u_data, "anime": a_data}
        with open("backup.json", "w") as f: json.dump(full_data, f, default=str)
        await query.message.reply_document(open("backup.json", "rb"), caption="DB Export")
        cur.close(); conn.close()

    elif data == "adm_ads":
        await query.message.reply_text("Reklama yuborish uchun parolni kiriting:")
        return A_SEND_ADS_PASS

    elif data == "adm_anime":
        kb = [[InlineKeyboardButton("➕ Anime qo'shish", callback_data="add_ani")],
              [InlineKeyboardButton("❌ Animeni o'chirish", callback_data="rem_ani")]]
        await query.edit_message_text("Anime boshqarish:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "add_ani":
        await query.message.reply_text("Anime ID sini kiriting (masalan: 101):")
        return A_ADD_ANI_ID

# ====================== FOYDALANUVCHI FUNKSIYALARI ======================
async def user_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text
    
    # Majburiy obuna tekshiruvi har bir xabarda
    if await check_sub(uid, context.bot):
        return await start(update, context)

    if text == "🎁 Bonus ballarim":
        conn = get_db(); cur = conn.cursor(); cur.execute("SELECT bonus FROM users WHERE user_id=%s", (uid,))
        res = cur.fetchone(); cur.close(); conn.close()
        await update.message.reply_text(f"Sizning jami bonus ballaringiz: {res[0] if res else 0} ⭐️")

    elif text == "📖 Qo'llanma":
        guide = (
            "🤖 *Botdan foydalanish qo'llanmasi*\n\n"
            "1. Anime qidirish tugmasi orqali ID yoki nom bo'yicha qidirishingiz mumkin.\n"
            "2. Har bir ko'rilgan anime uchun 1 bonus ball beriladi.\n"
            "3. VIP a'zo bo'lish uchun adminga murojaat qiling.\n"
            "4. Barcha anime ro'yxatini fayl ko'rinishida yuklab olishingiz mumkin."
        )
        await update.message.reply_text(guide, parse_mode="Markdown")

    elif text == "💎 VIP bo'lish":
        await update.message.reply_text(f"VIP status olish uchun admin bilan bog'laning: @AdminUsername")

    elif text == "📜 Barcha anime ro'yxati":
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, name, lang, ep FROM anime"); res = cur.fetchall()
        cur.close(); conn.close()
        with open("animes.json", "w") as f: json.dump(res, f, indent=4)
        await update.message.reply_document(open("animes.json", "rb"), caption="Barcha animelar ro'yxati")

    elif text == "🔍 Anime qidirish":
        kb = [[InlineKeyboardButton("🆔 ID bo'yicha", callback_data="search_id"),
               InlineKeyboardButton("📝 Nomi bo'yicha", callback_data="search_name")]]
        await update.message.reply_text("Qidirish usulini tanlang:", reply_markup=InlineKeyboardMarkup(kb))

    elif text.isdigit(): # ID bilan qidirish
        await send_anime_by_id(update, context, text)

# ====================== QIDIRUV VA BONUS MANTIQI ======================
async def send_anime_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE, aid):
    uid = update.effective_user.id
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM anime WHERE id=%s", (aid,))
    res = cur.fetchall()
    if res:
        for a in res:
            await update.message.reply_video(video=a['file_id'], caption=f"🎬 {a['name']}\n🔢 Qism: {a['ep']}\n🌐 Til: {a['lang']}")
        # Bonus berish
        cur.execute("UPDATE users SET bonus = bonus + 1 WHERE user_id=%s", (uid,))
        conn.commit()
    else:
        await update.message.reply_text("Kechirasiz, ushbu ID bilan anime topilmadi.")
    cur.close(); conn.close()

# ====================== CONVERSATION HANDLER FUNKSIYALARI ======================
async def add_ch_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO channels (username) VALUES (%s)", (update.message.text,))
    conn.commit(); cur.close(); conn.close()
    await update.message.reply_text("Kanal qo'shildi!", reply_markup=await get_main_kb(update.effective_user.id))
    return -1

async def ads_pass_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == ADVERTISING_PASSWORD:
        await update.message.reply_text("Parol to'g'ri. Reklama xabarini yuboring:")
        return A_SEND_ADS_MSG
    else:
        await update.message.reply_text("Parol noto'g'ri! Bekor qilindi.")
        return -1

async def ads_send_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db(); cur = conn.cursor(); cur.execute("SELECT user_id FROM users")
    users = cur.fetchall(); cur.close(); conn.close()
    count = 0
    for (uid,) in users:
        try:
            await update.message.copy(uid)
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await update.message.reply_text(f"Reklama {count} kishiga yuborildi.")
    return -1

# ====================== ANIME QO'SHISH (STEP-BY-STEP) ======================
async def ani_id_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ani_id'] = update.message.text
    await update.message.reply_text("Anime nomini kiriting:")
    return A_ADD_ANI_NAME

async def ani_name_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ani_name'] = update.message.text
    await update.message.reply_text("Tilni kiriting (O'zb/Rus):")
    return A_ADD_ANI_LANG

async def ani_lang_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ani_lang'] = update.message.text
    await update.message.reply_text("Qismni kiriting (masalan: 1-qism):")
    return A_ADD_ANI_EP

async def ani_ep_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ani_ep'] = update.message.text
    await update.message.reply_text("Videoni yuboring:")
    return A_ADD_ANI_FILE

async def ani_file_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fid = update.message.video.file_id
    d = context.user_data
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO anime (id, name, lang, ep, file_id) VALUES (%s, %s, %s, %s, %s)", 
                (d['ani_id'], d['ani_name'], d['ani_lang'], d['ani_ep'], fid))
    conn.commit(); cur.close(); conn.close()
    await update.message.reply_text("Anime saqlandi!")
    return -1

# ====================== MAIN ======================
def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    # Admin Conversation
    admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(callback_query_handler, pattern="^(add_ch|adm_ads|add_ani)$")
        ],
        states={
            A_ADD_CH: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_ch_finish)],
            A_SEND_ADS_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ads_pass_check)],
            A_SEND_ADS_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, ads_send_finish)],
            A_ADD_ANI_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ani_id_step)],
            A_ADD_ANI_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ani_name_step)],
            A_ADD_ANI_LANG: [MessageHandler(filters.TEXT & ~filters.COMMAND, ani_lang_step)],
            A_ADD_ANI_EP: [MessageHandler(filters.TEXT & ~filters.COMMAND, ani_ep_step)],
            A_ADD_ANI_FILE: [MessageHandler(filters.VIDEO, ani_file_step)],
        },
        fallbacks=[CommandHandler("cancel", start)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^🛠 ADMIN PANEL$"), admin_panel))
    app.add_handler(admin_conv)
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user_messages))

    print("Bot ishlamoqda...")
    app.run_polling()

if __name__ == "__main__":
    main()
