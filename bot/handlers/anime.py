import datetime
import urllib

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from db import db_pool, execute_query, get_db
from config import logger
from aiomysql import DictCursor, Pool, OperationalError
from config import ADMIN_GROUP_ID, MAIN_ADMIN_ID, BOT_TOKEN
from handlers.admin import show_anime_info
from utils import check_sub
from handlers.common import get_user_status
from states import U_FEEDBACK_SUBJ, U_FEEDBACK_MSG, A_MAIN,A_REM_ANI_LIST, A_SEARCH_BY_NAME, A_SEARCH_BY_ID, A_SEARCH_BY_CHARACTER, A_SHOW_FANDUB_LIST, A_SHOW_SELECTED_ANIME, A_SHOW_ANIME_DETAILS, A_ANI_CONTROL, A_GET_POSTER, A_GET_DATA, A_ADD_EP_FILES, A_SELECT_ANI_EP, A_ADD_MENU, A_REM_EP_ANI_LIST, A_REM_EP_NUM_LIST, A_REM_MENU 
from keyboards import get_cancel_kb, get_main_kb
from handlers.user import show_fandub_list, show_selected_anime, show_anime_details, get_admin_kb, get_pagination_keyboard, select_ani_for_rem_ep, list_animes_view, add_anime_panel



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


async def search_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qidiruv turini tanlash menyusi"""
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
    
    is_callback = bool(update.callback_query)
    msg_obj = update.callback_query.message if is_callback else update.message

    text = (
        "🎬 <b>Anime qidirish bo'limi</b>\n\n"
        "Qidiruv usulini tanlang:\n\n"
        "💡 <i>Maslahat: Rasm orqali qidirish (AI) animesi esingizda yo'q kadrlarni topishga yordam beradi!</i>"
    )

    if is_callback:
        await update.callback_query.edit_message_text(
            text=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
        )
    else:
        await msg_obj.reply_text(
            text=text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
        )
    
    # 🔥 MANA BU QATOR JUDA MUHIM:
    return A_MAIN 


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


# ===================================================================================


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


#===================================================================================


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


#===================================================================================


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


#===================================================================================


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
    
#===================================================================================

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


#===================================================================================


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

#===================================================================================


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


#===================================================================================


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
    

#===================================================================================

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
    

#===================================================================================

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

#===================================================================================

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

#===================================================================================

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


#=======================================================================================================


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

#===================================================================================

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


#===================================================================================


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



#===================================================================================


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


#========================================================================================================

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


#========================================================================================================


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



# ----------------- CALLBACK HANDLER (MUHIM QISM) -----------------


async def anime_callback_handle(update, context):
    query = update.callback_query
    data = query.data
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




async def search_callback_handle(update, context, status):
    query = update.callback_query
    data = query.data
    
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

    elif data == "back_to_search_menu":
        # ... (yuqoridagi search_btns kodi)
        return None 

    elif data == "cancel_search":
        await query.message.delete()
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text="🏠 <b>Qidiruv bekor qilindi.</b>\nAsosiy menyu:",
            reply_markup=get_main_kb(status),
            parse_mode="HTML"
        )
        return ConversationHandler.END