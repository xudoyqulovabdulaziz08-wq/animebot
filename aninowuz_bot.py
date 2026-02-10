import os
import requests
import logging
import aiomysql
import asyncio
import httpx
import urllib.parse
import datetime
import json
import io
import ssl
import random  # Tasodifiy tavsiyalar va reklama uchun
import re      # Matnlarni (shikoyat, izoh) filtrlash uchun
import matplotlib
matplotlib.use('Agg') # Grafikni ekranga chiqarmay, faylga (xotiraga) yozish rejimi
from threading import Thread

# === YANGI QO'SHILADIGAN KUTUBXONALAR ===
from apscheduler.schedulers.asyncio import AsyncIOScheduler # Vaqtli vazifalarni bajarish uchun (masalan, obunani tekshirish, reklama va VIP muddati)
from apscheduler.schedulers.background import BackgroundScheduler # Avtomatik reklama va VIP muddati uchun
import matplotlib.pyplot as plt # Admin panel uchun statistika grafiklari (rasm ko'rinishida)

# ========================================

# Flask qismi
from flask import Flask, render_template, Response, request, jsonify

# Telegram Bot qismi
from telegram import (
    LabeledPrice, Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InputMediaPhoto # Anime rasm qidiruvida natijani chiqarish uchun
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)
from telegram.error import Forbidden, TelegramError
from telegram import LabeledPrice
from telegram.constants import ParseMode # Xabarlarni chiroyli (HTML/Markdown) chiqarish uchun

# Logging sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====================== WEB SERVICE (RENDER UCHUN) ======================
app = Flask('')

# Bot tokenini Render Environment Variables'dan oladi
BOT_TOKEN = os.getenv("BOT_TOKEN") 
# Siz bergan guruh ID raqami



@app.route('/')
async def home(): # 'async' qo'shildi
    conn = None
    try:
        # get_db() asinxron bo'lishi kerak
        conn = await get_db() 
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT anime_id as id, name, poster_id FROM anime_list ORDER BY id DESC")
            animes = await cursor.fetchall()
            return render_template('aninovuz.html', animes=animes)
    except Exception as e:
        logger.error(f"Saytda xatolik: {e}")
        return f"Xatolik: {e}"
    finally:
        if conn:
            # aiomysql pool ishlatganda db.close() o'rniga pool.release(conn) ishlatiladi
            db_pool.release(conn)

# --- YANGI QO'SHILGAN RASM PROXY FUNKSIYASI ---
@app.route('/image/<file_id>')
def get_telegram_image(file_id):
    try:
        # 1. Telegram API orqali fayl yo'lini topish (TOKEN o'zgaruvchisi bilan)
        file_info_url = f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={file_id}"
        file_info = requests.get(file_info_url).json()
        
        if not file_info.get('ok'):
            return "Fayl topilmadi", 404
            
        file_path = file_info['result']['file_path']
        
        # 2. Haqiqiy rasm faylini yuklab olish
        img_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
        img_res = requests.get(img_url)
        
        # 3. Rasmni brauzerga qaytarish
        return Response(img_res.content, mimetype='image/jpeg')
    except Exception as e:
        return str(e), 500
@app.route('/services.html')
async def services():
    conn = None
    try:
        # 1. Asinxron ulanish olish
        conn = await get_db()
        
        # 2. 'async with' orqali kursorni ochish (aiomysql uchun shart)
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            # 3. 'await' bilan so'rovni bajarish
            await cursor.execute("SELECT anime_id as id, name, poster_id FROM anime_list ORDER BY name ASC")
            
            # 4. 'await' bilan natijani olish
            all_animes = await cursor.fetchall()
            
            # Kursorni yopish async with ichida avtomatik bajariladi
            return render_template('services.html', animes=all_animes)
            
    except Exception as e:
        logger.error(f"Services sahifasida xato: {e}")
        return f"Xato: {e}"
    finally:
        # 5. aiomysql pool bilan ishlashda db.close() ishlatilmaydi
        # Uning o'rniga ulanishni poolga qaytarish kerak
        if conn:
            await db_pool.release(conn)
    
@app.route('/contact.html')
def contact():
    # Tarix yoki aloqa sahifasi
    return render_template('contact.html')

@app.route('/malumot.html')
async def about():
    conn = None
    try:
        conn = await get_db()
        async with conn.cursor() as cursor:
            # 1. Jami animelar
            await cursor.execute("SELECT COUNT(*) FROM anime_list")
            res = await cursor.fetchone()
            anime_count = res[0] if res else 0

            # 2. Jami foydalanuvchilar
            await cursor.execute("SELECT COUNT(*) FROM users")
            res = await cursor.fetchone()
            user_count = res[0] if res else 0

            # 3. VIP foydalanuvchilar
            await cursor.execute("SELECT COUNT(*) FROM users WHERE status = 'vip'")
            res = await cursor.fetchone()
            vip_count = res[0] if res else 0

            return render_template('malumot.html', 
                                   anime_count=anime_count, 
                                   user_count=user_count, 
                                   vip_count=vip_count)
    except Exception as e:
        logger.error(f"Statistika xatosi: {e}")
        return render_template('malumot.html', anime_count="0", user_count="0", vip_count="0")
    finally:
        if conn:
            await db_pool.release(conn)
# ----------------------------------------------
def run():
    # Render'da portni o'zi beradi, topilmasa 10000 ni oladi
    port = int(os.environ.get("PORT", 10000))
    # use_reloader=False - bu juda muhim!
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()
    

# ====================== XAVFSIZ KONFIGURATSIYA ======================

# Ularni Render Dashboard -> Settings -> Environment Variables qismiga qo'shing.

TOKEN = os.getenv("TOKEN")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", -5128040712)) # Guruh ID sini ham o'zgartiring
MAIN_ADMIN_ID = int(os.getenv("ADMIN_ID", 8244870375))
ADVERTISING_PASSWORD = os.getenv("ADS_PASS", "2009")

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", 27624)),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "db": os.getenv("DB_NAME"), # <--- "database" edi, "db" bo'lishi shart!
    "autocommit": True,
    # Quyidagi ikki qator aiomysql uchun standart emas, ularni olib tashlasangiz ham bo'ladi
    "ssl_disabled": False, 
    "ssl_mode": "REQUIRED" 
}


# ====================== CONVERSATION STATES ======================
(
    # --- ADMIN & KANALLAR (0-5) ---
    A_ADD_CH,            # 0: Kanal qo'shish
    A_REM_CH,            # 1: Kanal o'chirish
    A_ADD_ADM,           # 2: Yangi admin ID sini qabul qilish
    A_CONFIRM_REM_ADM,   # 3: Adminni o'chirishni tasdiqlash
    A_ADD_VIP,           # 4: VIP foydalanuvchi qo'shish
    A_REM_VIP,           # 5: VIP-ni bekor qilish

    # --- REKLAMA VA QIDIRUV (6-12) ---
    A_SEND_ADS_PASS,      # 6: Reklama parolini tekshirish
    A_SELECT_ADS_TARGET,  # 7: Reklama nishonini tanlash
    A_SEND_ADS_MSG,       # 8: Reklama xabarini yuborish
    A_SEARCH_BY_ID,       # 9: ID orqali qidirish
    A_SEARCH_BY_NAME,     # 10: Nomi orqali qidirish

    # --- ANIME CONTROL PANEL ---
    A_ANI_CONTROL,        # 11: Anime control asosiy menyusi
    A_ADD_MENU,           # 12: Add Anime paneli
    
    # Yangi Anime qo'shish (Fandub qo'shildi)
    A_GET_POSTER,         # 13: Poster qabul qilish
    A_GET_DATA,           # 14: Ma'lumotlar (Nomi | Tili | Janri | Yili | Fandub)
    A_ADD_EP_FILES,       # 15: Video qabul qilish
    
    # Mavjud animega qism qo'shish
    A_SELECT_ANI_EP,      # 16: Qism qo'shish uchun anime tanlash
    A_ADD_NEW_EP_FILES,   # 17: Videolar qabul qilish

    # Anime List va O'chirish
    A_LIST_VIEW,          # 18: Animelar ro'yxati
    A_REM_MENU,           # 19: O'chirish menyusi
    A_REM_ANI_LIST,       # 20: O'chirsh uchun anime tanlash
    A_REM_EP_ANI_LIST,    # 21: Qism o'chirish uchun anime tanlash
    A_REM_EP_NUM_LIST,    # 22: Qism tanlash
    
    # === YANGI QO'SHILGAN STATUSLAR (23-35) ===
    
    # 20-band: Murojaatlar va Shikoyatlar
    U_FEEDBACK_SUBJ,      # 23: Shikoyat mavzusini tanlash
    U_FEEDBACK_MSG,       # 24: Shikoyat matnini yozish

    # 5-band: Izohlar tizimi
    U_ADD_COMMENT,        # 25: Animega izoh yozish holati

    # 1-band: AI Qidiruv (Agar rasm yuborgandan keyin tasdiqlash kerak bo'lsa)
    U_AI_PHOTO_SEARCH,    # 26: AI uchun rasm kutish

    # 26-band: Avtomatik/Vaqtli Reklama qo'shish (Admin uchun)
    A_ADD_AUTO_AD_CONTENT,# 27: Reklama kontentini olish (Rasm/Video)
    A_ADD_AUTO_AD_DAYS,   # 28: Reklama necha kun turishini tanlash (1 kun, 1 hafta...)

    # 25-band: Ballarni ayirboshlash
    U_REDEEM_POINTS,      # 29: Ballarni VIP yoki Reklamaga almashtirish tanlovi

    # 22-band: Donat tizimi
    U_DONATE_AMOUNT,      # 30: Donat miqdorini kiritish

    # 15-band: Do'st orttirish (Chat/Profile)
    U_CREATE_PROFILE,     # 31: Muxlis profilini yaratish
    U_CHAT_MESSAGE,       # 32: Boshqa muxlisga xabar yozish

    A_MAIN                # 33: Main/Asosiy funksiya qaytishi
) = range(34)


# ====================== MA'LUMOTLAR BAZASI (TUZATILGAN VA OPTIMAL) ======================


async def init_db_pool():
    global db_pool # Kichik harf bilan
    loop = asyncio.get_running_loop()
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        db_pool = await aiomysql.create_pool(
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            db=DB_CONFIG['db'],
            autocommit=True,
            minsize=1, 
            maxsize=20,
            pool_recycle=300,
            charset='utf8mb4',
            cursorclass=aiomysql.DictCursor,
            ssl=ctx
        )
        
        # Jadvallarni yaratish (Asinxron rejimda)
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Foydalanuvchilar (VIP, Ballar, Sog'liq rejimi)
                await cur.execute("""CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY, 
                    username VARCHAR(255),
                    joined_at DATETIME, 
                    points INT DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'user',
                    vip_expire_date DATETIME DEFAULT NULL,
                    health_mode TINYINT(1) DEFAULT 1,
                    referral_count INT DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 2. Animelar (Reyting, Janr, Fandub, Ko'rilishlar)
                await cur.execute("""CREATE TABLE IF NOT EXISTS anime_list (
                    anime_id INT AUTO_INCREMENT PRIMARY KEY, 
                    name VARCHAR(255) NOT NULL, 
                    poster_id TEXT,
                    lang VARCHAR(100),
                    genre VARCHAR(255),
                    year VARCHAR(20),
                    fandub VARCHAR(255),
                    description TEXT,
                    rating_sum FLOAT DEFAULT 0,
                    rating_count INT DEFAULT 0,
                    views_week INT DEFAULT 0,
                    is_completed TINYINT(1) DEFAULT 0,
                    INDEX (name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 3. Anime qismlari
                await cur.execute("""CREATE TABLE IF NOT EXISTS anime_episodes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    anime_id INT,
                    episode INT,
                    file_id TEXT,
                    FOREIGN KEY (anime_id) REFERENCES anime_list(anime_id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                
                # 4. Sevimli animelar (Cascade qo'shildi)
                await cur.execute("""CREATE TABLE IF NOT EXISTS favorites (
                    user_id BIGINT,
                    anime_id INT,
                    PRIMARY KEY (user_id, anime_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (anime_id) REFERENCES anime_list(anime_id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 5. Korishlar tarixi (Index qo'shildi)
                await cur.execute("""CREATE TABLE IF NOT EXISTS history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT,
                    anime_id INT,
                    last_episode INT,
                    watched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX (user_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (anime_id) REFERENCES anime_list(anime_id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 6. izohlar jadvali

                await cur.execute("""CREATE TABLE IF NOT EXISTS comments (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT,
                    anime_id INT,
                    comment_text TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (anime_id) REFERENCES anime_list(anime_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                # 7. Reklamalar boshqaruvi (14, 26-bandlar)
                await cur.execute("""CREATE TABLE IF NOT EXISTS advertisements (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    content_type VARCHAR(20), -- 'photo', 'video', 'text
                    file_id TEXT,
                    caption TEXT,
                    start_date DATETIME,
                    end_date DATETIME,
                    is_active TINYINT(1) DEFAULT 1
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                #8 Shikoyatlar va Murojaatlar (20-band)
                await cur.execute("""CREATE TABLE IF NOT EXISTS feedback (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT,
                    subject VARCHAR(255),
                    message TEXT,
                    status VARCHAR(20) DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 9. Donatlar va Moliyaviy statistika
                await cur.execute("""CREATE TABLE IF NOT EXISTS donations (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT,
                    amount DECIMAL(10,2),
                    donated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 10. Kanallar
                await cur.execute("""CREATE TABLE IF NOT EXISTS channels (
                    username VARCHAR(255) PRIMARY KEY,
                    subscribers_added INT DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 11. Adminlar logs (Admin_id uchun users jadvaliga bog'liqlik)
                await cur.execute("""CREATE TABLE IF NOT EXISTS admin_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    admin_id BIGINT,
                    action TEXT,
                    action_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (admin_id) REFERENCES users(user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 28-BANDGA MOS QO'SHIMCHA: Sevimli janrlar (Shaxsiy tavsiyalar uchun)
                await cur.execute("""CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id BIGINT,
                    genre VARCHAR(100),
                    interest_level INT DEFAULT 1,
                    PRIMARY KEY (user_id, genre)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

        print("✅ Asinxron DB Pool yaratildi va jadvallar tayyor!")
    except Exception as e:
        logger.error(f"❌ DB Pool Error: {e}")

async def get_db():
    global db_pool
    if db_pool is None:
        await init_db_pool()
    return await db_pool.acquire()


async def execute_query(query, params=None, fetch="none"):
    # ... (pool tekshirish qismi)
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params or ())
                if fetch == "one":
                    return await cur.fetchone()
                elif fetch == "all":
                    return await cur.fetchall()
                elif fetch == "id": # Yangi qo'shilgan ID ni olish uchun
                    return cur.lastrowid
                return cur.rowcount 
    except Exception as e:
        logger.error(f"❌ SQL Xatolik: {e} | Query: {query}")
        return None
# ====================== YORDAMCHI FUNKSIYALAR (TUZATILDI) ======================


async def get_user_status(user_id: int):
    """
    Foydalanuvchi statusini asinxron aniqlash.
    28-band: VIP muddatini avtomatik tekshirish va statusni yangilash qo'shildi.
    """
    # 1. Asosiy egasini tekshirish
    if user_id == MAIN_ADMIN_ID: 
        return "main_admin"
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 2. Adminlar jadvalini tekshirish
                # Eslatma: init_db da 'admin_id' jadvali qolib ketgan bo'lsa, uni yaratishni unutmang
                await cur.execute("SELECT user_id FROM admin_id WHERE user_id=%s", (user_id,))
                if await cur.fetchone():
                    return "admin"
                
                # 3. Foydalanuvchi ma'lumotlarini olish
                await cur.execute("SELECT status, vip_expire_date FROM users WHERE user_id=%s", (user_id,))
                res = await cur.fetchone()
                
                if not res:
                    return "user"
                
                status = res['status']
                vip_date = res['vip_expire_date']
                
                # 4. 28-BAND: VIP muddati o'tganini tekshirish (Avtomatlashtirish)
                if status == 'vip' and vip_date:
                    if datetime.datetime.now() > vip_date:
                        # Muddat tugagan bo'lsa statusni tushiramiz
                        await cur.execute("UPDATE users SET status='user', vip_expire_date=NULL WHERE user_id=%s", (user_id,))
                        return "user"
                
                return status
                
    except Exception as e:
        logger.error(f"⚠️ Status aniqlashda (aiomysql) xato: {e}")
        return "user"



# ===================================================================================

async def check_sub(user_id: int, bot):
    not_joined = []
    
    # 1. Kanallarni bazadan olishni try-except ichiga olamiz
    channels = []
    try:
        # Timeout qo'shamizki, baza qotib qolsa bot o'lib qolmasin
        async with asyncio.timeout(5): 
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT username FROM channels")
                    channels = await cur.fetchall()
    except Exception as e:
        logger.error(f"⚠️ Kanal bazasida xato: {e}")
        return [] # Xato bo'lsa tekshirmasdan o'tkazib yuboramiz

    for row in channels:
        # DictCursor yoki oddiy Cursor ekanligiga qarab username ni olamiz
        ch = row['username'] if isinstance(row, dict) else row[0]
        
        try:
            target = str(ch).strip()
            if not target.startswith('@') and not target.startswith('-'):
                target = f"@{target}"
            
            # 2. Har bir kanalni tekshirishga 3 soniya vaqt beramiz
            async with asyncio.timeout(3):
                member = await bot.get_chat_member(target, user_id)
                if member.status in ['left', 'kicked']:
                    not_joined.append(ch)
                    
        except Exception as e:
            # 3. KANAL TOPILMASA YOKI BOT ADMIN BO'LMASA - TASHLAB KETAMIZ
            logger.warning(f"❗ Kanal tashlab ketildi: {ch}. Sabab: {e}")
            continue 
            
    return not_joined
    




# ====================== KLAVIATURALAR (TUZATILDI) ======================

def get_main_kb(status):
    """
    Asosiy menyu: Do'st orttirish va Muxlislar bo'limi qo'shildi.
    """
    kb = [
        [KeyboardButton("🔍 Anime qidirish 🎬"), KeyboardButton("🔥 Trenddagilar")],
        [KeyboardButton("👤 Shaxsiy Kabinet"), KeyboardButton("🎁 Ballar & VIP")],
        [KeyboardButton("🤝 Muxlislar Klubi"), KeyboardButton("📂 Barcha animelar")], # Yangi tugma
        [KeyboardButton("✍️ Murojaat & Shikoyat"), KeyboardButton("📖 Qo'llanma ❓")]
    ]
    
    if status in ["main_admin", "admin"]:
        kb.append([KeyboardButton("🛠 ADMIN PANEL")])
    
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def create_fan_profile(user_id: int, bio: str, fav_genre: str):
    """
    28-band (15-band): Muxlis profilini yaratish yoki yangilash.
    """
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            # Profil ma'lumotlarini 'users' jadvaliga yoki alohida jadvalga saqlash
            # Bu yerda oddiyroq bo'lishi uchun 'users' jadvaliga 'bio' ustuni qo'shilgan deb hisoblaymiz
            await cur.execute(
                "UPDATE users SET bio = %s, favorite_genre = %s WHERE user_id = %s",
                (bio, fav_genre, user_id)
            )

# ===================================================================================



def get_admin_kb(is_main=False):
    """Admin panel ichidagi inline tugmalar"""
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
    
    # Faqat MAIN_ADMIN (Asosiy admin) uchun qo'shimcha boshqaruv tugmasi
    if is_main:
        buttons.append([InlineKeyboardButton("👮 Adminlarni boshqarish", callback_data="manage_admins")])
        
    return InlineKeyboardMarkup(buttons)



# ===================================================================================

async def admin_panel_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Admin ekanligini tekshirish (admin_id ro'yxatingiz bo'lishi kerak)
    if user_id not in admin_id and user_id != MAIN_ADMIN_ID:
        # Admin bo'lmaganlarga javob bermaslik yoki xabar yuborish
        return 

    # Eski holatlarni tozalash
    if context.user_data:
        context.user_data.clear()

    is_main = (user_id == MAIN_ADMIN_ID)
    
    await update.message.reply_text(
        "🛠 **ADMIN BOSHQARUV PANELI**\n\n"
        "Kerakli bo'limni tanlang:",
        reply_markup=get_admin_kb(is_main=is_main),
        parse_mode="Markdown"
    )
    # MUHIM: Bu return A_MAIN bo'lsa, conv_handler ichida A_MAIN stateda 
    # adm_ bilan boshlanadigan patternlarni tutadigan CallbackQueryHandler bo'lishi shart!
    return A_MAIN

# ===================================================================================



def get_cancel_kb():
    """Jarayonlarni bekor qilish uchun 'Orqaga' tugmasi"""
    return ReplyKeyboardMarkup([[KeyboardButton("⬅️ Orqaga")]], resize_keyboard=True)
    
    
    

# ====================== ASOSIY ISHLOVCHILAR (TUZATILGAN VA TO'LIQ) ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    user_obj = update.effective_user
    username = (user_obj.username or user_obj.first_name or "User")[:50]
    
    # 1. Deep Link
    ref_id = None
    if context.args:
        arg = context.args[0]
        if arg.startswith("ani_"):
            context.user_data['pending_anime'] = arg.replace("ani_", "")
        elif arg.isdigit():
            ref_id = int(arg)

    # 2. Baza bilan ishlash
    try:
        # DB pool ulanishini olish
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Avval foydalanuvchini tekshiramiz
                await cur.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
                user_exists = await cur.fetchone()
                
                new_user_bonus = False
                if not user_exists:
                    # Yangi foydalanuvchini qo'shish
                    await cur.execute(
                        "INSERT INTO users (user_id, username, joined_at, points) VALUES (%s, %s, %s, %s)",
                        (user_id, username, datetime.datetime.now(), 10)
                    )
                    new_user_bonus = True
                    
                    # Referral mantiqi
                    if ref_id and ref_id != user_id:
                        await cur.execute("UPDATE users SET points = points + 20 WHERE user_id = %s", (ref_id,))
                        try:
                            await context.bot.send_message(
                                chat_id=ref_id, 
                                text=f"🎉 Tabriklaymiz! Do'stingiz (@{username}) qo'shildi va sizga 20 ball berildi."
                            )
                        except: pass
                
                # O'zgarishlarni saqlash
                await conn.commit()
    except Exception as e:
        logger.error(f"DATABASE ERROR (Start): {e}")
        # Xato bo'lsa ham foydalanuvchini to'xtatmaymiz!
        # Faqat foydalanuvchi obuna bo'lganligini qo'lda tekshirishga o'tamiz


    # 3. Obunani tekshirish
    try:
        not_joined = await check_sub(user_id, context.bot)
        if not_joined:
            btn = [[InlineKeyboardButton("Obuna bo'lish ➕", url=f"https://t.me/{c.replace('@','')}") ] for c in not_joined]
            btn.append([InlineKeyboardButton("Tekshirish ✅", callback_data="recheck")])
            
            msg = "👋 Botdan foydalanish uchun kanallarga a'zo bo'ling:"
            if 'pending_anime' in context.user_data:
                msg = "🎬 <b>Siz tanlagan animeni ko'rish uchun</b> avval a'zo bo'ling:"

            return await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(btn), parse_mode="HTML")
    except Exception as e:
        logger.error(f"SUB CHECK ERROR: {e}")

    # 4. Asosiy Menyu
    try:
        status = await get_user_status(user_id)
        welcome_msg = f"✨ Xush kelibsiz, {user_obj.first_name}!\n"
        welcome_msg += "💰 10 ball bonus berildi!" if new_user_bonus else "Xush kelibsiz! 😊"

        await update.message.reply_text(welcome_msg, reply_markup=get_main_kb(status))
    except Exception as e:
        logger.error(f"MENU ERROR: {e}")
    
    return ConversationHandler.END
    
    

    
# =============================================================================================

async def recheck_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Obunani tekshirish va har bir kanal uchun o'sish statistikasini hisoblash.
    """
    query = update.callback_query
    user_id = query.from_user.id
    
    # 1. Hozirgi holatni tekshiramiz
    not_joined = await check_sub(user_id, context.bot)
    
    if not not_joined:
        # Foydalanuvchi hamma kanalga a'zo bo'ldi.
        # 2. Xotiradan avval a'zo bo'lmagan kanallar ro'yxatini olamiz
        old_not_joined = context.user_data.get('last_not_joined', [])
        
        if old_not_joined:
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # 3. 28-BAND (8-band): Har bir yangi a'zo bo'lingan kanal uchun +1
                    for ch_username in old_not_joined:
                        await cur.execute(
                            "UPDATE channels SET subscribers_added = subscribers_added + 1 WHERE username = %s",
                            (ch_username,)
                        )
            # Hisoblagandan keyin xotirani tozalaymiz
            context.user_data.pop('last_not_joined', None)

        try:
            await query.message.delete()
        except:
            pass
        
        # 4. Kutilayotgan anime bo'lsa ko'rsatish
        if 'pending_anime' in context.user_data:
            ani_id = context.user_data.pop('pending_anime')
            return await show_specific_anime_by_id(query, context, ani_id)
        
        # 5. Aks holda asosiy menyu
        status = await get_user_status(user_id)
        await query.message.reply_text(
            "✅ Rahmat! Obuna tasdiqlandi. Marhamat, botdan foydalanishingiz mumkin.", 
            reply_markup=get_main_kb(status)
        )
    else:
        # Foydalanuvchi hali ham a'zo emas. 
        # Keyingi safar solishtirish uchun hozirgi a'zo bo'lmagan kanallarini saqlab qo'yamiz.
        context.user_data['last_not_joined'] = not_joined
        await query.answer("❌ Hali hamma kanallarga a'zo emassiz!", show_alert=True)
    
# =============================================================================================

async def show_specific_anime_by_id(update_or_query, context, ani_id):
    """
    ID bo'yicha bazadan animeni topib, tafsilotlarini chiqaradi.
    28-band: Haftalik ko'rishlar sonini avtomatik oshirish qo'shildi.
    """
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Animeni bazadan qidirish
                await cur.execute("SELECT * FROM anime_list WHERE anime_id=%s", (ani_id,))
                anime = await cur.fetchone()
                
                if anime:
                    # 2. 28-BAND (11-band): Ko'rishlar sonini 1 taga oshirish
                    await cur.execute(
                        "UPDATE anime_list SET views_week = views_week + 1 WHERE anime_id=%s", 
                        (ani_id,)
                    )
                    # O'zgarishlarni saqlash shart emas (autocommit=True bo'lgani uchun)
                    
                    # Tafsilotlarni chiqarish funksiyasiga yuboramiz
                    return await show_anime_details(update_or_query, anime, context)
                
                else:
                    # Anime topilmasa xabar berish
                    error_text = "❌ Kechirasiz, bu anime bazadan o'chirilgan yoki topilmadi."
                    if hasattr(update_or_query, 'message') and update_or_query.message:
                        await update_or_query.message.reply_text(error_text)
                    else:
                        await update_or_query.edit_message_text(error_text)
                        
    except Exception as e:
        logger.error(f"⚠️ show_specific_anime_by_id xatosi: {e}")
        # Foydalanuvchiga texnik xato haqida bildirish
        msg = "⚠️ Ma'lumotlarni yuklashda xatolik yuz berdi."
        if hasattr(update_or_query, 'message') and update_or_query.message:
            await update_or_query.message.reply_text(msg)
        else:
            await update_or_query.edit_message_text(msg)

# ====================== ADMIN VA QO'SHIMCHA ISHLOVCHILAR (TO'G'RILANDI) ======================

async def admin_channels_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Bazadan kanallarni olamiz
    channels = await get_all_channels()
    
    text = "📢 <b>Majburiy obuna kanallari:</b>\n\n"
    if not channels:
        text += "<i>Hozircha kanallar qo'shilmagan.</i>"
    else:
        for ch in channels:
            text += f"🔹 {ch['username']} (Qo'shildi: {ch['subscribers_added']})\n"
            
    keyboard = [
        [InlineKeyboardButton("➕ Kanal qo'shish", callback_data="add_ch_start")],
        [InlineKeyboardButton("❌ Kanalni o'chirish", callback_data="rem_ch_start")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_main")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return A_MAIN

# =============================================================================================

async def exec_add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Kanal qo'shish ijrosi.
    28-band: Admin harakatlarini loglash (21-band) qo'shildi.
    """
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Username formatini to'g'rilash
    username = text if text.startswith('@') or text.startswith('-') else f"@{text}"
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Kanalni bazaga qo'shish
                await cur.execute("INSERT INTO channels (username) VALUES (%s)", (username,))
                
                # 2. 28-BAND (21-band): Admin harakatini tarixga yozish
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (user_id, f"Yangi kanal qo'shdi: {username}")
                )
                
                # O'zgarishlar autocommit=True bo'lsa avtomatik saqlanadi
                
        await update.message.reply_text(
            f"✅ Kanal muvaffaqiyatli qo'shildi: <b>{username}</b>\n\n"
            f"<i>Endi foydalanuvchilar ushbu kanalga obuna bo'lishlari majburiy.</i>",
            parse_mode="HTML"
        )
        
    except Exception as e:
        # Agar kanal bazada allaqachon bo'lsa 'Duplicate entry' xatosi chiqadi
        logger.error(f"Kanal qo'shishda xato: {e}")
        await update.message.reply_text(
            f"❌ Xatolik yuz berdi. Ehtimol, ushbu kanal allaqachon qo'shilgan yoki baza bilan aloqa uzilgan."
        )

    return ConversationHandler.END


# ===================================================================================


async def exec_rem_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Kanalni bazadan o'chirish ijrosi.
    21-band: Admin harakatini loglash qo'shildi.
    """
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Username formatini tekshirish
    username = text if text.startswith('@') or text.startswith('-') else f"@{text}"
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Avval kanal borligini tekshiramiz (Log uchun kerak bo'lishi mumkin)
                await cur.execute("SELECT username FROM channels WHERE username=%s", (username,))
                channel = await cur.fetchone()
                
                if not channel:
                    await update.message.reply_text(f"❌ Bunday kanal topilmadi: {username}")
                    return ConversationHandler.END

                # 2. Kanalni o'chirish
                await cur.execute("DELETE FROM channels WHERE username=%s", (username,))
                
                # 3. 28-BAND (21-band): Admin harakatini logga yozish
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (user_id, f"Kanalni o'chirdi: {username}")
                )
                
        await update.message.reply_text(
            f"🗑 <b>Kanal muvaffaqiyatli o'chirildi:</b> {username}\n\n"
            f"Endi ushbu kanal majburiy obuna ro'yxatida ko'rinmaydi.",
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"⚠️ Kanal o'chirishda xatolik: {e}")
        await update.message.reply_text(f"❌ Xatolik yuz berdi: {e}")

    return ConversationHandler.END

# ===================================================================================

async def admin_ch_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "add_ch_start":
        await query.message.reply_text("📝 Yangi kanal username'ini yuboring (masalan: @kanal_nomi):")
        return A_ADD_CH # Bu holatda exec_add_channel ishlaydi
        
    elif query.data == "rem_ch_start":
        await query.message.reply_text("🗑 O'chiriladigan kanal username'ini yuboring:")
        return A_REM_CH # Bu holatda exec_rem_channel ishlaydi

# ===================================================================================


async def get_all_channels():
    """
    Bazadan barcha kanallarni va ularning statistikasini olish.
    8-band: Obunachilar soni (subscribers_added) ham qo'shib olib kelinadi.
    """
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 28-band talabi uchun statistikani ham birga olamiz
                await cur.execute("SELECT username as id, username, subscribers_added FROM channels")
                channels = await cur.fetchall()
                
                # Agar kanallar topilmasa, bo'sh ro'yxat qaytaramiz
                return channels if channels else []
                
    except Exception as e:
        logger.error(f"⚠️ Kanallarni olishda xatolik (get_all_channels): {e}")
        return []


# ===================================================================================


async def delete_channel_by_id(ch_username, admin_id=None):
    """
    Kanalni username orqali bazadan o'chirish.
    21-band: Kim o'chirganini logga yozish imkoniyati qo'shildi.
    """
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Kanalni o'chirish
                await cur.execute("DELETE FROM channels WHERE username=%s", (ch_username,))
                
                # 2. 28-BAND (21-band): Admin harakatini logga yozish
                if admin_id:
                    await cur.execute(
                        "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                        (admin_id, f"Inline tugma orqali kanalni o'chirdi: {ch_username}")
                    )
                
                # Autocommit True bo'lgani uchun commit shart emas
                return True
    except Exception as e:
        logger.error(f"⚠️ delete_channel_by_id xatosi: {e}")
        return False
# ===================================================================================


async def exec_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin qo'shishdan oldin tasdiqlash so'rash.
    Xavfsizlik tekshiruvlari va 21-band uchun tayyorgarlik.
    """
    text = update.message.text.strip()
    
    # 1. ID raqam ekanligini tekshirish
    if not text.isdigit():
        await update.message.reply_text(
            "❌ <b>Xato!</b> Foydalanuvchi ID raqamini yuboring (masalan: 12345678).\n\n"
            "Qayta urinib ko'ring yoki bekor qiling:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Orqaga", callback_data="manage_admins")]
            ]),
            parse_mode="HTML"
        )
        return A_ADD_ADM # Conversation holatida qolamiz

    # 2. Main Admin o'zini o'zi admin qilib qo'shishiga yo'l qo'ymaslik
    if int(text) == MAIN_ADMIN_ID:
        await update.message.reply_text("❗ Siz allaqachon Asosiy Adminsiz.")
        return ConversationHandler.END

    # Tasdiqlash tugmasini yaratish
    # Callback_data ichida ID ni uzatamiz (conf_adm_12345)
    keyboard = [
        [InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"conf_adm_{text}")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="manage_admins")]
    ]
    
    await update.message.reply_text(
        f"👮 <b>Yangi admin qo'shishni tasdiqlaysizmi?</b>\n\n"
        f"👤 Foydalanuvchi ID: <code>{text}</code>\n\n"
        f"<i>Eslatma: Tasdiqlash tugmasini bossangiz, bu foydalanuvchi botni boshqarish huquqiga ega bo'ladi.</i>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    
    return None # Callback handler kutish rejimida qoladi


# ===================================================================================


async def admin_control(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin panel callback boshqaruvi.
    Har qanday jarayonni (Conversation) to'xtatib, asosiy panelga qaytaradi.
    """
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id
    await query.answer()

    # Barcha jarayonlarni yakunlab, asosiy panelga qaytish
    if data == "admin_main":
        # status funksiyamiz allaqachon aiomysql'da ishlaydi (await shart)
        status = await get_user_status(user_id)
        
        # Faqat adminlarga ruxsat berish
        if status not in ["main_admin", "admin"]:
            return await query.edit_message_text("❌ Sizda adminlik huquqi yo'q.")

        is_main = (status == "main_admin")
        
        # 28-BAND (21-band): Admin harakatini loglash
        # (Ixtiyoriy: Panelga qaytishni ham loglash mumkin)
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (user_id, "Admin panel bosh menyusiga qaytdi")
                )

        await query.edit_message_text(
            "🛠 <b>Admin paneliga xush kelibsiz:</b>\n\n"
            "Pastdagi tugmalar orqali botni boshqarishingiz mumkin.",
            reply_markup=get_admin_kb(is_main),
            parse_mode="HTML"
        )
        
        # ConversationHandler'dan chiqishni ta'minlaydi
        return ConversationHandler.END
# ===================================================================================


async def show_vip_removal_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    """
    VIP foydalanuvchilarni o'chirish ro'yxatini asinxron chiqarish.
    aiomysql Pool va Pagination bilan.
    """
    query = update.callback_query
    limit = 10
    offset = page * limit

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. VIP foydalanuvchilar sonini aniqlash
                await cur.execute("SELECT COUNT(*) as total FROM users WHERE status = 'vip'")
                result = await cur.fetchone()
                total_vips = result['total']
                
                # 2. Joriy sahifa uchun ma'lumotlarni olish
                await cur.execute(
                    "SELECT user_id, username FROM users WHERE status = 'vip' LIMIT %s OFFSET %s", 
                    (limit, offset)
                )
                vips = await cur.fetchall()

        if not vips and page == 0:
            await query.edit_message_text(
                "📭 <b>VIP foydalanuvchilar ro'yxati bo'sh!</b>",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="manage_vip")]]),
                parse_mode="HTML"
            )
            return

        keyboard = []
        # 3. Har bir VIP foydalanuvchi uchun tugma yaratish
        for v in vips:
            user_id = v['user_id']
            username = v['username'] or "Noma'lum"
            # Ko'rinishi chiroyli bo'lishi uchun ID va Username birga chiqadi
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ {username} ({user_id})", 
                    callback_data=f"exec_rem_vip_{user_id}_{page}"
                )
            ])

        # 4. Pagination tugmalari
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"rem_vip_page_{page-1}"))
        if (page + 1) * limit < total_vips:
            nav_buttons.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"rem_vip_page_{page+1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)

        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="manage_vip")])

        text = (
            f"🗑 <b>VIP O'CHIRISH BO'LIMI</b> (Jami: {total_vips})\n\n"
            f"<i>Sahifa: {page + 1}</i>\n"
            f"O'chirmoqchi bo'lgan foydalanuvchini tanlang: 👇"
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

    except Exception as e:
        logger.error(f"⚠️ show_vip_removal_list xatosi: {e}")
        await query.answer("❌ Ro'yxatni yuklashda xatolik yuz berdi.", show_alert=True)

    

# ----------------- CALLBACK HANDLER (MUHIM QISM) -----------------


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    # get_user_status allaqachon aiomysql pool bilan ishlaydi (await shart)
    status = await get_user_status(user_id)
    await query.answer()

    # ================= 1. HAMMA UCHUN OCHIQ CALLBACKLAR =================
    
    # Obunani qayta tekshirish
    if data == "recheck":
        # check_sub funksiyasi ham asinxron (await shart)
        not_joined = await check_sub(user_id, context.bot)
        
        if not not_joined: # Agar ro'yxat bo'sh bo'lsa (hamma kanalga a'zo)
            try:
                await query.message.delete()
            except:
                pass # Xabar allaqachon o'chirilgan bo'lishi mumkin
            
            # 28-BAND: Obuna tasdiqlangach asosiy menyu chiqadi
            await context.bot.send_message(
                chat_id=user_id, 
                text="<b>Tabriklaymiz! ✅ Obuna tasdiqlandi.</b>\nEndi botdan to'liq foydalanishingiz mumkin.", 
                reply_markup=get_main_kb(status),
                parse_mode="HTML"
            )
        else:
            # Hali a'zo bo'lmagan bo'lsa ogohlantirish
            await query.answer("❌ Hali hamma kanallarga a'zo emassiz!", show_alert=True)
        return None

    # ... bu yerda boshqa callbacklar davom etadi ...
        
# ===================================================================================
    
    # 1. Qidiruv turlari tanlanganda
    if data == "search_type_id":
        await query.edit_message_text(
            text="🔢 <b>Anime ID raqamini kiriting:</b>", 
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_search_menu")
            ]]), 
            parse_mode="HTML"
        )
        return A_SEARCH_BY_ID
        
    elif data == "search_type_name":
        await query.edit_message_text(
            text="📝 <b>Anime nomini kiriting:</b>", 
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_search_menu")
            ]]), 
            parse_mode="HTML"
        )
        return A_SEARCH_BY_NAME

    # 2. Qidiruv menyusiga qaytish
    elif data == "back_to_search_menu":
        search_btns = [
            [InlineKeyboardButton("🆔 ID orqali qidirish", callback_data="search_type_id")],
            [InlineKeyboardButton("🔎 Nomi orqali qidirish", callback_data="search_type_name")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_search")]
        ]
        await query.edit_message_text(
            text="🎬 <b>Anime qidirish bo'limi</b>\n\nQidiruv usulini tanlang: 👇", 
            reply_markup=InlineKeyboardMarkup(search_btns),
            parse_mode="HTML"
        )
        return None 

    # 3. Haqiqiy bekor qilish (Qidiruvdan chiqish)
    elif data == "cancel_search":
        # Statusni yuqorida await get_user_status orqali olganimiz uchun bu yerda tayyor
        await query.message.delete() # Eski xabarni o'chirib yuborish chiroyliroq chiqadi
        
        await context.bot.send_message(
            chat_id=user_id,
            text="🏠 <b>Qidiruv bekor qilindi.</b>\nAsosiy menyu:",
            reply_markup=get_main_kb(status),
            parse_mode="HTML"
        )
        return ConversationHandler.END
    
    # ===================================================================================

    # Sahifalash (Pagination) navigatsiyasini tutish
    # 1. Navigatsiyani tutish (Eng tepada)
    # Pagination (Sahifalash) boshqaruvi
    if data.startswith("pg_"):
        parts = data.split('_') # pg_viewani_1 -> ['pg', 'viewani', '1']
        prefix = parts[1]
        
        try:
            new_page = int(parts[-1])
        except (ValueError, IndexError):
            new_page = 0
        
        # 1. Animelar ro'yxatini ko'rish
        if prefix == "viewani":
            query.data = f"list_ani_pg_{new_page}"
            return await list_animes_view(update, context)
        
        # 2. Animeni o'chirish ro'yxati (Admin Panel)
        elif prefix == "delani":
            # get_pagination_keyboard endi asinxron bo'lishi shart!
            kb = await get_pagination_keyboard(
                table="anime_list", 
                page=new_page, 
                prefix="delani", 
                extra_callback="rem_ani_menu"
            )
            
            await query.edit_message_text(
                "🗑 <b>O'chirish uchun anime tanlang:</b>\n"
                f"<i>Sahifa: {new_page + 1}</i>", 
                reply_markup=kb, 
                parse_mode="HTML"
            )
            return A_REM_ANI_LIST
        
        # 3. Yangi qism (Episode) qo'shish uchun anime tanlash
        elif prefix == "addepto":
            query.data = f"pg_{new_page}"
            return await select_ani_for_new_ep(update, context)
        
        # 4. Qismni o'chirish uchun anime tanlash
        elif prefix == "remep":
            query.data = f"pg_{new_page}"
            return await select_ani_for_rem_ep(update, context)
            
        await query.answer()
        return None

     # --- ANIME CONTROL ASOSIY ---
    elif data in ["adm_ani_ctrl", "back_to_ctrl", "admin_main"]:
        return await anime_control_panel(update, context)

    # --- ADD ANIME BO'LIMI ---
    elif data == "add_ani_menu":
        return await add_anime_panel(update, context)

    elif data == "start_new_ani":
        return await start_new_ani(update, context)

    elif data.startswith("new_ep_ani"):
        return await select_ani_for_new_ep(update, context)

    # --- ANIMEGA QISM QO'SHISH (START) ---
    elif data.startswith("addepto_"):
        ani_id = data.split('_')[-1]
        context.user_data['cur_ani_id'] = ani_id
        
        try:
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # 'id' o'rniga 'anime_id' ishlatish to'g'ri (sizning bazangiz strukturasi)
                    await cur.execute("SELECT name FROM anime_list WHERE anime_id = %s", (ani_id,))
                    res = await cur.fetchone()
                    
                    if res:
                        # DictCursor bo'lgani uchun res['name'] deb olamiz
                        context.user_data['cur_ani_name'] = res['name']
                        
                        # 21-band: Admin harakatini loglash
                        await cur.execute(
                            "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                            (user_id, f"Animega qism qo'shishni boshladi: {res['name']} (ID: {ani_id})")
                        )
                    else:
                        context.user_data['cur_ani_name'] = "Noma'lum Anime"

            await query.edit_message_text(
                f"📥 <b>{context.user_data['cur_ani_name']}</b> uchun video/fayl yuboring:\n\n"
                f"<i>Eslatma: Bot avtomatik ravishda qism raqamini aniqlaydi va bazaga ulaydi.</i>", 
                parse_mode="HTML"
            )
            # Video qabul qilish holatiga o'tish
            return A_ADD_EP_FILES

        except Exception as e:
            logger.error(f"⚠️ addepto callback xatosi: {e}")
            await query.answer("❌ Ma'lumotni yuklashda xatolik yuz berdi.", show_alert=True)
            return ConversationHandler.END

    # --- LIST ANIME BO'LIMI ---
    elif data.startswith("list_ani_pg_"):
        # Sahifalangan ro'yxatni ko'rish
        return await list_animes_view(update, context)

    elif data.startswith("viewani_"):
        # Tanlangan anime haqida batafsil ma'lumot (28-band: Ko'rishlar soni shu ichida)
        return await show_anime_info(update, context)

    # --- REMOVE ANIME BO'LIMI ---
    elif data == "rem_ani_menu":
        # O'chirish bosh menyusi
        return await remove_menu_handler(update, context)

    elif data == "rem_ep_menu" or data.startswith("rem_ep_list_"):
        # Qismlarni (episode) o'chirish uchun anime tanlash
        return await select_ani_for_rem_ep(update, context)

    elif data.startswith("rem_ani_list_"):
        # Animeni butunlay o'chirish uchun ro'yxat
        try:
            page = int(data.split('_')[-1])
        except:
            page = 0
            
        # get_pagination_keyboard asinxron qilib o'zgartirilgan
        kb = await get_pagination_keyboard(
            table="anime_list", 
            page=page, 
            prefix="delani", # Prefixni funksiya ichida formatlash qulayroq
            extra_callback="rem_ani_menu"
        )
        
        await query.edit_message_text(
            "🗑 <b>O'chirish uchun anime tanlang:</b>\n\n"
            "<i>Eslatma: Anime o'chirilsa, unga tegishli barcha qismlar ham o'chib ketadi!</i>", 
            reply_markup=kb, 
            parse_mode="HTML"
        )
        return A_REM_ANI_LIST

    elif data.startswith("remep_"): 
        # Tanlangan animening qismlarini o'chirish uchun ro'yxat chiqarish
        return await list_episodes_for_delete(update, context)

    elif data.startswith("delani_"):
        ani_id = data.split('_')[-1]
        kb = [
            [InlineKeyboardButton("✅ TASDIQLASH", callback_data=f"exec_del_{ani_id}")],
            [InlineKeyboardButton("❌ BEKOR QILISH", callback_data="rem_ani_menu")]
        ]
        await query.edit_message_text(
            f"⚠️ <b>DIQQAT!</b>\n\nID: <code>{ani_id}</code> bo'lgan animeni o'chirmoqchimisiz?\n"
            f"<i>Bu animeni o'chirsangiz, unga tegishli barcha qismlar ham o'chib ketadi!</i>", 
            reply_markup=InlineKeyboardMarkup(kb), 
            parse_mode="HTML"
        )
        return A_REM_ANI_LIST

    elif data.startswith("exec_del_"):
        # Bu funksiya ichida ham aiomysql ishlatilgan bo'lishi kerak
        return await delete_anime_exec(update, context)

    elif data.startswith("ex_del_ep_"):
        ep_id = data.split('_')[-1]
        
        try:
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # 21-band: O'chirishdan oldin log uchun ma'lumot olish
                    await cur.execute(
                        "SELECT a.name, e.episode FROM anime_episodes e "
                        "JOIN anime_list a ON e.anime_id = a.anime_id WHERE e.id = %s", 
                        (ep_id,)
                    )
                    info = await cur.fetchone()
                    
                    # Qismni o'chirish
                    await cur.execute("DELETE FROM anime_episodes WHERE id = %s", (ep_id,))
                    
                    # Admin harakatini logga yozish
                    log_text = f"Qismni o'chirdi: {info['name']} - {info['episode']}-qism" if info else f"Qismni o'chirdi (ID: {ep_id})"
                    await cur.execute(
                        "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                        (user_id, log_text)
                    )
            
            await query.answer("✅ Qism o'chirildi!", show_alert=True)
        except Exception as e:
            logger.error(f"Qism o'chirishda xato: {e}")
            await query.answer("❌ O'chirishda xatolik yuz berdi.", show_alert=True)
            
        return await anime_control_panel(update, context)

    elif data == "finish_add":
        await query.message.reply_text("✅ Jarayon yakunlandi.")
        return await anime_control_panel(update, context)

    elif data.startswith("get_ep_"):
        # Tugmadan ep_id ni olamiz
        ep_id = data.replace("get_ep_", "")
    
        try:
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # JOIN orqali anime nomini va boshqa ma'lumotlarni olamiz
                    await cur.execute("""
                        SELECT e.file_id, e.episode, a.name 
                        FROM anime_episodes e 
                        JOIN anime_list a ON e.anime_id = a.anime_id 
                        WHERE e.id = %s
                    """, (ep_id,))
                    res = await cur.fetchone()
            
            if res:
                # DictCursor ishlatilgani uchun kalit so'zlar bilan olamiz
                file_id = res['file_id']
                ep_num = res['episode']
                ani_name = res['name']
            
                # 1. Tugmani bosganda "yuklanmoqda" degan yozuvni yo'qotish
                await query.answer(f"⌛ {ani_name}: {ep_num}-qism yuborilmoqda...")
            
                # 2. Videoni yuborish (14-band: Avtomatik caption yaratish)
                await query.message.reply_video(
                    video=file_id,
                    caption=(
                        f"🎬 <b>{ani_name}</b>\n"
                        f"💿 <b>{ep_num}-qism</b>\n\n"
                        f"✨ @Aninovuz — Eng sara animelar manbasi!"
                    ),
                    parse_mode="HTML"
                )
            else:
                await query.answer("❌ Kechirasiz, video fayl bazadan topilmadi.", show_alert=True)

        except Exception as e:
            logger.error(f"⚠️ get_ep_ xatosi: {e}")
            await query.answer("⚠️ Videoni yuklashda texnik xatolik yuz berdi.", show_alert=True)
      
      
# ===================================================================================
     
        
   # 1. VIP o'chirish ro'yxatini chiqarish
    elif data == "rem_vip_list":
        # show_vip_removal_list funksiyasi asinxron bo'lishi kerak
        await show_vip_removal_list(update, context, page=0)

    # 2. VIP ro'yxatida sahifadan sahifaga o'tish
    elif data.startswith("rem_vip_page_"):
        try:
            page = int(data.split("_")[-1]) # Oxirgi qismni olish xavfsizroq
        except (ValueError, IndexError):
            page = 0
        await show_vip_removal_list(update, context, page=page)

    # 3. VIP maqomini olib tashlash ijrosi
    elif data.startswith("exec_rem_vip_"):
        parts = data.split("_")
        # exec_rem_vip_{target_id}_{page} -> ['exec', 'rem', 'vip', '12345', '0']
        target_id = parts[3]
        
        try:
            current_page = int(parts[4])
        except:
            current_page = 0
        
        try:
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # Statusni yangilash
                    await cur.execute(
                        "UPDATE users SET status = 'user' WHERE user_id = %s", 
                        (target_id,)
                    )
                    
                    # 28-BAND (21-band): Admin harakatini logga yozish
                    await cur.execute(
                        "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                        (user_id, f"Foydalanuvchidan VIP maqomini oldi: {target_id}")
                    )
            
            await query.answer(f"✅ ID: {target_id} VIP ro'yxatidan o'chirildi!", show_alert=True)
            # Ro'yxatni yangilangan holda qayta ko'rsatish
            await show_vip_removal_list(update, context, page=current_page)
            
        except Exception as e:
            logger.error(f"⚠️ VIP o'chirishda xato: {e}")
            await query.answer("❌ Xatolik yuz berdi.", show_alert=True)

    # ================= VIP TASDIQLASH (ELIF VARIANTI) =================
    elif data.startswith("conf_vip_"):
        # callback_data dan ID raqamini ajratib olamiz
        target_id = data.split("_")[2]
        
        try:
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # 1. Foydalanuvchi statusini 'vip' ga o'zgartiramiz
                    await cur.execute("UPDATE users SET status = 'vip' WHERE user_id = %s", (target_id,))
                    
                    # 2. 28-BAND (21-band): Admin harakatini logga yozish
                    await cur.execute(
                        "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                        (user_id, f"Foydalanuvchiga VIP maqomi berdi: {target_id}")
                    )
            
            # Admin xabarini yangilaymiz
            await query.edit_message_text(
                f"✅ <b>Muvaffaqiyatli!</b>\n\nFoydalanuvchi (ID: <code>{target_id}</code>) endi VIP statusiga ega.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ VIP Menu", callback_data="manage_vip")]
                ]),
                parse_mode="HTML"
            )
            
            # 3. Foydalanuvchiga xabar yuborish
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text="✨ <b>Tabriklaymiz!</b> Sizga VIP statusi berildi.\nEndi botdan reklamalarsiz va cheklovsiz foydalanishingiz mumkin.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Foydalanuvchiga VIP xabari yuborilmadi ({target_id}): {e}")
                
        except Exception as e:
            logger.error(f"⚠️ VIP tasdiqlashda xato: {e}")
            await query.answer("❌ Ma'lumotni saqlashda texnik xatolik.", show_alert=True)
            
        return None


    # ================= 2. FAQAT ADMINLAR UCHUN CALLBACKLAR =================
    
    # Adminlik huquqini tekshirish (yuqorida status olingan deb hisoblaymiz)
    if status not in ["main_admin", "admin"]:
        return None

    # 1. Admin asosiy menyusiga qaytish
    if data in ["admin_main", "adm_back"]:
        is_main = (status == "main_admin")
        await query.edit_message_text(
            "🛠 <b>Admin paneli:</b>", 
            reply_markup=get_admin_kb(is_main),
            parse_mode="HTML"
        )
        return ConversationHandler.END

    # 2. KANALLAR BOSHQARUVI MENYUSI
    elif data == "adm_ch":
        keyboard = [
            [InlineKeyboardButton("➕ Qo'shish", callback_data="add_channel_start"),
             InlineKeyboardButton("❌ O'chirish", callback_data="rem_channel_start")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_main")]
        ]
        await query.edit_message_text(
            "📢 <b>Majburiy obuna kanallarini boshqarish:</b>", 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return None

    # 3. Kanal qo'shishni boshlash
    elif data == "add_channel_start":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="adm_ch")]])
        await query.edit_message_text(
            text="🔗 <b>Qo'shmoqchi bo'lgan kanalingiz usernamesini yuboring:</b>\n\n"
                 "<i>Masalan: @kanal_nomi yoki -100...</i>",
            reply_markup=kb,
            parse_mode="HTML"
        )
        return A_ADD_CH

    # 4. Kanallar ro'yxatini chiqarish (O'chirish uchun)
    elif data == "rem_channel_start":
        # get_all_channels asinxron ekanligiga ishonch hosil qiling
        channels = await get_all_channels() 
        
        if not channels:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="adm_ch")]])
            await query.edit_message_text("📢 <b>Hozircha majburiy obuna kanallari yo'q.</b>", reply_markup=kb, parse_mode="HTML")
            return None

        keyboard = []
        for ch in channels:
            # 8-band: Agar bazada obunachilar soni bo'lsa, yonida ko'rsatish
            ch_name = ch['username'] if isinstance(ch, dict) else ch[1]
            ch_id = ch['id'] if isinstance(ch, dict) else ch[0]
            sub_count = ch.get('subscribers_added', 0) if isinstance(ch, dict) else 0
            
            keyboard.append([InlineKeyboardButton(f"🗑 {ch_name} (+{sub_count})", callback_data=f"del_ch_{ch_id}")])
        
        keyboard.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="adm_ch")])
        
        await query.edit_message_text(
            "🗑 <b>O'chirmoqchi bo'lgan kanalni tanlang:</b>\n\n"
            "<i>Yonidagi raqam bot orqali qo'shilgan obunachilar soni.</i>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return None 
    
    # 5. Kanalni o'chirish ijrosi
    elif data.startswith("del_ch_"):
        ch_id = data.replace("del_ch_", "")
        
        # 21-band: Admin harakatini loglash uchun id o'rniga nomni olish (ixtiyoriy)
        # delete_channel_by_id ichida admin_id uzatishni tavsiya qilaman
        await delete_channel_by_id(ch_id, admin_id=user_id) 
        
        await query.answer("✅ Kanal majburiy obunadan olib tashlandi!", show_alert=True)
        
        # Ro'yxatni yangilash uchun qayta ko'rsatamiz
        # Sun'iy ravishda callback ma'lumotini o'zgartirib qayta chaqiramiz
        query.data = "rem_channel_start"
        return await handle_callback(update, context) # yoki qaytadan kanallar ro'yxatini chiqarish
    

# ===================================================================================

    elif data == "adm_ani_add":
        # 21-band: Admin harakatini logga yozish
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (user_id, "Yangi anime qo'shish jarayonini boshladi")
                )

        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_main")]]) 
        await query.edit_message_text(
            "1️⃣ <b>Anime uchun POSTER (rasm) yuboring:</b>\n\n"
            "<i>Eslatma: Rasm sifatli va vertikal bo'lishi tavsiya etiladi.</i>", 
            reply_markup=kb,
            parse_mode="HTML"
        )
        return A_ADD_ANI_POSTER

    # 1. REKLAMA YUBORISHNI BOSHLASH (PAROL SO'RASH)
    elif data == "adm_ads_start":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_main")]])
        
        await query.edit_message_text(
            text="🔑 <b>Reklama parolini kiriting:</b>\n\n"
                 "<i>Xavfsizlik maqsadida ushbu bo'lim parol bilan himoyalangan.</i>", 
            reply_markup=kb,
            parse_mode="HTML"
        )
        return A_SEND_ADS_PASS

    # 2. PAROLGA QAYTISH
    elif data == "back_to_pass":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_main")]])
        await query.edit_message_text(
            text="🔑 <b>Reklama parolini qaytadan kiriting:</b>",
            reply_markup=kb,
            parse_mode="HTML"
        )
        return A_SEND_ADS_PASS

    # 3. ADMIN PANELGA QAYTISH
    elif data == "admin_main":
        # Status yuqorida await get_user_status(user_id) orqali olingan
        is_main = (status == "main_admin")
        
        await query.edit_message_text(
            text="👨‍💻 <b>Admin paneliga xush kelibsiz:</b>",
            reply_markup=get_admin_kb(is_main),
            parse_mode="HTML"
        )
        return ConversationHandler.END # Holatni butunlay yopamiz

    # 4. REKLAMA GURUHI TANLANGANDA
    elif data.startswith("send_to_"):
        target_group = data.split("_")[2]
        context.user_data['ads_target'] = target_group
        
        group_names = {
            "user": "👥 Oddiy foydalanuvchilar",
            "vip": "💎 VIP a'zolar",
            "admin": "👮 Adminlar",
            "all": "🌍 Barcha foydalanuvchilar"
        }
        
        # 21-band: Admin harakatini loglash
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (user_id, f"Reklama yuborishni boshladi (Guruh: {target_group})")
                )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Guruhni o'zgartirish", callback_data="back_to_select_group")]
        ])
        
        group_name = group_names.get(target_group, "Noma'lum")

        await query.edit_message_text(
            text=(
                 f"🎯 Tanlangan guruh: <b>{group_name}</b>\n\n"
                "Endi ushbu guruhga yubormoqchi bo'lgan <b>reklama xabaringizni</b> "
                "yuboring (Matn, Rasm, Video yoki Forward):\n\n"
                "<i>Eslatma: Xabar yuborishni boshlashdan oldin uni yaxshilab tekshiring!</i>"
            ),
            reply_markup=kb,
            parse_mode="HTML"
        )
        return A_SEND_ADS_MSG

    # 5. BEKOR QILISH
    elif data == "cancel_ads":
        await query.edit_message_text("❌ Reklama yuborish bekor qilindi.")
        return ConversationHandler.END

    # 1. BAZANI EKSPORT QILISH (21-band: Audit log bilan)
    elif data == "adm_export":
        # Admin harakatini logga yozamiz (Eksport - xavfli amal)
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (user_id, "Bazani JSON formatda eksport qildi (Backup)")
                )
        
        # export_all_anime funksiyasi asinxron ekanligiga ishonch hosil qiling
        await export_all_anime(update, context)
        return None

    # 2. REKLAMA GURUHLARIGA QAYTISH
    elif data == "back_to_select_group":
        keyboard = [
            [InlineKeyboardButton("👥 Oddiy foydalanuvchilar (User)", callback_data="send_to_user")],
            [InlineKeyboardButton("💎 Faqat VIP a'zolar", callback_data="send_to_vip")],
            [InlineKeyboardButton("👮 Faqat Adminlar", callback_data="send_to_admin")],
            [InlineKeyboardButton("🌍 Barchaga (Hammaga)", callback_data="send_to_all")],
            [InlineKeyboardButton("⬅️ Parolga qaytish", callback_data="back_to_pass")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_ads")]
        ]
        
        await query.edit_message_text(
            text="🔄 <b>Guruhni qayta tanlang:</b>\n\n<i>Reklama yuboriladigan maqsadli auditoriyani belgilang.</i>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        # Holatni guruh tanlash bosqichiga qaytaramiz
        return A_SELECT_ADS_TARGET


    # 1. ADMINLARNI BOSHQARISH ASOSIY MENYUSI
    elif data == "manage_admins":
        if status == "main_admin":
            keyboard = [
                [InlineKeyboardButton("➕ Admin qo'shish", callback_data="add_admin_start")],
                [InlineKeyboardButton("🗑 Admin o'chirish", callback_data="rem_admin_list")],
                [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_main")]
            ]
            await query.edit_message_text(
                "👮 <b>Adminlarni boshqarish uchun quyidagilarni tanlang:</b> 👇",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
            return None
        else:
            await query.answer("❌ Bu funksiya faqat asosiy admin uchun!", show_alert=True)

    # 2. ADMIN QO'SHISHNI BOSHLASH (ID SO'RASH)
    elif data == "add_admin_start":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="manage_admins")]])
        await query.edit_message_text(
            "👮 <b>Yangi admin ID-sini yuboring:</b>\n\n"
            "<i>Eslatma: ID raqamini @userinfobot orqali olish mumkin.</i>", 
            reply_markup=kb,
            parse_mode="HTML"
        )
        return A_ADD_ADM

    # 3. ADMIN O'CHIRISH UCHUN RO'YXAT
    elif data == "rem_admin_list":
        try:
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT user_id FROM admin_id")
                    admin_id = await cur.fetchall()
            
            if not admin_id:
                await query.answer("📭 Hozircha adminlar yo'q (Sizdan tashqari).", show_alert=True)
                return None
                
            keyboard = []
            for adm in admin_id:
                keyboard.append([InlineKeyboardButton(f"🗑 ID: {adm['user_id']}", callback_data=f"del_adm_{adm['user_id']}")])
            
            keyboard.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="manage_admins")])
            
            await query.edit_message_text(
                "🗑 <b>O'chirmoqchi bo'lgan adminni tanlang:</b>", 
                reply_markup=InlineKeyboardMarkup(keyboard), 
                parse_mode="HTML"
            )
            return None
        except Exception as e:
            logger.error(f"Admin ro'yxati xatosi: {e}")
            await query.answer("⚠️ Ma'lumotni yuklab bo'lmadi.")

    # 4. ADMINNI O'CHIRISH IJROSI
    elif data.startswith("del_adm_"):
        adm_id = data.replace("del_adm_", "")
        try:
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # O'chirish
                    await cur.execute("DELETE FROM admin_id WHERE user_id = %s", (adm_id,))
                    # Statusni userga tushirish (agar users jadvalida bo'lsa)
                    await cur.execute("UPDATE users SET status = 'user' WHERE user_id = %s", (adm_id,))
                    # LOG (21-band)
                    await cur.execute(
                        "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                        (user_id, f"Adminlikdan olib tashladi: {adm_id}")
                    )
            
            await query.answer(f"✅ Admin {adm_id} o'chirildi!", show_alert=True)
            # Ro'yxatni yangilash
            query.data = "rem_admin_list"
            return await handle_callback(update, context)
        except Exception as e:
            logger.error(f"Admin o'chirish xatosi: {e}")

    # 5. ADMIN QO'SHISHNI TASDIQLASH
    elif data.startswith("conf_adm_"):
        new_id = data.replace("conf_adm_", "")
        try:
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # Admin jadvaliga qo'shish
                    await cur.execute("INSERT INTO admin_id (user_id) VALUES (%s)", (new_id,))
                    # Users jadvalida statusni yangilash
                    await cur.execute("UPDATE users SET status = 'admin' WHERE user_id = %s", (new_id,))
                    # LOG (21-band)
                    await cur.execute(
                        "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                        (user_id, f"Yangi admin tayinladi: {new_id}")
                    )
            
            await query.edit_message_text(f"✅ ID: <code>{new_id}</code> muvaffaqiyatli admin qilib tayinlandi.", parse_mode="HTML")
        except Exception as e:
            await query.edit_message_text(f"❌ Xatolik: {e}")
        
        return ConversationHandler.END


  # ================= VIP CONTROL (ADMIN PANEL) =================
    # 1. VIP ASOSIY MENYUSI
    if data in ["adm_vip_add", "manage_vip"]:
        keyboard = [
            [InlineKeyboardButton("➕ Add VIP User", callback_data="start_vip_add")],
            [InlineKeyboardButton("📜 VIP List", callback_data="vip_list")],
            [InlineKeyboardButton("🗑 Remove VIP", callback_data="rem_vip_list")],
            [InlineKeyboardButton("⬅️ Back", callback_data="admin_main")]
        ]
        await query.edit_message_text(
            "💎 <b>VIP CONTROL PANEL</b>\n\nKerakli bo'limni tanlang: 👇",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return None

    # 2. VIP QO'SHISHNI BOSHLASH
    elif data == "start_vip_add":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="manage_vip")]])
        await query.edit_message_text(
            "🆔 <b>VIP qilinadigan foydalanuvchi ID-sini yuboring:</b>", 
            reply_markup=kb, 
            parse_mode="HTML"
        )
        return A_ADD_VIP

    # 3. VIP FOYDALANUVCHILAR RO'YXATI
    elif data == "vip_list":
        try:
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT user_id FROM users WHERE status = 'vip'")
                    vips = await cur.fetchall()
            
            text = "📜 <b>VIP Users List:</b>\n\n"
            if not vips:
                text += "📭 Hozircha VIP foydalanuvchilar yo'q."
            else:
                for idx, v in enumerate(vips, 1):
                    # DictCursor bo'lsa v['user_id'], aks holda v[0]
                    u_id = v['user_id'] if isinstance(v, dict) else v[0]
                    text += f"{idx}. ID: <code>{u_id}</code>\n"
            
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="manage_vip")]])
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            logger.error(f"VIP List error: {e}")
            await query.answer("❌ Ro'yxatni yuklashda xatolik.")
        return None

    # 4. VIPDAN OLIB TASHLASH IJROSI
    elif data.startswith("exec_rem_vip_"):
        parts = data.split("_")
        target_id = parts[3]
        try:
            current_page = int(parts[4])
        except:
            current_page = 0
        
        try:
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # Statusni userga qaytarish
                    await cur.execute("UPDATE users SET status = 'user' WHERE user_id = %s", (target_id,))
                    
                    # 21-band: Logga yozish
                    await cur.execute(
                        "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                        (user_id, f"Foydalanuvchini VIP ro'yxatidan o'chirdi: {target_id}")
                    )
            
            await query.answer(f"✅ ID: {target_id} VIP-dan olib tashlandi!", show_alert=True)
            # Ro'yxatni yangilab ko'rsatish
            await show_vip_removal_list(update, context, page=current_page)
        except Exception as e:
            logger.error(f"Remove VIP error: {e}")
            await query.answer("❌ O'chirishda xatolik yuz berdi.")
 
    


# ----------------- BOSHQA FUNKSIYALAR -----------------

async def show_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        # aiomysql pool orqali ulanish
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT bonus, status FROM users WHERE user_id=%s", (user_id,))
                res = await cur.fetchone()
        
        # Ma'lumotlarni olish (DictCursor ishlatilgan deb hisoblaymiz)
        val = res['bonus'] if res else 0
        st = res['status'] if res else "user"
        
        # Statusga qarab chiroyli emoji tanlash
        st_emoji = "💎 VIP" if st == "vip" else "👤 Foydalanuvchi"
        if st in ["admin", "main_admin"]:
            st_emoji = "👮 Admin"

        text = (
            "🏦 <b>SHAXSIY HISOB</b>\n\n"
            f"👤 <b>Foydalanuvchi:</b> {update.effective_user.mention_html()}\n"
            f"💰 <b>To'plangan ballar:</b> <code>{val}</code>\n"
            f"⭐ <b>Maqomingiz:</b> {st_emoji}\n\n"
            "<i>💡 Ballar yordamida VIP statusini sotib olishingiz yoki maxsus imkoniyatlardan foydalanishingiz mumkin.</i>"
        )

        # Agar foydalanuvchi xabar yuborgan bo'lsa (command), aks holda callback bo'lsa
        if update.message:
            await update.message.reply_text(text, parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Bonus ko'rsatishda xato: {e}")
        error_msg = "⚠️ Ma'lumotlarni yuklashda xatolik yuz berdi."
        if update.message:
            await update.message.reply_text(error_msg)
        elif update.callback_query:
            await update.callback_query.answer(error_msg, show_alert=True)


# ===================================================================================


async def show_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Qo'llanma matni HTML formatida
    text = (
        "📖 <b>BOTDAN FOYDALANISH QO‘LLANMASI</b>\n\n"
        "🔍 <b>Anime qidirish:</b> Bosh menyudagi qidiruv tugmasi orqali anime nomi yoki ID raqamini kiriting.\n\n"
        "🎁 <b>Bonus ballar:</b> Har bir do'stingizni taklif qilganingiz uchun ball beriladi. Ballarni VIP maqomiga almashtirish mumkin.\n\n"
        "💎 <b>VIP maqomi:</b> Reklamasiz ko'rish va yangi qismlarni birinchilardan bo'lib ko'rish imkoniyati.\n\n"
        "📜 <b>Anime ro‘yxati:</b> Janrlar va alifbo bo'yicha saralangan barcha animelar to'plami.\n\n"
        "〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
        "❓ <b>Savollaringiz bormi?</b>\n"
        "Murojaat uchun: @Aninovuz_Admin"
    )

    # Qo'llanma ostiga foydali tugmalarni qo'shamiz
    keyboard = [
        [
            InlineKeyboardButton("💎 VIP sotib olish", callback_data="buy_vip"),
            InlineKeyboardButton("📊 Statistika", callback_data="user_stats")
        ],
        [InlineKeyboardButton("⬅️ Bosh menyu", callback_data="main_menu")]
    ]

    # Agar xabar komanda orqali kelsa (message), aks holda (callback_query)
    if update.message:
        await update.message.reply_text(
            text=text, 
            reply_markup=InlineKeyboardMarkup(keyboard), 
            parse_mode="HTML"
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text=text, 
            reply_markup=InlineKeyboardMarkup(keyboard), 
            parse_mode="HTML"
        )


# ===================================================================================


async def vip_pass_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchiga VIP PASS haqida batafsil ma'lumot beradi"""
    
    text = (
        "💎 <b>VIP PASS — CHEKSIZ IMKONIYATLAR!</b>\n\n"
        "Obuna bo'lish orqali siz quyidagi afzalliklarga ega bo'lasiz:\n\n"
        "🚫 <b>Reklamasiz tomosha:</b> Bot va kanallardagi ortiqcha reklamalarsiz kontentdan bahra oling.\n"
        "⚡️ <b>Eksklyuzivlik:</b> Yangi anime qismlarini barchadan oldin tomosha qiling.\n"
        "👥 <b>Yopiq hamjamiyat:</b> Maxsus VIP guruh va muhokamalarda qatnashing.\n"
        "🌟 <b>Yuqori sifat:</b> Videolarni eng yaxshi sifatda yuklab olish imkoniyati.\n\n"
        "💳 <b>VIP PASS sotib olish yoki savollar bo'lsa:</b>\n"
        "👉 @Khudoyqulov_pg — <i>Admin bilan bog'lanish</i>"
    )

    keyboard = [
        [InlineKeyboardButton("✅ Adminga yozish", url="https://t.me/Khudoyqulov_pg")],
        [InlineKeyboardButton("🔙 Bosh menyu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Callback bo'lsa xabarni tahrirlaymiz, aks holda yangi xabar yuboramiz
    if update.callback_query:
        # Eski xabarni tahrirlash (foydalanuvchi chatida joy tejash uchun)
        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    else:
        # /vip komandasi uchun yangi xabar
        await update.message.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )


# ===================================================================================


async def admin_panel_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 21-band: Foydalanuvchi maqomini tekshirish (Asinxron)
    status = await get_user_status(user_id)
    
    if status in ["main_admin", "admin"]:
        is_main = (status == "main_admin")
        
        # 21-band: Admin kirishini loglash (Audit uchun)
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (user_id, "Admin paneliga kirdi")
                )

        # Admin panel matni
        admin_info = "👑 <b>Bosh Admin Paneli</b>" if is_main else "👨‍💻 <b>Admin Paneli</b>"
        text = (
            f"{admin_info}\n\n"
            "Botni boshqarish va statistika bilan tanishish uchun quyidagi bo'limlardan birini tanlang:\n\n"
            "<i>Eslatma: Amalga oshirilgan barcha harakatlar qayd etiladi!</i>"
        )
        
        # Markdown o'rniga HTML xavfsizroq va chiroyliroq
        await update.message.reply_text(
            text=text,
            reply_markup=get_admin_kb(is_main),
            parse_mode="HTML"
        )
    else:
        # Oddiy foydalanuvchilar uchun ruxsat berilmasligi
        await update.message.reply_text("❌ <b>Sizda ushbu bo'limga kirish huquqi yo'q!</b>", parse_mode="HTML")
        

  
# ===================================================================================       

async def post_new_anime_to_channel(context, anime_id):
    """Qismlar yuklanib bo'lingach, kanalga avtomatik jozibador post yuborish"""
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Anime ma'lumotlarini bazadan olish
                await cur.execute("SELECT * FROM anime_list WHERE anime_id=%s", (anime_id,))
                anime_data = await cur.fetchone()
                
                if not anime_data:
                    logger.error(f"Xato: ID {anime_id} bo'yicha anime topilmadi")
                    return

                # 2. Haqiqiy qismlar sonini sanash
                await cur.execute("SELECT COUNT(id) as total FROM anime_episodes WHERE anime_id=%s", (anime_id,))
                res_count = await cur.fetchone()
                total_episodes = res_count['total']

        CHANNEL_ID = "@Aninovuz" 
        BOT_USERNAME = context.bot.username # Dinamik ravishda bot username'ni olish

        # Link yaratish (deep linking)
        bot_link = f"https://t.me/{BOT_USERNAME}?start=ani_{anime_id}"

        # 14-BAND: CAPTION dizaynini yanada jozibador qilish
        caption = (
            f"🎬 <b>{anime_data['name']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💎 <b>Status:</b> To'liq (Barcha qismlar)\n"
            f"🎞 <b>Qismlar:</b> {total_episodes} ta qism\n"
            f"🎙 <b>Tili:</b> {anime_data.get('lang', 'Oʻzbekcha')}\n"
            f"🎭 <b>Janri:</b> {anime_data.get('genre', 'Sarguzasht')}\n"
            f"📅 <b>Yili:</b> {anime_data.get('year', 'Noma’lum')}\n"
            f"🆔 <b>ID:</b> <code>{anime_id}</code>\n\n"
            f"✨ @Aninovuz — Eng sara animelar manbasi!\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📥 <b>Ko'rish uchun pastdagi tugmani bosing:</b>"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 KO'RISHNI BOSHLASH", url=bot_link)]
        ])

        # Kanalga yuborish
        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=anime_data['poster_id'],
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"✅ Anime {anime_id} kanalga muvaffaqiyatli joylandi.")

    except Exception as e:
        logger.error(f"❌ Kanalga post yuborishda xato: {e}")
    
# ====================== ANIME QIDIRISH VA PAGINATION (TO'LIQ) ======================

async def search_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qidiruv turini tanlash menyusi"""
    query = update.callback_query
    
    # 1. Tugmalarni shakllantirish
    kb = [
        [
            InlineKeyboardButton("🔎 Nomi orqali", callback_data="search_type_name"),
            InlineKeyboardButton("🆔 ID raqami", callback_data="search_type_id")
        ],
        [
            InlineKeyboardButton("🖼 Rasm orqali (AI)", callback_data="search_type_photo"),
            InlineKeyboardButton("👤 Personaj (AI)", callback_data="search_type_character")
        ],
        [
            InlineKeyboardButton("🎭 Janrlar", callback_data="search_type_genre"),
            InlineKeyboardButton("🎙 Fandublar", callback_data="search_type_fandub")
        ],
        [InlineKeyboardButton("🎲 Tasodifiy anime", callback_data="search_type_random")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_search")]
    ]
    
    text = (
        "🎬 <b>Anime qidirish bo'limi</b>\n\n"
        "Qidiruv usulini tanlang yoki savolingizni yozing:\n\n"
        "💡 <i>Maslahat: Rasm orqali qidirish (AI) animesi esingizda yo'q kadrlarni topishga yordam beradi!</i>"
    )

    # 2. Xabarni tahrirlash yoki yangi yuborish (Xabarlar to'planib ketmasligi uchun)
    try:
        if query:
            await query.answer()
            await query.edit_message_text(
                text=text, 
                reply_markup=InlineKeyboardMarkup(kb), 
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                text=text, 
                reply_markup=InlineKeyboardMarkup(kb), 
                parse_mode="HTML"
            )
    except Exception as e:
        # Agar xabar bir xil bo'lsa edit_message xato beradi, shuni oldini olamiz
        logger.error(f"Search menu xatosi: {e}")

    # 🔥 MUHIM: Foydalanuvchini aynan QIDIRUV holatiga o'tkazamiz
    # A_MAIN o'rniga A_SEARCH_BY_NAME yoki maxsus SEARCH holatini ishlating
    return A_SEARCH_BY_NAME 
    
    

# ===================================================================================

async def search_anime_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. CALLBACK QUERY (Inline tugmalar bosilganda)
    query = update.callback_query
    user_id = update.effective_user.id
    status = await get_user_status(user_id)

    if query:
        await query.answer()
        data = query.data
        
        # Qidiruv rejimini tanlash
        if data == "search_type_name":
            context.user_data["search_mode"] = "name"
            await query.message.reply_text("🔍 Anime <b>nomini</b> kiriting:", parse_mode="HTML", reply_markup=get_cancel_kb())
            return A_SEARCH_BY_NAME
            
        elif data == "search_type_id":
            context.user_data["search_mode"] = "id"
            await query.message.reply_text("🆔 Anime <b>ID raqamini</b> kiriting:", parse_mode="HTML", reply_markup=get_cancel_kb())
            return A_SEARCH_BY_ID
            
        elif data == "search_type_character":
            context.user_data["search_mode"] = "character"
            await query.message.reply_text("👤 <b>Personaj</b> yoki tavsif kiriting:", parse_mode="HTML", reply_markup=get_cancel_kb())
            return A_SEARCH_BY_NAME

        elif data == "search_type_fandub":
            # Skeletingizdagi show_fandub_list funksiyasini chaqiramiz
            return await show_fandub_list(update, context)

        elif data == "search_type_random":
            # Tasodifiy anime topish
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT anime_id FROM anime_list ORDER BY RAND() LIMIT 1")
                    res = await cur.fetchone()
                    if res:
                        return await show_selected_anime(update, context, res['anime_id'])
            return A_MAIN

        return A_MAIN

    # 2. MESSAGE (Matn yozilganda yoki Reply tugmalar bosilganda)
    if not update.message:
        return
        
    text = update.message.text.strip() if update.message.text else ""

    # "Bekor qilish" yoki "Orqaga" tugmalari bosilganda
    if text in ["❌ Bekor qilish", "⬅️ Orqaga", "Bekor qilish"]:
        await update.message.reply_text("🏠 Asosiy menyu", reply_markup=get_main_kb(status))
        return ConversationHandler.END

    if not text:
        return

    # Qidiruv rejimi
    search_type = context.user_data.get("search_mode", "name")

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur: # DictCursor juda muhim!
                # Dinamik SQL
                if text.isdigit() or search_type == "id":
                    query_sql = "SELECT * FROM anime_list WHERE anime_id=%s"
                    params = (int(text) if text.isdigit() else 0,)
                elif search_type == "character":
                    query_sql = "SELECT * FROM anime_list WHERE description LIKE %s OR genre LIKE %s LIMIT 21"
                    params = (f"%{text}%", f"%{text}%")
                else:
                    query_sql = "SELECT * FROM anime_list WHERE name LIKE %s OR original_name LIKE %s LIMIT 21"
                    params = (f"%{text}%", f"%{text}%")
                
                await cur.execute(query_sql, params)
                results = await cur.fetchall()

        if not results:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Qayta qidirish", callback_data="search_type_name")],
                [InlineKeyboardButton("❌ To'xtatish", callback_data="cancel_search")]
            ])
            await update.message.reply_text(
                f"😔 <b>'{text}'</b> bo'yicha hech narsa topilmadi.",
                reply_markup=kb, parse_mode="HTML"
            )
            return 

        # 🎯 MUHIM QISM: Bitta natija chiqsa
        if len(results) == 1:
            anime_id = results[0]['anime_id']
            # show_selected_anime funksiyasini chaqirishda xatolik bo'lmasligi uchun
            # argumentlarni tekshiring. Odatda (update, context) kifoya qiladi.
            # Agar funksiyangiz anime_id ni ham talab qilsa:
            return await show_selected_anime(update, context, anime_id)

        # 📋 Bir nechta natija chiqsa
        keyboard = []
        for anime in results[:20]:
            # Reytingni hisoblashda xato bermasligi uchun default qiymatlar
            r_sum = anime.get('rating_sum') or 0
            r_count = anime.get('rating_count') or 0
            rating = round(r_sum / r_count, 1) if r_count > 0 else "N/A"
            
            btn_text = f"🎬 {anime['name']} ⭐ {rating}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"show_anime_{anime['anime_id']}")])
        
        await update.message.reply_text(
            f"🔍 <b>'{text}' bo'yicha topilganlar:</b>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Search error detailed: {e}") # Konsolda aniq xatoni ko'rasiz
        await update.message.reply_text(f"❌ Xatolik: {e}") # Test vaqtida xatoni ko'rish uchun

# ===================================================================================

async def show_selected_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Callbackni yopamiz (soat belgisi ketishi uchun)
    await query.answer() 
    
    # IDni ajratib olish
    anime_id = query.data.replace("show_anime_", "")
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Anime ma'lumotlarini olish
                await cur.execute("SELECT * FROM anime_list WHERE anime_id=%s", (anime_id,))
                anime = await cur.fetchone()
                
                if anime:
                    # 11-BAND: Ko'rishlar sonini oshirish (Trendlar uchun)
                    # total_views - umumiy, views_week - haftalik statistika uchun
                    await cur.execute(
                        "UPDATE anime_list SET total_views = total_views + 1, views_week = views_week + 1 WHERE anime_id=%s",
                        (anime_id,)
                    )
                    
                    context.user_data['current_anime_id'] = anime_id
                    
                    # 2. Tafsilotlarni ko'rsatish funksiyasini chaqiramiz
                    return await show_anime_details(query, anime, context)
                else:
                    await query.edit_message_text("❌ Kechirasiz, ushbu anime topilmadi yoki o'chirilgan.")
                    
    except Exception as e:
        logger.error(f"⚠️ Anime tanlashda xato (ID: {anime_id}): {e}")
        await query.message.reply_text("🛠 Texnik xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")

# ===================================================================================


async def show_anime_details(update_or_query, anime, context):
    """Anime tafsilotlari, epizodlar va interaktiv tugmalar (HTML)"""
    
    anime_id = anime['anime_id']
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Epizodlarni olish
                await cur.execute(
                    "SELECT id, episode FROM anime_episodes WHERE anime_id=%s ORDER BY episode ASC", 
                    (anime_id,)
                )
                episodes = await cur.fetchall()
                
                # 2. Reytingni hisoblash (12-band)
                r_sum = anime.get('rating_sum', 0)
                r_count = anime.get('rating_count', 0)
                rating_val = f"⭐ {round(r_sum / r_count, 1)} / 10" if r_count > 0 else "Noma'lum"

        # Chat ID aniqlash
        chat_id = update_or_query.effective_chat.id
        
        # 3. Caption yasash (14-band dizayni)
        total_episodes = len(episodes)
        status_text = f"✅ {total_episodes} ta qism" if total_episodes > 0 else "⏳ Tez kunda..."

        # 1. Ma'lumotlarni tayyorlash (Xavfsiz usul)
        desc = anime.get("description", "Ma'lumot berilmagan.")[:200]
        fandub = anime.get('fandub', 'Aninovuz')
        lang = anime.get('lang', 'Oʻzbekcha')
        genre = anime.get('genre', 'Sarguzasht')
        year = anime.get('year', 'Noma’lum')

        # 2. Captionni shakllantirish
        caption = (
            f"🎬 <b>{anime['name']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>Reyting:</b> {rating_val}\n"
            f"🎥 <b>Status:</b> {status_text}\n"
            f"🎙 <b>Fandub:</b> {fandub}\n"
            f"🌐 <b>Tili:</b> {lang}\n"
            f"🎭 <b>Janri:</b> {genre}\n"
            f"📅 <b>Yili:</b> {year}\n"
            f"👁 <b>Ko'rilgan:</b> {anime.get('total_views', 0)} marta\n"
            f"🆔 <b>ID:</b> <code>{anime_id}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 <b>Tavsif:</b> {desc}...\n\n"
            f"📥 <b>Ko'rish uchun qismni tanlang:</b>"
        ) # Bu qavs ochilgan caption qavsini yopadi

        # 4. TUGMALAR (PAGINATION - 10-band)
        keyboard = []
        if episodes:
            row = []
            # Dastlabki 12 ta qismni chiqaramiz
            for ep in episodes[:12]:
                # DictCursor uchun ep['episode'], oddiy uchun ep[1]
                ep_num = ep['episode'] if isinstance(ep, dict) else ep[1]
                ep_db_id = ep['id'] if isinstance(ep, dict) else ep[0]
                
                row.append(InlineKeyboardButton(f"{ep_num}", callback_data=f"get_ep_{ep_db_id}"))
                if len(row) == 4:
                    keyboard.append(row)
                    row = []
            if row: keyboard.append(row)
            
            # Agar 12 tadan ko'p bo'lsa "Keyingi" tugmasi
            if len(episodes) > 12:
                keyboard.append([InlineKeyboardButton("Keyingi qismlar ➡️", callback_data=f"page_{anime_id}_12")])

        # 5. INTERAKTIV FUNKSIYALAR
        keyboard.append([
            InlineKeyboardButton("🌟 Baholash", callback_data=f"rate_{anime_id}"),
            InlineKeyboardButton("🔗 Ulashish", switch_inline_query=f"ani_{anime_id}")
        ])
        
        keyboard.append([
            InlineKeyboardButton("💬 Izohlar", callback_data=f"comm_{anime_id}"),
            InlineKeyboardButton("❤️ Sevimlilar", callback_data=f"fav_{anime_id}")
        ])

        # 6. YUBORISH
        try:
            # Poster bilan yuborish
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=anime['poster_id'],
                caption=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
            
            # Agar bu callback_query bo'lsa, eski qidiruv xabarini o'chiramiz
            if hasattr(update_or_query, 'data'):
                try: await update_or_query.message.delete()
                except: pass

        except Exception as e:
            # Agar rasmda xato bo'lsa (file_id o'zgargan bo'lsa), matn o'zini yuboramiz
            logger.warning(f"Poster yuborishda xato, matn yuborilmoqda: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🖼 <b>Poster yuklanmadi</b>\n\n{caption}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"Anime details display error: {e}")
        await context.bot.send_message(chat_id=chat_id, text="❌ Ma'lumotni yuklashda xatolik yuz berdi.")

    return ConversationHandler.END


# ===================================================================================


import datetime

async def get_episode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("_") 
    user_id = update.effective_user.id
    
    if len(data) < 3: 
        await query.answer("❌ Ma'lumot xatosi")
        return
        
    row_id = data[2] 
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Foydalanuvchi va Video ma'lumotlarini olish
                await cur.execute("SELECT health_mode, status FROM users WHERE user_id = %s", (user_id,))
                user_data = await cur.fetchone()

                await cur.execute("""
                    SELECT e.file_id, e.episode, e.anime_id, a.name 
                    FROM anime_episodes e 
                    JOIN anime_list a ON e.anime_id = a.anime_id 
                    WHERE e.id = %s
                """, (row_id,))
                res = await cur.fetchone()
                
                if not res:
                    await query.answer("❌ Video topilmadi!", show_alert=True)
                    return

                # 2. KO'RISH TARIXI (History - 11-band)
                await cur.execute("SELECT id FROM history WHERE user_id=%s AND anime_id=%s", (user_id, res['anime_id']))
                history_entry = await cur.fetchone()
                
                if history_entry:
                    await cur.execute(
                        "UPDATE history SET last_episode=%s, watched_at=NOW() WHERE id=%s", 
                        (res['episode'], history_entry['id'])
                    )
                else:
                    await cur.execute(
                        "INSERT INTO history (user_id, anime_id, last_episode) VALUES (%s, %s, %s)", 
                        (user_id, res['anime_id'], res['episode'])
                    )

                # 3. KEYINGI QISMNI QIDIRISH
                await cur.execute("""
                    SELECT id FROM anime_episodes 
                    WHERE anime_id = %s AND episode > %s 
                    ORDER BY episode ASC LIMIT 1
                """, (res['anime_id'], res['episode']))
                next_ep = await cur.fetchone()
                
                # 4. REKLAMA (Faqat VIP bo'lmaganlar uchun - 14-band)
                ads_text = ""
                if user_data and user_data['status'] != 'vip':
                    await cur.execute("SELECT caption FROM advertisements WHERE is_active=1 ORDER BY RAND() LIMIT 1")
                    ads = await cur.fetchone()
                    if ads:
                        ads_text = f"\n\n📢 <i>{ads['caption']}</i>"

        # 5. SOG'LIQ REJIMI (28-band: 01:00 - 05:00)
        current_hour = datetime.datetime.now().hour
        if user_data and user_data.get('health_mode') == 1:
            if 1 <= current_hour <= 5:
                await query.message.reply_text(
                    "🌙 <b>Sog'ligingiz haqida qayg'uramiz!</b>\n\n"
                    "Tungi soat 01:00 dan o'tdi. Uyqu yetishmasligi organizm uchun zararli. "
                    "Dam olib, ertaga davom ettirishni maslahat beramiz! 😊",
                    parse_mode="HTML"
                )

        # 6. TUGMALARNI SHAKLLANTIRISH
        keyboard = []
        if next_ep:
            # next_ep['id'] yoki next_ep[0] (Cursor turiga qarab)
            n_id = next_ep['id'] if isinstance(next_ep, dict) else next_ep[0]
            keyboard.append([InlineKeyboardButton("Keyingi qism ➡️", callback_data=f"get_ep_{n_id}")])
        else:
            keyboard.append([InlineKeyboardButton("⭐️ Animeni baholash", callback_data=f"rate_{res['anime_id']}")])
            keyboard.append([InlineKeyboardButton("✅ Tugatish va Ball olish", callback_data=f"finish_{res['anime_id']}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Anime sahifasiga", callback_data=f"show_anime_{res['anime_id']}")])

        # 7. VIDEONI YUBORISH
        await query.message.reply_video(
            video=res['file_id'],
            caption=(
                f"🎬 <b>{res['name']}</b>\n"
                f"🔢 <b>{res['episode']}-qism</b>\n"
                f"────────────────────\n"
                f"✅ @Aninovuz{ads_text}"
            ),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        await query.answer(f"Huzur qiling! {res['episode']}-qism")

    except Exception as e:
        logger.error(f"Video yuborish xatosi: {e}")
        await query.answer("❌ Video yuklashda xatolik yuz berdi.", show_alert=True)


# ===================================================================================


async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qismlar ro'yxatini varaqlash (Pagination) — Asinxron va optimallashtirilgan"""
    query = update.callback_query
    data_parts = query.data.split("_")
    
    if len(data_parts) < 3:
        return await query.answer("❌ Ma'lumot xatosi")
    
    anime_id = data_parts[1]
    offset = int(data_parts[2])
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Faqat ushbu animega tegishli barcha qismlarni olish
                await cur.execute(
                    "SELECT id, episode FROM anime_episodes WHERE anime_id=%s ORDER BY episode ASC", 
                    (anime_id,)
                )
                episodes = await cur.fetchall()

        if not episodes:
            return await query.answer("❌ Hozircha epizodlar mavjud emas", show_alert=True)

        keyboard = []
        row = []
        # Sahifada ko'rsatiladigan qismlarni ajratish (12 tadan)
        display_eps = episodes[offset : offset + 12]
        
        for ep in display_eps:
            # ep['episode'] (DictCursor) yoki ep[1] (Normal Cursor)
            ep_num = ep['episode'] if isinstance(ep, dict) else ep[1]
            ep_db_id = ep['id'] if isinstance(ep, dict) else ep[0]
            
            row.append(InlineKeyboardButton(text=str(ep_num), callback_data=f"get_ep_{ep_db_id}"))
            if len(row) == 4:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)

        # Navigatsiya tugmalari mantiqi
        nav_row = []
        if offset > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"page_{anime_id}_{max(0, offset-12)}"))
        
        # Hozirgi qamrovni ko'rsatish
        total = len(episodes)
        current_view = f"{offset + 1}-{min(offset + 12, total)}"
        nav_row.append(InlineKeyboardButton(f"📄 {current_view} / {total}", callback_data="none"))
        
        if offset + 12 < total:
            nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"page_{anime_id}_{offset+12}"))
        
        if nav_row:
            keyboard.append(nav_row)

        # 28-BAND: ANIME SAHIFASIGA QAYTISH
        keyboard.append([InlineKeyboardButton("🔙 Anime haqida ma'lumot", callback_data=f"show_anime_{anime_id}")])

        # Faqat klaviaturani yangilaymiz (Rasm va caption joyida qoladi)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        await query.answer()

    except Exception as e:
        logger.error(f"Pagination Error (Anime ID: {anime_id}): {e}")
        await query.answer("⚠️ Sahifani yuklashda xatolik yuz berdi.", show_alert=True)


# ====================== CONVERSATION STEPS (TUZATILDI) ======================

async def anime_control_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    # 1. Admin ekanligini qayta tekshirish (Xavfsizlik uchun)
    status = await get_user_status(user_id)
    if status not in ["admin", "main_admin"]:
        if query:
            await query.answer("❌ Ruxsat berilmagan!", show_alert=True)
        return ConversationHandler.END

    if query:
        await query.answer()
        # Admin asosiy menyusiga qaytish mantiqi
        if query.data == "admin_main":
            is_main = (status == "main_admin")
            await query.edit_message_text(
                "🛠 <b>Admin paneliga xush kelibsiz:</b>",
                reply_markup=get_admin_kb(is_main),
                parse_mode="HTML"
            )
            return ConversationHandler.END

    # 2. TUGMALAR STRUKTURASI
    kb = [
        [
            InlineKeyboardButton("➕ Yangi Anime", callback_data="add_ani_menu"),
            InlineKeyboardButton("📜 Barcha ro'yxat", callback_data="list_ani_pg_0")
        ],
        [
            InlineKeyboardButton("🔥 Top Animelar", callback_data="manage_top_ani"),
            InlineKeyboardButton("✅ Tugallanganlar", callback_data="manage_completed")
        ],
        [
            InlineKeyboardButton("🗑 Animeni o'chirish", callback_data="rem_ani_menu")
        ],
        [
            InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_main")
        ]
    ]
    
    # 14-BAND: CAPTION dizayni (HTML formatida)
    text = (
        "⚙️ <b>ANIME BOSHQARUV PANELI</b>\n\n"
        "Ushbu bo'lim orqali bazadagi animelarni tahrirlashingiz mumkin:\n\n"
        "• <b>Yangi Anime:</b> Baza va kanalga yangi kontent qo'shish\n"
        "• <b>Top Animelar:</b> Haftalik eng ommaboplar ro'yxati\n"
        "• <b>Tugallanganlar:</b> Statusni o'zgartirish\n"
        "• <b>O'chirish:</b> Xato yuklangan kontentni tozalash\n\n"
        "<i>⚠️ Eslatma: O'chirilgan ma'lumotlarni qayta tiklab bo'lmaydi!</i>"
    )
    
    reply_markup = InlineKeyboardMarkup(kb)

    try:
        if query:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
            
        # 21-BAND: Harakatni loglash
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (user_id, "Anime boshqaruv paneliga kirdi")
                )
    except Exception as e:
        logger.error(f"Anime control panel error: {e}")

    return A_ANI_CONTROL

# ===================================================================================


async def add_anime_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    # 1. Admin statusini tekshirish
    status = await get_user_status(user_id)
    if status not in ["admin", "main_admin"]:
        await query.answer("❌ Sizda bunday huquq yo'q!", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    # 2. Tugmalar tuzilishi
    kb = [
        [InlineKeyboardButton("✨ Yangi anime yaratish", callback_data="start_new_ani")],
        [InlineKeyboardButton("📼 Mavjudga qism qo'shish", callback_data="new_ep_ani")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_ctrl")]
    ]
    
    # 14-BAND: Yordamchi matn bilan dizaynni yaxshilash
    text = (
        "➕ <b>KONTENT QO'SHISH PANELI</b>\n\n"
        "<b>Yangi anime:</b> Bazada hali yo'q anime haqida ma'lumot (poster, janr, yil) kiritish.\n\n"
        "<b>Yangi qism:</b> Bazada bor animening keyingi qismlarini (video fayllarini) yuklash.\n\n"
        "<i>💡 Maslahat: Avval anime ma'lumotlarini yarating, keyin qismlarni yuklang.</i>"
    )

    # 21-BAND: Logga yozish
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (user_id, "Kontent qo'shish paneliga kirdi")
                )
    except Exception as e:
        logger.error(f"Audit log error: {e}")

    await query.edit_message_text(
        text=text, 
        reply_markup=InlineKeyboardMarkup(kb), 
        parse_mode="HTML"
    )
    return A_ADD_MENU


# ===================================================================================


async def start_new_ani(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Xavfsizlik: Faqat adminlar uchun
    status = await get_user_status(user_id)
    if status not in ["admin", "main_admin"]:
        await query.answer("❌ Ruxsat berilmagan!", show_alert=True)
        return ConversationHandler.END

    await query.answer()
    
    # 21-BAND: Audit log (Yangi anime yaratish boshlandi)
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                (user_id, "Yangi anime qo'shish jarayonini boshladi")
            )

    kb = [[InlineKeyboardButton("⬅️ Bekor qilish", callback_data="add_ani_menu")]]
    
    # HTML formatida chiroyliroq ko'rinish
    await query.edit_message_text(
        "🖼 <b>1-QADAM: POSTER YUKLASH</b>\n\n"
        "Iltimos, animening rasmini (posterini) yuboring.\n\n"
        "<i>💡 Maslahat: Sifatli va 3:4 nisbatdagi rasm kanalga chiroyli chiqadi.</i>",
        reply_markup=InlineKeyboardMarkup(kb), 
        parse_mode="HTML"
    )
    
    return A_GET_POSTER


# ===================================================================================

async def get_poster_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Faqat rasm ekanligini tekshiramiz
    if not update.message.photo:
        await update.message.reply_text("❌ Iltimos, anime uchun rasm (poster) yuboring!")
        return A_GET_POSTER
    
    # Eng yuqori sifatli rasmni saqlaymiz
    context.user_data['tmp_poster'] = update.message.photo[-1].file_id
    
    kb = [[InlineKeyboardButton("⬅️ Bekor qilish", callback_data="add_ani_menu")]]
    
    # 28-bandga mos (14-band dizayni uchun) formatlash
    text = (
        "✅ <b>Poster qabul qilindi!</b>\n\n"
        "Endi anime tafsilotlarini quyidagi formatda yuboring:\n\n"
        "<code>Nomi | Tili | Janri | Yili | Fandub | Tavsif</code>\n\n"
        "<b>Misol:</b>\n"
        "<code>Naruto | O'zbekcha | Sarguzasht | 2002 | Aninovuz | Ninja bolakay haqida sarguzashtlar.</code>\n\n"
        "⚠️ <i>Eslatma: Ma'lumotlarni ajratish uchun (|) belgisidan foydalaning!</i>"
    )
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(kb), 
        parse_mode="HTML"
    )
    return A_GET_DATA

# ===================================================================================


async def save_ani_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    # Format: Nomi | Tili | Janri | Yili | Fandub | Tavsif
    parts = [i.strip() for i in text.split("|")]
    
    if len(parts) < 4:
        await update.message.reply_text(
            "❌ <b>Xato format!</b>\nKamida 4 ta ma'lumot bo'lishi shart:\n"
            "<code>Nomi | Tili | Janri | Yili</code>",
            parse_mode="HTML"
        )
        return A_GET_DATA
    
    try:
        # Yetishmayotgan qismlarni 'Noma'lum' bilan to'ldirish
        while len(parts) < 6:
            parts.append("Noma'lum")
        
        name, lang, genre, year, fandub, description = parts
        poster_id = context.user_data.get('tmp_poster')
        
        if not poster_id:
            await update.message.reply_text("❌ Poster topilmadi. Avval rasm yuboring.")
            return A_GET_POSTER

        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 28-band: To'liq ustunlarni to'ldirish
                sql = """
                    INSERT INTO anime_list 
                    (name, poster_id, lang, genre, year, fandub, description, views_week, rating_sum, rating_count) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 0, 0)
                """
                await cur.execute(sql, (name, poster_id, lang, genre, year, fandub, description))
                new_id = cur.lastrowid
                
                # 21-band: Audit log
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (update.effective_user.id, f"Yangi anime qo'shdi: {name} (ID: {new_id})")
                )

        # Sessiyaga saqlash (Keyingi qadam - videolar uchun)
        context.user_data['cur_ani_id'] = new_id
        context.user_data['cur_ani_name'] = name
        context.user_data['ep_count'] = 0 

        await update.message.reply_text(
            f"✅ <b>{name}</b> muvaffaqiyatli saqlandi!\n\n"
            f"🆔 <b>Baza ID:</b> <code>{new_id}</code>\n"
            f"🎞 <b>Status:</b> Endi qismlarni (video) yuborishingiz mumkin.\n\n"
            f"💡 <i>Har bir yuborgan videongiz 1, 2, 3... tartibida qabul qilinadi.</i>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Kanalga e'lon qilish", callback_data=f"post_announcement_{new_id}")],
                [InlineKeyboardButton("⬅️ Admin Panel", callback_data="add_ani_menu")]
            ]),
            parse_mode="HTML"
        )
        return A_ADD_EP_FILES
        
    except Exception as e:
        logger.error(f"Save anime error: {e}")
        await update.message.reply_text(f"❌ Ma'lumotni saqlashda xatolik: {e}")
        return A_GET_DATA

# ===================================================================================


async def handle_ep_uploads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Fayl turini aniqlash (Video yoki Hujjatsiz video)
    video_obj = None
    if update.message.video:
        video_obj = update.message.video
    elif update.message.document and update.message.document.mime_type.startswith('video/'):
        video_obj = update.message.document

    if not video_obj:
        await update.message.reply_text("❌ Iltimos, video fayl yuboring!")
        return A_ADD_EP_FILES

    ani_id = context.user_data.get('cur_ani_id')
    ani_name = context.user_data.get('cur_ani_name')

    if not ani_id:
        await update.message.reply_text("❌ Seans muddati o'tgan. Iltimos, admin panelga qaytadan kiring.")
        return ConversationHandler.END

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 3. Qism raqamini aniqlash (MAX + 1 mantiqi)
                await cur.execute("SELECT MAX(episode) as last_ep FROM anime_episodes WHERE anime_id = %s", (ani_id,))
                res = await cur.fetchone()
                
                # DictCursor yoki oddiy cursorga qarab qiymatni olish
                last_ep_val = res['last_ep'] if isinstance(res, dict) else res[0]
                new_ep = (last_ep_val if last_ep_val is not None else 0) + 1
                
                # 4. Bazaga saqlash
                await cur.execute(
                    "INSERT INTO anime_episodes (anime_id, episode, file_id) VALUES (%s, %s, %s)",
                    (ani_id, new_ep, video_obj.file_id)
                )
                
                # 21-band: Audit log (Har bir qism yuklanishi qayd etiladi)
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (update.effective_user.id, f"Yuklandi: {ani_name}, {new_ep}-qism")
                )

        # 5. Navigatsiya tugmalari
        kb = [
            [InlineKeyboardButton("📢 Kanalga e'lon qilish", callback_data=f"post_to_chan_{ani_id}")],
            [InlineKeyboardButton("🏁 Jarayonni yakunlash", callback_data="add_ani_menu")]
        ]
        
        await update.message.reply_text(
            f"✅ <b>{ani_name}</b>\n🎬 <b>{new_ep}-qism</b> muvaffaqiyatli saqlandi!\n\n"
            f"🚀 Keyingi qismni yuborishingiz mumkin (avtomatik {new_ep + 1}-qism bo'ladi).\n"
            f"<i>Barcha qismlar tugagach, 'Yakunlash' tugmasini bosing.</i>",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Episode upload error: {e}")
        await update.message.reply_text(f"🛑 Xatolik yuz berdi: {e}")

    return A_ADD_EP_FILES
    

# ===================================================================================

async def post_to_channel_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() 
    
    # ID ni ajratib olish
    anime_id = query.data.split("_")[-1]
    admin_id = update.effective_user.id
    
    try:
        # 1. Avval yozilgan post_new_anime_to_channel funksiyasini chaqiramiz
        # Bu funksiya ichida barcha dizayn va tugmalar (14-band) tayyorlangan
        await post_new_anime_to_channel(context, anime_id)
        
        # 2. Audit Log (21-band): Kim kanalga post chiqarganini qayd etamiz
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (admin_id, f"Anime kanalga e'lon qilindi (ID: {anime_id})")
                )

        # 3. Admin xabarini muvaffaqiyatli yakun bilan tahrirlash
        await query.edit_message_text(
            text=(
                f"🚀 <b>Muvaffaqiyatli!</b>\n\n"
                f"Anime (ID: {anime_id}) @Aninovuz kanaliga yuborildi.\n"
                f"Foydalanuvchilar endi ushbu animeni bot orqali ko'rishlari mumkin."
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Boshqaruv Paneliga qaytish", callback_data="add_ani_menu")
            ]]),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Kanalga post chiqarishda xato (Admin: {admin_id}): {e}")
        await query.message.reply_text(
            f"❌ <b>Xatolik yuz berdi!</b>\n"
            f"Kanalga post yuborib bo'lmadi. Bot kanal admini ekanligini tekshiring.\n\n"
            f"<i>Xato tafsiloti: {e}</i>",
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Kanalga post chiqarishda xato (Admin: {admin_id}): {e}")
        await query.message.reply_text(
            f"❌ <b>Xatolik yuz berdi!</b>\n"
            f"Kanalga post yuborib bo'lmadi. Bot kanal admini ekanligini tekshiring.\n\n"
            f"<i>Xato tafsiloti: {e}</i>",
            parse_mode="HTML"
        )


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

async def admin_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin xabarga reply qilsa, foydalanuvchiga boradi (Universal: Matn, Rasm, Video)"""
    
    # 1. Faqat reply bo'lganda ishlaydi
    if not update.message.reply_to_message:
        return

    # Original xabar matnidan (yoki captionidan) foydalanuvchi ID sini qidiramiz
    orig_msg = update.message.reply_to_message
    search_text = orig_msg.text or orig_msg.caption or ""
    
    match = re.search(r"ID: (\d+)", search_text)
    if not match:
        return # Agar ID topilmasa, bu boshqa reply bo'lishi mumkin

    target_user_id = int(match.group(1))
    admin_id = update.effective_user.id

    try:
        # 28-BAND: UNIVERSAL JAVOB (Admin rasm yoki video ham yubora oladi)
        if update.message.text:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"✉️ <b>Admin javobi:</b>\n\n{update.message.text}",
                parse_mode="HTML"
            )
        else:
            # Agar rasm/video/fayl yuborilsa, uni nusxalaymiz (copy)
            await update.message.copy(
                chat_id=target_user_id,
                caption=f"✉️ <b>Admin javobi:</b>\n\n{update.message.caption or ''}",
                parse_mode="HTML"
            )

        # 21-BAND: Audit (Javobni bazaga yozish)
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (admin_id, f"Foydalanuvchiga javob yubordi (ID: {target_user_id})")
                )

        await update.message.reply_text("✅ Javob foydalanuvchiga yetkazildi!")

    except Exception as e:
        logger.error(f"Reply error: {e}")
        # Foydalanuvchi botni bloklagan bo'lishi mumkin
        await update.message.reply_text(
            f"❌ <b>Yuborib bo'lmadi!</b>\n\n"
            f"Ehtimol, foydalanuvchi botni bloklagan yoki o'chirilgan.",
            parse_mode="HTML"
        )

# ===================================================================================

async def pagination_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin paneldagi sahifalarni almashtirish handleri"""
    query = update.callback_query
    await query.answer()
    
    # Ma'lumotlarni ajratamiz: pg_prefix_page_number
    # Masalan: pg_remani_2 (Animeni o'chirish menyusi, 2-sahifa)
    data_parts = query.data.split('_')
    
    if len(data_parts) < 3:
        return

    # Prefix va yangi sahifa raqamini aniqlash
    # data_parts[-1] har doim sahifa raqami bo'ladi
    new_page = int(data_parts[-1])
    # O'rtadagi barcha qismlarni prefix sifatida birlashtiramiz
    target_prefix = "_".join(data_parts[1:-1]) + "_" 

    # 1. Dinamik "Orqaga" tugmasi mantiqi
    # Qaysi bo'limdaligimizga qarab qaytish manzili o'zgaradi
    extra = "admin_main" # Default
    if "addepto" in target_prefix: 
        extra = "add_ani_menu"
    elif "remani" in target_prefix or "remep" in target_prefix: 
        extra = "rem_ani_menu"
    elif "listani" in target_prefix:
        extra = "back_to_ctrl"

    # 2. Yangilangan klaviaturani olish
    kb = await get_pagination_keyboard(
        table_name="anime_list", 
        page=new_page, 
        prefix=target_prefix, 
        extra_callback=extra
    )

    if not kb:
        await query.answer("⚠️ Ma'lumot topilmadi.", show_alert=True)
        return

    # 3. Xabarni tahrirlash
    try:
        await query.edit_message_text(
            text=f"📂 <b>Baza ro'yxati</b>\n\n"
                 f"Sahifa: <code>{new_page + 1}</code>\n"
                 f"Amal turi: <i>{target_prefix.replace('_', ' ').title()}</i>",
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Pagination edit error: {e}")

# ===================================================================================

async def select_ani_for_ep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mavjud animega qism qo'shish uchun tanlash menyusi"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # 1. Admin statusini tekshirish
    status = await get_user_status(user_id)
    if status not in ["admin", "main_admin"]:
        await query.answer("❌ Ruxsat berilmagan!", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    # 2. Asinxron pagination klaviaturasini olish
    # Prefix "addepto_" handle_pagination va keyingi bosqichlar uchun kalit hisoblanadi
    markup = await get_pagination_keyboard(
        table_name="anime_list", 
        page=0, 
        prefix="addepto_", 
        extra_callback="add_ani_menu"
    )

    if not markup:
        await query.edit_message_text(
            "📭 <b>Baza bo'sh!</b>\n\nAvval yangi anime yaratishingiz kerak.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Yangi Anime", callback_data="start_new_ani")
            ]]),
            parse_mode="HTML"
        )
        return A_ADD_MENU

    # 21-BAND: Audit log
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                (user_id, "Qism qo'shish uchun anime tanlash bo'limiga kirdi")
            )

    # 3. Chiroyli matn va ko'rsatma
    text = (
        "📼 <b>QISM QO'SHISH</b>\n\n"
        "Quyidagi ro'yxatdan kerakli animeni tanlang.\n"
        "<i>💡 Agar ro'yxat uzun bo'lsa, pastdagi tugmalar orqali varaqlang.</i>"
    )

    await query.edit_message_text(
        text=text, 
        reply_markup=markup, 
        parse_mode="HTML"
    )
    
    return A_SELECT_ANI_EP


# ===================================================================================


async def select_ani_for_ep_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan anime ID sini tasdiqlash va video kutish holatiga o'tish"""
    query = update.callback_query
    await query.answer()
    
    # 1. ID ni ajratib olish va tekshirish
    try:
        # Prefix "addepto_" ni olib tashlaymiz
        ani_id_raw = query.data.replace("addepto_", "")
        ani_id = int(ani_id_raw)
    except (ValueError, IndexError):
        await query.message.reply_text("❌ Ma'lumot formati noto'g'ri!")
        return A_SELECT_ANI_EP
    
    try:
        # 2. Asinxron baza ulanishi
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT name FROM anime_list WHERE anime_id = %s", (ani_id,))
                res = await cur.fetchone()
                
                if res:
                    # DictCursor yoki Tuple uchun moslashuvchanlik
                    anime_name = res['name'] if isinstance(res, dict) else res[0]
                    
                    # 3. Sessiyaga (user_data) ma'lumotlarni saqlash
                    context.user_data['cur_ani_id'] = ani_id
                    context.user_data['cur_ani_name'] = anime_name
                    
                    # 21-BAND: Audit log (Admin qaysi animega qism qo'shayotgani)
                    await cur.execute(
                        "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                        (update.effective_user.id, f"Qism qo'shish uchun tanlandi: {anime_name}")
                    )

                    # 4. Adminni yo'naltirish
                    await query.edit_message_text(
                        f"📥 <b>{anime_name}</b> tanlandi.\n\n"
                        f"Endi ushbu anime uchun qismlarni (video fayl) birin-ketin yuboring.\n"
                        f"💡 <i>Bot avtomatik ravishda qismlarni tartiblab boradi.</i>",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("⬅️ Bekor qilish", callback_data="add_ani_menu")
                        ]]),
                        parse_mode="HTML"
                    )
                    return A_ADD_EP_FILES
                else:
                    await query.edit_message_text("❌ Kechirasiz, ushbu anime bazadan topilmadi!")
                    return A_SELECT_ANI_EP

    except Exception as e:
        logger.error(f"Select anime callback error: {e}")
        await query.message.reply_text("🛑 Bazaga ulanishda texnik xatolik yuz berdi.")
        return A_SELECT_ANI_EP



# ===================================================================================

async def list_episodes_for_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan animening qismlarini o'chirish uchun ro'yxat ko'rinishida chiqarish"""
    query = update.callback_query
    await query.answer()
    
    # Callback data'dan anime_id ni olamiz
    data_parts = query.data.split('_')
    ani_id = data_parts[-1]
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Animening barcha qismlarini olish
                # Eslatma: 'part' ustuni bazada 'episode' deb nomlangan bo'lishi mumkin
                await cur.execute(
                    "SELECT id, episode FROM anime_episodes WHERE anime_id = %s ORDER BY episode ASC", 
                    (ani_id,)
                )
                episodes = await cur.fetchall()

        if not episodes:
            await query.answer("📭 Bu animeda hali qismlar yuklanmagan!", show_alert=True)
            return A_REM_EP_ANI_LIST

        # 2. Tugmalarni shakllantirish (4 tadan qilib)
        buttons = []
        row = []
        for ep in episodes:
            # Cursor turiga qarab ep[1] yoki ep['episode']
            ep_id = ep['id'] if isinstance(ep, dict) else ep[0]
            ep_num = ep['episode'] if isinstance(ep, dict) else ep[1]
            
            buttons_text = f"❌ {ep_num}-qism"
            row.append(InlineKeyboardButton(buttons_text, callback_data=f"ex_del_ep_{ep_id}"))
            
            if len(row) == 4:
                buttons.append(row)
                row = []
        if row: buttons.append(row)
        
        # Orqaga qaytish tugmasi
        buttons.append([InlineKeyboardButton("🔙 Orqaga", callback_data="rem_ep_menu")])
        
        # 3. Xabarni chiqarish
        await query.edit_message_text(
            text=(
                "🗑 <b>QISMLARNI O'CHIRISH</b>\n\n"
                "O'chirmoqchi bo'lgan qismingiz ustiga bosing. "
                "<i>⚠️ Diqqat: O'chirilgan qismni qayta tiklab bo'lmaydi!</i>"
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML"
        )
        return A_REM_EP_NUM_LIST

    except Exception as e:
        logger.error(f"List episodes for delete error: {e}")
        await query.answer("🛑 Qismlarni yuklashda xatolik yuz berdi.", show_alert=True)
        return A_REM_EP_ANI_LIST


# ====================== ANIME LIST & VIEW ======================

async def list_animes_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adminlar uchun barcha animelar ro'yxatini ko'rish (Pagination bilan)"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # 1. Admin statusini tekshirish (Xavfsizlik)
    status = await get_user_status(user_id)
    if status not in ["admin", "main_admin"]:
        await query.answer("❌ Ruxsat berilmagan!", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    # 2. Sahifa raqamini aniqlash
    # Formatlar: list_ani_pg_0 yoki viewani_0
    data_parts = query.data.split('_')
    try:
        page = int(data_parts[-1])
    except (ValueError, IndexError):
        page = 0

    # 3. Asinxron pagination klaviaturasini yasash
    # Prefix "viewani_" handle_pagination funksiyasi bilan mos kelishi kerak
    kb = await get_pagination_keyboard(
        table_name="anime_list", 
        page=page, 
        prefix="viewani_", 
        extra_callback="back_to_ctrl"
    )

    if not kb:
        await query.edit_message_text(
            "📭 <b>Baza hozircha bo'sh!</b>",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_ctrl")
            ]]),
            parse_mode="HTML"
        )
        return A_ANI_CONTROL

    # 21-BAND: Audit log (Admin ro'yxatni ko'rmoqda)
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                (user_id, f"Anime ro'yxatini ko'zdan kechirdi (Sahifa: {page + 1})")
            )

    # 4. Vizual ko'rinishni yangilash
    text = (
        "📜 <b>ANIME RO'YXATI</b>\n\n"
        "Batafsil ma'lumot olish yoki tahrirlash uchun animeni tanlang:\n"
        f"<i>Hozirgi sahifa: {page + 1}</i>"
    )

    try:
        await query.edit_message_text(
            text=text,
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"List view error: {e}")
        
    return A_LIST_VIEW

# ===================================================================================


async def show_anime_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin uchun animening batafsil ma'lumotlarini ko'rsatish"""
    query = update.callback_query
    # Callback format: viewani_12 (Prefixni hisobga olgan holda)
    ani_id = query.data.split('_')[-1]
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Anime ma'lumotlarini olish
                await cur.execute("SELECT * FROM anime_list WHERE anime_id = %s", (ani_id,))
                ani = await cur.fetchone()
                
                if not ani:
                    await query.answer("❌ Anime bazadan topilmadi!", show_alert=True)
                    return A_LIST_VIEW
                
                # 2. Epizodlar sonini aniqlash
                await cur.execute("SELECT COUNT(*) FROM anime_episodes WHERE anime_id = %s", (ani_id,))
                res_eps = await cur.fetchone()
                eps_count = res_eps[0] if isinstance(res_eps, tuple) else res_eps['COUNT(*)']

        # Ma'lumotlarni cursor turiga qarab ajratish
        # (Anime jadvali tartibi: id, name, poster, lang, genre, year, fandub, desc, views, rat_sum, rat_cnt)
        if isinstance(ani, dict):
            a_id, name, poster, lang, genre, year = ani['anime_id'], ani['name'], ani['poster_id'], ani['lang'], ani['genre'], ani['year']
            views, r_sum, r_cnt = ani['views_week'], ani['rating_sum'], ani['rating_count']
        else:
            a_id, name, poster, lang, genre, year = ani[0], ani[1], ani[2], ani[3], ani[4], ani[5]
            views, r_sum, r_cnt = ani[8], ani[9], ani[10]

        # Reyting hisoblash
        rating = round(r_sum / r_cnt, 1) if r_cnt > 0 else 0.0

        # 3. Chiroyli HTML formatidagi matn (14-band dizayni)
        text = (
            f"🎬 <b>{name}</b>\n\n"
            f"🆔 <b>ID:</b> <code>{a_id}</code>\n"
            f"🌐 <b>Tili:</b> {lang}\n"
            f"🎭 <b>Janri:</b> {genre}\n"
            f"📅 <b>Yili:</b> {year}\n"
            f"📼 <b>Jami qismlar:</b> {eps_count} ta\n"
            f"📈 <b>Haftalik ko'rishlar:</b> {views}\n"
            f"⭐ <b>Reyting:</b> {rating} ({r_cnt} ovoz)\n\n"
            f"<i>💡 Bu ko'rinish faqat adminlar uchun.</i>"
        )

        kb = [[InlineKeyboardButton("⬅️ Ro'yxatga qaytish", callback_data="list_ani_pg_0")]]

        # 4. Rasm bilan chiqarish (Eski xabarni o'chirib, yangisini yuboramiz)
        await query.message.reply_photo(
            photo=poster, 
            caption=text, 
            reply_markup=InlineKeyboardMarkup(kb), 
            parse_mode="HTML"
        )
        await query.message.delete()
        
    except Exception as e:
        logger.error(f"Show anime info error: {e}")
        await query.answer("🛑 Ma'lumotni yuklashda xatolik.", show_alert=True)
        
    return A_LIST_VIEW



# ===================================================================================




# ====================== REMOVE LOGIC ======================
async def delete_anime_exec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin_id = update.effective_user.id
    ani_id = query.data.split('_')[-1]
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 0. Audit uchun anime nomini aniqlab olamiz
                await cur.execute("SELECT name FROM anime_list WHERE anime_id = %s", (ani_id,))
                res = await cur.fetchone()
                ani_name = res[0] if res else f"ID: {ani_id}"

                # 1. Tranzaksiyani boshlash (Biri o'chib, ikkinchisi qolib ketmasligi uchun)
                # 28-BAND: Kaskadli o'chirish (avval epizodlar, keyin anime)
                await cur.execute("DELETE FROM anime_episodes WHERE anime_id = %s", (ani_id,))
                await cur.execute("DELETE FROM anime_list WHERE anime_id = %s", (ani_id,))
                
                # 21-BAND: Admin Audit logiga yozish
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (admin_id, f"Animeni o'chirdi: {ani_name}")
                )
                
                await conn.commit()
                await query.answer(f"✅ {ani_name} butunlay o'chirildi!", show_alert=True)

    except Exception as e:
        logger.error(f"Delete anime error: {e}")
        await query.answer(f"❌ O'chirishda xatolik yuz berdi!", show_alert=True)
    
    # Boshqaruv paneliga qaytish
    return await anime_control_panel(update, context)

# ====================== QISMNI O'CHIRISH UCHUN ANIME TANLASH ======================
async def select_ani_for_new_ep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yangi qism qo'shish uchun anime tanlash listini chiqarish (Pagination bilan)"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # 1. Admin statusini tekshirish
    status = await get_user_status(user_id)
    if status not in ["admin", "main_admin"]:
        if query: await query.answer("❌ Ruxsat yo'q", show_alert=True)
        return ConversationHandler.END

    # 2. Sahifa raqamini aniqlash
    page = 0
    if query and "pg_" in query.data:
        try:
            # Format: pg_addepto_1 -> oxirgi element sahifa raqami
            page = int(query.data.split('_')[-1])
        except (ValueError, IndexError):
            page = 0
            
    # 3. Pagination klaviaturasini yasash
    # Prefix 'addepto_' keyingi select_ani_for_ep_callback uchun kalit vazifasini o'taydi
    kb = await get_pagination_keyboard(
        table_name="anime_list", 
        page=page, 
        prefix="addepto_", 
        extra_callback="add_ani_menu"
    )

    text = (
        "📼 <b>QISM QO'SHISH</b>\n\n"
        "Yangi epizod yuklash uchun quyidagi ro'yxatdan kerakli animeni tanlang:\n"
        f"<i>Sahifa: {page + 1}</i>"
    )

    # 4. Xabarni yuborish yoki tahrirlash
    try:
        if query:
            await query.answer()
            await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
        else:
            await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
            
        # 21-BAND: Audit log
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (user_id, f"Qism qo'shish uchun ro'yxatni ko'rdi (Sahifa: {page+1})")
                )
    except Exception as e:
        logger.error(f"Select anime for ep error: {e}")

    return A_SELECT_ANI_EP







# ====================== AI Qidiruv funksiyasi =====================================

async def search_anime_by_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """AI (Trace.moe) yordamida rasm orqali animeni aniqlash va bazadan topish"""
    message = update.message
    
    if not message.photo:
        await message.reply_text("🖼 Iltimos, anime qidirish uchun rasm yuboring!")
        return

    wait_msg = await message.reply_text("🔍 <b>AI rasmni tahlil qilmoqda...</b>", parse_mode="HTML")

    try:
        # 1. Rasmni Telegram serveridan olish
        photo_file = await message.photo[-1].get_file()
        image_url = photo_file.file_path

        # 2. Trace.moe API-ga asinxron so'rov yuborish
        # Timeout qo'shishni unutmang (AI ba'zan kechikishi mumkin)
        async with httpx.AsyncClient(timeout=10.0) as client:
            api_url = f"https://api.trace.moe/search?url={image_url}"
            response = await client.get(api_url)
            data = response.json()

        if data.get('result'):
            best_match = data['result'][0]
            # AI nomlari odatda fayl nomi bo'ladi, uni tozalaymiz
            anime_name = best_match['filename'].replace('.mp4', '').split(' - ')[0]
            similarity = round(best_match['similarity'] * 100, 2)
            episode = best_match.get('episode', 'Noma\'lum')

            # 3. Bizning bazadan animeni asinxron qidirish
            db_anime = None
            async with db_pool.acquire() as conn:
                async with conn.cursor(dictionary=True) as cur:
                    # AI qaytargan nomning bir qismi bizning nomda bormi?
                    search_query = f"%{anime_name[:12]}%"
                    await cur.execute(
                        "SELECT anime_id, name FROM anime_list WHERE name LIKE %s LIMIT 1", 
                        (search_query,)
                    )
                    db_anime = await cur.fetchone()

            # 4. Matnni shakllantirish
            text = (
                f"✅ <b>AI NATIJASI:</b>\n\n"
                f"🎬 <b>Nomi:</b> <code>{anime_name}</code>\n"
                f"🎞 <b>Taxminiy qism:</b> {episode}\n"
                f"🧬 <b>O'xshashlik:</b> {similarity}%\n\n"
            )

            if db_anime:
                a_id = db_anime['anime_id'] if isinstance(db_anime, dict) else db_anime[0]
                text += "✅ <b>Ushbu anime bazamizda topildi!</b>"
                keyboard = [[InlineKeyboardButton("📺 Ko'rish", callback_data=f"show_ani_{a_id}")]]
                await wait_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
            else:
                text += "😔 <b>Afsuski, bu anime hali bazamizda yo'q.</b>"
                await wait_msg.edit_text(text, parse_mode='HTML')
        else:
            await wait_msg.edit_text("❌ AI hech narsa topa olmadi. Sifatliroq rasm yuboring.")

    except Exception as e:
        logger.error(f"AI Search Error: {e}")
        await wait_msg.edit_text("⚠️ AI tizimi bilan bog'lanishda xatolik yuz berdi.")
# ===================================================================================


async def remove_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O'chirish bo'limining asosiy menyusi"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # 1. Faqat ruxsatnomasi bor adminlar uchun
    status = await get_user_status(user_id)
    if status not in ["admin", "main_admin"]:
        if query: await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return ConversationHandler.END

    # 2. Klaviatura tuzilishi
    kb = [
        [InlineKeyboardButton("❌ Butun animeni o'chirish", callback_data="rem_ani_list_0")],
        [InlineKeyboardButton("🎞 Alohida qismni o'chirish", callback_data="rem_ep_menu")],
        [InlineKeyboardButton("⬅️ Admin Panelga qaytish", callback_data="adm_ani_ctrl")]
    ]
    reply_markup = InlineKeyboardMarkup(kb)
    
    text = (
        "🗑 <b>O'CHIRISH BO'LIMI</b>\n\n"
        "Ehtiyot bo'ling! Ma'lumotlar bazadan o'chirilgach, ularni qayta tiklashning iloji yo'q.\n\n"
        "Tanlang: 👇"
    )

    # 21-BAND: Audit log (Admin o'chirish menyusiga kirdi)
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                (user_id, "O'chirish menyusiga kirdi")
            )

    # 3. Message yoki Callback ekanligiga qarab javob berish
    if query:
        await query.answer()
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
    
    return A_REM_MENU
          
            

# ====================== QO'SHIMCHA FUNKSIYALAR (TUZATILGAN) ======================

async def background_ads_task(bot, admin_id, users, msg_id, from_chat_id):
    """Fonda reklama yuborish va natijalarni real vaqtda yangilash"""
    sent = 0
    failed = 0
    total = len(users)
    
    # Boshlanish xabari
    progress_msg = await bot.send_message(
        admin_id, 
        f"⏳ <b>Reklama kampaniyasi boshlandi...</b>\nJami: <code>{total}</code> ta foydalanuvchi.",
        parse_mode="HTML"
    )

    for user in users:
        # User kortej yoki lug'at ko'rinishida bo'lishi mumkin (cursorga qarab)
        user_id = user['user_id'] if isinstance(user, dict) else user[0]
        
        try:
            # 28-BAND: Har qanday turdagi xabarni formatini buzmasdan nusxalash
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=from_chat_id,
                message_id=msg_id
            )
            sent += 1
            
        except FloodWait as e:
            # Telegram cheklovi bo'lsa, aytilgan vaqtcha kutamiz
            await asyncio.sleep(e.retry_after)
            # Kutishdan so'ng xabarni qayta yuborishga urinish (ixtiyoriy)
            continue 
            
        except Forbidden:
            # Foydalanuvchi botni bloklagan
            failed += 1
            # 28-BAND: Aktiv bo'lmagan foydalanuvchini bazada belgilash mumkin
            
        except TelegramError:
            failed += 1
        
        # Har 30 ta xabarda (Telegram limitiga yaqin) statusni yangilash
        if (sent + failed) % 30 == 0:
            try:
                # Progress bar hisoblash
                percent = round(((sent + failed) / total) * 100)
                await progress_msg.edit_text(
                    f"⏳ <b>Reklama yuborish jarayoni: {percent}%</b>\n\n"
                    f"📊 Jami: <code>{total}</code>\n"
                    f"✅ Yuborildi: <code>{sent}</code>\n"
                    f"❌ Bloklangan: <code>{failed}</code>",
                    parse_mode="HTML"
                )
            except Exception:
                pass # EditMessage limitiga tushmaslik uchun
        
        # Flood limitdan qochish uchun tanaffus
        await asyncio.sleep(0.04) 

    # 21-BAND: Audit log (Reklama tugaganini qayd etish)
    # Bu yerda db_pool orqali bazaga yozish mantiqini qo'shishingiz mumkin

    # Yakuniy hisobot
    await bot.send_message(
        admin_id, 
        f"🏁 <b>Reklama kampaniyasi yakunlandi!</b>\n\n"
        f"✅ Muvaffaqiyatli: <code>{sent}</code>\n"
        f"❌ Muvaffaqiyatsiz: <code>{failed}</code>\n"
        f"📊 Umumiy samaradorlik: <code>{round((sent/total)*100, 1)}%</code>",
        parse_mode="HTML"
    )

# ===================================================================================


async def check_ads_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reklama parolini tekshirish va maqsadli auditoriyani tanlash"""
    user_text = update.message.text
    user_id = update.effective_user.id
    
    # 1. Parol tekshiruvi
    if user_text == ADVERTISING_PASSWORD:
        keyboard = [
            [InlineKeyboardButton("👥 Oddiy foydalanuvchilar", callback_data="send_to_user")],
            [InlineKeyboardButton("💎 Faqat VIP a'zolar", callback_data="send_to_vip")],
            [InlineKeyboardButton("👮 Faqat Adminlar", callback_data="send_to_admin")],
            [InlineKeyboardButton("🌍 Barchaga yuborish", callback_data="send_to_all")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_pass"),
             InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_ads")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # 21-BAND: Audit (Muvaffaqiyatli kirish)
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (user_id, "Reklama paneliga parol orqali kirdi")
                )

        await update.message.reply_text(
            "🔓 <b>Parol tasdiqlandi!</b>\n\n"
            "Reklama kampaniyasi uchun maqsadli auditoriyani tanlang. "
            "<i>Eslatma: 'Barchaga' tanlansa, bloklanganlardan tashqari hamma foydalanuvchilar qamrab olinadi.</i>",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        return A_SELECT_ADS_TARGET
    
    else:
        # 2. Xato parol kiritilganda
        status = await get_user_status(user_id)
        
        # 21-BAND: Audit (Xato urinishni qayd etish - xavfsizlik uchun)
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (user_id, f"Reklama parolini noto'g'ri kiritdi: {user_text[:10]}...")
                )


# ===================================================================================


async def ads_send_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan guruhga reklamani fonda yuborishni boshlash"""
    msg = update.message
    admin_id = update.effective_user.id
    
    # Callback-dan saqlangan maqsadli guruhni olish
    target = context.user_data.get('ads_target', 'all')
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Guruh bo'yicha foydalanuvchilarni filtrlash
                if target == "all":
                    await cur.execute("SELECT user_id FROM users")
                else:
                    await cur.execute("SELECT user_id FROM users WHERE status = %s", (target,))
                
                users = await cur.fetchall()

                # 21-BAND: Audit (Reklama yuborishni kim boshlaganini qayd etish)
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (admin_id, f"Reklama yuborishni boshladi (Target: {target}, Users: {len(users)})")
                )

        if not users:
            await msg.reply_text(f"📭 Tanlangan guruhda (<code>{target}</code>) foydalanuvchilar topilmadi.", parse_mode="HTML")
            return ConversationHandler.END

        # 2. Fon rejimida yuborishni boshlash (Asinxron task yaratish)
        # Bu botning asosiy oqimini band qilmasdan reklamani orqada yuboradi
        asyncio.create_task(background_ads_task(
            bot=context.bot,
            admin_id=admin_id,
            users=users,
            msg_id=msg.message_id,
            from_chat_id=update.effective_chat.id
        ))

        # 3. Adminga muvaffaqiyatli boshlanganlik haqida xabar berish
        status = await get_user_status(admin_id)
        await msg.reply_text(
            f"🚀 <b>Reklama navbatga qo'shildi!</b>\n\n"
            f"🎯 <b>Guruh:</b> <code>{target}</code>\n"
            f"👥 <b>Soni:</b> <code>{len(users)}</code> ta\n\n"
            f"<i>Bot fonda ishlashni boshladi. Jarayon davomida hisobot berib turaman.</i>",
            reply_markup=get_main_kb(status),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Ads finish error: {e}")
        await msg.reply_text("🛑 Xatolik yuz berdi. Reklama yuborilmadi.")
    
    # User_data'ni tozalash
    context.user_data.pop('ads_target', None)
    
    return ConversationHandler.END


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


# ===================================================================================

async def export_all_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha animelar ro'yxatini JSON fayl qilib yuborish (Xotirada shakllantirish)"""
    query = update.callback_query
    msg = update.effective_message
    user_id = update.effective_user.id

    if query:
        await query.answer("📊 Fayl tayyorlanmoqda, kuting...")

    try:
        # 1. Asinxron bazadan ma'lumotlarni olish
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                await cur.execute("SELECT * FROM anime_list")
                animes = await cur.fetchall()

        if not animes:
            await msg.reply_text("📭 Bazada eksport qilish uchun ma'lumot topilmadi.")
            return

        # 21-BAND: Audit (Eksport amalini qayd etish)
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (user_id, f"Baza eksport qilindi ({len(animes)} ta anime)")
                )

        # 2. JSON ma'lumotlarini matn ko'rinishida tayyorlash
        json_data = json.dumps(animes, indent=4, default=str, ensure_ascii=False)
        
        # 3. Faylni diskka yozmasdan, RAM (BytesIO) orqali yuborish
        # Bu server xotirasini tejaydi va diskdagi qoldiq fayllarni kamaytiradi
        file_stream = io.BytesIO(json_data.encode('utf-8'))
        file_stream.name = f"anime_database_backup.json"

        await msg.reply_document(
            document=file_stream,
            caption=(
                f"📂 <b>BAZA EKSPORTI</b>\n\n"
                f"📊 <b>Jami animelar:</b> <code>{len(animes)}</code> ta\n"
                f"📅 <b>Sana:</b> <code>{context.args[0] if context.args else 'Bugun'}</code>\n"
                f"👤 <b>Eksport qildi:</b> Admin (ID: {user_id})"
            ),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Export error: {e}")
        await msg.reply_text(f"❌ Eksport jarayonida texnik xatolik: <code>{e}</code>", parse_mode="HTML")


# ===================================================================================


async def exec_vip_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """VIP qo'shishdan oldin ID-ni tekshirish va tasdiqlash so'rash"""
    text = update.message.text.strip()
    admin_id = update.effective_user.id

    # 1. ID raqam ekanligini tekshirish
    if not text.isdigit():
        await update.message.reply_text("❌ <b>Xato!</b> Foydalanuvchi ID-sini faqat raqamlarda yuboring.", parse_mode="HTML")
        return A_ADD_VIP

    target_id = int(text)

    try:
        # 2. Foydalanuvchi bazada borligini tekshirish
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                await cur.execute("SELECT name, status FROM users WHERE user_id = %s", (target_id,))
                user = await cur.fetchone()

        if not user:
            await update.message.reply_text(
                f"⚠️ <b>Foydalanuvchi topilmadi!</b>\n\nID: <code>{target_id}</code> bazada mavjud emas. "
                f"Foydalanuvchi kamida bir marta botga kirgan bo'lishi shart.",
                parse_mode="HTML"
            )
            return A_ADD_VIP
        
        # 3. Agar foydalanuvchi allaqachon VIP bo'lsa
        user_status = user['status'] if isinstance(user, dict) else user[1]
        if user_status == 'vip':
            await update.message.reply_text("💎 Bu foydalanuvchi allaqachon <b>VIP</b> maqomiga ega!", parse_mode="HTML")
            return ConversationHandler.END

        # 4. Tasdiqlash tugmalari
        keyboard = [
            [InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"conf_vip_{target_id}")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="manage_vip")]
        ]
        
        user_name = user['name'] if isinstance(user, dict) else user[0]
        await update.message.reply_text(
            f"💎 <b>VIP maqomini berishni tasdiqlaysizmi?</b>\n\n"
            f"👤 <b>Foydalanuvchi:</b> {user_name}\n"
            f"🆔 <b>ID:</b> <code>{target_id}</code>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return None # Keyingi qadam callback orqali bo'ladi

    except Exception as e:
        logger.error(f"VIP add check error: {e}")
        await update.message.reply_text("🛑 Texnik xatolik yuz berdi.")
        return ConversationHandler.END

# ===================================================================================

async def add_comment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchidan izoh so'rash (Callback orqali)"""
    query = update.callback_query
    # Format: addcomm_123
    try:
        anime_id = query.data.split("_")[1]
    except IndexError:
        await query.answer("❌ Xatolik!")
        return ConversationHandler.END

    # Sessiyada anime_id ni saqlaymiz
    context.user_data['commenting_anime_id'] = anime_id
    
    await query.answer()
    await query.message.reply_text(
        "📝 <b>Ushbu anime haqida fikringizni yozib qoldiring:</b>\n\n"
        "<i>⚠️ Eslatma: Haqoratli izohlar uchun botdan chetlatilishingiz mumkin.</i>",
        parse_mode="HTML"
    )
    return U_ADD_COMMENT

async def save_comment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Izohni bazaga saqlash va foydalanuvchini rag'batlantirish"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    anime_id = context.user_data.get('commenting_anime_id')

    # 1. Validatsiya (Izoh uzunligi va anime_id mavjudligi)
    if not anime_id or len(text) < 5:
        await update.message.reply_text("❌ <b>Xato:</b> Izoh juda qisqa (kamida 5 ta belgi) yoki vaqt tugagan.")
        return A_MAIN

    # 2. Spam filtr (ixtiyoriy: bir xil izohni takrorlashni oldini olish)
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 3. Izohni saqlash
                await cur.execute(
                    "INSERT INTO comments (user_id, anime_id, comment_text) VALUES (%s, %s, %s)",
                    (user_id, anime_id, text)
                )
                
                # 4. Bonus berish (28-band: Motivatsiya tizimi)
                # Foydalanuvchi statusiga qarab bonusni o'zgartirish ham mumkin
                await cur.execute(
                    "UPDATE users SET bonus = bonus + 2 WHERE user_id = %s", 
                    (user_id,)
                )
                
                await conn.commit()

        # 5. Muvaffaqiyatli xabar
        status = await get_user_status(user_id)
        await update.message.reply_text(
            f"✅ <b>Rahmat!</b> Izohingiz qabul qilindi.\n"
            f"🎁 Faollik uchun sizga <b>2 bonus ball</b> berildi!",
            reply_markup=get_main_kb(status),
            parse_mode="HTML"
        )
        
        # User_data ni tozalaymiz
        context.user_data.pop('commenting_anime_id', None)

    except Exception as e:
        logger.error(f"Comment save error: {e}")
        await update.message.reply_text("⚠️ Texnik xatolik tufayli izoh saqlanmadi.")

    return A_MAIN

# ===================================================================================

async def view_comments_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Animega tegishli oxirgi 10 ta izohni ko'rsatish"""
    query = update.callback_query
    # Callback format: view_comm_123
    try:
        anime_id = query.data.split("_")[-1]
    except IndexError:
        await query.answer("❌ Ma'lumot xatosi!")
        return

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                # SQL JOIN orqali izoh va foydalanuvchi ma'lumotlarini birga olamiz
                # 28-BAND: Izohlarni foydalanuvchi ismi bilan ko'rsatish
                query_sql = """
                    SELECT c.comment_text, c.created_at, u.name, u.user_id 
                    FROM comments c 
                    JOIN users u ON c.user_id = u.user_id 
                    WHERE c.anime_id = %s 
                    ORDER BY c.created_at DESC 
                    LIMIT 10
                """
                await cur.execute(query_sql, (anime_id,))
                comments = await cur.fetchall()

        if not comments:
            await query.answer("💬 Ushbu animega hali izoh qoldirilmagan. Birinchi bo'lib yozing!", show_alert=True)
            return

        # 1. Matnni shakllantirish
        text = "💬 <b>OXIRGI IZOHLAR:</b>\n"
        text += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
        
        for comm in comments:
            # Lug'at yoki Tuple ekanligini hisobga olamiz
            if isinstance(comm, dict):
                u_name = comm['name'] or f"User_{comm['user_id']}"
                u_text = comm['comment_text']
                u_date = comm['created_at'].strftime("%d.%m %H:%M")
            else:
                u_name = comm[2] or f"User_{comm[3]}"
                u_text = comm[0]
                u_date = comm[1].strftime("%d.%m %H:%M")
                
            text += f"👤 <b>{u_name}</b> | 🕒 <i>{u_date}</i>\n"
            text += f"└ <code>{u_text}</code>\n\n"

        # 2. Xabarni yuborish
        # reply_text ishlatamiz, chunki izohlar uzun bo'lib ketsa, asosiy postni buzishi mumkin
        await query.message.reply_text(
            text, 
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Yopish", callback_data="delete_this_msg")
            ]])
        )
        await query.answer()

    except Exception as e:
        logger.error(f"View comments error: {e}")
        await query.answer("🛑 Izohlarni yuklashda xatolik.", show_alert=True)

# ===================================================================================

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

async def save_rating_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ovozni bazaga yozish va umumiy reytingni hisoblash"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data.split("_")
    # Format: rate_set_123_5
    anime_id = data[2]
    stars = int(data[3])

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Anti-spam: Foydalanuvchi oldin ovoz berganmi?
                # Buning uchun 'user_ratings' degan kichik jadval kerak bo'ladi
                await cur.execute(
                    "SELECT id FROM user_ratings WHERE user_id = %s AND anime_id = %s", 
                    (user_id, anime_id)
                )
                if await cur.fetchone():
                    await query.answer("⚠️ Siz ushbu animega allaqachon ovoz bergansiz!", show_alert=True)
                    return

                # 2. Ovozni hisobga olish
                # user_ratings ga yozamiz
                await cur.execute(
                    "INSERT INTO user_ratings (user_id, anime_id, rating) VALUES (%s, %s, %s)",
                    (user_id, anime_id, stars)
                )
                
                # anime_list jadvalini yangilaymiz
                await cur.execute("""
                    UPDATE anime_list 
                    SET rating_sum = rating_sum + %s, rating_count = rating_count + 1 
                    WHERE anime_id = %s
                """, (stars, anime_id))
                
                await conn.commit()

        await query.answer(f"✅ Rahmat! Siz {stars} ball berdingiz.", show_alert=True)
        # 3. UI yangilash
        await query.edit_message_caption(
            caption="✅ <b>Bahoingiz qabul qilindi!</b>\n\nFikringiz uchun rahmat. Endi boshqa animelarni ham ko'rishingiz mumkin.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Asosiy menyu", callback_data="back_to_main")
            ]]),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Rating save error: {e}")
        await query.answer("🛑 Xatolik: Ovozni saqlash imkoni bo'lmadi.")

# ===================================================================================

async def auto_check_notifications(context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchilarni VIP tugashi va bonuslar haqida avtomatik ogohlantirish"""
    now = datetime.datetime.now()
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                
                # --- 1. VIP MUDDATI TUGASHINI TEKSHIRISH (Ertaga tugaydiganlar) ---
                tomorrow = (now + datetime.timedelta(days=1)).date()
                await cur.execute("""
                    SELECT user_id, name FROM users 
                    WHERE status = 'vip' 
                    AND DATE(vip_expire_date) = %s
                """, (tomorrow,))
                vip_users = await cur.fetchall()
                
                for user in vip_users:
                    try:
                        user_id = user['user_id'] if isinstance(user, dict) else user[0]
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=(
                                "⚠️ <b>VIP MUDDATI TUGAMOQDA!</b>\n\n"
                                "Ertaga VIP obunangiz muddati yakunlanadi. 💎\n"
                                "Reklamasiz tomosha va eksklyuziv imkoniyatlarni saqlab qolish uchun obunani yangilashingizni tavsiya qilamiz!"
                            ),
                            parse_mode="HTML"
                        )
                    except (Forbidden, TelegramError):
                        continue # Bot bloklangan bo'lsa o'tib ketamiz

                # --- 2. BONUSLARNI ES LATISH (1000 balldan oshganlar) ---
                # Faqat har 10-chi tekshiruvda (kuniga 1 marta bo'lsa, 10 kunda bir marta)
                if random.randint(1, 10) == 5:
                    await cur.execute("SELECT user_id, bonus FROM users WHERE bonus >= 1000")
                    rich_users = await cur.fetchall()
                    
                    for user in rich_users:
                        try:
                            user_id = user['user_id'] if isinstance(user, dict) else user[0]
                            bonus = user['bonus'] if isinstance(user, dict) else user[1]
                            await context.bot.send_message(
                                chat_id=user_id,
                                text=(
                                    f"🎁 <b>BALLARINGIZNI ALMASHTIRING!</b>\n\n"
                                    f"Sizda <b>{bonus}</b> ball to'planibdi. Ulardan foydalanib "
                                    f"VIP statusini sotib olishingiz yoki boshqa imtiyozlarga ega bo'lishingiz mumkin! 🔄"
                                ),
                                parse_mode="HTML"
                            )
                        except:
                            continue

    except Exception as e:
        logger.error(f"Auto notification error: {e}")

# ===================================================================================

async def show_fandub_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha fandab jamoalari ro'yxatini ko'rsatish (Asinxron)"""
    user_id = update.effective_user.id
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Bazadagi barcha jamoalarni takrorlanmas (DISTINCT) qilib olish
                await cur.execute("SELECT DISTINCT fandub FROM anime_list WHERE fandub IS NOT NULL AND fandub != ''")
                teams = await cur.fetchall()

        if not teams:
            await update.message.reply_text("😔 <b>Hozircha dublaj jamoalari haqida ma'lumot yo'q.</b>", parse_mode="HTML")
            return

        # 2. Tugmalarni shakllantirish
        keyboard = []
        for team in teams:
            team_name = team[0]
            # Callback data uzunligi 64 belgidan oshmasligi kerak. 
            # Jamoa nomi uzun bo'lsa, qisqartirish yoki ID ishlatish tavsiya etiladi.
            safe_name = urllib.parse.quote(team_name[:20]) 
            keyboard.append([InlineKeyboardButton(f"🎙 {team_name}", callback_data=f"fdub_{safe_name}")])
        
        # 28-BAND: Navigatsiya (Orqaga tugmasi)
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_main")])

        # 3. Xabarni yuborish
        await update.message.reply_text(
            "<b>DUBALJ JAMOLARI</b> 🎙\n\n"
            "O'zingizga yoqqan jamoani tanlang, biz ularning barcha ijod namunalarini saralab beramiz: 👇",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Fandub list error: {e}")
        await update.message.reply_text("⚠️ Ma'lumotlarni yuklashda xatolik yuz berdi.")

# ===================================================================================

async def filter_by_fandub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan fandub jamoasiga tegishli animelar ro'yxatini ko'rsatish"""
    query = update.callback_query
    
    # Callback data'dan jamoa nomini xavfsiz ajratib olish va decode qilish
    # Format: fdub_Nomi
    try:
        raw_name = query.data.split("_")[1]
        fandub_name = urllib.parse.unquote(raw_name)
    except Exception:
        await query.answer("❌ Ma'lumotni o'qishda xatolik!")
        return

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                # SQL: Ma'lum bir jamoa animelarini olish
                await cur.execute(
                    "SELECT anime_id, name, rating_sum, rating_count FROM anime_list WHERE fandub = %s", 
                    (fandub_name,)
                )
                animes = await cur.fetchall()

        if not animes:
            await query.answer(f"😔 {fandub_name} jamoasiga tegishli animelar topilmadi.", show_alert=True)
            return

        # 1. Matnni shakllantirish
        text = f"🎙 <b>{fandub_name}</b> jamoasi ijodiga mansub animelar:\n"
        text += f"━━━━━━━━━━━━━━━━━━\n"
        text += f"✅ Jami topildi: <b>{len(animes)}</b> ta\n\n"
        text += "Ko'rish uchun kerakli animeni tanlang: 👇"

        # 2. Tugmalarni shakllantirish
        keyboard = []
        for anime in animes:
            # Reytingni hisoblash (28-band: Vizual reyting)
            r_sum = anime.get('rating_sum', 0)
            r_count = anime.get('rating_count', 1) # 0 ga bo'linmaslik uchun
            stars = round(r_sum / r_count, 1) if r_count > 0 else 0
            
            btn_text = f"🎬 {anime['name']} ({stars} ⭐)"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"show_ani_{anime['anime_id']}")])

        # Orqaga qaytish tugmasi
        keyboard.append([InlineKeyboardButton("🔙 Ro'yxatga qaytish", callback_data="show_fandub_list")])

        # 3. Xabarni yangilash
        await query.edit_message_text(
            text=text, 
            reply_markup=InlineKeyboardMarkup(keyboard), 
            parse_mode="HTML"
        )
        await query.answer()

    except Exception as e:
        logger.error(f"Fandub filter error: {e}")
        await query.answer("🛑 Ma'lumotlarni saralashda xatolik yuz berdi.", show_alert=True)

# ===================================================================================

async def start_profile_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi profilini yaratish jarayonini boshlash"""
    user_id = update.effective_user.id
    
    # 7-BAND: Majburiy obuna tekshiruvi (agar kerak bo'lsa)
    is_subscribed = await check_user_subscription(user_id, context.bot)
    if not is_subscribed:
        # Obuna bo'lmagan bo'lsa, tekshirish funksiyasiga yo'naltiramiz
        return await subscription_alert(update, context)

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                # 1. Profil allaqachon mavjudligini tekshirish
                await cur.execute("SELECT name FROM users WHERE user_id = %s", (user_id,))
                user = await cur.fetchone()
                
                if user and user.get('name'):
                    # Profil bor bo'lsa, qayta yaratishga yo'l qo'ymaymiz (yoki tahrirlashni taklif qilamiz)
                    await update.message.reply_text(
                        f"✨ <b>Sizning profilingiz allaqachon mavjud!</b>\n\n"
                        f"Nikingiz: <code>{user['name']}</code>\n"
                        f"Uni o'zgartirish uchun sozlamalar bo'limiga o'ting.",
                        parse_mode="HTML"
                    )
                    return ConversationHandler.END

        # 2. Sessiyani tozalash
        context.user_data.clear()

        # 3. Profil yaratishga taklif
        await update.message.reply_text(
            "🌟 <b>Anime Muxlislari Hamjamiyatiga xush kelibsiz!</b>\n\n"
            "O'z profilingizni yarating va bot imkoniyatlaridan to'liq foydalaning.\n"
            "<i>(Izohlar qoldirish, reyting berish va bonuslar yig'ish uchun profil kerak)</i>\n\n"
            "✍️ <b>Nikingizni (taxallusingizni) kiriting:</b>",
            parse_mode="HTML"
        )
        return U_CREATE_PROFILE

    except Exception as e:
        logger.error(f"Profile creation start error: {e}")
        await update.message.reply_text("⚠️ Tizimda xatolik yuz berdi, keyinroq urinib ko'ring.")
        return ConversationHandler.END
# ===================================================================================

async def find_random_friend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bazada mavjud ochiq profillar orasidan tasodifiy birini ko'rsatish"""
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                # 1. Tasodifiy profilni tanlash
                # JOIN yordamida status va profil ma'lumotlarini birlashtiramiz
                # 28-BAND: Faqat is_public=1 bo'lgan ochiq profillar chiqadi
                await cur.execute("""
                    SELECT p.nickname, p.favorite_anime, p.about, p.user_id, u.status 
                    FROM user_profiles p 
                    JOIN users u ON p.user_id = u.user_id 
                    WHERE p.user_id != %s AND p.is_public = 1 
                    ORDER BY RAND() LIMIT 1
                """, (user_id,))
                friend = await cur.fetchone()

        if not friend:
            await query.answer("🧐 Hozircha ochiq profillar topilmadi. Keyinroq urinib ko'ring!", show_alert=True)
            return

        # 2. Ma'lumotlarni chiroyli formatlash
        # Statusga qarab maxsus emojilar qo'shamiz
        status_emoji = "💎" if friend['status'] == 'vip' else "👤"
        
        # 1. Oldindan tayyorlab olamiz
        fav_anime = friend['favorite_anime'] or 'Sirligicha qolgan'
        about_text = friend['about'] or "Ma'lumot berilmagan"
        status_cap = friend['status'].capitalize()

        # 2. Keyin f-string ichiga qo'yamiz
        text = (
            f"🌟 <b>ANIME MUXLISI PROFILI</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🏷 <b>Nik:</b> {friend['nickname']}\n"
            f"{status_emoji} <b>Maqomi:</b> {status_cap}\n"
            f"❤️ <b>Sevimli animesi:</b> <i>{fav_anime}</i>\n"
            f"📝 <b>Fikri:</b> <code>{about_text}</code>\n"
        )

        # 3. Tugmalar
        keyboard = [
            [InlineKeyboardButton("💌 Xabar yuborish", callback_data=f"send_msg_{friend['user_id']}")],
            [InlineKeyboardButton("🎲 Boshqasini ko'rish", callback_data="find_friend_rand")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_main")]
        ]
        
        # 4. Xabarni yangilash yoki yangi yuborish
        # reply_text orqali yuborish yaxshiroq, chunki har gal tasodifiy rasm yoki boshqa format bo'lishi mumkin
        await query.message.reply_text(
            text=text, 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        await query.answer()

    except Exception as e:
        logger.error(f"Find friend error: {e}")
        await query.answer("🛑 Ma'lumot topishda xatolik yuz berdi.", show_alert=True)

# ===================================================================================

async def send_message_to_friend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Boshqa muxlisga bot orqali xabar yuborish"""
    query = update.callback_query
    target_id = query.data.split("_")[2]
    
    context.user_data['msg_target_id'] = target_id
    await query.message.reply_text("Xabaringizni yozing, men uni egasiga yetkazaman:")
    return U_CHAT_MESSAGE

async def deliver_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xabarni manzilga yetkazish"""
    sender_id = update.effective_user.id
    target_id = context.user_data.get('msg_target_id')
    text = update.message.text

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"📩 **Yangi xabar!**\n\nMuxlisdan sizga xabar keldi:\n\n\"{text}\"\n\n"
                 f"Javob berish uchun profiliga o'ting.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("👤 Profilini ko'rish", callback_data=f"view_prof_{sender_id}")
            ]])
        )
        await update.message.reply_text("✅ Xabar yetkazildi!")
    except:
        await update.message.reply_text("❌ Xabarni yetkazib bo'lmadi (foydalanuvchi botni bloklagan bo'lishi mumkin).")
    
    return A_MAIN
# ===================================================================================

async def add_auto_ad_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin reklama yuboradi va u ma'lum vaqtdan so'ng avtomatik o'chadi"""
    ad_msg = update.message
    admin_id = update.effective_user.id
    
    # 1. Muddatni aniqlash (Default: 24 soat yoki admin kiritgan raqam)
    # Masalan: /add_ad 12 (12 soat uchun)
    try:
        if context.args:
            duration_hours = int(context.args[0])
        else:
            duration_hours = 24
    except ValueError:
        await ad_msg.reply_text("❌ Xato! Soatni raqamda kiriting. Masalan: <code>/add_ad 12</code>", parse_mode="HTML")
        return

    expire_time = datetime.datetime.now() + datetime.timedelta(hours=duration_hours)
    target_chat_id = "@sizning_kanalingiz" # Asosiy kanal yoki guruh ID-si

    try:
        # 2. Reklamani nusxalash (copy)
        sent_msg = await ad_msg.copy(chat_id=target_chat_id)

        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 3. Bazaga saqlash
                await cur.execute(
                    "INSERT INTO auto_ads (post_id, chat_id, expire_at) VALUES (%s, %s, %s)",
                    (sent_msg.message_id, str(target_chat_id), expire_time)
                )
                
                # 21-BAND: Audit log (Kim reklama qo'ydi?)
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (admin_id, f"Kanalga vaqtinchalik reklama qo'shdi ({duration_hours} soat)")
                )
                await conn.commit()

        await ad_msg.reply_text(
            f"✅ <b>Reklama muvaffaqiyatli joylandi!</b>\n\n"
            f"📍 <b>Joy:</b> <code>{target_chat_id}</code>\n"
            f"⏳ <b>Muddat:</b> <code>{duration_hours}</code> soat\n"
            f"🗑 <b>O'chish vaqti:</b> <code>{expire_time.strftime('%Y-%m-%d %H:%M')}</code>",
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Auto ad error: {e}")
        await ad_msg.reply_text("🛑 Reklamani joylashda xatolik yuz berdi.")

# ===================================================================================

async def delete_expired_ads(context: ContextTypes.DEFAULT_TYPE):
    """Muddati tugagan reklamalarni avtomatik o'chirish (JobQueue uchun)"""
    now = datetime.datetime.now()
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                # 1. Faol va muddati o'tgan reklamalarni saralash
                await cur.execute(
                    "SELECT * FROM auto_ads WHERE expire_at <= %s AND status = 'active'", 
                    (now,)
                )
                expired_ads = await cur.fetchall()

                if not expired_ads:
                    return

                for ad in expired_ads:
                    try:
                        # 2. Telegram'dan o'chirishga urinish
                        await context.bot.delete_message(
                            chat_id=ad['chat_id'], 
                            message_id=ad['post_id']
                        )
                        new_status = 'deleted'
                    
                    except BadRequest as e:
                        # Agar xabar allaqachon qo'lda o'chirilgan bo'lsa
                        logger.warning(f"Ad already gone: {e}")
                        new_status = 'manually_removed'
                    
                    except TelegramError as e:
                        logger.error(f"Telegram API error: {e}")
                        new_status = 'error'

                    # 3. Bazadagi statusni yangilash
                    await cur.execute(
                        "UPDATE auto_ads SET status = %s, deleted_at = %s WHERE id = %s",
                        (new_status, now, ad['id'])
                    )
                
                # Barcha o'zgarishlarni bitta tranzaksiyada saqlash
                await conn.commit()

    except Exception as e:
        logger.error(f"Cleanup job crash: {e}")

# ===================================================================================

async def show_redeem_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ballarni xizmatlarga ayirboshlash menyusi"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    try:
        # 1. Asinxron bazadan joriy ballarni olish
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                await cur.execute("SELECT bonus FROM users WHERE user_id = %s", (user_id,))
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

# ===================================================================================

async def process_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ballarni xizmatlarga haqiqiy ayirboshlash jarayoni"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data.split("_")
    
    # Ma'lumotlarni olish: redeem_vip_1 -> type='vip', value=1
    item_type = data[1]
    value = int(data[2])
    
    # Narxlar jadvali (Buni global o'zgaruvchi qilish ham mumkin)
    prices = {
        'ad_1': 250, 'ad_3': 500,
        'vip_1': 1000, 'vip_3': 2500
    }
    key = f"{item_type}_{value}"
    cost = prices.get(key, 999999)

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                # 1. Joriy ballarni tekshirish (SELECT)
                await cur.execute("SELECT bonus, name FROM users WHERE user_id = %s", (user_id,))
                user = await cur.fetchone()

                if not user or user['bonus'] < cost:
                    needed = cost - (user['bonus'] if user else 0)
                    await query.answer(f"❌ Ballar yetarli emas! Yana {needed} ball to'plashingiz kerak.", show_alert=True)
                    return

                # --- TRANZAKSIYA BOSHLANDI ---
                # 2. Ballarni ayirish
                await cur.execute("UPDATE users SET bonus = bonus - %s WHERE user_id = %s", (cost, user_id))
                
                if item_type == 'vip':
                    # VIP muddatini hisoblash va yangilash
                    # Avvalgi darslarda yozgan add_vip_logic funksiyamizni chaqiramiz
                    new_expire = await add_vip_logic(user_id, value) 
                    
                    msg_text = (
                        f"🎉 <b>Tabriklaymiz!</b>\n\n"
                        f"💎 <code>{value}</code> oylik VIP maqomi faollashtirildi.\n"
                        f"📅 Tugash muddati: <b>{new_expire.strftime('%d.%m.%Y')}</b>\n\n"
                        f"<i>Imkoniyatlardan bahramand bo'ling!</i>"
                    )
                
                elif item_type == 'ad':
                    # Reklama uchun adminni ogohlantirish (21-band: Audit)
                    admin_id = os.getenv("ADMIN_ID")
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=(
                            f"🔔 <b>YANGI REKLAMA BUYURTMASI (BALLI)</b>\n\n"
                            f"👤 <b>Foydalanuvchi:</b> {user['name']} (ID: {user_id})\n"
                            f"📊 <b>Tur:</b> {value} kunlik reklama\n"
                            f"💰 <b>Sarflangan:</b> {cost} ball"
                        ),
                        parse_mode="HTML"
                    )
                    msg_text = (
                        f"✅ <b>Ballar muvaffaqiyatli yechildi!</b>\n\n"
                        f"📢 <code>{value}</code> kunlik reklama buyurtmangiz qabul qilindi.\n"
                        f"Aloqa uchun: @admin_username"
                    )

                # 3. Tranzaksiyani yakunlash
                await conn.commit()
                # --- TRANZAKSIYA YAKUNLANDI ---

        await query.message.reply_text(msg_text, parse_mode="HTML")
        await query.answer("Muvaffaqiyatli bajarildi!")

    except Exception as e:
        logger.error(f"Redeem process error: {e}")
        await query.answer("🛑 Tranzaksiyada xatolik yuz berdi. Ballaringiz qaytarildi.", show_alert=True)

# ===================================================================================

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

# ===================================================================================

async def process_donation_reward(user_id: int, amount: int, context: ContextTypes.DEFAULT_TYPE):
    """Donat miqdoriga qarab sovg'alarni asinxron va xavfsiz taqdim etish"""
    
    msg = "🎉 <b>Rahmat! Sizning donatingiz muvaffaqiyatli qabul qilindi.</b>\n\n🎁 <b>Sizning sovg'alaringiz:</b>\n"
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Tranzaksiya ichida har bir amalni bajarish
                if amount == 5000:
                    await cur.execute("UPDATE users SET bonus = bonus + 500 WHERE user_id = %s", (user_id,))
                    msg += "✅ 500 bonus ball hisobingizga qo'shildi!"
                
                elif amount == 20000:
                    # VIP muddatini 1 oyga uzaytirish (asinxron logic)
                    await add_vip_logic(user_id, 1) 
                    await cur.execute("UPDATE users SET bonus = bonus + 1000 WHERE user_id = %s", (user_id,))
                    msg += "💎 1 oylik VIP maqomi faollashdi!\n✅ 1000 bonus ball qo'shildi!"
                    
                elif amount >= 100000:
                    # Lifetime VIP va Maxsus 'Homiy' statusi
                    await cur.execute(
                        "UPDATE users SET status = 'homiy', bonus = bonus + 10000 WHERE user_id = %s", 
                        (user_id,)
                    )
                    msg += "👑 Sizga <b>'Homiy'</b> maqomi berildi!\n💎 Cheksiz VIP imkoniyati yaratildi!\n✅ 10 000 bonus ball qo'shildi!"

                # 2. To'lov tarixini yozish (Audit)
                await cur.execute(
                    "INSERT INTO donation_logs (user_id, amount, date) VALUES (%s, %s, %s)",
                    (user_id, amount, datetime.datetime.now())
                )
                
                # 3. Hamma amallar muvaffaqiyatli bo'lsa, bazani saqlash
                await conn.commit()

        # Foydalanuvchini tabriklash
        await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="HTML")
        
        # 4. Adminni xabardor qilish
        await context.bot.send_message(
            chat_id=os.getenv("ADMIN_ID"),
            text=f"💰 <b>Yangi Donat!</b>\n👤 Foydalanuvchi: <code>{user_id}</code>\n💵 Miqdor: <code>{amount}</code> so'm",
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Donation reward error: {e}")
        # Xato bo'lsa, xabar yuborish (bazada commit bo'lmagani uchun ballar qo'shilmaydi)
        await context.bot.send_message(
            chat_id=user_id, 
            text="⚠️ Sovg'alarni taqdim etishda xatolik yuz berdi. Iltimos, adminga murojaat qiling."
        )

# ===================================================================================

# Telegram Stars (Invoice) yuborish namunasi
async def send_donation_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchiga Telegram Stars orqali to'lov hisobini yuborish"""
    query = update.callback_query
    user_id = query.from_user.id
    
    # Callback'dan miqdorni olamiz (masalan: don_5000 -> 5000)
    try:
        amount_uzs = int(query.data.split("_")[1])
    except (IndexError, ValueError):
        await query.answer("❌ Miqdorni aniqlashda xatolik!")
        return

    # Telegram Stars (XTR) kursini belgilash 
    # Eslatma: 1 Star taxminan 250-300 so'm atrofida (Telegram belgilagan kurs bo'yicha)
    star_count = amount_uzs // 300 
    
    # Agar hisob-kitob 1 dan kam bo'lsa, kamida 1 Star qilamiz
    star_count = max(star_count, 1)

    await query.answer() # Tugma yuklanishini to'xtatish

    try:
        # Invoys yuborish
        await context.bot.send_invoice(
            chat_id=user_id,
            title="💎 Botni qo'llab-quvvatlash",
            description=(
                f"Siz tanlagan paket: {amount_uzs} so'm.\n"
                f"Bu taxminan {star_count} Telegram Stars bo'ladi.\n\n"
                "Rahmat! Sizning yordamingiz biz uchun juda muhim."
            ),
            payload=f"donate_{amount_uzs}_{user_id}", # To'lovni tekshirish uchun ma'lumot
            provider_token="", # Stars uchun har doim bo'sh qoladi
            currency="XTR",
            prices=[LabeledPrice(label="Donat (XTR)", amount=star_count)],
            photo_url="https://telegram.org/img/t_logo.png", # Ixtiyoriy rasm
            need_name=False,
            need_phone_number=False,
            need_email=False,
            is_flexible=False
        )
    except Exception as e:
        logger.error(f"Invoice send error: {e}")
        await query.message.reply_text("🛑 To'lov tizimini ishga tushirishda xatolik. Keyinroq urinib ko'ring.")

# ===================================================================================

async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Murojaat turini tanlash (Conversation boshlanishi)"""
    # 7-BAND: Obunani tekshirish (faqat a'zolar murojaat qila olishi uchun)
    user_id = update.effective_user.id
    
    keyboard = [
        [
            InlineKeyboardButton("⚠️ Shikoyat", callback_data="subj_shikoyat"),
            InlineKeyboardButton("💡 Taklif", callback_data="subj_taklif")
        ],
        [InlineKeyboardButton("❓ Savol", callback_data="subj_savol")],
        [InlineKeyboardButton("🔙 Bekor qilish", callback_data="cancel_feedback")]
    ]
    
    await update.message.reply_text(
        "<b>Murojaat turini tanlang:</b>\n\n"
        "Adminlarimiz sizning fikringizni diqqat bilan o'rganib chiqishadi. "
        "Iltimos, xabaringizni bitta xabarda batafsil yozing.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return U_FEEDBACK_SUBJ

async def feedback_subject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mavzuni eslab qolish va matnli xabarni kutish holatiga o'tish"""
    query = update.callback_query
    # Callback format: subj_taklif
    subject = query.data.split("_")[1]
    
    # Sessiyada mavzuni saqlaymiz
    context.user_data['fb_subject'] = subject
    
    # Mavzularga qarab turli emojilar
    emojis = {"shikoyat": "⚠️", "taklif": "💡", "savol": "❓"}
    current_emoji = emojis.get(subject, "📝")

    await query.answer()
    await query.edit_message_text(
        f"{current_emoji} <b>Tanlangan yo'nalish:</b> {subject.capitalize()}\n\n"
        f"Endi murojaatingiz matnini yozib yuboring. Matn 10 ta belgidan kam bo'lmasligi kerak:",
        parse_mode="HTML"
    )
    return U_FEEDBACK_MSG

# ===================================================================================

async def feedback_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Murojaatni qabul qilish, bazaga yozish va adminga tugma bilan yuborish"""
    user = update.effective_user
    text = update.message.text.strip()
    subject = context.user_data.get('fb_subject', 'Umumiy')
    admin_chat_id = os.getenv("ADMIN_ID") # Admin yoki Maxsus Gruppa ID si

    # 1. Validatsiya: Juda qisqa xabarlarni rad etamiz
    if len(text) < 10:
        await update.message.reply_text(
            "❌ <b>Xabar juda qisqa!</b>\n"
            "Murojaatingiz tushunarli bo'lishi uchun kamida 10 ta belgi yozing.",
            parse_mode="HTML"
        )
        return U_FEEDBACK_MSG

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 2. Bazaga saqlash
                await cur.execute(
                    "INSERT INTO feedback (user_id, subject, message, created_at) VALUES (%s, %s, %s, %s)",
                    (user.id, subject, text, datetime.datetime.now())
                )
                await conn.commit()

        # 3. Admin uchun chiroyli formatlangan xabar
        admin_text = (
            f"📩 <b>YANGI MUROJAAT</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Kimdan:</b> {user.mention_html()}\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
            f"📌 <b>Mavzu:</b> #{subject.upper()}\n"
            f"📝 <b>Xabar:</b> <code>{text}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <i>Vaqti: {datetime.datetime.now().strftime('%H:%M | %d.%m')}</i>"
        )
        
        # 4. Adminga javob berish tugmasini qo'shish
        # Bu tugma admin bosganida foydalanuvchi ID sini avtomatik reply sifatida oladi
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✍️ Javob berish", callback_data=f"reply_to_{user.id}")]
        ])

        await context.bot.send_message(
            chat_id=admin_chat_id, 
            text=admin_text, 
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        # 5. Foydalanuvchiga tasdiqlash
        await update.message.reply_text(
            "✅ <b>Xabaringiz muvaffaqiyatli yuborildi!</b>\n\n"
            "Adminlarimiz tez orada siz bilan bog'lanishadi yoki "
            "bot orqali javob yuborishadi. Rahmat!",
            parse_mode="HTML"
        )
        
        # Sessiyani tozalash
        context.user_data.pop('fb_subject', None)
        return A_MAIN

    except Exception as e:
        logger.error(f"Feedback send error: {e}")
        await update.message.reply_text("⚠️ Xatolik yuz berdi. Keyinroq urinib ko'ring.")
        return ConversationHandler.END

# ===================================================================================
async def admin_stats_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Jami foydalanuvchilar
                await cur.execute("SELECT COUNT(*) as total FROM users")
                u_count = await cur.fetchone()

                # 2. Jami animelar
                await cur.execute("SELECT COUNT(*) as total FROM anime_list")
                a_count = await cur.fetchone()

                # 3. Jami qismlar (epizodlar)
                await cur.execute("SELECT COUNT(*) as total FROM anime_episodes")
                e_count = await cur.fetchone()

                # 4. Majburiy kanallar soni
                await cur.execute("SELECT COUNT(*) as total FROM channels")
                c_count = await cur.fetchone()

        stats_text = (
            "📊 <b>Botning umumiy statistikasi:</b>\n\n"
            f"👥 Foydalanuvchilar: <b>{u_count['total']} ta</b>\n"
            f"🎬 Animelar: <b>{a_count['total']} ta</b>\n"
            f"🎞 Yuklangan qismlar: <b>{e_count['total']} ta</b>\n"
            f"📢 Majburiy kanallar: <b>{c_count['total']} ta</b>\n\n"
            f"🕒 Yangilangan vaqt: <i>{datetime.datetime.now().strftime('%H:%M:%S')}</i>"
        )

        keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_main")]]
        
        await query.edit_message_text(
            text=stats_text, 
            reply_markup=InlineKeyboardMarkup(keyboard), 
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Statistika olishda xato: {e}")
        await query.message.reply_text("❌ Statistikani yuklashda xatolik yuz berdi.")

# ===================================================================================

async def show_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT a.id, a.name 
        FROM anime_list a 
        JOIN favorites f ON a.anime_id = f.anime_id 
        WHERE f.user_id = %s
    """, (user_id,))
    favs = cur.fetchall()
    cur.close(); conn.close()

    if not favs:
        await update.message.reply_text("❤️ Sevimlilar ro'yxatingiz hozircha bo'sh.")
        return

    text = "❤️ **Sizning sevimlilaringiz:**\n\n"
    keyboard = []
    for anime in favs:
        keyboard.append([InlineKeyboardButton(f"🎬 {anime['name']}", callback_data=f"show_anime_{anime['id']}")])
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ===================================================================================

async def add_favorite_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anime'ni sevimlilarga qo'shish yoki olib tashlash (Toggle)"""
    query = update.callback_query
    user_id = query.from_user.id
    # Callback format: fav_123
    try:
        anime_id = query.data.split("_")[-1]
    except IndexError:
        await query.answer("❌ Ma'lumot xatosi!")
        return

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Avval mavjudligini tekshiramiz
                await cur.execute(
                    "SELECT id FROM favorites WHERE user_id = %s AND anime_id = %s", 
                    (user_id, anime_id)
                )
                is_fav = await cur.fetchone()

                if is_fav:
                    # 2. Mavjud bo'lsa - O'chiramiz
                    await cur.execute(
                        "DELETE FROM favorites WHERE user_id = %s AND anime_id = %s", 
                        (user_id, anime_id)
                    )
                    msg = "💔 Sevimlilardan olib tashlandi."
                else:
                    # 3. Mavjud bo'lmasa - Qo'shamiz
                    await cur.execute(
                        "INSERT INTO favorites (user_id, anime_id) VALUES (%s, %s)",
                        (user_id, anime_id)
                    )
                    msg = "❤️ Sevimlilarga qo'shildi!"
                
                await conn.commit()

        # 4. Foydalanuvchiga javob berish
        # show_alert=False qilsak, tepada kichik xabarcha chiqadi (Toast)
        await query.answer(msg)
        
        # Tugma rangini yoki matnini yangilash uchun xabarni qayta tahrirlash mumkin
        # Masalan, ❤️ belgisi o'rniga 🤍 qo'yish uchun

    except Exception as e:
        logger.error(f"Favorite toggle error: {e}")
        await query.answer("🛑 Bazaga ulanishda xatolik.", show_alert=True)

# ===================================================================================

async def show_user_cabinet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi shaxsiy kabinetini ko'rsatish"""
    user_id = update.effective_user.id
    query = update.callback_query
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                # 1. Foydalanuvchi asosiy ma'lumotlari
                await cur.execute("""
                    SELECT points, status, health_mode, joined_at 
                    FROM users WHERE user_id = %s
                """, (user_id,))
                user = await cur.fetchone()
                
                if not user:
                    await (query.answer("❌ Profil topilmadi", show_alert=True) if query else update.message.reply_text("❌ Profil topilmadi."))
                    return

                # 2. Tarixiy ma'lumotlarni hisoblash
                await cur.execute("SELECT COUNT(*) as total FROM history WHERE user_id = %s", (user_id,))
                hist_res = await cur.fetchone()
                history_count = hist_res['total']

        # 3. Vizual formatlash
        status_icon = "💎 <b>VIP</b>" if user['status'] == 'vip' else "👤 <b>Oddiy foydalanuvchi</b>"
        health_status = "✅ <b>Yoqilgan</b>" if user['health_mode'] == 1 else "❌ <b>O'chirilgan</b>"
        
        text = (
            f"<b>🏠 SHAXSIY KABINET</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🆔 <b>Sizning ID:</b> <code>{user_id}</code>\n"
            f"🌟 <b>Status:</b> {status_icon}\n"
            f"💰 <b>Ballaringiz:</b> <code>{user['points']}</code> ball\n"
            f"🎬 <b>Ko'rilgan animelar:</b> <b>{history_count}</b> ta\n"
            f"🌙 <b>Sog'liq rejimi:</b> {health_status}\n"
            f"📅 <b>Ro'yxatdan o'tgan:</b> <code>{user['joined_at'].strftime('%d.%m.%Y')}</code>\n\n"
            f"────────────────────\n"
            f"💡 <i>Sog'liq rejimi tunda botdan ko'p foydalansangiz, dam olishni eslatib turish uchun kerak.</i>"
        )

        # 4. Klaviatura
        kb = [
            [InlineKeyboardButton("🔄 Sog'liq rejimini o'zgartirish", callback_data="toggle_health")],
            [InlineKeyboardButton("🎁 Ballarni almashtirish", callback_data="redeem_menu")],
            [InlineKeyboardButton("🔙 Asosiy menyu", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(kb)

        # 5. Xabarni yuborish yoki tahrirlash
        if query:
            await query.answer()
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Cabinet error: {e}")
        error_msg = "🛑 Kabinetni yuklashda xatolik yuz berdi."
        if query: await query.answer(error_msg, show_alert=True)
        else: await update.message.reply_text(error_msg)

# ===================================================================================

async def toggle_health_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sog'liq rejimini yoqish yoki o'chirish (Asinxron)"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Atomar yangilash: 1 - 0 = 1 yoki 1 - 1 = 0
                # Bu usul SELECT so'rovini tejaydi va bazaga yuklamani kamaytiradi
                await cur.execute(
                    "UPDATE users SET health_mode = 1 - health_mode WHERE user_id = %s", 
                    (user_id,)
                )
                await conn.commit()

        # 2. Foydalanuvchiga bildirishnoma (Toast) yuborish
        await query.answer("✅ Sozlama muvaffaqiyatli yangilandi!")
        
        # 3. Kabinetni qayta yangilab ko'rsatish
        # Bu foydalanuvchiga o'zgarishni darhol ko'rish imkonini beradi
        return await show_user_cabinet(update, context)

    except Exception as e:
        logger.error(f"Health toggle error: {e}")
        await query.answer("🛑 Sozlamani o'zgartirishda xatolik yuz berdi.", show_alert=True)


# ===================================================================================

async def reset_init_db_pool():
    global db_pool
    if db_pool is None:
        await init_db_pool()
    
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            # Foreign key tekshiruvini vaqtincha o'chirish (o'chirishda xato bermasligi uchun)
            await cur.execute("SET FOREIGN_KEY_CHECKS = 0;")
            
            # O'chirilishi kerak bo'lgan barcha jadvallar ro'yxati
            tables = [
                'user_preferences', 'admin_logs', 'channels', 'donations', 
                'feedback', 'advertisements', 'comments', 'history', 
                'favorites', 'anime_episodes', 'anime_list', 'users'
            ]
            
            for table in tables:
                await cur.execute(f"DROP TABLE IF EXISTS {table};")
            
            await cur.execute("SET FOREIGN_KEY_CHECKS = 1;")
            
    # Jadvallarni qaytadan noldan yaratish uchun eski funksiyani chaqiramiz
    await init_db_pool()

# ===================================================================================


async def reset_db_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # 1. 🔐 MAX HIMOYA: Admin tekshiruvi
    if user.id != MAIN_ADMIN_ID:
        await update.message.reply_text("⛔ Bu buyruq faqat asosiy admin uchun!")
        return

    # 2. 🔐 Shaxsiy chat tekshiruvi
    if update.effective_chat.type != "private":
        await update.message.reply_text("❗ Xavfsizlik yuzasidan bu buyruq faqat shaxsiy chatda ishlaydi.")
        return

    # 3. ⚠️ Ogohlantirish xabari
    status_msg = await update.message.reply_text("⚠️ MYSQL TO‘LIQ TOZALANMOQDA... Iltimos kuting.")

    try:
        # 4. 🔥 Bazani tozalash va qayta yaratish
        await reset_init_db_pool()

        # 5. ✅ Muvaffaqiyatli yakun
        await status_msg.edit_text(
            "🔥 **MYSQL TOZALANDI VA QAYTA YARATILDI**\n\n"
            "🛑 Bot hozir o‘chadi (Restart kerak).\n"
            "➡️ Endi `/reset` handlerni kodingizdan olib tashlang."
        )

        logging.critical(f"DB RESET: Admin {user.id} tomonidan ma'lumotlar bazasi tozalandi!")

        # 6. 🛑 BOTNI O‘LDIRISH
        # Systemd yoki Docker ishlatayotgan bo'lsangiz, bot avtomatik restart bo'ladi
        os._exit(0)

    except Exception as e:
        logging.exception("RESET ERROR")
        await update.message.reply_text(f"❌ XATO YUZ BERDI:\n`{e}`", parse_mode="Markdown")
        
# ====================== MAIN FUNKSIYA (TUZATILDI) =======================



async def main():
    # 1. Serverni uyg'oq saqlash (Keep-alive mantiqi)
    # Eslatma: keep_alive() funksiyasi yuqorida aniqlangan bo'lishi kerak
    try:
        keep_alive() 
    except NameError:
        logger.warning("keep_alive funksiyasi topilmadi, davom etamiz...")

    # 2. Ma'lumotlar bazasini ishga tushirish
    try:
        await init_db_pool() 
        if db_pool is None:
            logger.error("🛑 Baza ulanmadi (pool is None)!")
            return
        logger.info("✅ Ma'lumotlar bazasi asinxron ulandi.")
    except Exception as e:
        logger.error(f"🛑 Baza ulanishida xato: {e}")
        return

    # 3. Applicationni qurish
    # drop_pending_updates=True bot o'chib yonganda to'planib qolgan eski xabarlarni o'chirib yuboradi
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # 4. Menyu filtri (Regex)
    menu_filter = filters.Regex(
        r"^(Anime qidirish|VIP PASS|Bonus ballarim|Qo'llanma|Barcha anime ro'yxati|ADMIN PANEL|Bekor qilish|"
        r"🎙 Fandablar|❤️ Sevimlilar|🤝 Do'st orttirish|Rasm orqali qidirish)$"
    )
    
    # 5. Conversation Handler
    conv_handler = ConversationHandler(
        entry_points=[
            # Start buyrug'ini eng birinchi entry_point qilib qo'yamiz
            CommandHandler("start", start),
            MessageHandler(filters.Regex(r"Anime qidirish"), search_menu_cmd),
            MessageHandler(filters.Regex(r"ADMIN PANEL"), admin_panel_text_handler),
            MessageHandler(filters.Regex(r"🤝 Do'st orttirish"), start_profile_creation),
            CallbackQueryHandler(add_comment_callback, pattern="^comment_"),
        ],
        states={
            A_MAIN: [
                CallbackQueryHandler(admin_channels_menu, pattern="^adm_ch$"),
                CallbackQueryHandler(admin_ch_callback_handler, pattern="^(add_ch_start|rem_ch_start)$"),
                CallbackQueryHandler(anime_control_panel, pattern="^adm_ani_ctrl$"),
                CallbackQueryHandler(admin_stats_logic, pattern="^adm_stats$"),
                CallbackQueryHandler(check_ads_pass, pattern="^adm_ads_start$"),
                CallbackQueryHandler(export_all_anime, pattern="^adm_export$"),
                MessageHandler(filters.Regex("Anime boshqaruvi"), anime_control_panel),
                CallbackQueryHandler(search_anime_logic, pattern="^search_type_"),
                CallbackQueryHandler(handle_callback),
            ],
            A_ANI_CONTROL: [
                MessageHandler(filters.Regex("Anime List"), list_animes_view),
                MessageHandler(filters.Regex("Yangi anime"), add_anime_panel),
                MessageHandler(filters.Regex("Anime o'chirish"), remove_menu_handler),
                MessageHandler(filters.Regex("Yangi qism qo'shish"), select_ani_for_new_ep),
                MessageHandler(filters.Regex("Orqaga"), admin_panel_text_handler),
                CallbackQueryHandler(handle_callback),
            ],
            A_GET_POSTER: [
                MessageHandler(filters.PHOTO, get_poster_handler), 
                CallbackQueryHandler(handle_callback)
            ],
            A_GET_DATA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_filter, save_ani_handler), 
                CallbackQueryHandler(handle_callback)
            ],
            A_ADD_EP_FILES: [
                MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_ep_uploads),
                CallbackQueryHandler(handle_callback)
            ],
            A_ADD_CH: [MessageHandler(filters.TEXT & ~filters.COMMAND, exec_add_channel)],
            A_REM_CH: [MessageHandler(filters.TEXT & ~filters.COMMAND, exec_rem_channel)],
            A_SEND_ADS_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_ads_pass)],
            A_SEND_ADS_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, ads_send_finish)],
            U_ADD_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_comment_handler)],
            U_FEEDBACK_SUBJ: [CallbackQueryHandler(feedback_subject_callback, pattern="^subj_")],
            U_FEEDBACK_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_message_handler)],
            A_SEARCH_BY_ID: [
                CallbackQueryHandler(show_selected_anime, pattern="^show_anime_"), 
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_filter, search_anime_logic),
                CallbackQueryHandler(handle_callback)
            ],
            A_SEARCH_BY_NAME: [
                CallbackQueryHandler(show_selected_anime, pattern="^show_anime_"), 
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_filter, search_anime_logic),
                CallbackQueryHandler(handle_callback)
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^Bekor qilish$"), start),
            CallbackQueryHandler(start, pattern="^cancel_search$")
        ],
        allow_reentry=True,
        name="aninow_v103_persistent"
    )

    # 6. TAYMERNI (SCHEDULER) SOZLASH
    scheduler = AsyncIOScheduler()
    scheduler.add_job(auto_check_notifications, 'cron', hour=10, minute=0, args=[application])
    scheduler.add_job(delete_expired_ads, 'interval', minutes=15, args=[application])
    scheduler.start()

    # 7. HANDLERLARNI RO'YXATGA OLISH
    
    # 7.1. Avvalo Start va Reset buyruqlari (Eng muhimi!)
    application.add_handler(CommandHandler("start", start))
    

    # 7.2. Maxsus Callbacklar
    application.add_handler(CallbackQueryHandler(recheck_callback, pattern="^recheck$"))
    application.add_handler(CallbackQueryHandler(handle_pagination, pattern="^page_"))
    application.add_handler(CallbackQueryHandler(pagination_handler, pattern="^pg_"))
    application.add_handler(CallbackQueryHandler(get_episode_handler, pattern="^get_ep_"))
    application.add_handler(CallbackQueryHandler(show_selected_anime, pattern="^show_anime_"))
    application.add_handler(CallbackQueryHandler(view_comments_handler, pattern="^view_comm_"))
    application.add_handler(CallbackQueryHandler(add_favorite_handler, pattern="^fav_"))
    application.add_handler(CallbackQueryHandler(process_redeem, pattern="^redeem_"))

    # 7.3. CONVERSATION HANDLER (Mustaqil buyruqlardan keyin, matnlardan oldin)
    application.add_handler(conv_handler)

    # 7.4. MATNLI TUGMALAR
    application.add_handler(MessageHandler(filters.Regex(r"Shaxsiy Kabinet"), show_user_cabinet))
    application.add_handler(MessageHandler(filters.Regex(r"Muxlislar Klubi"), start_profile_creation))
    application.add_handler(MessageHandler(filters.Regex(r"Murojaat & Shikoyat"), feedback_start))
    application.add_handler(MessageHandler(filters.Regex(r"Ballar & VIP"), show_bonus))
    application.add_handler(MessageHandler(filters.Regex(r"Barcha animelar"), export_all_anime))
    application.add_handler(MessageHandler(filters.Regex(r"Qo'llanma"), show_guide))
    application.add_handler(MessageHandler(filters.Regex(r"VIP PASS"), vip_pass_info))

    # 7.5. MEDIA VA ADMIN JAVOBI
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, search_anime_by_photo))
    application.add_handler(MessageHandler(filters.Chat(ADMIN_GROUP_ID) & filters.REPLY, admin_reply_handler))

    # 8. BOTNI ISHGA TUSHIRISH
    logger.info("🚀 Bot polling rejimida ishga tushdi...")
    
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        # To'g'ri to'xtash uchun Event kutamiz
        stop_event = asyncio.Event()
        await stop_event.wait()

if __name__ == '__main__':
    # Flaskni alohida oqimda ishga tushirish (Render Portni tinglashi shart)
    from threading import Thread
    import os
    
    # Render PORTni environmentdan oladi
    port = int(os.environ.get("PORT", 10000))
    
    def run_flask():
        try:
            # app obyektini kodingiz yuqorisida aniqlagan bo'lishingiz kerak (app = Flask(__name__))
            from app import app # Agar app boshqa faylda bo'lsa
            app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
        except Exception as e:
            logger.error(f"Flask xatosi: {e}")

    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Botni yangi event loop bilan ishga tushirish
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Bot to'xtatildi.")
    except Exception as e:
        logger.error(f"Kutilmagan xato: {e}")
        










