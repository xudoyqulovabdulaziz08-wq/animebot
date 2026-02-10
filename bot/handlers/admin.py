import datetime
import re
import io
import json
import asyncio
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from handlers.callback_router import handle_callback
from handlers.common import get_user_status
from states import A_ADD_CH, A_REM_CH, A_SEND_ADS_PASS, A_ANI_CONTROL, A_MAIN,A_SEND_ADS_MSG, A_ADD_ADM, A_ADD_ANI_POSTER, A_ADD_VIP, A_REM_VIP, A_LIST_VIEW, A_SELECT_ADS_TARGET # va boshqa holatlar
from keyboards import get_admin_kb, get_main_kb # admin tugmalari
from config import ADMIN_GROUP_ID, MAIN_ADMIN_ID, ADVERTISING_PASSWORD, logger
from db import execute_query, get_db

from utils import check_sub, is_admin,  get_pagination_keyboard,  anime_control_panel, get_all_channels, add_channel, remove_channel, get_user_status, delete_channel_by_id, add_admin, remove_admin, get_all_admins, add_vip, remove_vip, get_all_vips,  background_ads_task
import json
from config import logger
from aiomysql import Pool
db_pool: Pool = None



# ===================================================================================

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


# ===================================================================================


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
    
    elif query.data == "admin_main":
        return await admin_channels_menu(update, context) # Kanal boshqaruv menyusiga qaytish
    
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


#==================================================================================



#==================================================================================


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

        if status in ["admin", "main_admin"]:
            await update.message.reply_text(
                "❌ <b>Noto'g'ri parol!</b>\n\n"
                "Iltimos, reklama kampaniyasini boshlash uchun to'g'ri parolni kiriting yoki bekor qiling:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_pass")],
                    [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_ads")]
                ]),
                parse_mode="HTML"
            )
            return A_SEND_ADS_PASS
        else:
            await update.message.reply_text("❌ Sizda reklama kampaniyasini boshlash huquqi yo'q!")
            return ConversationHandler.END
    


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


# ----------------- CALLBACK HANDLER (MUHIM QISM) -----------------

async def admin_callback_handle(update, context, status):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

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
                    await cur.execute("SELECT user_id FROM admins")
                    admins = await cur.fetchall()
            
            if not admins:
                await query.answer("📭 Hozircha adminlar yo'q (Sizdan tashqari).", show_alert=True)
                return None
                
            keyboard = []
            for adm in admins:
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
                    await cur.execute("DELETE FROM admins WHERE user_id = %s", (adm_id,))
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
                    await cur.execute("INSERT INTO admins (user_id) VALUES (%s)", (new_id,))
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
