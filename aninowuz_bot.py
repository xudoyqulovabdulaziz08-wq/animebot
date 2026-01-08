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



def get_admin_kb(is_main=False):
    """Admin panel ichidagi inline tugmalar"""
    buttons = [
        [
            InlineKeyboardButton("📢 Kanallar", callback_data="adm_ch"), 
            InlineKeyboardButton("🎬 Anime Qo'shish", callback_data="adm_ani_add")
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

    # --- 1. HAMMA UCHUN OCHIQ CALLBACKLAR ---
    if data == "recheck":
        if not await check_sub(uid, context.bot):
            await query.message.delete()
            await context.bot.send_message(uid, "Tabriklaymiz! ✅ Obuna tasdiqlandi.", reply_markup=get_main_kb(status))
        else:
            await query.answer("❌ Hali hamma kanallarga a'zo emassiz!", show_alert=True)
        return

    elif data == "search_type_id":
        await query.edit_message_text("🆔 **Anime kodini (ID) yuboring:**", parse_mode="Markdown")
        return A_SEARCH_BY_ID

    elif data == "search_type_name":
        await query.edit_message_text("🔎 **Anime nomini kiriting:**", parse_mode="Markdown")
        return A_SEARCH_BY_NAME

    elif data == "cancel_search":
        context.user_data.clear() 
        if query.message: await query.message.delete()
        await context.bot.send_message(uid, "✅ Jarayon yakunlandi.", reply_markup=get_main_kb(status))
        return ConversationHandler.END

    # --- 2. ADMINLAR UCHUN CALLBACKLAR ---
    if status not in ["main_admin", "admin"]: 
        return

    # Anime qo'shishni boshlash (Poster so'rash)
    if data == "adm_ani_add":
        await query.message.reply_text("1️⃣ Anime uchun POSTER (rasm) yuboring:")
        return A_ADD_ANI_POSTER

    # KEYINGI QISMNI QO'SHISH (Siz so'ragan asosiy o'zgarish)
    elif data == "add_more_ep":
        await query.message.reply_text(
            "Endi **VIDEONI** yuboring.\n\n"
            "⚠️ **DIQQAT:** Video ostiga (caption) quyidagi ma'lumotni yozing:\n"
            "`ID | Nomi | Tili | Qismi`",
            parse_mode="Markdown"
        )
        return A_ADD_ANI_DATA  # Botni yana video kutish holatiga qaytaradi

    # Kanallar boshqaruvi
    elif data == "adm_ch":
        kb = [[InlineKeyboardButton("➕ Qo'shish", callback_data="add_channel_start"), 
               InlineKeyboardButton("❌ O'chirish", callback_data="rem_channel_start")],
              [InlineKeyboardButton("⬅️ Orqaga", callback_data="adm_back")]]
        await query.edit_message_text("📢 Kanallarni boshqarish:", reply_markup=InlineKeyboardMarkup(kb))
        return



    # Orqaga qaytish
    elif data == "adm_back" or data == "admin_main":
        is_main = (status == "main_admin")
        await query.edit_message_text("🛠 Admin paneli:", reply_markup=get_admin_kb(is_main))
        return ConversationHandler.END

    # Qolgan state qaytaruvchi callbacklar
    elif data == "add_channel_start": return A_ADD_CH
    elif data == "rem_channel_start": return A_REM_CH
    elif data == "add_admin_start": return A_ADD_ADM
    elif data == "adm_vip_add": return A_ADD_VIP
    elif data == "adm_ads_start": 
        await query.message.reply_text("🔑 Reklama parolini kiriting:")
        return A_SEND_ADS_PASS

    return None
    
    

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
                        text="✨ **Tabriklaymiz!** Sizga VIP statusi berildi.\nEndi botdan cheklovsiz foydalanishingiz mumkin."
                    )
                except:
                    pass
                    
            except Exception as e:
                await query.answer(f"❌ Baza xatosi: {e}", show_alert=True)
            finally:
                cur.close(); conn.close()
        return None
        
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
        
    
# ================= STATISTIKA (FULL PRO) =================
    elif data == "adm_stats":
        conn = get_db()
        cur = conn.cursor()
        try:
            # 1. Foydalanuvchilar
            cur.execute("SELECT COUNT(*) FROM users")
            u_count = cur.fetchone()[0]
            
            # 2. VIPlar
            cur.execute("SELECT COUNT(*) FROM users WHERE status='vip'")
            v_count = cur.fetchone()[0]
            
            # 3. Animelar (Siz aytgan 'animes' jadvalidan)
            cur.execute("SELECT COUNT(*) FROM animes")
            a_count = cur.fetchone()[0]
            
            # 4. Kanallar
            cur.execute("SELECT COUNT(*) FROM channels")
            c_count = cur.fetchone()[0]

            text = (
                "📊 **BOTNING UMUMIY STATISTIKASI**\n\n"
                f"👤 **Foydalanuvchilar:** `{u_count}` ta\n"
                f"💎 **VIP a'zolar:** `{v_count}` ta\n"
                f"🎬 **Jami animelar:** `{a_count}` ta\n"
                f"📢 **Majburiy kanallar:** `{c_count}` ta\n\n"
                "🕒 _Barcha ma'lumotlar bazadan real vaqtda olindi._"
            )
            
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Asosiy menyuga qaytish", callback_data="admin_main")]
            ])

            # MUHIM: Bu yerda faqat edit ishlatamiz!
            await query.edit_message_text(text=text, reply_markup=kb, parse_mode="Markdown")
            
        except Exception as e:
            await query.answer(f"❌ Statistika xatosi: {e}", show_alert=True)
        finally:
            cur.close()
            conn.close()
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

    # Agar admin parolni noto'g'ri kiritsa yoki o'sha yerda "Orqaga"ni bossa
    # Bu qism handle_callback ichida bo'lishi kerak
    elif data == "admin_main":
        # Admin bosh menyusini chiqarish kodi...
        status = await get_user_status(uid)
        await query.edit_message_text(
            text="👨‍💻 **Admin paneliga xush kelibsiz:**",
            reply_markup=get_admin_kb(), # Admin bosh menyu tugmalari
            parse_mode="Markdown"
        )
        return ConversationHandler.END # Reklama kutish holatidan chiqamiz

    # DB EXPORT (JSON)
    elif data == "adm_export":
        await export_all_anime(update, context)
        return None


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
    # YANGI (To'g'ri):
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
        # Orqaga (menyuga) va To'xtatish (yopish) tugmalarini qo'shamiz
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_search_menu")],
            [InlineKeyboardButton("❌ To'xtatish", callback_data="cancel_search")]
        ])
        
        await update.message.reply_text(
            f"😔 `{text}` bo'yicha hech narsa topilmadi.\n\n"
            "Iltimos, ID raqamni yoki nomini qayta tekshirib ko'ring yoki quyidagi tugmalar orqali navigatsiya qiling:",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        return # Foydalanuvchi yana kiritib ko'rishi uchun state'da (A_SEARCH_BY_ID yoki A_SEARCH_BY_NAME) qoladi

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
                caption=f"🎬 **{anime_info['name']}**\n🔢 **{episode_num}-qism**\n\n✅ @Aninovuz"
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
    """Anime ma'lumotlarini va videoni saqlash"""
    uid = update.effective_user.id
    
    # 1. Video kelganini tekshirish
    if not update.message.video:
        await update.message.reply_text(
            "⚠️ Iltimos, anime qismini **VIDEO** shaklida yuboring.\n"
            "Caption (izoh) qismida ma'lumotlarni unutmang!",
            parse_mode="Markdown"
        )
        return A_ADD_ANI_DATA

    v_id = update.message.video.file_id
    caption = update.message.caption
    
    # 2. Caption (izoh) borligini tekshirish
    if not caption or "|" not in caption:
        await update.message.reply_text(
            "❌ **Xato!** Video izohida ma'lumotlar topilmadi.\n\n"
            "Format: `ID | Nomi | Tili | Qismi`", 
            parse_mode="Markdown"
        )
        return A_ADD_ANI_DATA

    try:
        # 3. Ma'lumotlarni ajratish
        parts = [i.strip() for i in caption.split("|")]
        if len(parts) < 4:
            raise ValueError("Ma'lumotlar yetarli emas (4 ta qism bo'lishi shart)")
            
        aid, name, lang, ep = parts
        p_id = context.user_data.get('poster')

        if not p_id:
            await update.message.reply_text("❌ **Poster topilmadi!** Jarayonni qayta boshlang: /start")
            return ConversationHandler.END

        # 4. Ma'lumotlar bazasiga yozish
        conn = get_db()
        if not conn:
            await update.message.reply_text("❌ Bazaga ulanishda xato!")
            return A_ADD_ANI_DATA
            
        cur = conn.cursor()
        
        # Anime ro'yxatini yangilash (Agar anime avval bo'lmasa qo'shadi, bo'lsa yangilaydi)
        cur.execute("""
            INSERT INTO anime_list (anime_id, name, poster_id) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE name=%s, poster_id=%s
        """, (aid, name, p_id, name, p_id))
        
        # Qismni yuklash
        cur.execute("""
            INSERT INTO anime_episodes (anime_id, episode, lang, file_id) 
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE file_id=%s, lang=%s
        """, (aid, ep, lang, v_id, v_id, lang))
        
        conn.commit()
        cur.close()
        conn.close()

        # 5. Muvaffaqiyatli tugmalar
        kb = [
            [InlineKeyboardButton("➕ Yana qism qo'shish (Xuddi shu anime)", callback_data="add_more_ep")],
            [InlineKeyboardButton("✅ Jarayonni yakunlash", callback_data="admin_main")]
        ]
        
        await update.message.reply_text(
            f"✅ **Qism muvaffaqiyatli saqlandi!**\n\n"
            f"📺 **Anime:** {name}\n"
            f"🔢 **Qism:** {ep}\n"
            f"🌐 **Til:** {lang}\n\n"
            f"Yana qism qo'shish uchun video yuboring yoki quyidagilardan birini tanlang:",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
        
        # MUHIM O'ZGARIŞ: ConversationHandler.END o'rniga holatni saqlab qolamiz
        # Shunda foydalanuvchi tugmani bosmasdan ham ketma-ket video tashlayverishi mumkin
        return A_ADD_ANI_DATA 

    except Exception as e:
        await update.message.reply_text(
            f"❌ **Xatolik yuz berdi:**\n`{str(e)}`\n\n"
            f"Formatni tekshiring: `ID | Nomi | Tili | Qismi`",
            parse_mode="Markdown"
        )
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
    
        
# ====================== MAIN FUNKSIYA (TO'LIQ VA YAKUNIY VARIANT) ======================
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
    
    # Menyu filtri (Tugmalarni tanish uchun)
    menu_filter = filters.Regex("Anime qidirish|VIP PASS|Bonus ballarim|Qo'llanma|Barcha anime ro'yxati|ADMIN PANEL|Bekor qilish")

    # 4. CONVERSATION HANDLER
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            # Regexni yanada soddalashtirdik
            MessageHandler(filters.Regex(r"Anime qidirish"), search_menu_cmd),
            MessageHandler(filters.Regex(r"VIP PASS"), vip_pass_info),
            MessageHandler(filters.Regex(r"Bonus ballarim"), show_bonus),
            MessageHandler(filters.Regex(r"Qo'llanma"), show_guide),
            MessageHandler(filters.Regex(r"Barcha anime ro'yxati"), export_all_anime),
            MessageHandler(filters.Regex(r"ADMIN PANEL"), lambda u, c: u.message.reply_text(
                "🛠 Admin paneli:", 
                reply_markup=get_admin_kb(u.effective_user.id == MAIN_ADMIN_ID)
            )),
            CallbackQueryHandler(handle_callback)
        ],
        states={
            A_SEARCH_BY_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_filter, search_anime_logic)],
            A_SEARCH_BY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_filter, search_anime_logic)],
            A_ADD_CH: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_filter, exec_add_channel)],
            A_REM_CH: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_filter, exec_rem_channel)],
            A_ADD_ADM: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_filter, exec_add_admin)],
            A_ADD_ANI_POSTER: [MessageHandler(filters.PHOTO, add_ani_poster)],
            A_ADD_ANI_DATA: [MessageHandler(filters.VIDEO | (filters.TEXT & ~menu_filter), add_ani_data)],
            A_SEND_ADS_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_ads_pass)],
            A_SEND_ADS_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND & ~menu_filter, ads_send_finish)],
            A_ADD_VIP: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_filter, exec_vip_add)],
        },
        fallbacks=[
            CommandHandler("start", start),
            # VIP PASS ni fallbacksga qo'shish "tiqilib" qolishdan chiqaradi
            MessageHandler(filters.Regex(r"VIP PASS|Orqaga|Bekor qilish"), start),
            CallbackQueryHandler(handle_callback)
        ],
        allow_reentry=True,
        # MUHIM: Har safar name o'zgarsa, bot eski "blok"lardan chiqadi
        name="aninow_final_v99" 
    )

    # 5. HANDLERLARNI QO'SHISH (TARTIB O'ZGARTIRILDI!)
    
    # Birinchi navbatda CommandHandlerlarni qo'shish kerak
    app_bot.add_handler(CommandHandler("start", start))
    
    # Keyin Inline tugmalar (Page, Episode)
    app_bot.add_handler(CallbackQueryHandler(handle_pagination, pattern="^page_"))
    app_bot.add_handler(CallbackQueryHandler(get_episode_handler, pattern="^get_ep_"))

    app_bot.add_handler(CallbackQueryHandler(show_vip_removal_list, pattern="^rem_vip_list"))
    app_bot.add_handler(CallbackQueryHandler(show_vip_removal_list, pattern="^rem_vip_page_"))

    # Keyin Conversation Handler
    app_bot.add_handler(conv_handler)
    
    # Oxirida zaxira handlerlar
    app_bot.add_handler(CallbackQueryHandler(handle_callback))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start))

    # 6. Botni ishga tushirish
    print("🚀 Bot muvaffaqiyatli ishga tushdi...")
    app_bot.run_polling()


if __name__ == '__main__':
    main()

    

    

    





































