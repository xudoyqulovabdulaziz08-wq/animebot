from email.mime import application
import os
import uuid
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
from sqlalchemy import BigInteger, Integer, String, DateTime, Text, Boolean, Float, ForeignKey, func, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
# ========================================


# Flask qismi
from flask import Flask, app, render_template, Response, request, jsonify

# Telegram Bot qismi
from telegram import (
    InlineQueryResultArticle, InputTextMessageContent, LabeledPrice, Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InputMediaPhoto # Anime rasm qidiruvida natijani chiqarish uchun
)
import uuid
from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, InlineQueryHandler,
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
MAIN_ADMIN_ID = int(os.getenv("ADMIN_ID", 8244870375))
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
    
    # === YANGI QO'SHILGAN STATUSLAR (23-36) ===
    
    # 20-band: Murojaatlar va Shikoyatlar
    U_FEEDBACK_SUBJ,      # 23: Shikoyat mavzusini tanlash
    U_FEEDBACK_MSG,       # 24: Shikoyat matnini yozish

    # 5-band: Izohlar tizimi
    U_ADD_COMMENT,        # 25: Animega izoh yozish holati

    # 1-band: AI Qidiruv 
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

    A_MAIN,               # 33: Main/Asosiy funksiya qaytishi

    # Inline va qidiruv uchun yangi holatlar
    A_SEARCH_BY_NAME,     # 34: Nomi bo'yicha qidirish
    A_SEARCH_BY_ID,       # 35: ID bo'yicha qidirish
    U_AI_PHOTO_SEARCH     # 36: AI rasm qidiruv
) = range(37)

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
    try:
        anime = await execute_query("SELECT * FROM anime_list WHERE anime_id=%s", (ani_id,), fetch="one")
        
        if anime:
            # Ko'rishlar sonini oshirish
            await execute_query(
                "UPDATE anime_list SET views_week = views_week + 1, total_views = total_views + 1 WHERE anime_id=%s", 
                (ani_id,)
            )
            return await show_anime_details(update_or_query, anime, context)
        else:
            msg = "❌ Anime topilmadi."
            if hasattr(update_or_query, 'callback_query') and update_or_query.callback_query:
                await update_or_query.callback_query.answer(msg, show_alert=True)
            else:
                target = update_or_query.message if hasattr(update_or_query, 'message') else update_or_query
                await target.reply_text(msg)
    except Exception as e:
        logger.error(f"Error in show_specific_anime_by_id: {e}")

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

async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Tugma bosilgani haqida darhol javob beramiz (soat belgisi yo'qolishi uchun)
    await query.answer()
    
    data_parts = query.data.split("_")
    if len(data_parts) < 3:
        return 

    anime_id = data_parts[1]
    offset = int(data_parts[2])
    limit = 12 # Sahifadagi qismlar soni

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Faqat ushbu animega tegishli barcha qismlarni olish
                # ORDER BY episode ASC muhim, qismlar aralashib ketmasligi uchun
                await cur.execute(
                    "SELECT id, episode FROM anime_episodes WHERE anime_id=%s ORDER BY episode ASC", 
                    (anime_id,)
                )
                episodes = await cur.fetchall()

        if not episodes:
            return await query.answer("❌ Epizodlar topilmadi", show_alert=True)

        total = len(episodes)
        # Sahifada ko'rsatiladigan qismlarni ajratish
        display_eps = episodes[offset : offset + limit]
        
        keyboard = []
        row = []
        for ep in display_eps:
            # Cursor tipiga qarab ma'lumot olish (Dict vs Tuple)
            is_dict = isinstance(ep, dict)
            ep_num = ep['episode'] if is_dict else ep[1]
            ep_db_id = ep['id'] if is_dict else ep[0]
            
            row.append(InlineKeyboardButton(text=f"{ep_num}", callback_data=f"get_ep_{ep_db_id}"))
            if len(row) == 4: # Bir qatorda 4 tadan tugma
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)

        # Navigatsiya tugmalari (Pagination bar)
        nav_row = []
        # Orqaga tugmasi
        if offset > 0:
            nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"page_{anime_id}_{max(0, offset - limit)}"))
        
        # Markaziy ma'lumot: Masalan "13-24 / 50"
        current_range = f"{offset + 1}-{min(offset + limit, total)}"
        nav_row.append(InlineKeyboardButton(f"{current_range} / {total}", callback_data="ignore"))
        
        # Oldinga tugmasi
        if offset + limit < total:
            nav_row.append(InlineKeyboardButton("➡️", callback_data=f"page_{anime_id}_{offset + limit}"))
        
        if nav_row:
            keyboard.append(nav_row)

        # Qismlardan anime sahifasiga qaytish
        keyboard.append([InlineKeyboardButton("🔙 Anime sahifasiga qaytish", callback_data=f"show_anime_{anime_id}")])

        # Faqat klaviaturani yangilaymiz
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        new_caption = "<b>📺 Qismlar ro'yxati</b>\n\nMarhamat, ko'rmoqchi bo'lgan qismingizni tanlang:"
        try:
            # Agar rasm bo'lsa edit_message_caption, rasm bo'lmasa edit_message_text
            await query.edit_message_caption(
                caption=new_caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        except Exception:
            # Agar xabar rasm bo'lmasa (fallback)
            await query.edit_message_text(
                text=new_caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        
        await query.answer()

    except Exception as e:
        logger.error(f"Pagination Error: {e}")
        # Xatolik yuz bersa foydalanuvchiga xabar beramiz
        await query.answer("⚠️ Ma'lumot yangilashda xatolik.", show_alert=True)

#=======================================================================================================

async def show_episodes_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anime tafsilotlaridan epizodlar ro'yxatiga o'tish (Start pagination)"""
    query = update.callback_query
    # callback_data: show_episodes_{anime_id}
    anime_id = query.data.split("_")[2]
    
    # pagination funksiyasini 0-offset bilan chaqiramiz
    # Biz kodingizni qayta ishlatish uchun query.data ni o'zgartirib yuboramiz
    query.data = f"page_{anime_id}_0"
    return await handle_pagination(update, context)

#=======================================================================================================



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
async def search_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("⚡ Tezkor qidiruv (Inline)", switch_inline_query_current_chat="")],
        [
            InlineKeyboardButton("🔎 Nomi orqali", callback_data="search_type_name"),
            InlineKeyboardButton("🆔 ID raqami", callback_data="search_type_id")
        ],
        [
            InlineKeyboardButton("🖼 Rasm orqali (AI)", callback_data="search_type_photo"),
            InlineKeyboardButton("👤 Personaj (AI)", callback_data="search_type_character")
        ],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_search")]
    ]
    
    text = (
        "🎬 <b>Anime qidirish bo'limi</b>\n\n"
        "Qidiruv usulini tanlang:\n\n"
        "💡 <i>Maslahat: Rasm orqali qidirish (AI) esingizda yo'q kadrlarni topishga yordam beradi!</i>"
    )

    # CallbackQuery bo'lsa edit qiladi, xabar bo'lsa yangi yuboradi
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            text=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
        )
    
    # Qidiruv bosqichida qolish uchun:
    return A_ANI_CONTROL


#=======================================================================================================



#=======================================================================================================

async def search_anime_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    query = update.callback_query
    
  
    if update.message and update.message.text:
        text = update.message.text.strip()

        # Agar yozilgan matn asosiy menyu tugmalaridan biri bo'lsa
        if text in MENU_TEXTS:
         # Qidiruv holatidan chiqamiz va o'sha bo'limga tegishli javobni berish uchun 
            # END qaytaramiz. Shunda keyingi bosqichda bot matnli handlerga o'tadi.
            await update.message.reply_text("🔍 Qidiruv to'xtatildi.")
            return ConversationHandler.END

    # 2. CALLBACK QUERY (Tugmalar bosilganda)
    if query:
        data = query.data
        await query.answer()

        if data == "cancel_search":
            return await search_menu_cmd(update, context)

        if data.startswith("select_ani_"):
            ani_id = data.replace("select_ani_", "")
            return await show_specific_anime_by_id(query, context, ani_id)
        
        modes = {
            "search_type_name": ("name", "🔍 Anime <b>nomini</b> kiriting:"),
            "search_type_id": ("id", "🆔 Anime <b>ID raqamini</b> kiriting:"),
            "search_type_character": ("character", "👤 <b>Personaj</b> ismini yozing:")
        }
        
        if data in modes:
            mode, msg = modes[data]
            context.user_data["search_mode"] = mode
            await query.edit_message_text(
                text=msg, 
                parse_mode="HTML", 
                reply_markup=get_cancel_kb() # Bu yerda Inline bo'lishi shart
            )
            # Rejimga qarab state o'zgaradi
            return A_SEARCH_BY_NAME if mode != "id" else A_SEARCH_BY_ID

        elif data == "search_type_random":
            res = await execute_query("SELECT anime_id FROM anime_list ORDER BY RAND() LIMIT 1", fetch="one")
            if res:
                return await show_specific_anime_by_id(query, context, res['anime_id'])
            return A_ANI_CONTROL

    # 3. QIDIRUV MANTIQI (Matn yozilganda davom etadi)
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    search_type = context.user_data.get("search_mode", "name")
    
    # SQL so'rovlari (O'zgarishsiz)
    if search_type == "id" and text.isdigit():
        sql = "SELECT * FROM anime_list WHERE anime_id = %s"
        params = (int(text),)
    elif search_type == "character":
        sql = "SELECT * FROM anime_list WHERE description LIKE %s OR genre LIKE %s LIMIT 20"
        params = (f"%{text}%", f"%{text}%")
    else:
        sql = "SELECT * FROM anime_list WHERE name LIKE %s LIMIT 20"
        params = (f"%{text}%",)

    results = await execute_query(sql, params, fetch="all")

    if not results:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Qayta qidirish", callback_data="search_type_name")]])
        await update.message.reply_text(f"😔 <b>'{text}'</b> bo'yicha natija topilmadi.", reply_markup=kb, parse_mode="HTML")
        return A_ANI_CONTROL # Qidiruvda qoladi, foydalanuvchi boshqa nom yozishi mumkin

    # Natijalarni chiqarish (O'zgarishsiz)
    if len(results) == 1:
        return await show_specific_anime_by_id(update.message, context, results[0]['anime_id'])

    buttons = []
    for ani in results:
        try:
            r_sum, r_count = ani.get('rating_sum', 0), ani.get('rating_count', 0)
            rating = f"⭐ {r_sum/r_count:.1f}" if r_count > 0 else "🌑"
        except: rating = "🌑"
        
        buttons.append([InlineKeyboardButton(f"🎬 {ani['name']} | {rating}", callback_data=f"select_ani_{ani['anime_id']}")])

    await update.message.reply_text(
        f"🔍 <b>'{text}'</b> bo'yicha natijalar:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML"
    )
    return A_ANI_CONTROL


#=======================================================================================================


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

#=======================================================================================================

def get_cancel_kb():
    """Jarayonlarni bekor qilish uchun 'Orqaga' tugmasi"""
    return ReplyKeyboardMarkup([[KeyboardButton("⬅️ Orqaga")]], resize_keyboard=True)

#=======================================================================================================

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

#=======================================================================================================

async def show_anime_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    anime_id = query.data.replace("show_anime_", "")
    # Bazadan ma'lumotni olib, keyin show_anime_details ni chaqirish kerak
    anime = await execute_query("SELECT * FROM anime_list WHERE anime_id=%s", (anime_id,), fetch="one")
    if anime:
        await show_anime_details(query, anime, context)

#=======================================================================================================


#=======================================================================================================

# Inline qidiruv funksiyasi
async def inline_query_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query

    # Bazadan qidirish (LIKE orqali)
    sql = "SELECT * FROM anime_list WHERE name LIKE %s LIMIT 20"
    results = await execute_query(sql, (f"%{query}%",), fetch="all")

    inline_results = []
    
    if results:
        for anime in results:
            # Rasmda ko'rsatilgan format: Nomi, Reyting, Qismlar soni, Yili
            r_sum = anime.get('rating_sum', 0)
            r_count = anime.get('rating_count', 0)
            rating = f"{r_sum / r_count:.1f}" if r_count > 0 else "0.0"
            
            description = (
                f"⭐ {rating} • 📺 {anime.get('year')}-yil\n"
                f"🎭 {anime.get('genre', 'Janrsiz')}"
            )
            
            inline_results.append(
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title=f"📕 {anime['name']}",
                    description=description,
                    thumbnail_url=anime.get('poster_id'), # Agar poster_id URL bo'lsa
                    input_message_content=InputTextMessageContent(
                        message_text=f"/start ani_{anime['anime_id']}" 
                    )
                )
            )

    await update.inline_query.answer(inline_results, cache_time=300)


#=======================================================================================================



#=======================================================================================================

async def process_search_by_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text
    
    # 1. Uzunlikni tekshirish
    if len(query_text) < 3:
        await update.message.reply_text("⚠️ Kamida 3 ta harf kiriting!")
        return A_SEARCH_BY_NAME

    # 2. Bazadan qidirish
    sql = "SELECT anime_id, name, year FROM anime_list WHERE name LIKE %s LIMIT 10"
    results = await execute_query(sql, (f"%{query_text}%",), fetch="all")

    # 3. Agar natija topilmasa
    if not results:
        retry_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Qayta urinish", callback_data="search_name")],
            [InlineKeyboardButton("❌ Qidiruvni yopish", callback_data="cancel_search")]
        ])
        await update.message.reply_text(
            "😔 Kechirasiz, bunday nomli anime topilmadi. Qiruvni qayta urunib koring yoki qidirishni toxtating.",
            reply_markup=retry_kb
        )
        return A_SEARCH_BY_NAME # Holatni saqlab qolamiz

    # 4. Natijalar topilsa
    buttons = []
    for anime in results:
        btn_text = f"🎬 {anime['name']} ({anime['year']})"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"show_ani_{anime['anime_id']}")])
    
    buttons.append([InlineKeyboardButton("⬅️ Bekor qilish", callback_data="back_to_search")])
    
    await update.message.reply_text(
        f"🔍 <b>'{query_text}'</b> bo'yicha topilgan natijalar:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML"
    )
    return A_ANI_CONTROL # Keyingi tanlov uchun holatga o'tkazamiz

#=======================================================================================================



#=======================================================================================================

async def get_episode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # callback_data formati: "get_ep_ROWID"
    data = query.data.split("_") 
    uid = update.effective_user.id
    
    if len(data) < 3: 
        await query.answer("❌ Ma'lumot xatosi")
        return
        
    row_id = data[2] 
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Foydalanuvchi ma'lumotlarini olish
                await cur.execute("SELECT health_mode, status FROM users WHERE user_id = %s", (uid,))
                user_data = await cur.fetchone()

                # 2. Video va Anime ma'lumotlarini olish (JOIN orqali)
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

                # 3. KO'RISH TARIXI (History)
                # INSERT ... ON DUPLICATE KEY UPDATE ishlatish qulayroq, 
                # lekin sizning mantiqingiz ham to'g'ri.
                await cur.execute("SELECT id FROM history WHERE user_id=%s AND anime_id=%s", (uid, res['anime_id']))
                history_entry = await cur.fetchone()
                
                if history_entry:
                    await cur.execute(
                        "UPDATE history SET last_episode=%s, watched_at=NOW() WHERE id=%s", 
                        (res['episode'], history_entry['id'])
                    )
                else:
                    await cur.execute(
                        "INSERT INTO history (user_id, anime_id, last_episode) VALUES (%s, %s, %s)", 
                        (uid, res['anime_id'], res['episode'])
                    )
                # O'zgarishlarni saqlash
                await conn.commit()

                # 4. KEYINGI QISMNI QIDIRISH (Mavjudligini tekshirish uchun)
                await cur.execute("""
                    SELECT id FROM anime_episodes 
                    WHERE anime_id = %s AND episode > %s 
                    ORDER BY episode ASC LIMIT 1
                """, (res['anime_id'], res['episode']))
                next_ep = await cur.fetchone()
                
                # 5. REKLAMA (VIP bo'lmaganlar uchun)
                ads_text = ""
                if user_data and user_data['status'] != 'vip':
                    await cur.execute("SELECT caption FROM advertisements WHERE is_active=1 ORDER BY RAND() LIMIT 1")
                    ads = await cur.fetchone()
                    if ads:
                        ads_text = f"\n\n📢 <b>Reklama:</b> <i>{ads['caption']}</i>"

        # 6. SOG'LIQ REJIMI (01:00 - 05:00)
        current_hour = datetime.datetime.now().hour
        if user_data and user_data.get('health_mode') == 1:
            if 1 <= current_hour <= 5:
                # Faqat ogohlantirish, videoni to'xtatmaydi (agar to'xtatmoqchi bo'lsangiz return qiling)
                await context.bot.send_message(
                    chat_id=uid,
                    text="🌙 <b>Sog'ligingiz haqida qayg'uramiz!</b>\nTungi soat 01:00 dan o'tdi. Dam olishni tavsiya qilamiz! 😊",
                    parse_mode="HTML"
                )

        # 7. TUGMALARNI SHAKLLANTIRISH
        keyboard = []
        if next_ep:
            # next_ep['id'] DictCursor ishlatilgani uchun shunday olinadi
            keyboard.append([InlineKeyboardButton("Keyingi qism ➡️", callback_data=f"get_ep_{next_ep['id']}")])
        else:
            keyboard.append([InlineKeyboardButton("⭐️ Animeni baholash", callback_data=f"rate_{res['anime_id']}")])
            keyboard.append([InlineKeyboardButton("✅ Tugatish va Ball olish", callback_data=f"finish_{res['anime_id']}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Anime sahifasiga", callback_data=f"show_anime_{res['anime_id']}")])

        # 8. VIDEONI YUBORISH
        # query.message.edit_reply_markup() orqali eski tugmani o'chirish yaxshi praktika
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except: pass

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
        print(f"Video yuborish xatosi: {e}") # Loger o'rniga oddiy print yoki o'z logeringiz
        await query.answer("❌ Video yuborishda xatolik yuz berdi.", show_alert=True)

#=======================================================================================================

async def get_user_status(uid: int):
    """
    Foydalanuvchi statusini asinxron aniqlash.
    28-band: VIP muddatini avtomatik tekshirish va statusni yangilash qo'shildi.
    """
    # 1. Asosiy egasini tekshirish
    if uid == MAIN_ADMIN_ID: 
        return "main_admin"
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 2. Adminlar jadvalini tekshirish
                # Eslatma: init_db da 'admins' jadvali qolib ketgan bo'lsa, uni yaratishni unutmang
                await cur.execute("SELECT user_id FROM admins WHERE user_id=%s", (uid,))
                if await cur.fetchone():
                    return "admin"
                
                # 3. Foydalanuvchi ma'lumotlarini olish
                await cur.execute("SELECT status, vip_expire_date FROM users WHERE user_id=%s", (uid,))
                res = await cur.fetchone()
                
                if not res:
                    return "user"
                
                status = res['status']
                vip_date = res['vip_expire_date']
                
                # 4. 28-BAND: VIP muddati o'tganini tekshirish (Avtomatlashtirish)
                if status == 'vip' and vip_date:
                    if datetime.datetime.now() > vip_date:
                        # Muddat tugagan bo'lsa statusni tushiramiz
                        await cur.execute("UPDATE users SET status='user', vip_expire_date=NULL WHERE user_id=%s", (uid,))
                        return "user"
                
                return status
                
    except Exception as e:
        logger.error(f"⚠️ Status aniqlashda (aiomysql) xato: {e}")
        return "user"

#=======================================================================================================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    
    # get_user_status allaqachon aiomysql pool bilan ishlaydi (await shart)
    status = await get_user_status(uid)
    await query.answer()
#=======================================================================================================

async def show_user_cabinet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi shaxsiy kabinetini ko'rsatish"""
    uid = update.effective_user.id
    query = update.callback_query
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                # 1. Foydalanuvchi asosiy ma'lumotlari
                await cur.execute("""
                    SELECT points, status, health_mode, joined_at 
                    FROM users WHERE user_id = %s
                """, (uid,))
                user = await cur.fetchone()
                
                if not user:
                    await (query.answer("❌ Profil topilmadi", show_alert=True) if query else update.message.reply_text("❌ Profil topilmadi."))
                    return

                # 2. Tarixiy ma'lumotlarni hisoblash
                await cur.execute("SELECT COUNT(*) as total FROM history WHERE user_id = %s", (uid,))
                hist_res = await cur.fetchone()
                history_count = hist_res['total']

        # 3. Vizual formatlash
        status_icon = "💎 <b>VIP</b>" if user['status'] == 'vip' else "👤 <b>Oddiy foydalanuvchi</b>"
        health_status = "✅ <b>Yoqilgan</b>" if user['health_mode'] == 1 else "❌ <b>O'chirilgan</b>"
        
        text = (
            f"<b>🏠 SHAXSIY KABINET</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🆔 <b>Sizning ID:</b> <code>{uid}</code>\n"
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


async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Murojaat turini tanlash (Conversation boshlanishi)"""
    # 7-BAND: Obunani tekshirish (faqat a'zolar murojaat qila olishi uchun)
    uid = update.effective_user.id
    
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

#=======================================================================================================

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

#=======================================================================================================

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
#=======================================================================================================

# === 1. AVVAL FILTRLARNI ANIQLAB OLAMIZ ===
MENU_TEXTS = [
    "🔍 Anime qidirish 🎬", "🔥 Trenddagilar", 
    "👤 Shaxsiy Kabinet", "🎁 Ballar & VIP",
    "🤝 Muxlislar Klubi", "📂 Barcha animelar",
    "✍️ Murojaat & Shikoyat", "📖 Qo'llanma ❓", "🛠 ADMIN PANEL"
]

# Faqat menyu tugmasi bo'lmagan matnlarni qabul qiluvchi filtr
# Bu filtr qidiruv rejimida menyu tugmasi bosilsa, qidiruvni auto-stop qilish uchun kerak
search_filter = filters.TEXT & ~filters.COMMAND & ~filters.Text(MENU_TEXTS)
menu_filter = filters.Regex(
        "Anime qidirish|VIP PASS|Bonus ballarim|Qo'llanma|Barcha anime ro'yxati|ADMIN PANEL|Bekor qilish|"
        "🎙 Fandablar|❤️ Sevimlilar|🤝 Do'st orttirish|Rasm orqali qidirish"
    )
# === 2. MAIN FUNKSIYASI ===
def main():
    # Application yaratish
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # --- HANDLERLARNI QO'SHISH TARTIBI MUHIM ---

    # 1. Inline Query (Tezkor qidiruv uchun)
    application.add_handler(InlineQueryHandler(inline_query_search))

    # 2. Qidiruv bo'limi uchun ConversationHandler
    search_conv = ConversationHandler(
        entry_points=[
            # "🔍 Anime qidirish 🎬" tugmasi bosilganda boshlanadi
            MessageHandler(filters.Text("🔍 Anime qidirish 🎬"), search_menu_cmd)
        ],
        states={
            # Holat: Tanlov menyusi (Nomi, ID yoki AI tugmalari)
            A_ANI_CONTROL: [
                CallbackQueryHandler(search_anime_logic, pattern="^search_type_"),
                CallbackQueryHandler(search_menu_cmd, pattern="^back_to_search$")
            ],
            A_SEARCH_BY_ID: [
                # select_ani_ pattern koddagi buttons.append ga moslandi
                CallbackQueryHandler(search_anime_logic, pattern="^select_ani_"), 
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_filter, search_anime_logic),
            ],
            A_SEARCH_BY_NAME: [
                CallbackQueryHandler(search_anime_logic, pattern="^select_ani_"), 
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_filter, search_anime_logic),
            ],
            
            # Holat: Rasm kutish
            
        },
        fallbacks=[
            # Agar foydalanuvchi qidiruvdan chiqmoqchi bo'lib menyu tugmasini bossa
            MessageHandler(filters.Text(MENU_TEXTS), start),
            # /start komandasi har doim qidiruvni buzadi
            CommandHandler("start", start),
            # Bekor qilish tugmasi
            CallbackQueryHandler(search_menu_cmd, pattern="^cancel_search$")
        ],
        name="search_conversation",
        persistent=False,
        allow_reentry=True
    )

    # 3. Handlerlarni registratsiya qilish
    application.add_handler(search_conv)
    
    # Start va Recheck (Majburiy obuna) handlerlari
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(recheck_callback, pattern="^recheck$"))
    
    # Ro'yxatdan anime tanlangandagi callback (select_ani_...)
    # Bu search_conv dan tashqarida bo'lishi mumkin yoki ichiga qo'shish ham mumkin
    application.add_handler(CallbackQueryHandler(search_anime_logic, pattern="^select_ani_"))
    # 1. Anime haqida ma'lumot (Tavsif, rasm, janr)
    # Bu handler sizning bazadan animeni topish kodingizda bo'ladi
    application.add_handler(CallbackQueryHandler(show_anime_details, pattern=r"^show_anime_"))

    # 2. "Qismlarni ko'rish" tugmasi bosilganda
    application.add_handler(CallbackQueryHandler(show_episodes_list, pattern=r"^show_episodes_"))

    # 3. Varaqlash (Keyingi/Oldingi) tugmalari bosilganda
    application.add_handler(CallbackQueryHandler(handle_pagination, pattern=r"^page_"))

    # 4. Epizod tanlanganda (Video yuborish)
    application.add_handler(CallbackQueryHandler(get_episode_handler, pattern=r"^get_ep_"))
    
    

    # --- BOTNI ISHGA TUSHIRISH ---
    logger.info("🚀 Bot polling rejimida ishga tushdi...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    # Flask (Web server) fonda ishga tushadi (Render uchun kerak)
    flask_thread = Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000))), daemon=True)
    flask_thread.start()
    
    # Botni ishga tushirish
    main()

