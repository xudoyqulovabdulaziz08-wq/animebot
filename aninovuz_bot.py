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
import matplotlib.pyplot as plt
from threading import Thread

# === YANGI QO'SHILADIGAN KUTUBXONALAR ===
from apscheduler.schedulers.asyncio import AsyncIOScheduler # Vaqtli vazifalarni bajarish uchun (masalan, obunani tekshirish, reklama va VIP muddati)
from apscheduler.schedulers.background import BackgroundScheduler # Avtomatik reklama va VIP muddati uchun
import matplotlib.pyplot as plt # Admin panel uchun statistika grafiklari (rasm ko'rinishida)
import io # Grafik rasmlarni xotirada saqlash uchun
# ========================================

from typing import List, Optional
from datetime import datetime
from sqlalchemy import BigInteger, Integer, String, DateTime, Text, Boolean, Float, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
# ========================================


# Flask qismi
from flask import Flask, app, render_template, Response, request, jsonify

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

# ====== DATABASE SOZLAMALARI ======
# ======Telegram bot tokeni va admin IDsi======

# Bot tokenini Render Environment Variables'dan oladi

BOT_TOKEN = os.getenv("BOT_TOKEN") 
# Global o'zgaruvchini oldindan aniqlab qo'yamiz
db_pool = None 

# Bu yerda group idsi yoziladi

ADMIN_GROUP_ID = -5128040712 
# 1. Konfiguratsiyani yuklash
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", 27624)),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "db": os.getenv("DB_NAME"),
    "autocommit": True,
}

# 2. SQLAlchemy URL obyektini yaratish (Maxsus belgilar uchun xavfsiz usul)
from sqlalchemy.engine import URL
db_url = URL.create(
    drivername="mysql+aiomysql",
    username=DB_CONFIG['user'],
    password=DB_CONFIG['password'],
    host=DB_CONFIG['host'],
    port=DB_CONFIG['port'],
    database=DB_CONFIG['db']
)

# 3. Engine yaratish (Faqat bitta engine yetarli)
engine = create_async_engine(
    db_url,
    pool_size=20,           # Bir vaqtning o'zida ochiq ulanishlar
    max_overflow=10,        # Zarurat tug'ilganda qo'shimcha ulanishlar
    pool_recycle=3600,      # Ulanishni har soatda yangilash
    echo=False              # Loglarni productionda o'chirish
)

# 4. Session factory
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
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

# Loglash sozlamalari

logging.basicConfig(

    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',

    level=logging.INFO

)

logger = logging.getLogger(__name__)
#=======================================================================================================
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running!"
#=======================================================================================================
# === baza jadvalari ma'lumotlari ===
# 3. Engine yaratish (FAQAT SHU BITTA QOLSIN)
engine = create_async_engine(
    db_url,
    pool_size=20,
    max_overflow=10,
    pool_recycle=3600,
    echo=False
)

# 4. Session factory
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)



class Base(DeclarativeBase):
    pass

# --- 1. USER GURUHI ---
class User(Base):
    __tablename__ = "users"
    
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(255))
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    points: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="user") # 'user', 'admin', 'vip'
    vip_expire_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    health_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    referral_count: Mapped[int] = mapped_column(Integer, default=0)

    # Bog'lanishlar
    favorites: Mapped[List["Favorite"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    history: Mapped[List["History"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    comments: Mapped[List["Comment"]] = relationship(back_populates="user")

# --- 2. ANIME VA QISMLAR ---
class Anime(Base):
    __tablename__ = "anime_list"
    
    anime_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    poster_id: Mapped[Optional[str]] = mapped_column(Text)
    lang: Mapped[Optional[str]] = mapped_column(String(100))
    genre: Mapped[Optional[str]] = mapped_column(String(255))
    year: Mapped[Optional[int]] = mapped_column(Integer) # <--- Optimallashtirildi (String(20) dan Integer ga)
    fandub: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    rating_sum: Mapped[float] = mapped_column(Float, default=0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    views_week: Mapped[int] = mapped_column(Integer, default=0)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Bog'lanishlar
    episodes: Mapped[List["Episode"]] = relationship(back_populates="anime", cascade="all, delete-orphan")
    favorites: Mapped[List["Favorite"]] = relationship(back_populates="anime", cascade="all, delete-orphan")
    history: Mapped[List["History"]] = relationship(back_populates="anime", cascade="all, delete-orphan")
    comments: Mapped[List["Comment"]] = relationship(back_populates="anime", cascade="all, delete-orphan")

class Episode(Base):
    __tablename__ = "anime_episodes"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anime_id: Mapped[int] = mapped_column(ForeignKey("anime_list.anime_id", ondelete="CASCADE"))
    episode: Mapped[int] = mapped_column(Integer)
    file_id: Mapped[str] = mapped_column(Text)
    
    anime: Mapped["Anime"] = relationship(back_populates="episodes")

# --- 3. FOYDALANUVCHI AMALLARI (Fevorites, History, Comments) ---
class Favorite(Base):
    __tablename__ = "favorites"
    
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    anime_id: Mapped[int] = mapped_column(ForeignKey("anime_list.anime_id", ondelete="CASCADE"), primary_key=True)

    user: Mapped["User"] = relationship(back_populates="favorites")
    anime: Mapped["Anime"] = relationship(back_populates="favorites")

class History(Base):
    __tablename__ = "history"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    anime_id: Mapped[int] = mapped_column(ForeignKey("anime_list.anime_id", ondelete="CASCADE"))
    last_episode: Mapped[int] = mapped_column(Integer)
    watched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="history")
    anime: Mapped["Anime"] = relationship(back_populates="history")

class Comment(Base):
    __tablename__ = "comments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    anime_id: Mapped[int] = mapped_column(ForeignKey("anime_list.anime_id", ondelete="CASCADE"))
    comment_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="comments")
    anime: Mapped["Anime"] = relationship(back_populates="comments")

#=======================================================================================================

async def init_db_pool():
    global db_pool
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        # 1. DB_CONFIG dan nusxa olamiz va aiomysql tanimaydigan kalitlarni o'chiramiz
        pool_config = DB_CONFIG.copy()
        pool_config.pop('autocommit', None)  # aiomysql pool buni tanimaydi
        pool_config.pop('ssl_disabled', None) 
        pool_config.pop('ssl_mode', None)

        # 2. Pool yaratish
        db_pool = await aiomysql.create_pool(
            **pool_config,
            minsize=5, 
            maxsize=25,
            pool_recycle=300,
            cursorclass=aiomysql.DictCursor,
            ssl=ctx,
            autocommit=True # Autocommitni shu yerda alohida berish xavfsizroq
        )
        
        # ... qolgan CREATE TABLE so'rovlari ...
        
        
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. USERS
                await cur.execute("""CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY, 
                    username VARCHAR(255),
                    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP, 
                    points INT DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'user',
                    vip_expire_date DATETIME DEFAULT NULL,
                    health_mode TINYINT(1) DEFAULT 1,
                    referral_count INT DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 2. ANIME_LIST
                await cur.execute("""CREATE TABLE IF NOT EXISTS anime_list (
                    anime_id INT AUTO_INCREMENT PRIMARY KEY, 
                    name VARCHAR(255) NOT NULL, 
                    poster_id TEXT,
                    lang VARCHAR(100),
                    genre VARCHAR(255),
                    year INT, -- <--- Modeldagi String(20) bilan moslashdi (Optimallashtirildi)
                    fandub VARCHAR(255),
                    description TEXT,
                    rating_sum FLOAT DEFAULT 0,
                    rating_count INT DEFAULT 0,
                    views_week INT DEFAULT 0,
                    is_completed TINYINT(1) DEFAULT 0,
                    INDEX (name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 3. ANIME_EPISODES
                await cur.execute("""CREATE TABLE IF NOT EXISTS anime_episodes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    anime_id INT,
                    episode INT,
                    file_id TEXT,
                    FOREIGN KEY (anime_id) REFERENCES anime_list(anime_id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 4. FAVORITES
                await cur.execute("""CREATE TABLE IF NOT EXISTS favorites (
                    user_id BIGINT,
                    anime_id INT,
                    PRIMARY KEY (user_id, anime_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (anime_id) REFERENCES anime_list(anime_id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 5. HISTORY
                await cur.execute("""CREATE TABLE IF NOT EXISTS history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT,
                    anime_id INT,
                    last_episode INT,
                    watched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (anime_id) REFERENCES anime_list(anime_id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 6. COMMENTS
                await cur.execute("""CREATE TABLE IF NOT EXISTS comments (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT,
                    anime_id INT,
                    comment_text TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL,
                    FOREIGN KEY (anime_id) REFERENCES anime_list(anime_id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

                # 7. CHANNELS
                await cur.execute("""CREATE TABLE IF NOT EXISTS channels (
                    username VARCHAR(255) PRIMARY KEY,
                    subscribers_added INT DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

        logger.info("✅ Database Schema va SQLAlchemy Modellari 100% moslashtirildi.")
    except Exception as e:
        logger.error(f"❌ DB Pool Error: {e}")
# Bot ishga tushish qismini optimallashtirish

#=======================================================================================================

#==bot ishga tushgandan keyin bajariladigan amallar==#
async def post_init(application):
    """
    Bot to'liq ishga tushgandan keyin bajariladigan amallar
    """
    await init_db_pool()
    logger.info("Bot va baza tayyor!")

#=======================================================================================================

#==Bazaga so'rov yuborish uchun markazlashgan helper==#
async def execute_query(query: str, params: tuple = None, fetch: str = "none"):
    """
    Bazaga so'rov yuborish uchun markazlashgan helper.
    fetch: 'one', 'all', 'rowcount' yoki 'none'
    """
    global db_pool
    # Poolni tekshirish va qayta tiklash
    if db_pool is None or db_pool._closed:
        await init_db_pool()
        if db_pool is None:
            logger.error("❌ DB Poolni inisializatsiya qilib bo'lmadi!")
            return None

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params or ())
                
                if fetch == "one":
                    return await cur.fetchone()
                elif fetch == "all":
                    return await cur.fetchall()
                elif fetch == "rowcount":
                    return cur.rowcount
                
                # Agar INSERT bo'lsa, oxirgi IDni qaytarish foydali bo'lishi mumkin
                if "INSERT" in query.upper():
                    return cur.lastrowid
                
                return True
    except aiomysql.Error as e:
        logger.error(f"❌ SQL Xatolik: {e} | Query: {query} | Params: {params}")
        return None
#=======================================================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user = update.effective_user
    uid = user.id
    username = (user.username or user.first_name or "User")[:50]
    
    # 1. Deep Link tahlili
    ref_id = None
    if context.args:
        arg = context.args[0]
        if arg.startswith("ani_"):
            context.user_data['pending_anime'] = arg.replace("ani_", "")
        elif arg.isdigit() and int(arg) != uid:
            ref_id = int(arg)

    # 2. Foydalanuvchini bazadan tekshirish
    existing_user = await execute_query("SELECT user_id, status FROM users WHERE user_id = %s", (uid,), fetch="one")
    is_new_user = False

    if not existing_user:
        # Yangi foydalanuvchini ro'yxatdan o'tkazish
        is_new_user = True
        await execute_query(
            "INSERT INTO users (user_id, username, points) VALUES (%s, %s, %s)",
            (uid, username, 10)
        )
        # Referral bonus (faqat yangi foydalanuvchi uchun)
        if ref_id:
            await execute_query(
                "UPDATE users SET points = points + 20, referral_count = referral_count + 1 WHERE user_id = %s",
                (ref_id,)
            )
            try:
                await context.bot.send_message(
                    chat_id=ref_id,
                    text=f"🎉 <b>Yangi taklif!</b>\n\nDo'stingiz @{username} botga qo'shildi. Sizga <b>20 ball</b> bonus berildi!",
                    parse_mode="HTML"
                )
            except: pass

    # 3. Majburiy obunani tekshirish
    not_joined = await check_sub(uid, context.bot)
    if not_joined:
        # Agar yangi bo'lsa, balli haqidagi xabarni keyinga saqlab qo'yamiz
        if is_new_user:
            context.user_data['show_bonus_msg'] = True
            
        keyboard = [[InlineKeyboardButton(f"Obuna bo'lish ➕", url=f"https://t.me/{c.strip('@')}")] for c in not_joined]
        keyboard.append([InlineKeyboardButton("Tekshirish ✅", callback_data="recheck")])
        
        msg = "🎬 <b>Animelarni ko'rish uchun</b> quyidagi kanallarga a'zo bo'lishingiz kerak:"
        return await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

    # 4. Xabar matnini shakllantirish
    # Agar foydalanuvchi hozirgina obuna bo'lib qaytgan bo'lsa yoki is_new_user bo'lsa
    if is_new_user or context.user_data.get('show_bonus_msg'):
        welcome_msg = f"✨ Xush kelibsiz, <b>{user.first_name}</b>!\n💰 Botimizga ilk bor tashrif buyurganingiz uchun <b>10 ball</b> sovg'a qilindi!"
        context.user_data.pop('show_bonus_msg', None) # Xabarni o'chirib tashlaymiz
    else:
        welcome_msg = f"Sizni yana ko'rib turganimizdan xursandmiz, <b>{user.first_name}</b>! 😊"

    # 5. Menyu chiqarish
    status = existing_user['status'] if existing_user else "user"
    await update.message.reply_text(
        welcome_msg, 
        reply_markup=get_main_kb(status),
        parse_mode="HTML"
    )
    
    return ConversationHandler.END
    


#=======================================================================================================
#==Obunani tekshirish funksiyasi==
async def check_sub(uid: int, bot):
    """
    Foydalanuvchi majburiy kanallarga a'zo ekanligini tekshiradi.
    """
    not_joined = []
    
    # 1. Kanallarni bazadan olish (Helper orqali)
    try:
        # execute_query o'zi try-except ichida va timeout bilan ishlashi mumkin
        channels = await execute_query("SELECT username FROM channels", fetch="all")
    except Exception as e:
        logger.error(f"⚠️ Kanal bazasida xato: {e}")
        return [] # Baza ishlamasa, foydalanuvchini to'xtatmaymiz

    if not channels:
        return []

    for row in channels:
        # DictCursor bo'lgani uchun row['username'] ko'rinishida olamiz
        ch_username = row['username']
        
        try:
            # Username formatini to'g'irlash
            target = str(ch_username).strip()
            if not target.startswith('@') and not target.startswith('-'):
                target = f"@{target}"
            
            # 2. Telegram API orqali tekshirish (Timeout bilan)
            async with asyncio.timeout(3):
                member = await bot.get_chat_member(target, uid)
                # Statuslar: creator, administrator, member, restricted, left, kicked
                if member.status in ['left', 'kicked']:
                    not_joined.append(ch_username)
                    
        except asyncio.TimeoutError:
            logger.warning(f"⌛ Kanal tekshirishda timeout: {ch_username}")
            continue # Telegram javob bermasa, bu kanalni o'tkazib yuboramiz
        except Exception as e:
            # Agar bot kanalga admin bo'lmasa yoki kanal topilmasa
            logger.warning(f"❗ Kanalda xatolik ({ch_username}): {e}")
            continue 
            
    return not_joined

#=======================================================================================================

#==Callback query orqali obunani qayta tekshirish va foydalanuvchini yo'naltirish==
async def recheck_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Obunani qayta tekshirish, statistika yuritish va foydalanuvchini yo'naltirish.
    """
    query = update.callback_query
    uid = query.from_user.id
    
    # 1. Hozirgi holatni tekshiramiz
    not_joined = await check_sub(uid, context.bot)
    
    if not not_joined:
        # Foydalanuvchi hamma kanalga a'zo bo'ldi.
        
        # 2. Statistika: Yangi a'zo bo'lingan kanallar sonini oshirish
        old_not_joined = context.user_data.get('last_not_joined', [])
        if old_not_joined:
            for ch_username in old_not_joined:
                # Har bir kanal uchun subscribers_added ustunini +1 qilamiz
                await execute_query(
                    "UPDATE channels SET subscribers_added = subscribers_added + 1 WHERE username = %s",
                    (ch_username,)
                )
            context.user_data.pop('last_not_joined', None)

        # 3. Eski xabarni o'chirish
        try:
            await query.message.delete()
        except:
            pass
        
        # 4. Kutilayotgan anime bo'lsa, o'shanga yo'naltirish
        if 'pending_anime' in context.user_data:
            ani_id = context.user_data.pop('pending_anime')
            # Bu funksiya sizda ID orqali animeni ko'rsatishi kerak
            return await show_specific_anime_by_id(query, context, ani_id)
        
        # 5. Foydalanuvchi statusini olamiz va asosiy menyuni chiqaramiz
        user_row = await execute_query("SELECT status FROM users WHERE user_id = %s", (uid,), fetch="one")
        status = user_row['status'] if user_row else "user"

        await query.message.reply_text(
            "✅ Tabriklaymiz! Barcha kanallarga obuna bo'lindi.\nEndi botdan cheklovsiz foydalanishingiz mumkin.", 
            reply_markup=get_main_kb(status),
            parse_mode="HTML"
        )
        await query.answer() # Callback queryni yopish
    else:
        # Hali ham obuna bo'lmagan bo'lsa
        context.user_data['last_not_joined'] = not_joined
        
        # Qaysi kanallar qolib ketganini eslatib o'tish (ixtiyoriy, UX uchun yaxshi)
        left_channels = ", ".join(not_joined)
        await query.answer(
            f"❌ Hali hamma kanallarga a'zo emassiz!\nQolib ketgan: {left_channels}", 
            show_alert=True
        )

#=======================================================================================================

#==ID bo'yicha animeni ko'rsatish va ko'rishlar sonini oshirish==
async def show_specific_anime_by_id(update_or_query, context, ani_id):
    """
    ID bo'yicha bazadan animeni topadi va ko'rishlar sonini oshiradi.
    """
    # 1. Animeni bazadan qidirish
    anime = await execute_query("SELECT * FROM anime_list WHERE anime_id=%s", (ani_id,), fetch="one")
    
    if not anime:
        error_text = "❌ Kechirasiz, bu anime bazadan o'chirilgan yoki hali qo'shilmagan."
        if hasattr(update_or_query, 'callback_query') and update_or_query.callback_query:
            await update_or_query.callback_query.answer(error_text, show_alert=True)
        elif hasattr(update_or_query, 'message') and update_or_query.message:
            await update_or_query.message.reply_text(error_text)
        else:
            # CallbackQuery obyektining o'zi kelsa (recheck_callback'dagi kabi)
            await update_or_query.message.reply_text(error_text)
        return

    # 2. Haftalik ko'rishlar sonini oshirish (Async execute)
    await execute_query(
        "UPDATE anime_list SET views_week = views_week + 1 WHERE anime_id=%s", 
        (ani_id,)
    )

    # 3. Tafsilotlarni chiqarish funksiyasiga yuboramiz
    # Eslatma: show_anime_details funksiyasini keyingi qadamda yozamiz
    return await show_anime_details(update_or_query, anime, context)

#=======================================================================================================
#==Anime tafsilotlarini chiroyli formatda chiqarish==
async def show_anime_details(update_or_query, anime_data, context: ContextTypes.DEFAULT_TYPE):
    """
    Anime tafsilotlarini chiroyli formatda chiqaradi.
    anime_data: Bazadan kelgan lug'at (dict) yoki SQLAlchemy obyekti
    """
    # 1. Update yoki CallbackQuery ekanligini aniqlash
    is_callback = hasattr(update_or_query, 'data')
    query = update_or_query if is_callback else None
    chat_id = query.message.chat_id if is_callback else update_or_query.effective_chat.id
    
    anime_id = anime_data['anime_id']

    # 2. Ma'lumotlarni tayyorlash (Null qiymatlarni tekshirish)
    name = anime_data.get('name', 'Noma\'lum')
    genre = anime_data.get('genre', 'Noma\'lum')
    year = anime_data.get('year', 'Noma\'lum')
    fandub = anime_data.get('fandub', 'Noma\'lum')
    lang = anime_data.get('lang', 'O\'zbek')
    views = anime_data.get('views_week', 0)
    poster = anime_data.get('poster_id')
    desc = anime_data.get('description') or "Tavsif mavjud emas."
    
    # Reyting hisoblash
    r_sum = anime_data.get('rating_sum', 0)
    r_count = anime_data.get('rating_count', 0)
    rating = f"⭐ {r_sum / r_count:.1f}" if r_count > 0 else "Hali baholanmagan"
    
    holati = "✅ Tugallangan" if anime_data.get('is_completed') else "🎬 Davom etmoqda"

    # Tavsifni qisqartirish (Telegram limitiga moslash)
    if len(desc) > 400:
        desc = desc[:400].rsplit(' ', 1)[0] + "..."

    # 3. HTML Caption (Chiroyli dizayn)
    caption = (
        f"<b>🎬 {name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎭 <b>Janr:</b> {genre}\n"
        f"📅 <b>Yil:</b> {year}\n"
        f"🎙 <b>Fandub:</b> {fandub}\n"
        f"🌐 <b>Til:</b> {lang}\n"
        f"👁 <b>Ko‘rishlar:</b> {views}\n"
        f"📊 <b>Reyting:</b> {rating}\n"
        f"💎 <b>Holati:</b> {holati}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📖 <b>Qisqacha mazmuni:</b>\n<i>{desc}</i>"
    )

    # 4. Inline tugmalar
    buttons = [
        [InlineKeyboardButton("🎞 Qismlarni ko'rish", callback_data=f"show_episodes_{anime_id}")],
        [
            InlineKeyboardButton("🌟 Sevimlilar", callback_data=f"fav_{anime_id}"),
            InlineKeyboardButton("✍️ Sharhlar", callback_data=f"comments_{anime_id}")
        ],
        [InlineKeyboardButton("⭐ Baholash", callback_data=f"rate_{anime_id}")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_list")]
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    # 5. Yuborish logikasi
    try:
        if is_callback:
            await query.answer()
            # Eski xabarni o'chirib yangisini yuborish (Poster o'zgarishi uchun shart)
            await query.message.delete()

        if poster:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=poster,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"❌ show_anime_details xatosi: {e}")
        await context.bot.send_message(chat_id=chat_id, text="⚠️ Ma'lumotni yuklashda texnik xatolik yuz berdi.")
#=======================================================================================================

# Asosiy menyu tugmalari (statusga qarab o'zgaradi)
def get_main_kb(status: str):
    # Har doim ko'rinadigan tugmalar
    kb = [
        [KeyboardButton("🔍 Anime qidirish 🎬"), KeyboardButton("🔥 Trenddagilar")],
        [KeyboardButton("👤 Shaxsiy Kabinet"), KeyboardButton("🎁 Ballar & VIP")],
        [KeyboardButton("🤝 Muxlislar Klubi"), KeyboardButton("📂 Barcha animelar")],
        [KeyboardButton("✍️ Murojaat & Shikoyat"), KeyboardButton("📖 Qo'llanma ❓")]
    ]
    
    # Statusga qarab qo'shimcha menyu
    if status in ["main_admin", "admin"]:
        # Adminlar uchun alohida qator
        kb.insert(0, [KeyboardButton("🛠 ADMIN PANEL")]) # Eng tepada bo'lishi qulayroq
    
    elif status == "vip":
        # VIP foydalanuvchilar uchun vizual "ajralib turish"
        kb.insert(0, [KeyboardButton("🌟 VIP IMKONIYATLAR 🌟")])

    return ReplyKeyboardMarkup(kb, resize_keyboard=True, input_field_placeholder="Kerakli bo'limni tanlang...")

#=======================================================================================================
# Botni ishga tushirish qismi
def main():
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Start handler
    application.add_handler(CommandHandler("start", start))
    
    # Callbacklar (Tekshirish tugmasi uchun)
    application.add_handler(CallbackQueryHandler(recheck_callback, pattern="^recheck$"))
    
    # Anime qismlarini ko'rish va boshqa callbacklar uchun (pattern moslashuvchan)
    # application.add_handler(CallbackQueryHandler(handle_callbacks)) 

    logger.info("🚀 Bot polling rejimida ishga tushdi...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    # Flaskni fonda ishga tushirish
    flask_thread = Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000))), daemon=True)
    flask_thread.start()
    
    # Botni ishga tushirish

    main()










