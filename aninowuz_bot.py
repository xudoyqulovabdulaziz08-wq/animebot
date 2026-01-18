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
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
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
(
    # --- ADMIN & KANALLAR (0-5) ---
    A_ADD_CH,            # 0: Kanal qo'shish
    A_REM_CH,            # 1: Kanal o'chirish
    A_ADD_ADM,           # 2: Yangi admin ID sini qabul qilish
    A_CONFIRM_REM_ADM,    # 3: Adminni o'chirishni tasdiqlash
    A_ADD_VIP,           # 4: VIP foydalanuvchi qo'shish
    A_REM_VIP,           # 5: VIP-ni bekor qilish

    # --- REKLAMA VA QIDIRUV (6-12) ---
    A_SEND_ADS_PASS,      # 6: Reklama parolini tekshirish
    A_SELECT_ADS_TARGET,  # 7: Reklama nishonini tanlash
    A_SEND_ADS_MSG,       # 8: Reklama xabarini yuborish
    A_SEARCH_BY_ID,       # 9: ID orqali qidirish
    A_SEARCH_BY_NAME,     # 10: Nomi orqali qidirish

    # --- ANIME CONTROL PANEL (YANGI: 200+) ---
    A_ANI_CONTROL,       # 11: Anime control asosiy menyusi
    A_ADD_MENU,          # 12: Add Anime paneli (Yangi anime yoki yangi qism)
    
    # Yangi Anime qo'shish jarayoni
    A_GET_POSTER,        # 13: 1-qadam: Poster qabul qilish
    A_GET_DATA,          # 14: 2-qadam: Ma'lumotlarni qabul qilish (Nomi | Tili | Janri | Yili)
    A_ADD_EP_FILES,      # 15: 3-qadam: Ketma-ket video/qism qabul qilish
    
    # Mavjud animega qism qo'shish
    A_SELECT_ANI_EP,     # 16: Qism qo'shish uchun animeni tanlash (List)
    A_ADD_NEW_EP_FILES,  # 17: Tanlangan animega yangi videolar qabul qilish

    # Anime List va Ko'rish
    A_LIST_VIEW,         # 18: Animelar ro'yxatini ko'rish (Pagination 15 talik)

    # Anime/Qism o'chirish
    A_REM_MENU,          # 19: Remove Anime paneli (Anime yoki Qism tanlash)
    A_REM_ANI_LIST,      # 20: O'chirish uchun anime tanlash listi
    A_REM_EP_ANI_LIST,   # 23: Qismini o'chirish uchun anime tanlash
    A_REM_EP_NUM_LIST,    # 23: Tanlangan animening qismlarini tanlash (24 talik list)
    A_MAIN               #23 main funksiya
    

) = range(24) # Jami statuslar soni

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
            port=int(os.getenv("DB_PORT", 27624)),
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


# ===================================================================================


def init_db():
    """Ma'lumotlar bazasi jadvallarini yangilangan talablar asosida yaratish va sozlash"""
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
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

        # 2. Yangilangan Animelar jadvali (id, name, poster, lang, genre, year)
        # Eslatma: anime_id endi VARCHAR(50) emas, INT AUTO_INCREMENT bo'lgani ma'qul, 
        # chunki foydalanuvchi ID kiritishini osonlashtiradi.
        cur.execute("""CREATE TABLE IF NOT EXISTS anime_list (
            id INT AUTO_INCREMENT PRIMARY KEY, 
            name VARCHAR(255) NOT NULL, 
            poster_id TEXT,
            lang VARCHAR(100),
            genre VARCHAR(255),
            year VARCHAR(20),
            INDEX (name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

        # 3. Yangilangan Anime qismlari jadvali
        # episode_num - bot avtomatik sanashi uchun INT formatida
        cur.execute("""CREATE TABLE IF NOT EXISTS anime_episodes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            anime_id INT,
            episode_num INT,
            file_id TEXT,
            FOREIGN KEY (anime_id) REFERENCES anime_list(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
        
        # 4. Kanallar jadvali
        cur.execute("""CREATE TABLE IF NOT EXISTS channels (
            username VARCHAR(255) PRIMARY KEY
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

        # 5. Adminlar jadvali
        cur.execute("""CREATE TABLE IF NOT EXISTS admins (
            user_id BIGINT PRIMARY KEY
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
        
        conn.commit()
        print("✅ Ma'lumotlar bazasi yangi tizim uchun muvaffaqiyatli tayyorlandi.")
        
    except Exception as e:
        print(f"❌ Jadvallarni yaratishda xatolik: {e}")
        logger.error(f"Database Init Error: {e}")
    finally:
        cur.close()
        conn.close()


# ===================================================================================


async def get_all_channels():
    """Bazadan barcha kanallarni ro'yxat shaklida olish"""
    conn = get_db()
    if not conn: return []
    cur = conn.cursor(dictionary=True)
    try:
        # Username-ni id sifatida ham, nom sifatida ham ishlatamiz
        cur.execute("SELECT username as id, username FROM channels") 
        return cur.fetchall()
    finally:
        cur.close(); conn.close()


# ===================================================================================


async def delete_channel_by_id(ch_username):
    """Kanalni username orqali bazadan o'chirish"""
    conn = get_db()
    if not conn: return
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM channels WHERE username=%s", (ch_username,))
        conn.commit()
    finally:
        cur.close(); conn.close()       


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



# ===================================================================================


async def check_sub(uid, bot):
    """Majburiy obunani tekshirish (Tuzatilgan variant)"""
    # Main admin va adminlar uchun obunani tekshirmaslik (ixtiyoriy, qulaylik uchun)
    # if uid == MAIN_ADMIN_ID: return []

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
            target = str(ch).strip()
            # ID yoki Username ekanligini tekshirish
            if not target.startswith('@') and not target.startswith('-'):
                target = f"@{target}"
                
            member = await bot.get_chat_member(target, uid)
            # Agar foydalanuvchi guruh/kanaldan haydalgan bo'lsa (left yoki kicked)
            if member.status in ['left', 'kicked']:
                not_joined.append(ch)
        except Exception as e:
            # MUHIM: Agar bot kanalga admin bo'lmasa yoki kanal o'chib ketgan bo'lsa, 
            # foydalanuvchini ayblamaslik kerak. Shuning uchun bu kanalni tashlab o'tamiz.
            logger.warning(f"Kanalga bot admin emas yoki xato: {ch} -> {e}")
            continue # not_joined ga qo'shmaymiz!
            
    return not_joined



# ====================== KLAVIATURALAR (TUZATILDI) ======================

def get_main_kb(status):
    """
    Asosiy menyu klaviaturasi. 
    Status funksiya tashqarisida (get_user_status orqali) aniqlanib uzatiladi.
    """
    kb = [
        [KeyboardButton("🔍 Anime qidirish 🎬")],
        [KeyboardButton("🎁 Bonus ballarim 💰"), KeyboardButton("💎 VIP PASS")],
        [KeyboardButton("📜 Barcha anime ro'yxati 📂"), KeyboardButton("📖 Qo'llanma ❓")]
    ]
    
    # Statusga qarab Admin Panel tugmasini qo'shish
    if status in ["main_admin", "admin"]:
        kb.append([KeyboardButton("🛠 ADMIN PANEL")])
    
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)



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



def get_cancel_kb():
    """Jarayonlarni bekor qilish uchun 'Orqaga' tugmasi"""
    return ReplyKeyboardMarkup([[KeyboardButton("⬅️ Orqaga")]], resize_keyboard=True)
    
    
    

# ====================== ASOSIY ISHLOVCHILAR (TUZATILGAN VA TO'LIQ) ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Botni ishga tushirish, obunani tekshirish va Deep Linkni qayta ishlash"""
    uid = update.effective_user.id
    
    # --- 1. DEEP LINK TEKSHIRISH (Kanal orqali kelgan bo'lsa) ---
    if context.args and context.args[0].startswith("ani_"):
        anime_id = context.args[0].replace("ani_", "")
        context.user_data['pending_anime'] = anime_id  # Obuna bo'lguncha eslab qolamiz

    # --- 2. BAZAGA FOYDALANUVCHINI QO'SHISH ---
    conn = get_db()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("INSERT IGNORE INTO users (user_id, joined_at, status) VALUES (%s, %s, 'user')", 
                        (uid, datetime.datetime.now()))
            conn.commit()
            cur.close(); conn.close()
        except Exception as e:
            print(f"Baza xatosi (user add): {e}")

    # --- 3. OBUNANI TEKSHIRISH ---
    not_joined = await check_sub(uid, context.bot)
    if not_joined:
        btn = [[InlineKeyboardButton(f"Obuna bo'lish ➕", url=f"https://t.me/{c.replace('@','')}") ] for c in not_joined]
        btn.append([InlineKeyboardButton("Tekshirish ✅", callback_data="recheck")])
        
        msg = "👋 Botdan foydalanish uchun kanallarga a'zo bo'ling:"
        if 'pending_anime' in context.user_data:
            msg = "🎬 <b>Siz tanlagan animeni ko'rish uchun</b> avval kanallarga a'zo bo'lishingiz kerak:"

        return await update.message.reply_text(
            msg, 
            reply_markup=InlineKeyboardMarkup(btn),
            parse_mode="HTML"
        )
    
    # --- 4. OBUNA BO'LGAN BO'LSA VA ANIME KUTAYOTGAN BO'LSA ---
    if 'pending_anime' in context.user_data:
        ani_id = context.user_data.pop('pending_anime')
        return await show_specific_anime_by_id(update, context, ani_id)

    # --- 5. ASOSIY MENYU ---
    status = await get_user_status(uid)
    await update.message.reply_text(
        "✨ Xush kelibsiz botimizga! Anime olamiga marhamat.", 
        reply_markup=get_main_kb(status)
    )
    
    return ConversationHandler.END

    
# =============================================================================================

async def recheck_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    
    not_joined = await check_sub(uid, context.bot)
    
    if not not_joined: # Agar ro'yxat bo'sh bo'lsa (hamma kanalga a'zo)
        await query.message.delete()
        
        # Xotirada anime bormi?
        if 'pending_anime' in context.user_data:
            ani_id = context.user_data.pop('pending_anime')
            return await show_specific_anime_by_id(query, context, ani_id)
        
        # Agar yo'q bo'lsa, shunchaki asosiy menyu
        status = await get_user_status(uid)
        await query.message.reply_text("✅ Rahmat! Obuna tasdiqlandi.", reply_markup=get_main_kb(status))
    else:
        await query.answer("❌ Hali hamma kanallarga a'zo emassiz!", show_alert=True)


    
# =============================================================================================

async def show_specific_anime_by_id(update_or_query, context, ani_id):
    """ID bo'yicha bazadan animeni topib, tafsilotlarini chiqaradi"""
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM anime_list WHERE anime_id=%s", (ani_id,))
    anime = cur.fetchone()
    cur.close(); conn.close()
    
    if anime:
        # Avvalgi darslarda yaratgan funksiyamiz
        return await show_anime_details(update_or_query, anime, context)
    else:
        # Agar anime bazadan o'chib ketgan bo'lsa
        if hasattr(update_or_query, 'message'):
            await update_or_query.message.reply_text("❌ Kechirasiz, bu anime topilmadi.")
        else:
            await update_or_query.edit_message_text("❌ Kechirasiz, bu anime topilmadi.")

# ====================== ADMIN VA QO'SHIMCHA ISHLOVCHILAR (TO'G'RILANDI) ======================

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
        await update.message.reply_text(f"✅ Kanal qo'shildi: {username}\n\n/start bosib menyuga qayting.")
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik (Ehtimol bu kanal allaqachon bor): {e}")
    finally:
        cur.close(); conn.close()
    return ConversationHandler.END


# ===================================================================================


async def exec_rem_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kanalni o'chirish ijrosi"""
    text = update.message.text.strip()
    username = text if text.startswith('@') or text.startswith('-') else f"@{text}"
    
    conn = get_db()
    if not conn: return ConversationHandler.END
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM channels WHERE username=%s", (username,))
        conn.commit()
        await update.message.reply_text(f"🗑 Kanal o'chirildi: {username}\n\n/start bosib menyuga qayting.")
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {e}")
    finally:
        cur.close(); conn.close()
    return ConversationHandler.END


# ===================================================================================


async def exec_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin qo'shishdan oldin tasdiqlash so'rash"""
    text = update.message.text.strip()
    
    # Faqat raqamlardan iboratligini tekshirish
    if not text.isdigit():
        await update.message.reply_text(
            "❌ **Xato!** Foydalanuvchi ID raqamini yuboring (faqat raqamlar).\n\n"
            "Qayta urinib ko'ring yoki bekor qiling:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="manage_admins")]]),
            parse_mode="Markdown"
        )
        return A_ADD_ADM


    # Tasdiqlash tugmasini yaratish
    keyboard = [
        [InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"conf_adm_{text}")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="manage_admins")]
    ]
    
    await update.message.reply_text(
        f"👮 **Yangi admin qo'shishni tasdiqlaysizmi?**\n\n"
        f"👤 Foydalanuvchi ID: `{text}`\n\n"
        f"Tasdiqlash tugmasini bossangiz, bu foydalanuvchi admin huquqiga ega bo'ladi.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    # Eslatma: Bu yerda END qaytarmaymiz, callback_handler yakunlab qo'yadi
    return None 


# ===================================================================================


async def admin_control(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    uid = update.effective_user.id
    await query.answer()

    # MANA SHU QISM LABIRINTNI BUZADI VA ASOSIY ADMIN PANELGA QAYTARADI
    if data == "admin_main":
        status = await get_user_status(uid)
        is_main = (status == "main_admin")
        await query.edit_message_text(
            "🛠 **Admin paneliga xush kelibsiz:**",
            reply_markup=get_admin_kb(is_main),
            parse_mode="Markdown"
        )
        return ConversationHandler.END # <--- Jarayonni butunlay tugatish
        

# ===================================================================================


async def show_vip_removal_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    query = update.callback_query
    limit = 10
    offset = page * limit

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    
    # VIP foydalanuvchilar sonini aniqlash
    cur.execute("SELECT COUNT(*) as total FROM users WHERE status = 'vip'")
    total_vips = cur.fetchone()['total']
    
    # Joriy sahifa uchun ma'lumotlarni olish
    cur.execute("SELECT user_id FROM users WHERE status = 'vip' LIMIT %s OFFSET %s", (limit, offset))
    vips = cur.fetchall()
    cur.close(); conn.close()

    if not vips and page == 0:
        await query.edit_message_text(
            "📭 **VIP foydalanuvchilar ro'yxati bo'sh!**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="manage_vip")]]),
            parse_mode="Markdown"
        )
        return

    keyboard = []
    # Har bir VIP foydalanuvchi uchun alohida o'chirish tugmasi
    for v in vips:
        user_id = v['user_id']
        keyboard.append([InlineKeyboardButton(f"❌ O'chirish: {user_id}", callback_data=f"exec_rem_vip_{user_id}_{page}")])

    # Pagination tugmalari (Oldingi / Keyingi)
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"rem_vip_page_{page-1}"))
    if (page + 1) * limit < total_vips:
        nav_buttons.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"rem_vip_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="manage_vip")])

    text = f"🗑 **VIP O'CHIRISH BO'LIMI** (Jami: {total_vips})\n\nO'chirmoqchi bo'lgan foydalanuvchini tanlang: 👇"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    

# ----------------- CALLBACK HANDLER (MUHIM QISM) -----------------


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    # Foydalanuvchi statusini aniqlash (Adminlik huquqini tekshirish uchun)
    status = await get_user_status(uid)
    await query.answer()

    # ================= 1. HAMMA UCHUN OCHIQ CALLBACKLAR =================
    
    # Obunani qayta tekshirish
    if data == "recheck":
        if not await check_sub(uid, context.bot):
            await query.message.delete()
            await context.bot.send_message(uid, "Tabriklaymiz! ✅ Obuna tasdiqlandi.", reply_markup=get_main_kb(status))
        else:
            await query.answer("❌ Hali hamma kanallarga a'zo emassiz!", show_alert=True)
        return None
        
# ===================================================================================
    
    # 1. Qidiruv turlari tanlanganda
    if data == "search_type_id":
        await query.edit_message_text(
            text="🔢 **Anime ID raqamini kiriting:**", 
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_search_menu")
            ]]), 
            parse_mode="Markdown"
        )
        return A_SEARCH_BY_ID
        
    elif data == "search_type_name":
        await query.edit_message_text(
            text="📝 **Anime nomini kiriting:**", 
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_search_menu")
            ]]), 
            parse_mode="Markdown"
        )
        return A_SEARCH_BY_NAME

    # 2. Qidiruv menyusiga qaytish (Tanlov bosqichiga)
    elif data == "back_to_search_menu":
        search_btns = [
            [InlineKeyboardButton("🆔 ID orqali qidirish", callback_data="search_type_id")],
            [InlineKeyboardButton("🔎 Nomi orqali qidirish", callback_data="search_type_name")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_search")]
        ]
        await query.edit_message_text(
            text="🎬 **Anime qidirish bo'limi**\n\nQidiruv usulini tanlang:👇", 
            reply_markup=InlineKeyboardMarkup(search_btns),
            parse_mode="Markdown"
        )
        # BU YERDA END QAYTARMANG, CHUNKI FOYDALANUVCHI HALI QIDIRUV BO'LIMIDA
        return None 

    # 3. Haqiqiy bekor qilish (Butunlay qidiruvdan chiqish)
    elif data == "cancel_search":
        await query.edit_message_text("🏠 Jarayon yakunlandi. Menyudan foydalanishingiz mumkin.")
        await context.bot.send_message(
            chat_id=uid,
            text="Asosiy menyu:",
            reply_markup=get_main_kb(status)
        )
        return ConversationHandler.END

    # Sahifalash (Pagination) navigatsiyasini tutish
    # 1. Navigatsiyani tutish (Eng tepada)
    if data.startswith("pg_"):
        parts = data.split('_') # pg_viewani_1 -> ['pg', 'viewani', '1']
        prefix = parts[1]
        try:
            new_page = int(parts[-1])
        except:
            new_page = 0
        
        if prefix == "viewani":
            update.callback_query.data = f"list_ani_pg_{new_page}"
            return await list_animes_view(update, context)
        elif prefix == "delani":
            update.callback_query.data = f"rem_ani_list_{new_page}"
            # O'chirish listini qayta yuklaymiz
            kb = await get_pagination_keyboard("anime_list", page=new_page, prefix="delani_", extra_callback="rem_ani_menu")
            await query.edit_message_text("🗑 **O'chirish uchun anime tanlang:**", reply_markup=kb, parse_mode="Markdown")
            return A_REM_ANI_LIST
        elif prefix == "addepto":
            # Qism qo'shish uchun anime tanlash listi
            # query.data ni yangilab funksiyani chaqiramiz
            query.data = f"pg_{new_page}"
            return await select_ani_for_new_ep(update, context)
        elif prefix == "remep":
            # Qism o'chirish uchun anime tanlash listi
            query.data = f"pg_{new_page}"
            return await select_ani_for_rem_ep(update, context)
        return await query.answer()

     # --- ANIME CONTROL ASOSIY ---
    elif data == "adm_ani_ctrl" or data == "back_to_ctrl" or data == "admin_main":
        return await anime_control_panel(update, context)
    # --- ADD ANIME BO'LIMI ---
    elif data == "add_ani_menu":
        return await add_anime_panel(update, context)

    elif data == "start_new_ani":
        return await start_new_ani(update, context)

    elif data.startswith("new_ep_ani"): # Tugmadagi "new_ep_ani_" ni ham tutadi
        return await select_ani_for_new_ep(update, context)

    elif data.startswith("addepto_"):
        ani_id = data.split('_')[-1]
        context.user_data['cur_ani_id'] = ani_id
        
        conn = get_db(); cur = conn.cursor()
        # BU YERNI O'ZGARTIRDIK: id -> anime_id
        cur.execute("SELECT name FROM anime_list WHERE anime_id = %s", (ani_id,))
        res = cur.fetchone()
        context.user_data['cur_ani_name'] = res[0] if res else "Anime"
        cur.close(); conn.close()
        
        await query.edit_message_text(
            f"📥 **{context.user_data['cur_ani_name']}** uchun video yuboring:\n"
            f"(Bot avtomatik qism raqamini beradi)", 
            parse_mode="Markdown"
        )
        return A_ADD_EP_FILES

    # --- LIST ANIME BO'LIMI ---
    elif data.startswith("list_ani_pg_"):
        return await list_animes_view(update, context)

    elif data.startswith("viewani_"):
        return await show_anime_info(update, context)

    # --- REMOVE ANIME BO'LIMI ---
    elif data == "rem_ani_menu":
        return await remove_menu_handler(update, context)

    elif data == "rem_ep_menu" or data.startswith("rem_ep_list_"):
        return await select_ani_for_rem_ep(update, context)

    elif data.startswith("rem_ani_list_"):
        page = int(data.split('_')[-1])
        kb = await get_pagination_keyboard("anime_list", page=page, prefix="delani_", extra_callback="rem_ani_menu")
        await query.edit_message_text("🗑 **O'chirish uchun anime tanlang:**", reply_markup=kb, parse_mode="Markdown")
        return A_REM_ANI_LIST

    elif data.startswith("remep_"): 
        return await list_episodes_for_delete(update, context)

    elif data.startswith("delani_"):
        ani_id = data.split('_')[-1]
        kb = [
            [InlineKeyboardButton("✅ TASDIQLASH", callback_data=f"exec_del_{ani_id}")],
            [InlineKeyboardButton("❌ BEKOR QILISH", callback_data="rem_ani_menu")]
        ]
        await query.edit_message_text(
            f"⚠️ **DIQQAT!**\n\nID: {ani_id} bo'lgan animeni o'chirmoqchimisiz?", 
            reply_markup=InlineKeyboardMarkup(kb), 
            parse_mode="Markdown"
        )
        return A_REM_ANI_LIST

    elif data.startswith("exec_del_"):
        return await delete_anime_exec(update, context)

    elif data.startswith("ex_del_ep_"):
        ep_id = data.split('_')[-1]
        conn = get_db(); cur = conn.cursor()
        cur.execute("DELETE FROM anime_episodes WHERE id = %s", (ep_id,))
        conn.commit(); cur.close(); conn.close()
        await query.answer("✅ Qism o'chirildi!", show_alert=True)
        # Qayta ro'yxatni chiqarish yoki panelga qaytish
        return await anime_control_panel(update, context)

    elif data == "finish_add":
        await query.message.reply_text("✅ Jarayon yakunlandi.")
        return await anime_control_panel(update, context)

    elif data.startswith("get_ep_"):
        # Tugmadan ep_id ni olamiz (masalan: get_ep_25)
        ep_id = data.replace("get_ep_", "")
    
        conn = get_db()
        cur = conn.cursor()
        # Join orqali anime nomini ham birga olamiz
        cur.execute("""
            SELECT e.file_id, e.episode, a.name 
            FROM anime_episodes e 
            JOIN anime_list a ON e.anime_id = a.anime_id 
            WHERE e.id = %s
        """, (ep_id,))
        res = cur.fetchone()
        cur.close(); conn.close()
    
        if res:
            file_id, ep_num, ani_name = res
        
            # 1. Tugmani bosganda "yuklanmoqda" degan yozuvni yo'qotish
            await query.answer(f"⌛ {ani_name}: {ep_num}-qism yuborilmoqda...")
        
            # 2. Videoni oddiy xabar ko'rinishida yuborish
            # caption="" berilsa, videoning barcha eski matnlari o'chib ketadi
            await query.message.reply_video(
                video=file_id,
                caption=(
                    f"🎬 {ani_name}\n"
                    f"💿 {ep_num}-qism\n\n"
                    f"✨ @Aninovuz — Eng sara animelar manbasi!"
                ),
                parse_mode="Markdown"
            )
        else:
            await query.answer("❌ Kechirasiz, video fayl bazadan topilmadi.", show_alert=True)
        
    # MANA BU YERDA 'if' EMAS, 'elif' ISHLATISH KERAK:
    elif data == "rem_vip_list":
        await show_vip_removal_list(update, context, page=0)

    elif data.startswith("rem_vip_page_"):
        page = int(data.split("_")[3])
        await show_vip_removal_list(update, context, page=page)

    elif data.startswith("exec_rem_vip_"):
        parts = data.split("_")
        target_id = parts[3]
        current_page = int(parts[4])
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET status = 'user' WHERE user_id = %s", (target_id,))
        conn.commit()
        cur.close(); conn.close()
        
        await query.answer(f"✅ ID: {target_id} VIP ro'yxatidan o'chirildi!", show_alert=True)
        await show_vip_removal_list(update, context, page=current_page)

    # ================= VIP TASDIQLASH (ELIF VARIANTI) =================
    elif data.startswith("conf_vip_"):
        # callback_data dan ID raqamini ajratib olamiz (conf_vip_12345 -> 12345)
        target_id = data.split("_")[2]
        
        conn = get_db()
        if conn:
            cur = conn.cursor()
            try:
                # Foydalanuvchi statusini 'vip' ga o'zgartiramiz
                cur.execute("UPDATE users SET status = 'vip' WHERE user_id = %s", (target_id,))
                conn.commit()
                
                # Admin xabarini yangilaymiz
                await query.edit_message_text(
                    f"✅ **Muvaffaqiyatli!**\n\nFoydalanuvchi (ID: `{target_id}`) endi VIP statusiga ega.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ VIP Menu", callback_data="manage_vip")]]),
                    parse_mode="Markdown"
                )
                
                # Foydalanuvchiga xabar yuborish
                try:
                    await context.bot.send_message(
                        chat_id=target_id,
                        text="✨ Tabriklaymiz! Sizga VIP statusi berildi.\nEndi botdan cheklovsiz foydalanishingiz mumkin."
                    )
                except:
                    pass
                    
            except Exception as e:
                await query.answer(f"❌ Baza xatosi: {e}", show_alert=True)
            finally:
                cur.close(); conn.close()
        return None


    # ================= 2. FAQAT ADMINLAR UCHUN CALLBACKLAR =================
    
    if status not in ["main_admin", "admin"]:
        return None

    # Admin asosiy menyusiga qaytish
    if data == "admin_main" or data == "adm_back":
        is_main = (status == "main_admin")
        await query.edit_message_text("🛠 Admin paneli:", reply_markup=get_admin_kb(is_main))
        return ConversationHandler.END

    # KANALLAR BOSHQARUVI
    elif data == "adm_ch":
        keyboard = [
            [InlineKeyboardButton("➕ Qo'shish", callback_data="add_channel_start"),
             InlineKeyboardButton("❌ O'chirish", callback_data="rem_channel_start")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_main")]
        ]
        await query.edit_message_text("📢 Kanallarni boshqarish bo'limi:", reply_markup=InlineKeyboardMarkup(keyboard))
        return None

    # Kanal qo'shishni boshlash
    elif data == "add_channel_start":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="adm_ch")]])
        await query.edit_message_text(
            text="🔗 Qo'shmoqchi bo'lgan kanalingiz usernamesini yuboring:\n(Masalan: @kanal_nomi)",
            reply_markup=kb # Tugma chiqishi uchun bu shart
        )
        return A_ADD_CH

    elif data == "rem_channel_start":
        # Bazadan barcha kanallarni olamiz
        channels = await get_all_channels() 
        
        if not channels:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="adm_ch")]])
            await query.edit_message_text("📢 Hozircha majburiy obuna kanallari yo'q.", reply_markup=kb)
            return None

        keyboard = []
        for ch in channels:
            # ch['username'] yoki ch[1] - bazangiz tuzilishiga qarab
            ch_name = ch['username'] if isinstance(ch, dict) else ch[1]
            ch_id = ch['id'] if isinstance(ch, dict) else ch[0]
            
            # Har bir kanal uchun "O'chirish" tugmasi
            keyboard.append([InlineKeyboardButton(f"🗑 {ch_name}", callback_data=f"del_ch_{ch_id}")])
        
        # Orqaga qaytish tugmasi
        keyboard.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="adm_ch")])
        
        await query.edit_message_text(
            "🗑 **O'chirmoqchi bo'lgan kanalni tanlang:**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return None # Endi matn kutish shart emas, hamma narsa tugma orqali amalga oshadi
    
    # Kanalni o'chirishni qayta ishlash
    elif data.startswith("del_ch_"):
        ch_id = data.replace("del_ch_", "")
        
        # Bazadan o'chirish funksiyasi (buni o'zingiz yozgan bo'lishingiz kerak)
        await delete_channel_by_id(ch_id) 
        
        await query.answer("✅ Kanal o'chirildi!", show_alert=True)
        
        # Ro'yxatni yangilash uchun menyuni qayta chaqiramiz
        return await handle_callback(update, context) # yoki qaytadan kanallar ro'yxatini chiqarish

        # ANIME QO'SHISH BOSHLANISHI
    elif data == "adm_ani_add":
        # callback_data="admin_main" ga o'zgartirildi
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_main")]]) 
        await query.edit_message_text(
            "1️⃣ **Anime uchun POSTER (rasm) yuboring:**", 
            reply_markup=kb,
            parse_mode="Markdown"
        )
        return A_ADD_ANI_POSTER
        
    
# Statistika (Yangilangan: Anime soni + Edit Message)
    elif data == "adm_stats":
        conn = get_db()
        cur = conn.cursor()
        
        # 1. Jami foydalanuvchilar
        cur.execute("SELECT COUNT(*) FROM users")
        u_count = cur.fetchone()[0]
        
        # 2. VIP foydalanuvchilar
        cur.execute("SELECT COUNT(*) FROM users WHERE status='vip'")
        v_count = cur.fetchone()[0]
        
        # 3. Jami animelar (animes jadvali bor deb hisoblaymiz)
        try:
            cur.execute("SELECT COUNT(*) FROM anime_list")
            a_count = cur.fetchone()[0]
        except:
            a_count = 0 # Agar jadval hali yaratilmagan bo'lsa xato bermasligi uchun
            
        cur.close(); conn.close()
        
        # Chiroyli dizayndagi matn
        text = (
            "📊 **BOTNING UMUMIY STATISTIKASI**\n\n"
            f"👤 **Foydalanuvchilar:** `{u_count}` ta\n"
            f"💎 **VIP a'zolar:** `{v_count}` ta\n"
            f"🎬 **Jami animelar:** `{a_count}` ta\n\n"
            "🕒 _Ma'lumotlar avtomatik yangilandi._"
        )
        
        # Orqaga tugmasi - callback_data sizning admin menyu kodingizga mos bo'lishi kerak
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Asosiy menyuga qaytish", callback_data="admin_main")]
        ])
        
        # MUHIM: reply_text emas, edit_message_text ishlatamiz!
        await query.edit_message_text(
            text=text, 
            reply_markup=kb, 
            parse_mode="Markdown"
        )
        return None

    # REKLAMA YUBORISH BOSHLANISHI
    elif data == "adm_ads_start":
        # Orqaga qaytish admin panel bosh sahifasiga bo'lishi kerak
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_main")]])
        
        await query.edit_message_text(
            text="🔑 **Reklama parolini kiriting:**\n\n_Jarayonni bekor qilish uchun 'Orqaga' tugmasini bosing._", 
            reply_markup=kb,
            parse_mode="Markdown"
        )
        return A_SEND_ADS_PASS

    # 2. YANGI: Guruh tanlash joyidan PAROLGA qaytish
    elif data == "back_to_pass":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin_main")]])
        await query.edit_message_text(
            text="🔑 **Reklama parolini qaytadan kiriting:**",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        return A_SEND_ADS_PASS

    # Reklama kutish holatidan chiqamiz
    elif data == "admin_main":
        # Hamma qatorlar elif'dan 4 ta probel ichkarida bo'lishi shart:
        uid = query.from_user.id 
        status = await get_user_status(uid)
        
        await query.edit_message_text(
            text="👨‍💻 **Admin paneliga xush kelibsiz:**",
            reply_markup=get_admin_kb(),
            parse_mode="Markdown"
        )
        return A_MAIN  # Endi muammo hal bo'ldi


    elif data.startswith("send_to_"):
        target_group = data.split("_")[2]
        context.user_data['ads_target'] = target_group
        
        group_names = {
            "user": "👥 Oddiy foydalanuvchilar",
            "vip": "💎 VIP a'zolar",
            "admin": "👮 Adminlar",
            "all": "🌍 Barcha foydalanuvchilar"
        }
        
        # Xabarni yuborish so'ralganda "Orqaga" tugmasini ham qo'shamiz
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Guruhni o'zgartirish", callback_data="back_to_select_group")]
        ])
        
        await query.edit_message_text(
            text=f"🎯 Tanlangan guruh: **{group_names[target_group]}**\n\n"
                 "Endi ushbu guruhga yubormoqchi bo'lgan **reklama xabaringizni** yuboring:",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        return A_SEND_ADS_MSG

    elif data == "cancel_ads":
        await query.edit_message_text("❌ Reklama yuborish bekor qilindi.")
        return ConversationHandler.END

    # DB EXPORT (JSON)
    elif data == "adm_export":
        await export_all_anime(update, context)
        return None

    elif data == "back_to_select_group":
        # Guruhlar ro'yxati tugmalari (check_ads_pass dagi kabi)
        keyboard = [
            [InlineKeyboardButton("👥 Oddiy foydalanuvchilar (User)", callback_data="send_to_user")],
            [InlineKeyboardButton("💎 Faqat VIP a'zolar", callback_data="send_to_vip")],
            [InlineKeyboardButton("👮 Faqat Adminlar", callback_data="send_to_admin")],
            [InlineKeyboardButton("🌍 Barchaga (Hammaga)", callback_data="send_to_all")],
            [InlineKeyboardButton("⬅️ Parolga qaytish", callback_data="back_to_pass")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_ads")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🔄 **Guruhni qayta tanlang:**",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        # Holatni guruh tanlashga qaytaramiz
        return A_SELECT_ADS_TARGET


    # ADMINLARNI BOSHQARISH (ASOSIY MENYU)
    elif data == "manage_admins":
        if status == "main_admin":
            # Siz xohlagandek: Admin qo'shish, O'chirish va Orqaga tugmalari
            keyboard = [
                [InlineKeyboardButton("➕ Admin qo'shish", callback_data="add_admin_start")],
                [InlineKeyboardButton("🗑 Admin o'chirish", callback_data="rem_admin_list")],
                [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_main")]
            ]
            await query.edit_message_text(
                "👮 **Adminlarni boshqarish uchun quyidagilarni tanlang:** 👇",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            return None
        else:
            await query.answer("❌ Bu funksiya faqat asosiy admin uchun!", show_alert=True)

    # Admin qo'shishni boshlash (ID so'rash)
    elif data == "add_admin_start":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="manage_admins")]])
        await query.edit_message_text(
            "👮 **Yangi admin ID-sini yuboring:**", 
            reply_markup=kb,
            parse_mode="Markdown"
        )
        return A_ADD_ADM

    # Admin o'chirish uchun ro'yxatni chiqarish
    elif data == "rem_admin_list":
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT user_id FROM admins")
        admins = cur.fetchall()
        cur.close(); conn.close()
        
        if not admins:
            await query.answer("📭 Hozircha adminlar yo'q (Sizdan tashqari).", show_alert=True)
            return None
            
        keyboard = []
        for adm in admins:
            # Har bir admin uchun o'chirish tugmasi
            keyboard.append([InlineKeyboardButton(f"🗑 ID: {adm['user_id']}", callback_data=f"del_adm_{adm['user_id']}")])
        
        keyboard.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="manage_admins")])
        
        await query.edit_message_text(
            "🗑 **O'chirmoqchi bo'lgan adminni tanlang:**", 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return None

    # Adminni bazadan o'chirish ijrosi
    elif data.startswith("del_adm_"):
        adm_id = data.replace("del_adm_", "")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM admins WHERE user_id = %s", (adm_id,))
        conn.commit()
        cur.close(); conn.close()
        
        await query.answer(f"✅ Admin {adm_id} o'chirildi!", show_alert=True)
        # O'chirilgandan keyin ro'yxatni yangilab ko'rsatamiz
        return await handle_callback(update, context) # yoki qaytadan rem_admin_list chaqirish

    # Admin qo'shishni yakuniy TASDIQLASH (ID yuborilgandan keyin)
    elif data.startswith("conf_adm_"):
        new_id = data.replace("conf_adm_", "")
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO admins (user_id) VALUES (%s)", (new_id,))
            conn.commit()
            await query.edit_message_text(f"✅ ID: `{new_id}` muvaffaqiyatli admin qilib tayinlandi.", parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(f"❌ Xatolik: {e}")
        finally:
            cur.close(); conn.close()
        return ConversationHandler.END


  # ================= VIP CONTROL (ADMIN PANEL) =================
    if data == "adm_vip_add" or data == "manage_vip":
        keyboard = [
            [InlineKeyboardButton("➕ Add VIP User", callback_data="start_vip_add")],
            [InlineKeyboardButton("📜 VIP List", callback_data="vip_list")],
            [InlineKeyboardButton("🗑 Remove VIP", callback_data="rem_vip_list")],
            [InlineKeyboardButton("⬅️ Back", callback_data="admin_main")]
        ]
        await query.edit_message_text(
            "💎 **VIP CONTROL PANEL**\n\nKerakli bo'limni tanlang: 👇",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return None

    # VIP qo'shishni boshlash (ID so'rash)
    elif data == "start_vip_add":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="manage_vip")]])
        await query.edit_message_text(
            "🆔 **VIP qilinadigan foydalanuvchi ID-sini yuboring:**", 
            reply_markup=kb, 
            parse_mode="Markdown"
        )
        return A_ADD_VIP

    # VIP ro'yxati
    elif data == "vip_list":
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT user_id FROM users WHERE status = 'vip'")
        vips = cur.fetchall()
        cur.close(); conn.close()
        text = "📜 **VIP Users List:**\n\n"
        if not vips: text += "📭 Hozircha VIP foydalanuvchilar yo'q."
        else:
            for idx, v in enumerate(vips, 1): text += f"{idx}. ID: `{v['user_id']}`\n"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="manage_vip")]])
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
        return None

    # Remove VIP ro'yxatini chiqarish
    elif data == "rem_vip_list":
        await show_vip_removal_list(update, context, page=0)

    # Sahifadan sahifaga o'tish
    elif data.startswith("rem_vip_page_"):
        page = int(data.split("_")[3])
        await show_vip_removal_list(update, context, page=page)

    # Tanlangan VIPni o'chirish (Statusni 'user'ga qaytarish)
    elif data.startswith("exec_rem_vip_"):
        parts = data.split("_")
        target_id = parts[3]
        current_page = int(parts[4])
        
        conn = get_db(); cur = conn.cursor()
        cur.execute("UPDATE users SET status = 'user' WHERE user_id = %s", (target_id,))
        conn.commit()
        cur.close(); conn.close()
        
        await query.answer(f"✅ ID: {target_id} VIP-dan olib tashlandi!", show_alert=True)
        # Ro'yxatni yangilab qo'yamiz
        await show_vip_removal_list(update, context, page=current_page)
 
    


# ----------------- BOSHQA FUNKSIYALAR -----------------

async def show_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


# ===================================================================================


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

async def vip_pass_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchiga VIP PASS haqida ma'lumot"""
    text = (
        "💎 **VIP PASS IMKONIYATLARI:**\n\n"
        "✅ Reklamasiz ko'rish\n"
        "✅ Yangi qismlarni birinchilardan bo'lib ko'rish\n"
        "✅ Maxsus VIP guruhga a'zolik\n\n"
        "💳 VIP PASS sotib olish uchun adminga yozing:\n"
        "👉 @Khudoyqulov_pg"
    )
    if update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")


# ===================================================================================


async def admin_panel_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    status = await get_user_status(uid)
    
    if status in ["main_admin", "admin"]:
        is_main = (status == "main_admin")
        await update.message.reply_text(
            "🛠 **Admin paneliga xush kelibsiz:**",
            reply_markup=get_admin_kb(is_main), # Siz so'ragan get_admin_kb shu yerda chaqiriladi
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Sizda admin huquqlari yo'q.")
        

  
# ===================================================================================       

async def post_new_anime_to_channel(context, anime_id):
    """Qismlar yuklanib bo'lingach, kanalga post yuborish"""
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    
    # 1. Anime ma'lumotlarini bazadan olish
    cur.execute("SELECT * FROM anime_list WHERE anime_id=%s", (anime_id,))
    anime_data = cur.fetchone()
    
    # 2. Haqiqiy qismlar sonini o'sha zahoti sanash
    cur.execute("SELECT COUNT(id) as total FROM anime_episodes WHERE anime_id=%s", (anime_id,))
    total_episodes = cur.fetchone()['total']
    
    cur.close()
    conn.close()

    if not anime_data:
        print(f"Xato: ID {anime_id} bo'yicha anime topilmadi")
        return

    CHANNEL_ID = "@Aninovuz" 
    BOT_USERNAME = "Aninovuz_bot" 

    # Link yaratish
    bot_link = f"https://t.me/{BOT_USERNAME}?start=ani_{anime_id}"

    # CAPTION qismi
    caption = (
        f"┏━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃ 🎬 <b>{anime_data['name']}</b>\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"┃ 🎥 <b>Qismlar soni:</b> {total_episodes} ta\n"
        f"┃ 🌐 <b>Tili:</b> {anime_data.get('lang', 'Oʻzbekcha')}\n"
        f"┃ 🎭 <b>Janri:</b> {anime_data.get('genre', 'Sarguzasht')}\n"
        f"┃ 📅 <b>Yili:</b> {anime_data.get('year', 'Noma’lum')}\n"
        f"┃ 🆔 <b>ID:</b> <code>{anime_id}</code>\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃ 📢 <a href='https://t.me/Aninovuz'>@Aninovuz</a>\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"📥 <b>Hozir ko'rish uchun pastdagi tugmani bosing:</b>"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 Ko'rish", url=bot_link)]
    ])

    try:
        await context.bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=anime_data['poster_id'],
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Kanalga post yuborishda xato: {e}")
    
# ====================== ANIME QIDIRISH VA PAGINATION (TO'LIQ) ======================

async def search_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qidiruv turini tanlash menyusi"""
    kb = [
        [InlineKeyboardButton("🆔 ID orqali qidirish", callback_data="search_type_id")],
        [InlineKeyboardButton("🔎 Nomi orqali qidirish", callback_data="search_type_name")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_search")]
    ]
    # Agar xabar reply orqali kelsa (MessageHandler), update.message ishlatiladi
    # Agar callback orqali kelsa, query.message ishlatiladi
    msg = update.message if update.message else update.callback_query.message
    
    await msg.reply_text(
        "🎬 <b>Anime qidirish bo'limi</b>\n\nQidiruv usulini tanlang:", 
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="HTML"
    )


# ===================================================================================


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
    
    # ID yoki Nom bo'yicha qidirish
    if text.isdigit():
        cur.execute("SELECT * FROM anime_list WHERE anime_id=%s", (text,))
    else:
        cur.execute("SELECT * FROM anime_list WHERE name LIKE %s", (f"%{text}%",))
    
    results = cur.fetchall()
    cur.close(); conn.close()
    
    if not results:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_search_menu")],
            [InlineKeyboardButton("❌ To'xtatish", callback_data="cancel_search")]
        ])
        await update.message.reply_text(
            f"😔 <b>'{text}'</b> bo'yicha hech narsa topilmadi.",
            reply_markup=kb, parse_mode="HTML"
        )
        return 

    # FAQAT BITTA NATIJA CHIQSA (ID bo'yicha qidirilganda ham shu ishlaydi)
    if len(results) == 1:
        # DIQQAT: Funksiya nomi show_anime_details bo'lishi shart!
        return await show_anime_details(update, results[0], context)

    # BIR NECHTA NATIJA CHIQSA
    keyboard = []
    # Natijalar juda ko'p bo'lsa (masalan 50 ta), xabar yuborib bo'lmaydi, shuning uchun 20 ta bilan cheklaymiz
    for anime in results[:20]:
        keyboard.append([InlineKeyboardButton(f"🎬 {anime['name']}", callback_data=f"show_anime_{anime['anime_id']}")])
    
    await update.message.reply_text(
        f"🔍 <b>'{text}' bo'yicha {len(results)} ta natija topildi:</b>\n\nIltimos, tanlang:👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# ===================================================================================


async def show_selected_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() 
    
    anime_id = query.data.replace("show_anime_", "")
    
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM anime_list WHERE anime_id=%s", (anime_id,))
    anime = cur.fetchone()
    cur.close(); conn.close()
    
    if anime:
        # Bu yerda ham show_anime_details nomini ishlating!
        return await show_anime_details(query, anime, context)
    else:
        await query.edit_message_text("❌ Anime ma'lumotlari topilmadi.")

# ===================================================================================


async def show_anime_details(update_or_query, anime, context):
    """Qidiruvdan kelgan animeni ko'rsatish funksiyasi"""
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    
    # 1. Epizodlar ro'yxatini olish (SQlni faqat 1 marta ishlatamiz)
    cur.execute("SELECT id, episode FROM anime_episodes WHERE anime_id=%s ORDER BY episode ASC", (anime['anime_id'],))
    episodes = cur.fetchall()
    cur.close(); conn.close()

    # Chat ID va xabarni aniqlash
    if hasattr(update_or_query, 'message') and update_or_query.message:
        chat_id = update_or_query.message.chat_id
        orig_msg = update_or_query.message
    else:
        chat_id = update_or_query.effective_chat.id
        orig_msg = update_or_query.effective_message

    # 2. Epizodlarni sanash va status
    total_episodes = len(episodes)
    status_text = f"{total_episodes} ta" if total_episodes > 0 else "Tez kunda... ⏳"

    # 3. Caption yasash
    caption = (
        f"┏━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃ 🎬 <b>{anime['name']}</b>\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━┛\n"
        f"┃ 🎥 <b>Qismlar soni:</b> {status_text}\n"
        f"┃ 🌐 <b>Tili:</b> {anime.get('lang', 'Oʻzbekcha')}\n"
        f"┃ 🎭 <b>Janri:</b> {anime.get('genre', 'Sarguzasht')}\n"
        f"┃ 📅 <b>Yili:</b> {anime.get('year', 'Noma’lum')}\n"
        f"┃ 🆔 <b>ID:</b> <code>{anime['anime_id']}</code>\n"
        f"┣━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"┃ 📢 <a href='https://t.me/Aninovuz'>@Aninovuz</a>\n"
        f"┗━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"📥 <b>Qismlardan birini tanlang:</b>"
    )

    # 4. TUGMALARNI YASASH
    keyboard = []
    if episodes:
        row = []
        for ep in episodes[:12]:
            button = InlineKeyboardButton(str(ep['episode']), callback_data=f"get_ep_{ep['id']}")
            row.append(button)
            if len(row) == 4:
                keyboard.append(row)
                row = []
        if row: 
            keyboard.append(row)
        
        if len(episodes) > 12:
            keyboard.append([InlineKeyboardButton("Keyingi ➡️", callback_data=f"page_{anime['anime_id']}_12")])

    # 5. YUBORISH VA XATOLIKNI BOSHQARISH
    try:
        # Rasm va ma'lumotni yuborish
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=anime['poster_id'],
            caption=caption if episodes else caption + "\n\n⚠️ <i>Ushbu animening qismlari tez kunda yuklanadi.</i>",
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
            parse_mode="HTML"
        )
        
        # Agar bu callback (tugma bosish) bo'lsa, eski "Natijalar" xabarini o'chiramiz
        if hasattr(update_or_query, 'data'):
            try:
                await orig_msg.delete()
            except:
                pass

    except Exception as e:
        print(f"Poster yuborishda xatolik: {e}")
        # Rasm yuborib bo'lmasa, shunchaki matn yuboramiz
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎬 {anime['name']}\n\n{caption}",
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
            parse_mode="HTML"
        )

    return ConversationHandler.END


# ===================================================================================



async def get_episode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan qismni video qilib yuborish"""
    query = update.callback_query
    data = query.data.split("_") 
    
    # Agar data 'get_ep_123' bo'lsa, id uchinchi element (index 2) bo'ladi
    if len(data) < 3: 
        await query.answer("❌ Ma'lumot formati noto'g'ri")
        return
        
    row_id = data[2] 
    
    await query.answer("Video yuklanmoqda...", show_alert=False)
    
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT e.file_id, e.episode, a.name 
        FROM anime_episodes e 
        JOIN anime_list a ON e.anime_id = a.anime_id 
        WHERE e.id = %s
    """, (row_id,))
    res = cur.fetchone()
    cur.close(); conn.close()

    if res:
        try:
            await query.message.reply_video(
                video=res['file_id'],
                caption=f"🎬 <b>{res['name']}</b>\n🔢 <b>{res['episode']}-qism</b>\n\n✅ @Aninovuz",
                parse_mode="HTML"
            )
        except Exception as e:
            await query.message.reply_text(f"❌ Video yuborishda xatolik: {e}")
    else:
        await query.answer("❌ Video bazadan topilmadi!", show_alert=True)


# ===================================================================================



async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sahifadan sahifaga o'tish"""
    query = update.callback_query
    # page_aid_offset
    parts = query.data.split("_")
    if len(parts) < 3: return
    
    aid, offset = parts[1], int(parts[2])
    
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, episode FROM anime_episodes WHERE anime_id=%s ORDER BY episode ASC", (aid,))
    episodes = cur.fetchall()
    cur.close(); conn.close()

    if not episodes:
        await query.answer("Epizodlar topilmadi")
        return

    keyboard = []
    row = []
    display_eps = episodes[offset:offset+12]
    
    for ep in display_eps:
        # MUHIM: get_episode_handler data[2] ni o'qishi uchun callback_data shunday bo'lishi kerak:
        row.append(InlineKeyboardButton(text=str(ep['episode']), callback_data=f"get_ep_{ep['id']}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)

    nav_buttons = []
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"page_{aid}_{offset-12}"))
    if offset + 12 < len(episodes):
        nav_buttons.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"page_{aid}_{offset+12}"))
    
    if nav_buttons: 
        keyboard.append(nav_buttons)

    # Xabarni tahrirlash (yangi tugmalarni qo'yish)
    try:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        print(f"Pagination Error: {e}")
        
    await query.answer()
    

    
    

# ====================== CONVERSATION STEPS (TUZATILDI) ======================

async def anime_control_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        
        # AGAR FOYDALANUVCHI "ORQAGA" TUGMASINI BOSGAN BO'LSA
        if query.data == "admin_main":
            uid = update.effective_user.id
            status = await get_user_status(uid)
            is_main = (status == "main_admin")
            
            await query.edit_message_text(
                "🛠 **Admin paneliga xush kelibsiz:**",
                reply_markup=get_admin_kb(is_main),
                parse_mode="Markdown"
            )
            # MANA SHU YERDA END QAYTARAMIZ, SHUNDA STATE YOPILADI
            return ConversationHandler.END

    # Oddiy menyu ko'rsatish qismi
    kb = [
        [InlineKeyboardButton("➕ Add Anime", callback_data="add_ani_menu"),
         InlineKeyboardButton("📜 Anime List", callback_data="list_ani_pg_0")],
        [InlineKeyboardButton("🗑 Remove Anime", callback_data="rem_ani_menu")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_main")]
    ]
    
    text = "🛠 **Anime Control Panel**\n\nKerakli bo'limni tanlang: 👇"
    reply_markup = InlineKeyboardMarkup(kb)

    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    
    return A_ANI_CONTROL


# ===================================================================================


# Add Anime Panel (Yangi anime yoki qism)
async def add_anime_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    kb = [
        [InlineKeyboardButton("✨ Yangi anime qo'shish", callback_data="start_new_ani")],
        [InlineKeyboardButton("📼 Yangi qism qo'shish", callback_data="new_ep_ani")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_ctrl")]
    ]
    text = "➕ **Add Anime Panel**\n\nTanlang: 👇"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return A_ADD_MENU


# ===================================================================================


# 1-qadam: Poster so'rash
async def start_new_ani(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    kb = [[InlineKeyboardButton("⬅️ Orqaga", callback_data="add_ani_menu")]]
    await query.edit_message_text("1️⃣ Anime uchun **POSTER** (rasm) yuboring:", 
                                  reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return A_GET_POSTER


# ===================================================================================


# 2-qadam: Ma'lumotlarni so'rash
async def get_poster_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ Iltimos, rasm yuboring!")
        return A_GET_POSTER
    
    context.user_data['tmp_poster'] = update.message.photo[-1].file_id
    kb = [[InlineKeyboardButton("⬅️ Orqaga", callback_data="start_new_ani")]]
    await update.message.reply_text(
        "📝 Anime ma'lumotlarini tashlang:\nFormat: `Nomi | Tili | Janri | Yili`",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )
    return A_GET_DATA

# ===================================================================================

async def save_ani_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "|" not in text:
        await update.message.reply_text("❌ Format xato! `Nomi | Tili | Janri | Yili` ko'rinishida yuboring.")
        return A_GET_DATA
    
    try:
        # Ma'lumotlarni ajratib olamiz
        n, l, g, y = [i.strip() for i in text.split("|")]
        poster_id = context.user_data.get('tmp_poster')
        
        if not poster_id:
            await update.message.reply_text("❌ Poster topilmadi. Iltimos, avval rasm yuboring.")
            return A_GET_DATA

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO anime_list (name, poster_id, lang, genre, year) VALUES (%s, %s, %s, %s, %s)",
            (n, poster_id, l, g, y)
        )
        new_id = cur.lastrowid
        conn.commit()
        cur.close()
        conn.close()

        # Keyingi bosqichda ishlatish uchun sessiyaga saqlaymiz
        context.user_data['cur_ani_id'] = new_id
        context.user_data['cur_ani_name'] = n

        # DIQQAT: Kanalga avtomatik yuborish qismi bu yerdan olib tashlandi.
        # Endi faqat admin videolarni yuklab bo'lgach o'zi yuboradi.

        await update.message.reply_text(
            f"✅ <b>{n}</b> bazaga muvaffaqiyatli qo'shildi! (ID: {new_id})\n\n"
            f"📥 Endi anime qismlarini (video fayllarni) ketma-ket yuboring.\n"
            f"🏁 Hammasini yuklab bo'lgach, 'Kanalga e'lon qilish' tugmasini bosishingiz mumkin.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Bekor qilish", callback_data="add_ani_menu")]]),
            parse_mode="HTML"
        )
        return A_ADD_EP_FILES
        
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik yuz berdi: {e}")
        return A_GET_DATA




# ===================================================================================


async def handle_ep_uploads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Videoni aniqlash (oddiy video yoki hujjat sifatidagi video)
    # Forward qilingan videolar ba'zan hujjat (document) ko'rinishida keladi
    video_obj = None
    if update.message.video:
        video_obj = update.message.video
    elif update.message.document and update.message.document.mime_type.startswith('video/'):
        video_obj = update.message.document

    # Agar xabar video bo'lmasa
    if not video_obj:
        await update.message.reply_text("❌ Iltimos, video fayl yuboring!")
        return A_ADD_EP_FILES

    # 2. Sessiyadan anime ma'lumotlarini olish
    ani_id = context.user_data.get('cur_ani_id')
    ani_name = context.user_data.get('cur_ani_name')

    if not ani_id:
        await update.message.reply_text("❌ Xatolik: Anime ID topilmadi. Iltimos, jarayonni qaytadan boshlang.")
        return "add_ani_menu"

    conn = get_db()
    cur = conn.cursor()
    try:
        # 3. Oxirgi qism raqamini aniqlash
        cur.execute("SELECT MAX(episode) FROM anime_episodes WHERE anime_id = %s", (ani_id,))
        res = cur.fetchone()
        last_ep = res[0] if res and res[0] is not None else 0
        new_ep = last_ep + 1
        
        # 4. Videoni bazaga saqlash
        # Biz faqat file_id ni saqlaymiz, shuning uchun eski caption (matn) bazaga kirmaydi
        cur.execute(
            "INSERT INTO anime_episodes (anime_id, episode, file_id) VALUES (%s, %s, %s)",
            (ani_id, new_ep, video_obj.file_id)
        )
        conn.commit()
        
        # 5. Javob qaytarish (Tugmalar bilan)
        kb = [[InlineKeyboardButton("🏁 Jarayonni tugatish", callback_data="add_ani_menu")],
             [InlineKeyboardButton("📢 Kanalga e'lon qilish", callback_data=f"post_to_chan_{ani_id}")]
        ]
        await update.message.reply_text(
            f"✅ **{ani_name}**\n🎬 **{new_ep}-qism** muvaffaqiyatli qo'shildi!\n\n"
            f"ℹ️ *Video ostidagi eski matnlar (caption) avtomatik olib tashlandi.* \n\n"
            f"Yana qism yuborishingiz mumkin 👇",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Bazaga saqlashda texnik xatolik: {e}")
        print(f"DEBUG: Video upload error: {e}")
    finally:
        cur.close()
        conn.close()

    return A_ADD_EP_FILES
    

# ===================================================================================

async def post_to_channel_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # Soat belgisini yo'qotish uchun
    
    # callback_data dan ID ni ajratib olamiz: "post_to_chan_12" -> "12"
    anime_id = query.data.split("_")[-1]
    
    try:
        # Kanalga yuborish funksiyasini chaqiramiz
        await post_new_anime_to_channel(context, anime_id)
        
        # Admin xabarini tahrirlaymiz
        await query.edit_message_text(
            text=f"✅ Anime (ID: {anime_id}) kanalga muvaffaqiyatli e'lon qilindi!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Asosiy Menyu", callback_data="add_ani_menu")
            ]])
        )
    except Exception as e:
        await query.message.reply_text(f"❌ Xatolik yuz berdi: {e}")


# ===================================================================================


async def get_pagination_keyboard(table_name, page=0, per_page=15, prefix="selani_", extra_callback=""):
    conn = get_db()
    cur = conn.cursor()
    
    # Ma'lumotlarni bazadan olish
    cur.execute(f"SELECT anime_id, name FROM {table_name} ORDER BY anime_id DESC")
    all_data = cur.fetchall()
    cur.close(); conn.close()

    start = page * per_page
    end = start + per_page
    current_items = all_data[start:end]

    buttons = []
    # Prefix oxirida bitta "_" bo'lishini ta'minlaymiz
    base_prefix = prefix.rstrip('_') + "_"

    for item in current_items:
        # item[0] -> anime_id, item[1] -> name
        btn_text = f"{item[1]} [ID: {item[0]}]"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"{base_prefix}{item[0]}")])

    # Navigatsiya tugmalari
    nav_buttons = []
    if page > 0:
        # Format: pg_[prefix]_[page] -> Masalan: pg_addepto_0
        nav_buttons.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"pg_{base_prefix}{page-1}"))
    
    if end < len(all_data):
        # Format: pg_[prefix]_[page] -> Masalan: pg_addepto_2
        nav_buttons.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"pg_{base_prefix}{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)

    back_call = extra_callback if extra_callback else "back_to_ctrl"
    buttons.append([InlineKeyboardButton("⬅️ Orqaga", callback_data=back_call)])
    
    return InlineKeyboardMarkup(buttons)


# ===================================================================================


# Mavjud animega qism qo'shish uchun ro'yxatni ko'rsatish
async def select_ani_for_ep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Prefixni 'addepto_' qildik (handle_callback'ga moslab)
    markup = await get_pagination_keyboard("anime_list", page=0, prefix="addepto_")
    await query.edit_message_text("📼 Qaysi animega yangi qism qo'shmoqchisiz?", reply_markup=markup)
    return A_SELECT_ANI_EP


# ===================================================================================


# Tanlangan anime uchun video kutish
async def select_ani_for_ep_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # 'addepto_' prefixini olib tashlab faqat ID ni olamiz
    ani_id_raw = query.data.replace("addepto_", "")
    
    # ID ni son ko'rinishiga keltiramiz
    try:
        ani_id = int(ani_id_raw)
    except ValueError:
        await query.message.reply_text("❌ ID xatosi!")
        return A_SELECT_ANI_EP
    
    conn = get_db()
    cur = conn.cursor()
    # Ustun nomi 'anime_id' ekanligiga ishonch hosil qiling
    cur.execute("SELECT name FROM anime_list WHERE anime_id = %s", (ani_id,))
    res = cur.fetchone()
    cur.close(); conn.close()
    
    if res:
        context.user_data['cur_ani_id'] = ani_id
        context.user_data['cur_ani_name'] = res[0]
        
        await query.edit_message_text(
            f"📥 **{res[0]}** tanlandi.\n\nEndi yangi qismlarni yuboring (videofayl):",
            parse_mode="Markdown"
        )
        return A_ADD_EP_FILES
    else:
        await query.edit_message_text("❌ Anime topilmadi!")
        return A_SELECT_ANI_EP



# ===================================================================================


async def list_episodes_for_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    ani_id = query.data.split('_')[-1]
    
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, part FROM anime_episodes WHERE anime_id = %s ORDER BY part ASC", (ani_id,))
    episodes = cur.fetchall()
    cur.close(); conn.close()
    
    if not episodes:
        await query.answer("📭 Bu animeda qismlar mavjud emas!", show_alert=True)
        return A_REM_EP_ANI_LIST

    buttons = []
    # Qismlarni 4 tadan qilib chiqarish
    row = []
    for ep in episodes:
        row.append(InlineKeyboardButton(f"{ep[1]}-qism", callback_data=f"ex_del_ep_{ep[0]}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    
    buttons.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="rem_ep_menu")])
    
    await query.edit_message_text(f"🗑 **Qaysi qismni o'chirmoqchisiz?**", reply_markup=InlineKeyboardMarkup(buttons))
    return A_REM_EP_NUM_LIST

# ====================== ANIME LIST & VIEW ======================
async def list_animes_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Sahifa raqamini olish mantiqi
    page = 0
    if "_" in query.data:
        try:
            page = int(query.data.split('_')[-1])
        except ValueError:
            page = 0
            
    kb = await get_pagination_keyboard("anime_list", page=page, prefix="viewani_", extra_callback="back_to_ctrl")
    await query.edit_message_text("📜 **Anime ro'yxati:**\nBatafsil ma'lumot uchun tanlang:", reply_markup=kb, parse_mode="Markdown")
    return A_LIST_VIEW


# ===================================================================================


async def show_anime_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    ani_id = query.data.split('_')[-1]
    
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM anime_list WHERE anime_id = %s", (ani_id,))
    ani = cur.fetchone()
    if not ani:
        await query.answer("❌ Anime topilmadi!")
        return A_LIST_VIEW
        
    cur.execute("SELECT COUNT(*) FROM anime_episodes WHERE anime_id = %s", (ani_id,))
    
    eps = cur.fetchone()[0]
    cur.close(); conn.close()
    
    text = (f"🎬 **{ani[1]}**\n\n"
            f"🆔 ID: `{ani[0]}`\n"
            f"🌐 Tili: {ani[3]}\n"
            f"🎭 Janri: {ani[4]}\n"
            f"📅 Yili: {ani[5]}\n"
            f"📼 Jami qismlar: {eps} ta")
    
    # Orqaga qaytishda 0-sahifaga yo'naltirish
    kb = [[InlineKeyboardButton("⬅️ Ro'yxatga qaytish", callback_data="list_ani_pg_0")]]
    
    # Rasm yuborish va eski xabarni o'chirish
    await query.message.reply_photo(photo=ani[2], caption=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    await query.message.delete()
    return A_LIST_VIEW


# ===================================================================================


async def select_ani_for_new_ep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Yangi qism qo'shish uchun avval animeni tanlash listini chiqarish
    """
    query = update.callback_query
    # Sahifa raqamini aniqlash
    page = 0
    if query and "pg_" in query.data:
        try:
            page = int(query.data.split('_')[-1])
        except:
            page = 0
            
    # Diqqat: Prefix 'addepto_' bo'lishi kerak, chunki handle_callback shuni kutyapti
    kb = await get_pagination_keyboard(
        "anime_list", 
        page=page, 
        prefix="addepto_", 
        extra_callback="add_ani_menu"
    )
    
    text = "📼 **Qaysi animega yangi qism qo'shmoqchisiz?**\nRo'yxatdan tanlang: 👇"
    
    if query:
        await query.answer()
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")
        
    return A_SELECT_ANI_EP

# ====================== REMOVE LOGIC ======================
async def delete_anime_exec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    ani_id = query.data.split('_')[-1]
    
    conn = get_db(); cur = conn.cursor()
    try:
        # 1. Avval ushbu animega tegishli barcha qismlarni o'chiramiz
        cur.execute("DELETE FROM anime_episodes WHERE anime_id = %s", (ani_id,))
        # 2. Keyin animening o'zini o'chiramiz
        cur.execute("DELETE FROM anime_list WHERE anime_id = %s", (ani_id,))
        conn.commit()
        await query.answer("✅ Anime va uning barcha qismlari muvaffaqiyatli o'chirildi!", show_alert=True)
    except Exception as e:
        conn.rollback()
        await query.answer(f"❌ O'chirishda xatolik: {e}", show_alert=True)
    finally:
        cur.close(); conn.close()
    
    return await anime_control_panel(update, context)

# ====================== QISMNI O'CHIRISH UCHUN ANIME TANLASH ======================
async def select_ani_for_rem_ep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Sahifa raqamini aniqlash
    page = 0
    if query and "pg_" in query.data:
        page = int(query.data.split('_')[-1])
        
    kb = await get_pagination_keyboard(
        "anime_list", 
        page=page, 
        prefix="remep_", 
        extra_callback="rem_ani_menu" # Remove menyusiga qaytish
    )
    
    text = "🎞 **Qaysi animening qismini o‘chirmoqchisiz?**\nRo'yxatdan tanlang: 👇"
    
    if query:
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")
        
    return A_REM_EP_ANI_LIST


# ===================================================================================


async def remove_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Bu yerda query yoki message ekanligini tekshiramiz
    query = update.callback_query
    
    kb = [
        [InlineKeyboardButton("❌ Animeni o'chirish", callback_data="rem_ani_list_0")],
        [InlineKeyboardButton("🎞 Qismni o'chirish", callback_data="rem_ep_menu")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="adm_ani_ctrl")]
    ]
    reply_markup = InlineKeyboardMarkup(kb)
    text = "🗑 **Remove Anime paneli**\nNimani o'chirmoqchisiz?"

    if query:
        await query.answer()
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    
    return A_REM_MENU
          
            

# ====================== QO'SHIMCHA FUNKSIYALAR (TUZATILGAN) ======================

# --- 1. FONDA REKLAMA YUBORISH (PROGRESS BILAN) ---
async def background_ads_task(bot, admin_id, users, msg_id, from_chat_id):
    sent = 0
    failed = 0
    total = len(users)
    
    # Adminni jarayon boshlangani haqida ogohlantirish
    progress_msg = await bot.send_message(
        admin_id, 
        f"⏳ **Reklama yuborish boshlandi...**\nJami: `{total}` ta foydalanuvchi."
    )

    for user in users:
        uid = user[0]  # Kortejdan (ID,) formatidan raqamni olish
        try:
            # Har qanday turdagi xabarni (rasm, video, tekst) nusxalab yuboradi
            await bot.copy_message(
                chat_id=uid,
                from_chat_id=from_chat_id,
                message_id=msg_id
            )
            sent += 1
        except Exception:
            failed += 1
        
        # Har 20 ta xabarda admin panelidagi statusni yangilab turish
        if (sent + failed) % 20 == 0:
            try:
                await progress_msg.edit_text(
                    f"⏳ **Yuborish jarayoni:**\n\n"
                    f"📊 Jami: `{total}`\n"
                    f"✅ Yuborildi: `{sent}`\n"
                    f"❌ Xato: `{failed}`",
                    parse_mode="Markdown"
                )
            except:
                pass
        
        # Telegram bloklamasligi uchun qisqa tanaffus
        await asyncio.sleep(0.05) 

    # Yakuniy hisobot
    await bot.send_message(
        admin_id, 
        f"🏁 **Reklama yakunlandi!**\n\n"
        f"✅ Muvaffaqiyatli: `{sent}`\n"
        f"❌ Muvaffaqiyatsiz: `{failed}`",
        parse_mode="Markdown"
    )


# ===================================================================================


# --- 2. PAROLNI TEKSHIRISH ---
async def check_ads_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == ADVERTISING_PASSWORD:
        keyboard = [
            [InlineKeyboardButton("👥 Oddiy foydalanuvchilar (user)", callback_data="send_to_user")],
            [InlineKeyboardButton("💎 Faqat VIP a'zolar (vip)", callback_data="send_to_vip")],
            [InlineKeyboardButton("👮 Faqat Adminlar (admin)", callback_data="send_to_admin")],
            [InlineKeyboardButton("🌍 Barchaga (Hammaga)", callback_data="send_to_all")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_pass")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_ads")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "✅ **Parol tasdiqlandi!**\n\nKimlarga yubormoqchisiz? Tanlang 👇",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return A_SELECT_ADS_TARGET
    else:
        uid = update.effective_user.id
        status = await get_user_status(uid)
        await update.message.reply_text("❌ Parol noto'g'ri!", reply_markup=get_main_kb(status))
        return ConversationHandler.END


# ===================================================================================


# --- 3. REKLAMANI YAKUNLASH VA YUBORISHNI BOSHLASH ---
async def ads_send_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    admin_id = update.effective_user.id
    
    # Callback-dan saqlangan guruhni olish
    target = context.user_data.get('ads_target', 'all')
    
    conn = get_db()
    if not conn:
        await msg.reply_text("❌ Bazaga ulanishda xato!")
        return ConversationHandler.END
        
    cur = conn.cursor()
    
    # Guruh bo'yicha filtrlash
    if target == "all":
        cur.execute("SELECT user_id FROM users")
    else:
        # Bazadagi status kichik harf bo'lsa target bilan mos tushadi
        cur.execute("SELECT user_id FROM users WHERE status = %s", (target,))
        
    users = cur.fetchall()
    cur.close()
    conn.close()

    if not users:
        await msg.reply_text(f"📭 Tanlangan guruhda ({target}) foydalanuvchilar topilmadi.")
        return ConversationHandler.END

    # Fon rejimida yuborishni boshlash
    asyncio.create_task(background_ads_task(
        bot=context.bot,
        admin_id=admin_id,
        users=users,
        msg_id=msg.message_id,
        from_chat_id=update.effective_chat.id
    ))

    uid = update.effective_user.id
    status = await get_user_status(uid)
    await msg.reply_text(
        f"🚀 **Reklama navbatga qo'shildi!**\n\n"
        f"🎯 Guruh: `{target}`\n"
        f"👥 Soni: `{len(users)}` ta\n\n"
        f"Bot fonda ishlashni boshladi. Tugagach hisobot yuboraman.",
        reply_markup=get_main_kb(status),
        parse_mode="Markdown"
    )
    
    return ConversationHandler.END


# ===================================================================================


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha jarayonlarni to'xtatadi va asosiy menyuga qaytaradi"""
    uid = update.effective_user.id
    status = await get_user_status(uid) # Admin yoki User ekanini aniqlash

    await update.message.reply_text(
        "🔙 Bekor qilindi. Asosiy menyu:",
        reply_markup=get_main_kb(status) # Sizdagi asosiy menyu funksiyasi
    )
    return ConversationHandler.END # MANA SHU QATOR SIZNI LABIRINTDAN CHIQARADI!


# ===================================================================================


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


# ===================================================================================


async def exec_vip_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """VIP qo'shishdan oldin tasdiqlash so'rash"""
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ Xato! Foydalanuvchi ID-sini raqamlarda yuboring.")
        return A_ADD_VIP

    keyboard = [
        [InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"conf_vip_{text}")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="manage_vip")]
    ]
    
    await update.message.reply_text(
        f"💎 **Foydalanuvchini VIP qilishni tasdiqlaysizmi?**\n\nID: `{text}`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return None


# ===================================================================================


async def reset_and_init_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Faqat asosiy admin ishlata olishi uchun
    if update.effective_user.id != MAIN_ADMIN_ID:
        return

    conn = get_db()
    if not conn:
        await update.message.reply_text("❌ Bazaga ulanib bo'lmadi!")
        return

    cur = conn.cursor()
    try:
        # 1. Cheklovlarni vaqtincha o'chirish
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")

        # 2. Eskilarini butunlay o'chirish
        cur.execute("DROP TABLE IF EXISTS anime_episodes")
        cur.execute("DROP TABLE IF EXISTS anime_list")
        # 'users' jadvalini o'chirmasangiz ham bo'ladi, agar userlar kerak bo'lsa
        # cur.execute("DROP TABLE IF EXISTS users") 

        # 3. 'anime_list' jadvalini to'g'ri AUTO_INCREMENT bilan yaratish
        cur.execute("""
            CREATE TABLE anime_list (
                anime_id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                poster_id TEXT,
                lang VARCHAR(100),
                genre VARCHAR(255),
                year VARCHAR(20)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # 4. 'anime_episodes' jadvalini yaratish
        cur.execute("""
            CREATE TABLE anime_episodes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                anime_id INT,
                episode INT,
                file_id TEXT,
                FOREIGN KEY (anime_id) REFERENCES anime_list(anime_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()

        await update.message.reply_text(
            "🚀 **Baza tozalandi va AUTO_INCREMENT yoqildi!**\n\n"
            "Endi anime qo'shsangiz, ID raqami 1 dan boshlab avtomatik beriladi."
        )

    except Exception as e:
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        await update.message.reply_text(f"❌ Xatolik: {e}")
    finally:
        cur.close()
        conn.close()
        
# ====================== MAIN FUNKSIYA (TUZATILDI) =======================
def main():
    # 1. Serverni uyg'oq saqlash
    keep_alive()

    # 2. Bazani ishga tushirish
    try:
        init_db()
    except Exception as e:
        print(f"🛑 Baza ulanishida xato: {e}")
        
    # 3. Botni yaratish
    app_bot = ApplicationBuilder().token(TOKEN).build()
    
    # Menyu filtri
    menu_filter = filters.Regex("Anime qidirish|VIP PASS|Bonus ballarim|Qo'llanma|Barcha anime ro'yxati|ADMIN PANEL|Bekor qilish")

    # 4. CONVERSATION HANDLER
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex(r"Anime qidirish"), search_menu_cmd),
            MessageHandler(filters.Regex(r"ADMIN PANEL"), admin_panel_text_handler),
            CallbackQueryHandler(handle_callback) 
        ],
        states={
            A_MAIN: [
                CallbackQueryHandler(handle_callback),
                MessageHandler(filters.Regex("Anime boshqaruvi"), anime_control_panel),
            ],
            
            A_ANI_CONTROL: [
                CallbackQueryHandler(handle_callback),
                MessageHandler(filters.Regex("Anime List"), list_animes_view),
                MessageHandler(filters.Regex("Yangi anime"), add_anime_panel),
                MessageHandler(filters.Regex("Anime o'chirish"), remove_menu_handler),
                MessageHandler(filters.Regex("Yangi qism qo'shish"), select_ani_for_new_ep),
                MessageHandler(filters.Regex("Orqaga"), anime_control_panel),
            ],
            
            A_LIST_VIEW: [CallbackQueryHandler(handle_callback)],
            A_REM_MENU: [CallbackQueryHandler(handle_callback)],
            A_REM_ANI_LIST: [CallbackQueryHandler(handle_callback)],
            A_REM_EP_ANI_LIST: [CallbackQueryHandler(handle_callback)],
            A_REM_EP_NUM_LIST: [CallbackQueryHandler(handle_callback)],
            A_SELECT_ANI_EP: [CallbackQueryHandler(handle_callback)],
            
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
           
            A_SEARCH_BY_ID: [
                # 1. Avval tanlangan animeni ko'rsatishni tekshirsin
                CallbackQueryHandler(show_selected_anime, pattern="^show_anime_"), 
                # 2. Keyin matn yozilsa qidiruvni davom ettirsin
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_filter, search_anime_logic),
                # 3. Oxirida boshqa callbacklarni tekshirsin
                CallbackQueryHandler(handle_callback)
            ],
            A_SEARCH_BY_NAME: [
                # 1. Birinchi navbatda tugma bosilishini ushlasin
                CallbackQueryHandler(show_selected_anime, pattern="^show_anime_"), 
                # 2. Keyin qidiruv matnini ushlasin
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_filter, search_anime_logic),
                # 3. Oxirida qolgan callbacklar
                CallbackQueryHandler(handle_callback)
            ],

            A_ADD_CH: [MessageHandler(filters.TEXT & ~filters.COMMAND, exec_add_channel)],
            A_REM_CH: [MessageHandler(filters.TEXT & ~filters.COMMAND, exec_rem_channel)],
            A_ADD_ADM: [MessageHandler(filters.TEXT & ~filters.COMMAND, exec_add_admin)],
            A_ADD_VIP: [MessageHandler(filters.TEXT & ~filters.COMMAND, exec_vip_add)],
            A_SEND_ADS_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_ads_pass)],
            A_SELECT_ADS_TARGET: [CallbackQueryHandler(handle_callback)],
            A_SEND_ADS_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, ads_send_finish)],
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex(r"Orqaga|Bekor qilish|Bosh menyu"), start),
            CallbackQueryHandler(handle_callback)
        ],
        allow_reentry=True,
        name="aninow_v103",
    )

    # 5. HANDLERLARNI RO'YXATGA OLISH
    app_bot.add_handler(CallbackQueryHandler(handle_pagination, pattern="^page_"))
    app_bot.add_handler(CallbackQueryHandler(get_episode_handler, pattern="^get_ep_"))
    app_bot.add_handler(CallbackQueryHandler(show_selected_anime, pattern="^show_anime_"))
    app_bot.add_handler(CallbackQueryHandler(recheck_callback, pattern="^recheck$"))
    app_bot.add_handler(CallbackQueryHandler(post_to_channel_button_handler, pattern="^post_to_chan_"))
    app_bot.add_handler(CallbackQueryHandler(show_vip_removal_list, pattern="^rem_vip_list"))
    app_bot.add_handler(CallbackQueryHandler(show_vip_removal_list, pattern="^rem_vip_page_"))
    
    app_bot.add_handler(conv_handler)

    app_bot.add_handler(CommandHandler("start", start))

    app_bot.add_handler(MessageHandler(filters.Regex("Anime qidirish"), search_menu_cmd))
    app_bot.add_handler(MessageHandler(filters.Regex("Bonus ballarim"), show_bonus))
    app_bot.add_handler(MessageHandler(filters.Regex("Qo'llanma"), show_guide))
    app_bot.add_handler(MessageHandler(filters.Regex("VIP PASS"), vip_pass_info))
    app_bot.add_handler(MessageHandler(filters.Regex("Barcha anime ro'yxati"), export_all_anime))

    app_bot.add_handler(CallbackQueryHandler(handle_callback))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start))

    print("🚀 Bot ishga tushdi...")
    app_bot.run_polling()

if __name__ == '__main__':
    main()

























