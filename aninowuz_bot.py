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

# ====================== CONVERSATION STATES ======================
# Yangi professional qidiruv mantiqi uchun holatlar (Optimallashtirildi)
(
    A_ADD_CH,            # 0: Kanal qo'shish
    A_REM_CH,            # 1: Kanal o'chirish
    A_ADD_ADM,           # 2: Yangi admin ID sini qabul qilish
    A_CONFIRM_REM_ADM,   # 3: Adminni o'chirishni tasdiqlash
    A_ADD_VIP,           # 4: VIP foydalanuvchi qo'shish
    A_REM_VIP,           # 5: VIP-ni bekor qilish
    A_ADD_ANI_POSTER,    # 6: Anime posterini qabul qilish
    A_ADD_ANI_DATA,      # 7: Anime ma'lumotlarini qabul qilish
    A_SEND_ADS_PASS,     # 8: Reklama parolini tekshirish
    A_SEND_ADS_MSG,      # 9: Reklama xabarini tarqatish
    A_SEARCH_BY_ID,      # 10: ID orqali qidirish
    A_SEARCH_BY_NAME     # 11: Nomi orqali qidirish
) = range(12)

# Loglash sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)




# ====================== MA'LUMOTLAR BAZASI (TUZATILGAN VA OPTIMAL) ======================

def get_db():
    try:
        # DB_CONFIG o'rniga to'g'ridan-to'g'ri os.getenv ishlatish Render uchun ishonchliroq
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", 3306)),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            database=os.getenv("DB_NAME"),
            # 'ssl_mode' xatosini oldini olish uchun uni 'ssl_disabled' ga almashtiramiz 
            # yoki butunlay olib tashlaymiz. Aksariyat bulutli bazalar buni avtomatik hal qiladi.
            autocommit=True,
            connection_timeout=30
        )
        return conn
    except mysql.connector.Error as err:
        logger.error(f"❌ Ma'lumotlar bazasiga ulanishda xato: {err}")
        return None

def init_db():
    """Jadvallarni yaratish va tuzatish"""
    conn = get_db()
    if not conn:
        logger.error("❌ Bazaga ulanib bo'lmagani uchun jadvallar yaratilmadi.")
        return
    
    cur = conn.cursor()
    try:
        # 1. Foydalanuvchilar jadvali
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY, 
            joined_at DATETIME, 
            bonus INT DEFAULT 0,
            status VARCHAR(20) DEFAULT 'user'
        )""")

        # 2. Animelar jadvali 
        # FULLTEXT ba'zi serverlarda xato berishi mumkin, shuning uchun oddiy INDEX ishlatamiz
        cur.execute("""CREATE TABLE IF NOT EXISTS anime_list (
            anime_id VARCHAR(50) PRIMARY KEY, 
            name VARCHAR(255), 
            poster_id TEXT,
            INDEX (name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

        # 3. Anime qismlari jadvali
        cur.execute("""CREATE TABLE IF NOT EXISTS anime_episodes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            anime_id VARCHAR(50),
            episode INT,
            lang VARCHAR(50),
            file_id TEXT,
            FOREIGN KEY (anime_id) REFERENCES anime_list(anime_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
        
        # 4. Kanallar jadvali (Check-sub uchun)
        cur.execute("""CREATE TABLE IF NOT EXISTS channels (
            username VARCHAR(255) PRIMARY KEY
        )""")

        # 5. Adminlar jadvali
        cur.execute("""CREATE TABLE IF NOT EXISTS admins (
            user_id BIGINT PRIMARY KEY
        )""")
        
        conn.commit()
        print("✅ Ma'lumotlar bazasi muvaffaqiyatli tayyorlandi.")
    except Exception as e:
        print(f"❌ Jadvallarni yaratishda xatolik: {e}")
    finally:
        cur.close()
        conn.close()
        


# ====================== YORDAMCHI FUNKSIYALAR (TUZATILDI) ======================

async def get_user_status(uid):
    """Foydalanuvchi statusini aniqlash (Main Admin, Admin, VIP yoki Oddiy foydalanuvchi)"""
    if uid == MAIN_ADMIN_ID: 
        return "main_admin"
    
    conn = get_db()
    if not conn: 
        return "user"
    
    cur = conn.cursor()
    try:
        # 1. Avval 'admins' jadvalini tekshiramiz
        cur.execute("SELECT user_id FROM admins WHERE user_id=%s", (uid,))
        if cur.fetchone():
            return "admin"
            
        # 2. Keyin 'users' jadvalidagi umumiy statusni (vip/user) tekshiramiz
        cur.execute("SELECT status FROM users WHERE user_id=%s", (uid,))
        res = cur.fetchone()
        return res[0] if res else "user"
    except Exception as e:
        logger.error(f"Status aniqlashda xato: {e}")
        return "user"
    finally:
        cur.close()
        conn.close()

async def check_sub(uid, bot):
    """Majburiy obunani tekshirish mantiqi"""
    conn = get_db()
    if not conn: 
        return []
    
    cur = conn.cursor()
    try:
        cur.execute("SELECT username FROM channels")
        channels = cur.fetchall()
    except Exception as e:
        logger.error(f"Kanallarni olishda xato: {e}")
        return []
    finally:
        cur.close()
        conn.close()
    
    not_joined = []
    for (ch,) in channels:
        try:
            # Username formatini to'g'irlash
            target = str(ch)
            if not target.startswith('@') and not target.startswith('-'):
                target = f"@{target}"
                
            member = await bot.get_chat_member(target, uid)
            if member.status not in ['member', 'administrator', 'creator']: 
                not_joined.append(ch)
        except Exception as e:
            # Agar bot kanalga admin bo'lmasa yoki kanal topilmasa xato beradi
            logger.warning(f"Obunani tekshirishda xato ({ch}): {e}")
            not_joined.append(ch)
            
    return not_joined
    
    

# ====================== KLAVIATURALAR (TUZATILDI) ======================

def get_main_kb(status):
    """
    Asosiy menyu klaviaturasi. 
    Status funksiya tashqarisida (get_user_status orqali) aniqlanib uzatiladi.
    """
    kb = [
        [KeyboardButton("🔍 Anime qidirish 🎬")],
        [KeyboardButton("🎁 Bonus ballarim 💰"), KeyboardButton("💎 VIP bo'lish ⭐")],
        [KeyboardButton("📜 Barcha anime ro'yxati 📂"), KeyboardButton("📖 Qo'llanma ❓")]
    ]
    
    # Statusga qarab Admin Panel tugmasini qo'shish
    if status in ["main_admin", "admin"]:
        kb.append([KeyboardButton("🛠 ADMIN PANEL")])
    
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)



def get_admin_kb(is_main=False):
    """Admin panel ichidagi inline tugmalar"""
    buttons = [
        [
            InlineKeyboardButton("📢 Kanallar", callback_data="adm_ch"), 
            InlineKeyboardButton("🎬 Anime Qo'shish", callback_data="adm_ani_add")
        ],
        [
            InlineKeyboardButton("💎 VIP Qo'shish", callback_data="adm_vip_add"), 
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



def get_cancel_kb():
    """Jarayonlarni bekor qilish uchun 'Orqaga' tugmasi"""
    return ReplyKeyboardMarkup([[KeyboardButton("⬅️ Orqaga")]], resize_keyboard=True)
    
    
    

# ====================== ASOSIY ISHLOVCHILAR (TUZATILGAN VA TO'LIQ) ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Botni ishga tushirish va foydalanuvchini ro'yxatga olish"""
    uid = update.effective_user.id
    status = await get_user_status(uid)
    
    conn = get_db()
    if conn:
        cur = conn.cursor()
        cur.execute("INSERT IGNORE INTO users (user_id, joined_at, status) VALUES (%s, %s, 'user')", 
                    (uid, datetime.datetime.now()))
        conn.commit(); cur.close(); conn.close()
    
    not_joined = await check_sub(uid, context.bot)
    if not_joined:
        btn = [[InlineKeyboardButton(f"Obuna bo'lish ➕", url=f"https://t.me/{c.replace('@','')}") ] for c in not_joined]
        btn.append([InlineKeyboardButton("Tekshirish ✅", callback_data="recheck")])
        return await update.message.reply_text(
            "👋 Botdan foydalanish uchun kanallarga a'zo bo'ling:", 
            reply_markup=InlineKeyboardMarkup(btn)
        )
    
    await update.message.reply_text(
        "✨ Xush kelibsiz! Anime olamiga marhamat.", 
        reply_markup=get_main_kb(status)
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha inline tugmalar bosilishini boshqarish"""
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    status = await get_user_status(uid)
    await query.answer()

    # --- OBUNANI QAYTA TEKSHIRISH ---
    if data == "recheck":
        if not await check_sub(uid, context.bot):
            await query.message.delete()
            await context.bot.send_message(uid, "Tabriklaymiz! ✅ Obuna tasdiqlandi.", reply_markup=get_main_kb(status))
        else:
            await query.answer("❌ Hali hamma kanallarga a'zo emassiz!", show_alert=True)
        return

    # --- ANIME QIDIRUVNI BOSHLASH ---
    if data == "search_type_id":
        await query.edit_message_text("🆔 **Anime kodini (ID) yuboring:**", parse_mode="Markdown")
        return A_SEARCH_BY_ID

    elif data == "search_type_name":
        await query.edit_message_text("🔎 **Anime nomini kiriting:**", parse_mode="Markdown")
        return A_SEARCH_BY_NAME

    elif data == "cancel_search":
        context.user_data.pop('poster', None)
        context.user_data.pop('tmp_ani', None)
        if query.message: await query.message.delete()
        await context.bot.send_message(uid, "✅ Jarayon yakunlandi.", reply_markup=get_main_kb(status))
        return ConversationHandler.END

    # --- QIDIRUV NATIJALARI BILAN ISHLASH (YANGI QO'SHILDI) ---
    # Agar foydalanuvchi qism tugmasini bossa (get_ep_ID_EP)
    if data.startswith("get_ep_"):
        # Bu callback get_episode_handler funksiyasiga o'tishi kerak 
        # (Lekin biz uni main funksiyada alohida ulaymiz)
        pass

    # Admin bo'lmaganlar uchun quyidagi amallar yopiq
    if status not in ["main_admin", "admin"]: 
        return

    # --- ADMIN: ANIME QO'SHISH VA BOSHQARUV ---
    if data == "adm_ani_add":
        await query.message.reply_text("1️⃣ Anime uchun POSTER (rasm) yuboring:")
        return A_ADD_ANI_POSTER

    elif data == "add_more_ep":
        await query.message.reply_text(
            "🎞 Keyingi qism VIDEOSINI yuboring.\n\n⚠️ Captionda: `ID | Nomi | Tili | Qismi`", 
            parse_mode="Markdown"
        )
        return A_ADD_ANI_DATA

    elif data == "adm_ch":
        kb = [[InlineKeyboardButton("➕ Qo'shish", callback_data="add_channel_start"), 
               InlineKeyboardButton("❌ O'chirish", callback_data="rem_channel_start")],
              [InlineKeyboardButton("⬅️ Orqaga", callback_data="adm_back")]]
        await query.edit_message_text("📢 Kanallarni boshqarish:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "adm_stats":
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        u_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE status='vip'")
        v_count = cur.fetchone()[0]
        cur.close(); conn.close()
        text = f"📊 **Statistika:**\n\n👤 Jami: {u_count}\n💎 VIP: {v_count}"
        await query.message.reply_text(text, parse_mode="Markdown")
        return

    elif data == "adm_back":
        await query.edit_message_text("🛠 Boshqaruv paneli:", reply_markup=get_admin_kb(status == "main_admin"))
        return

    # Adminlarni boshqarish callbacklari
    elif data == "add_channel_start": return A_ADD_CH
    elif data == "rem_channel_start": return A_REM_CH
    elif data == "add_admin_start": return A_ADD_ADM
    elif data == "adm_vip_add": return A_ADD_VIP
    elif data == "adm_ads_start": 
        await query.message.reply_text("🔑 Reklama parolini kiriting:")
        return A_SEND_ADS_PASS

    return None

# ====================== ADMIN VA QO'SHIMCHA ISHLOVCHILAR (YETISHMAYOTGAN) ======================

async def exec_add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kanal qo'shish ijrosi"""
    text = update.message.text.strip()
    username = text if text.startswith('@') or text.startswith('-') else f"@{text}"
    
    conn = get_db()
    if not conn: return ConversationHandler.END
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO channels (username) VALUES (%s)", (username,))
        conn.commit()
        await update.message.reply_text(f"✅ Kanal qo'shildi: {username}")
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {e}")
    finally:
        cur.close(); conn.close()
    return ConversationHandler.END

async def exec_rem_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kanalni o'chirish ijrosi"""
    text = update.message.text.strip()
    username = text if text.startswith('@') or text.startswith('-') else f"@{text}"
    
    conn = get_db()
    if not conn: return ConversationHandler.END
    cur = conn.cursor()
    cur.execute("DELETE FROM channels WHERE username=%s", (username,))
    conn.commit()
    cur.close(); conn.close()
    
    await update.message.reply_text(f"🗑 Kanal o'chirildi: {username}")
    return ConversationHandler.END

async def exec_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin qo'shish ijrosi"""
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ Xato! Foydalanuvchi ID raqamini yuboring.")
        return A_ADD_ADM

    conn = get_db()
    if not conn: return ConversationHandler.END
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO admins (user_id) VALUES (%s)", (int(text),))
        conn.commit()
        await update.message.reply_text(f"👮 Yangi admin qo'shildi: {text}")
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {e}")
    finally:
        cur.close(); conn.close()
    return ConversationHandler.END

async def show_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi bonusini ko'rsatish"""
    uid = update.effective_user.id
    conn = get_db()
    if not conn: return
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT bonus, status FROM users WHERE user_id=%s", (uid,))
    res = cur.fetchone()
    cur.close(); conn.close()
    
    val = res['bonus'] if res else 0
    st = res['status'] if res else "user"
    await update.message.reply_text(f"💰 Ballaringiz: {val}\n⭐ Status: {st.upper()}")
    
async def show_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 **Qo‘llanma**\n\n"
        "🔍 *Anime qidirish* — anime nomi yoki ID orqali topish\n"
        "🎁 *Bonus ballarim* — sizning ballaringiz\n"
        "💎 *VIP bo‘lish* — VIP imkoniyatlar\n"
        "📜 *Anime ro‘yxati* — mavjud animelar\n\n"
        "❓ Savollar bo‘lsa admin bilan bog‘laning"
    )
    await update.message.reply_text(text, parse_mode="Markdown")    

    
async def vip_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchiga VIP haqida ma'lumot va admin linkini yuborish"""
    text = (
        "💎 **VIP STATUS IMKONIYATLARI:**\n\n"
        "✅ Reklamasiz ko'rish\n"
        "✅ Yangi qismlarni birinchilardan bo'lib ko'rish\n"
        "✅ Maxsus guruhga a'zolik\n\n"
        "💳 VIP status sotib olish uchun adminga murojaat qiling:\n"
        "👉 @SizningUsername" # <--- BU YERGA O'Z USERNAME-INGIZNI YOZING
    )
    await update.message.reply_text(text, parse_mode="Markdown")


    
# ====================== ANIME QIDIRISH VA PAGINATION (TUZATILDI) ======================

async def search_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qidiruv turini tanlash menyusi"""
    kb = [
        [InlineKeyboardButton("🆔 ID orqali qidirish", callback_data="search_type_id")],
        [InlineKeyboardButton("🔎 Nomi orqali qidirish", callback_data="search_type_name")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_search")]
    ]
    await update.message.reply_text(
        "🎬 **Anime qidirish bo'limi**\n\nQidiruv usulini tanlang:", 
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

async def search_anime_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anime nomi yoki ID bo'yicha qidirish mantiqi"""
    if not update.message or not update.message.text:
        return
        
    text = update.message.text.strip()
    uid = update.effective_user.id
    status = await get_user_status(uid)
    
    if text == "⬅️ Orqaga":
        await update.message.reply_text("Bosh menyu", reply_markup=get_main_kb(status))
        return ConversationHandler.END

    conn = get_db()
    if not conn:
        await update.message.reply_text("❌ Bazaga ulanishda xato.")
        return ConversationHandler.END

    cur = conn.cursor(dictionary=True)
    
    # ID yoki Nom bo'yicha qidirish (Optimallashtirildi)
    if text.isdigit():
        cur.execute("SELECT * FROM anime_list WHERE anime_id=%s", (text,))
    else:
        cur.execute("SELECT * FROM anime_list WHERE name LIKE %s", (f"%{text}%",))
    
    anime = cur.fetchone()
    
    if not anime:
        await update.message.reply_text(
            f"😔 `{text}` bo'yicha hech narsa topilmadi.\n\n"
            "Iltimos, ID raqamni yoki nomini qayta tekshirib ko'ring:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ To'xtatish", callback_data="cancel_search")]])
        )
        return # Foydalanuvchi qayta kiritishi uchun state'da qoladi

    # Anime qismlarini olish
    cur.execute("SELECT episode FROM anime_episodes WHERE anime_id=%s ORDER BY episode ASC", (anime['anime_id'],))
    episodes = cur.fetchall()
    cur.close(); conn.close()

    if not episodes:
        await update.message.reply_text("⚠️ Bu anime topildi, lekin qismlar hali yuklanmagan.")
        return ConversationHandler.END

    # Pagination Keyboard (Dastlabki 10 ta qism)
    keyboard = []
    row = []
    for ep in episodes[:10]:
        row.append(InlineKeyboardButton(str(ep['episode']), callback_data=f"get_ep_{anime['anime_id']}_{ep['episode']}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    
    if len(episodes) > 10:
        keyboard.append([InlineKeyboardButton("Keyingi ➡️", callback_data=f"page_{anime['anime_id']}_10")])

    await update.message.reply_photo(
        photo=anime['poster_id'],
        caption=f"🎬 **{anime['name']}**\n🆔 ID: `{anime['anime_id']}`\n\nQuyidagi qismlardan birini tanlang 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def get_episode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qism tugmasi bosilganda videoni yuborish (SIZDA SHU QISM YO'Q EDI)"""
    query = update.callback_query
    data = query.data.split("_") # get_ep_ID_EPISODE
    
    anime_id = data[2]
    episode_num = data[3]
    
    await query.answer("Video yuklanmoqda...")
    
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM anime_episodes WHERE anime_id=%s AND episode=%s", (anime_id, episode_num))
    episode_data = cur.fetchone()
    
    cur.execute("SELECT name FROM anime_list WHERE anime_id=%s", (anime_id,))
    anime_info = cur.fetchone()
    cur.close(); conn.close()

    if episode_data:
        try:
            await query.message.reply_video(
                video=episode_data['file_id'],
                caption=f"🎬 **{anime_info['name']}**\n🔢 **{episode_num}-qism**\n\n✅ @SizningKanalingiz"
            )
        except Exception as e:
            await query.message.reply_text(f"❌ Videoni yuborishda xatolik: {e}")
    else:
        await query.answer("❌ Video topilmadi!", show_alert=True)

async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sahifadan sahifaga o'tish"""
    query = update.callback_query
    parts = query.data.split("_")
    aid = parts[1]
    offset = int(parts[2])
    
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT episode FROM anime_episodes WHERE anime_id=%s ORDER BY episode ASC", (aid,))
    episodes = cur.fetchall()
    cur.close(); conn.close()

    keyboard = []
    row = []
    display_eps = episodes[offset:offset+10]
    
    for ep in display_eps:
        row.append(InlineKeyboardButton(str(ep['episode']), callback_data=f"get_ep_{aid}_{ep['episode']}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)

    nav_buttons = []
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"page_{aid}_{offset-10}"))
    if offset + 10 < len(episodes):
        nav_buttons.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"page_{aid}_{offset+10}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)

    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
    await query.answer()
    
    

    
    

# ====================== CONVERSATION STEPS (TUZATILDI) ======================

async def add_ani_poster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anime posterini qabul qilish"""
    context.user_data['poster'] = update.message.photo[-1].file_id
    await update.message.reply_text(
        "✅ Poster qabul qilindi.\n\n"
        "Endi **VIDEONI** yuboring.\n\n"
        "⚠️ **DIQQAT:** Video ostiga (caption) quyidagi ma'lumotni yozing:\n"
        "`ID | Nomi | Tili | Qismi`", 
        parse_mode="Markdown"
    )
    return A_ADD_ANI_DATA

async def add_ani_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anime ma'lumotlarini va videoni birga yoki ketma-ket qabul qilish"""
    uid = update.effective_user.id
    status = await get_user_status(uid)
    
    # Videoni va uning captionidagi ma'lumotni olish
    if update.message.video:
        v_id = update.message.video.file_id
        caption = update.message.caption
        
        if not caption or "|" not in caption:
            await update.message.reply_text(
                "❌ Xato! Video captioniga ma'lumotni yozmadingiz.\n"
                "Format: `ID | Nomi | Tili | Qismi`", 
                parse_mode="Markdown"
            )
            return A_ADD_ANI_DATA

        try:
            # Ma'lumotlarni ajratib olish
            parts = [i.strip() for i in caption.split("|")]
            if len(parts) < 4:
                raise ValueError("Ma'lumotlar yetarli emas")
                
            aid, name, lang, ep = parts
            p_id = context.user_data.get('poster')

            if not p_id:
                await update.message.reply_text("❌ Poster topilmadi. Avval rasm yuboring.")
                return A_ADD_ANI_POSTER

            conn = get_db()
            cur = conn.cursor()
            
            # 1. Anime listini yangilash
            cur.execute("""
                INSERT INTO anime_list (anime_id, name, poster_id) 
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE name=%s, poster_id=%s
            """, (aid, name, p_id, name, p_id))
            
            # 2. Qismni qo'shish
            cur.execute("""
                INSERT INTO anime_episodes (anime_id, episode, lang, file_id) 
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE file_id=%s, lang=%s
            """, (aid, ep, lang, v_id, v_id, lang))
            
            conn.commit()
            cur.close(); conn.close()

            # Tezkor yuklash tugmalari
            kb = [
                [InlineKeyboardButton("➕ Keyingi qismni qo'shish", callback_data="add_more_ep")],
                [InlineKeyboardButton("✅ Jarayonni yakunlash", callback_data="cancel_search")]
            ]
            
            await update.message.reply_text(
                f"✅ **Muvaffaqiyatli saqlandi!**\n\n"
                f"📺 Anime: {name}\n"
                f"🔢 Qism: {ep}\n\n"
                f"Keyingi qismni qo'shasizmi yoki tugatasizmi?",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="Markdown"
            )
            return ConversationHandler.END # Tugma bosilganda handle_callback orqali qayta kiradi

        except Exception as e:
            await update.message.reply_text(f"❌ Xatolik: {e}\nFormatni tekshiring: `ID | Nomi | Tili | Qismi`")
            return A_ADD_ANI_DATA

    else:
        await update.message.reply_text("Iltimos, videoni caption (matn) bilan birga yuboring.")
        return A_ADD_ANI_DATA
        
    
            

# ====================== QO'SHIMCHA FUNKSIYALAR (TUZATILGAN) ======================

async def check_ads_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reklama parolini tekshirish va xabar so'rash"""
    if update.message.text == ADVERTISING_PASSWORD:
        await update.message.reply_text(
            "✅ Parol tasdiqlandi! \n\nEndi barcha foydalanuvchilarga yubormoqchi bo'lgan **reklama xabaringizni** yuboring (Rasm, Video, Matn yoki Post):"
        )
        return A_SEND_ADS_MSG
    else:
        status = await get_user_status(update.effective_user.id)
        await update.message.reply_text("❌ Parol noto'g'ri!", reply_markup=get_main_kb(status))
        return ConversationHandler.END

async def ads_send_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reklamani barcha foydalanuvchilarga tarqatish"""
    msg = update.message
    conn = get_db()
    if not conn:
        await update.message.reply_text("❌ Bazaga ulanib bo'lmadi.")
        return ConversationHandler.END
        
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()
    cur.close(); conn.close()

    count = 0
    status = await get_user_status(update.effective_user.id)
    status_msg = await update.message.reply_text(f"🚀 Reklama yuborish boshlandi (0/{len(users)})...")

    for user in users:
        try:
            # copy_message - caption va tugmalar bilan xabarni ko'chirib beradi
            await context.bot.copy_message(
                chat_id=user[0],
                from_chat_id=update.effective_chat.id,
                message_id=msg.message_id
            )
            count += 1
            await asyncio.sleep(0.05) # Telegram limitlariga tushmaslik uchun kichik kechikish

            if count % 50 == 0:
                await status_msg.edit_text(f"🚀 Reklama yuborilmoqda ({count}/{len(users)})...")
        except Exception:
            continue

    await update.message.reply_text(
        f"✅ Reklama yakunlandi. {count} ta foydalanuvchiga yuborildi.", 
        reply_markup=get_main_kb(status)
    )
    return ConversationHandler.END

async def export_all_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha animelar ro'yxatini JSON fayl qilib yuborish"""
    if update.callback_query:
        await update.callback_query.answer("Fayl tayyorlanmoqda...")
        
    msg = update.effective_message
    conn = get_db()
    if not conn:
        await msg.reply_text("❌ Bazaga ulanishda xato.")
        return

    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM anime_list")
        animes = cur.fetchall()
        cur.close(); conn.close()
        
        if not animes:
            await msg.reply_text("📭 Bazada anime yo'q.")
            return

        file_name = "anime_list.json"
        with open(file_name, "w", encoding="utf-8") as f:
            json.dump(animes, f, indent=4, default=str, ensure_ascii=False)
        
        with open(file_name, "rb") as doc:
            await msg.reply_document(
                document=doc, 
                caption=f"🎬 **Barcha animelar bazasi**\n📊 Jami: {len(animes)} ta.",
                parse_mode="Markdown"
            )
    except Exception as e:
        await msg.reply_text(f"❌ Eksportda xatolik: {e}")

async def exec_vip_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchini VIP qilish ijrosi"""
    status = await get_user_status(update.effective_user.id)
    if not update.message.text:
        return A_ADD_VIP
        
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ Xato! Faqat ID (raqam) yuboring.")
        return A_ADD_VIP

    try:
        target_id = int(text)
        conn = get_db(); cur = conn.cursor()
        cur.execute("UPDATE users SET status = 'vip' WHERE user_id = %s", (target_id,))
        conn.commit(); cur.close(); conn.close()
        
        await update.message.reply_text(
            f"✅ Foydalanuvchi {target_id} muvaffaqiyatli VIP qilindi.", 
            reply_markup=get_main_kb(status)
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {e}")
    
    return ConversationHandler.END
    


# ====================== MAIN FUNKSIYA (TO'G'RILANGAN VARIANT) ======================

def main():
    # Hostingda o'chib qolmasligi uchun web-server
    keep_alive()
    
    # Bazani tayyorlash
    init_db()

    # Botni qurish
    app_bot = ApplicationBuilder().token(TOKEN).build()

    # 1. Conversation Handler (Admin va Qidiruv uchun)
    conv_handler = ConversationHandler(
        entry_points=[
            # Faqat callback tugmalar suhbatni boshlaydi
            CallbackQueryHandler(
                handle_callback,
                pattern="^(search_type_id|search_type_name|adm_ani_add|adm_ads_start|adm_vip_add|add_channel_start|rem_channel_start|add_admin_start|manage_admins)$"
            ),
            # Rasm qo'shib bo'lgach videoga o'tish uchun callback
            CallbackQueryHandler(lambda u, c: A_ADD_ANI_DATA, pattern="^add_more_ep$")
        ],
        states={
            # Har bir holatda FAQAT kutilgan ma'lumotni qabul qilamiz
            A_SEARCH_BY_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔍|📜|🎁|🛠|⬅️"), search_anime_logic)],
            A_SEARCH_BY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔍|📜|🎁|🛠|⬅️"), search_anime_logic)],

            A_ADD_CH: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔍|📜|🎁|🛠|⬅️"), exec_add_channel)],
            A_REM_CH: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔍|📜|🎁|🛠|⬅️"), exec_rem_channel)],
            A_ADD_ADM: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔍|📜|🎁|🛠|⬅️"), exec_add_admin)],

            A_ADD_ANI_POSTER: [MessageHandler(filters.PHOTO, add_ani_poster)],
            A_ADD_ANI_DATA: [MessageHandler(filters.VIDEO | (filters.TEXT & ~filters.Regex("^🔍|📜|🎁|🛠|⬅️")), add_ani_data)],

            A_SEND_ADS_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_ads_pass)],
            A_SEND_ADS_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.Regex("^🔍|📜|🎁|🛠|⬅️"), ads_send_finish)],
            A_ADD_VIP: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^🔍|📜|🎁|🛠|⬅️"), exec_vip_add)],
        },
        fallbacks=[
            # Agar foydalanuvchi /start bossa yoki menyu tugmasini bossa, suhbatni darhol tugatamiz
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^🔍 Anime qidirish 🎬$"), search_menu_cmd),
            MessageHandler(filters.Regex("^⬅️ Orqaga$"), start),
            CallbackQueryHandler(handle_callback, pattern="^cancel_search$")
        ],
        allow_reentry=True
    )

    # ================= HANDLERLARNI QO‘SHISH TARTIBI MUHIM =================

    # 1. Conversation (Bu birinchi turishi kerak, chunki u holatlarni nazorat qiladi)
    app_bot.add_handler(conv_handler)

    # 2. Start buyrug'i
    app_bot.add_handler(CommandHandler("start", start))

    # 3. Asosiy menyu (Reply Keyboard) - conv_handler ichidan tashqaridagi holatlar uchun
    app_bot.add_handler(MessageHandler(filters.Regex("^🔍 Anime qidirish 🎬$"), search_menu_cmd))
    app_bot.add_handler(MessageHandler(filters.Regex("^📜 Barcha anime ro'yxati 📂$"), export_all_anime))
    app_bot.add_handler(MessageHandler(filters.Regex("^🎁 Bonus ballarim 💰$"), show_bonus))
    app_bot.add_handler(MessageHandler(filters.Regex("^📖 Qo'llanma ❓$"), show_guide)) # BU YERDA YETISHMAYOTGAN EDI
    app_bot.add_handler(MessageHandler(filters.Regex("^💎 VIP bo'lish ⭐$"), vip_info)) 
    
    app_bot.add_handler(
        MessageHandler(
            filters.Regex("^🛠 ADMIN PANEL$"),
            lambda u, c: u.message.reply_text(
                "🛠 Admin paneli:",
                reply_markup=get_admin_kb(u.effective_user.id == MAIN_ADMIN_ID)
            )
        )
    )

    # 4. Callbacklar (Inline tugmalar uchun)
    app_bot.add_handler(CallbackQueryHandler(get_episode_handler, pattern="^get_ep_"))
    app_bot.add_handler(CallbackQueryHandler(handle_pagination, pattern="^page_"))
    app_bot.add_handler(CallbackQueryHandler(handle_callback))

    # ================= BOTNI ISHGA TUSHIRISH =================
    print("Bot muvaffaqiyatli ishga tushdi...")
    app_bot.run_polling()
    



if __name__ == "__main__":
    main()


























