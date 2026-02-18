import html
from sqlalchemy import func, select
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from database.db import get_anime_session, session_factories   # Router va sessiyalar
from database.models import Anime, Episode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters
 # 7 ta sessiya fabrikasi
from database.models import Anime, Episode
POSTER, DATA, VIDEO,  = range(3)
# ===================================================================================


async def show_anime_details(update: Update, context: ContextTypes.DEFAULT_TYPE, anime_id: int):
    is_callback = update.callback_query is not None
    target = update.callback_query.message if is_callback else update.message
    
    anime = None
    active_session_factory = None

    # 1. 🔍 3 ta anime bazasidan qidirish (A1, A2, A3)
    for key in ["a1", "a2", "a3"]:
        async with session_factories[key]() as session:
            stmt = select(Anime).where(Anime.anime_id == anime_id)
            res = await session.execute(stmt)
            found_anime = res.scalar_one_or_none()
            
            if found_anime:
                # Topildi! Endi ma'lumotlarni o'zgaruvchiga olamiz
                # Session yopilishidan oldin obyektni "jonli" saqlash kerak
                anime = found_anime
                # Ko'rishlar sonini oshiramiz
                anime.views_week += 1
                await session.commit() 
                
                # Ma'lumotlarni dict ko'rinishida saqlab olamiz (session yopilganda error bermasligi uchun)
                anime_data = {
                    "name": anime.name,
                    "genre": anime.genre or "Noma'lum",
                    "year": anime.year or "Noma'lum",
                    "fandub": anime.fandub or "Noma'lum",
                    "lang": anime.lang or "O'zbek",
                    "views": anime.views_week,
                    "is_completed": anime.is_completed,
                    "poster_id": anime.poster_id,
                    "description": anime.description or "Tavsif mavjud emas.",
                    "rating": f"{anime.rating_sum / anime.rating_count:.1f}" if anime.rating_count > 0 else "Hali reyting berilmagan"
                }
                break 

    # 2. ❌ Agar topilmasa
    if not anime:
        msg = "❌ Kechirasiz, bu anime haqida ma'lumot topilmadi."
        if is_callback: await update.callback_query.answer(msg, show_alert=True)
        else: await target.reply_text(msg)
        return

    # 3. 📝 Matnni shakllantirish
    desc = anime_data["description"]
    if len(desc) > 500:
        desc = desc[:500].rsplit(' ', 1)[0] + "..."

    holati = "Tugallangan" if anime_data["is_completed"] else "Davom etmoqda"

    caption = (
        f"🎬 <b>{anime_data['name']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎭 <b>Janr:</b> {anime_data['genre']}\n"
        f"📅 <b>Yil:</b> {anime_data['year']}\n"
        f"🎙 <b>Fandub:</b> {anime_data['fandub']}\n"
        f"🌐 <b>Til:</b> {anime_data['lang']}\n"
        f"👁 <b>Ko‘rishlar:</b> {anime_data['views']}\n"
        f"📊 <b>Reyting:</b> ⭐ {anime_data['rating']}\n"
        f"✅ <b>Holati:</b> {holati}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📖 <b>Qisqacha mazmuni:</b>\n<i>{desc}</i>"
    )

    # 4. ⌨️ Klaviatura
    buttons = [
        [InlineKeyboardButton("🎞 Qismlarni ko'rish", callback_data=f"show_episodes_{anime_id}")],
        [
            InlineKeyboardButton("🌟 Sevimlilar", callback_data=f"fav_{anime_id}"),
            InlineKeyboardButton("✍️ Sharhlar", callback_data=f"comments_{anime_id}")
        ],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_search_main")]
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    # 5. 📤 Yuborish
    try:
        if is_callback: await update.callback_query.answer()

        if anime_data["poster_id"]:
            await context.bot.send_photo(
                chat_id=target.chat_id,
                photo=anime_data["poster_id"],
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            await context.bot.send_message(
                chat_id=target.chat_id,
                text=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        
        # Eski ro'yxatni o'chirish (Xabarni toza saqlash uchun)
        if is_callback:
            await update.callback_query.message.delete()

    except Exception as e:
        print(f"🚀 Render Error (show_details): {e}")
        await target.reply_text("⚠️ Ma'lumotni yuklashda texnik xatolik yuz berdi.")



# ===================================================================================




async def show_episodes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data_parts = query.data.split("_")
    
    # Callback format: show_episodes_ID_PAGE
    anime_id = int(data_parts[2]) 
    page = int(data_parts[3]) if len(data_parts) > 3 else 1
    
    items_per_page = 12 
    all_episodes = []

    # 1. 🔍 Anime qaysi bazadaligini topish va qismlarni olish
    # (Eslatma: Anime va uning epizodlari bitta bazada bo'ladi)
    found_in_db = None
    for key in ["a1", "a2", "a3"]:
        async with session_factories[key]() as session:
            stmt = select(Episode).where(Episode.anime_id == anime_id).order_by(Episode.episode.asc())
            res = await session.execute(stmt)
            ep_list = res.scalars().all()
            
            if ep_list:
                # Agar qismlar topilsa, demak bazani topdik
                all_episodes = ep_list
                found_in_db = key
                break

    # 2. ❌ Agar qismlar topilmasa
    if not all_episodes:
        await query.answer("😔 Hozircha qismlar yuklanmagan yoki anime topilmadi.", show_alert=True)
        return

    # 3. 📑 Paginnatsiya mantiqi
    total_episodes = len(all_episodes)
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    current_page_episodes = all_episodes[start_idx:end_idx]

    # 4. ⌨️ Tugmalarni yasash
    buttons = []
    row = []
    for ep in current_page_episodes:
        # Muhim: video_ callbackiga DB kalitini ham qo'shsak bo'ladi (ixtiyoriy)
        row.append(InlineKeyboardButton(f"{ep.episode}", callback_data=f"video_{ep.id}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Navigatsiya tugmalari
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"show_episodes_{anime_id}_{page-1}"))
    
    # "Orqaga" tugmasi anime detallariga qaytaradi
    nav_buttons.append(InlineKeyboardButton("🏘 Orqaga", callback_data=f"info_{anime_id}"))

    if end_idx < total_episodes:
        nav_buttons.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"show_episodes_{anime_id}_{page+1}"))

    buttons.append(nav_buttons)

    # 5. 📤 Ekranni yangilash
    total_pages = (total_episodes + items_per_page - 1) // items_per_page
    caption = f"🎞 <b>Qismlar ro'yxati</b> (Sahifa: {page}/{total_pages})\n\n<i>Kerakli qismni tanlang:</i>"

    try:
        await query.answer() # Yuklanish belgisini o'chirish
        await query.edit_message_caption(
            caption=caption,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Pagination Error: {e}")
        # Agar caption bo'lmasa (masalan rasm o'chib ketgan bo'lsa), oddiy xabar yuboramiz
        await query.edit_message_text(
            text=caption,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML"
        )


# ===================================================================================




async def video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # callback_data format: video_EPISODE_ID
    ep_db_id = int(query.data.split("_")[1])
    
    current_ep = None
    anime = None
    next_ep = None
    
    # 1. 🔍 3 ta anime bazasidan joriy qismni qidiramiz
    for key in ["a1", "a2", "a3"]:
        async with session_factories[key]() as session:
            # Epizodni ID bo'yicha qidirish
            stmt = select(Episode).where(Episode.id == ep_db_id)
            res = await session.execute(stmt)
            found_ep = res.scalar_one_or_none()
            
            if found_ep:
                current_ep = found_ep
                
                # 2. Anime nomini ham o'sha bazadan olamiz (caption uchun)
                anime_stmt = select(Anime).where(Anime.anime_id == current_ep.anime_id)
                a_res = await session.execute(anime_stmt)
                anime = a_res.scalar_one_or_none()

                # 3. Keyingi qism bormi? (Aynan shu bazadan qidiramiz)
                next_ep_stmt = select(Episode).where(
                    Episode.anime_id == current_ep.anime_id,
                    Episode.episode == current_ep.episode + 1
                )
                next_res = await session.execute(next_ep_stmt)
                next_ep = next_res.scalar_one_or_none()
                
                # Bazani topdik va hamma kerakli narsani oldik, tsikldan chiqamiz
                break

    # 4. ❌ Agar topilmasa
    if not current_ep or not anime:
        await query.answer("❌ Video yoki anime ma'lumotlari topilmadi!", show_alert=True)
        return

    # 5. ⌨️ Tugmalarni yasaymiz
    vid_buttons = []
    # Orqaga qaytish: show_episodes_{anime_id}
    row = [InlineKeyboardButton("⬅️ Qismlar ro'yxati", callback_data=f"show_episodes_{current_ep.anime_id}")]
    
    if next_ep:
        row.append(InlineKeyboardButton("Keyingi qism ➡️", callback_data=f"video_{next_ep.id}"))
    
    vid_buttons.append(row)
    vid_buttons.append([
        InlineKeyboardButton("💾 Tugatish", callback_data=f"finish_ep_{current_ep.id}")
    ])

    # 6. 📤 Videoni yuboramiz
    caption = (
        f"🎬 <b>{anime.name}</b>\n"
        f"🎞 <b>{current_ep.episode}-qism</b>\n\n"
        f"📢 @aninovuz"
    )

    try:
        # Foydalanuvchiga yuklanish effekti uchun javob beramiz
        await query.answer("🚀 Video yuklanmoqda...")
        
        await query.message.reply_video(
            video=current_ep.file_id,
            caption=caption,
            reply_markup=InlineKeyboardMarkup(vid_buttons),
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"❌ Video yuborishda xatolik: {e}")
        await query.message.reply_text("⚠️ Videoni yuborishda texnik xatolik yuz berdi.")


# ===================================================================================



async def show_anime_details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    anime_id = int(query.data.split("_")[1])
    await show_anime_details(update, context, anime_id)
    await query.answer()

# ===================================================================================



async def show_anime_details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    anime_id = int(query.data.split("_")[1])
    await show_anime_details(update, context, anime_id)
    await query.answer()



# ===================================================================================



async def admin_list_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        page = int(query.data.split('_')[-1])
    except (ValueError, IndexError):
        page = 0

    limit = 20
    offset = page * limit

    all_animes = []
    total_count = 0

    # 1. 🔄 Hamma anime bazalarini (A1, A2, A3) aylanib chiqamiz
    for key in ["a1", "a2", "a3"]:
        async with session_factories[key]() as session:
            # Har bir bazadagi sonini sanaymiz
            count_stmt = select(func.count(Anime.anime_id))
            res_count = await session.execute(count_stmt)
            total_count += res_count.scalar()

            # Har bir bazadan oxirgi qo'shilganlarini olamiz
            # (Pagination to'g'ri ishlashi uchun hamma bazadan limit miqdoricha olib turamiz)
            stmt = select(Anime).order_by(Anime.anime_id.desc()).limit(offset + limit)
            res = await session.execute(stmt)
            all_animes.extend(res.scalars().all())

    # 2. 🔀 Barcha bazalardan olingan animelarni ID bo'yicha teskari tartibda saralaymiz
    all_animes.sort(key=lambda x: x.anime_id, reverse=True)

    # 3. ✂️ Kerakli sahifa (offset:limit) qismini qirqib olamiz
    paged_animes = all_animes[offset : offset + limit]

    buttons = []
    for anime in paged_animes:
        # ID yoniga qaysi bazada ekanligini bildirish uchun belgi qo'ysak ham bo'ladi (ixtiyoriy)
        buttons.append([InlineKeyboardButton(
            f"🆔 {anime.anime_id} | {anime.name}", 
            callback_data=f"adm_v_{anime.anime_id}"
        )])

    # 4. 🕹 Navigatsiya tugmalari
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"admin_list_anime_{page - 1}"))
    
    if offset + limit < total_count:
        nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"admin_list_anime_{page + 1}"))
    
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("⬅️ Anime Controlga qaytish", callback_data="adm_ani_ctrl")])
    
    text = (
        f"<b>📜 Barcha bazalardagi animelar (A1+A2+A3)</b>\n\n"
        f"Jami: <b>{total_count}</b> ta\n"
        f"Sahifa: <b>{page + 1}</b> / {int((total_count + limit - 1) / limit)}"
    )

    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


# ===================================================================================



async def admin_view_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # adm_v_123 -> 123
    anime_id = int(query.data.split('_')[-1])

    anime = None
    ep_count = 0
    found_db = None

    # 1. 🔍 3 ta anime bazasidan (A1, A2, A3) qidirish
    for key in ["a1", "a2", "a3"]:
        async with session_factories[key]() as session:
            # Animeni olish
            stmt = select(Anime).where(Anime.anime_id == anime_id)
            res = await session.execute(stmt)
            found_anime = res.scalar_one_or_none()

            if found_anime:
                anime = found_anime
                # 2. Shu bazaning o'zidan epizodlar sonini sanash
                ep_count_stmt = select(func.count(Episode.id)).where(Episode.anime_id == anime_id)
                ep_res = await session.execute(ep_count_stmt)
                ep_count = ep_res.scalar()
                
                # Topilgan ma'lumotlarni o'zgaruvchilarga saqlab, sessiyadan uzilamiz
                anime_info = {
                    "id": anime.anime_id,
                    "name": anime.name,
                    "lang": anime.lang,
                    "genre": anime.genre,
                    "year": anime.year,
                    "fandub": anime.fandub,
                    "views": anime.views_week,
                    "rating": anime.rating_sum / anime.rating_count if anime.rating_count > 0 else 0
                }
                found_db = key # Qaysi bazadan topilganini eslab qolamiz (admin uchun foydali bo'lishi mumkin)
                break

    if not anime:
        await query.edit_message_text("❌ Kechirasiz, bu anime bazadan topilmadi!")
        return

    # 3. 📝 Ma'lumotlarni chiqarish
    text = (
        f"<b>🛠 Admin Ko'rinishi</b> ({found_db.upper()} bazasi)\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>ID:</b> <code>{anime_info['id']}</code>\n"
        f"🎬 <b>Nomi:</b> {anime_info['name']}\n"
        f"🎞 <b>Qismlar soni:</b> {ep_count}\n"
        f"🌐 <b>Tili:</b> {anime_info['lang'] or 'Noma`lum'}\n"
        f"🎭 <b>Janri:</b> {anime_info['genre'] or 'Noma`lum'}\n"
        f"📅 <b>Yili:</b> {anime_info['year'] or 'Noma`lum'}\n"
        f"🎙 <b>Fandub:</b> {anime_info['fandub'] or 'Noma`lum'}\n"
        f"👁 <b>Haftalik ko'rilgan:</b> {anime_info['views']}\n"
        f"⭐ <b>Reyting:</b> {anime_info['rating']:.1f}\n"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎞 Epizodlarni boshqarish", callback_data=f"adm_ep_ctrl_{anime_id}")],
        [InlineKeyboardButton("⬅️ Ro'yxatga qaytish", callback_data="admin_list_anime_0")]
    ])

    await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="HTML")


# ===================================================================================




# --- 1-QADAM: POSTER (O'zgarmaydi) ---
async def start_add_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎬 <b>Yangi anime qo'shish.</b>\n\n1. Poster yuboring:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Bekor qilish", callback_data="adm_ani_ctrl")]])
    )
    return POSTER

# handlers/anime.py ichida

async def get_poster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Posterni file_id ko'rinishida olish (Rasm yoki Hujjat)"""
    msg = update.message
    
    file_id = None
    if msg.photo:
        # Eng sifatli rasm IDsi
        file_id = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type.startswith('image/'):
        # Hujjat ko'rinishida yuborilgan rasm IDsi
        file_id = msg.document.file_id
    else:
        await msg.reply_text("❌ Iltimos, faqat rasm yuboring!")
        return POSTER # POSTER holatida qolamiz

    # Keyingi qadam uchun saqlaymiz
    context.user_data['poster_id'] = file_id
    
    await msg.reply_text(
        "✅ Poster qabul qilindi.\n\n"
        "2. Endi ma'lumotlarni quyidagi formatda yuboring:\n\n"
        "<code>Nomi | Tili | Janri | Yili | Fandub | Tavsif</code>\n\n"
        "<i>Eslatma: Janrlarni vergul bilan ajratib yozing.</i>",
        parse_mode="HTML"
    )
    return DATA # DATA holatiga o'tamiz
 
# --- 2-QADAM: DATA (Router qo'shildi) ---
async def get_anime_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text
    parts = [p.strip() for p in raw_text.split('|')]
    
    if len(parts) < 4:
        await update.message.reply_text("❌ Format xato! Nomi | Tili | Janri | Yili...")
        return DATA

    name, lang, genre, year = parts[0], parts[1], parts[2], parts[3]
    fandub = parts[4] if len(parts) > 4 else "Noma'lum"
    description = parts[5] if len(parts) > 5 else "Tavsif mavjud emas."

    # 🚀 ROUTER: Nomi bo'yicha qaysi bazaga tushishini aniqlaymiz
    # Masalan: "Naruto" -> A2 sessiyasini beradi
    async with get_anime_session(name) as session:
        try:
            new_anime = Anime(
                name=name,
                poster_id=context.user_data.get('poster_id'),
                lang=lang, genre=genre, year=year,
                fandub=fandub, description=description,
                is_completed=False
            )
            session.add(new_anime)
            await session.commit()
            await session.refresh(new_anime)
            
            # Keyingi qadamlar uchun ma'lumotlarni saqlaymiz
            context.user_data['current_anime_id'] = new_anime.anime_id
            context.user_data['anime_name'] = name
            context.user_data['last_ep_num'] = 0
            
            # MUHIM: Videolar ham aynan shu bazaga tushishi uchun bazani eslab qolamiz
            # Bu yerda nomning birinchi harfi orqali bazani aniqlash kalitini saqlaymiz
            from database.db import anime_router
            context.user_data['target_db'] = anime_router(name) 

            await update.message.reply_text(
                f"✅ <b>'{html.escape(name)}'</b> saqlandi!\n"
                f"📍 Baza: <b>{context.user_data['target_db'].upper()}</b>\n"
                f"🆔 ID: <code>{new_anime.anime_id}</code>\n\n"
                f"📹 Endi videolarni yuboring.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Tugatish", callback_data="finish_add")]
                ])
            )
            return VIDEO
        except Exception as e:
            await session.rollback()
            await update.message.reply_text(f"❌ Xatolik: {e}")
            return ConversationHandler.END

# --- 3-QADAM: VIDEOLAR (Belgilangan bazaga yozish) ---
async def get_episodes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    ani_id = context.user_data.get('current_anime_id')
    db_key = context.user_data.get('target_db') # A1, A2 yoki A3

    file_id = msg.video.file_id if msg.video else (msg.document.file_id if msg.document else None)
    
    if not file_id or not db_key:
        await msg.reply_text("❌ Video yuboring!")
        return VIDEO

    context.user_data['last_ep_num'] += 1
    current_ep = context.user_data['last_ep_num']

    # 💾 Animening o'zi qaysi bazada bo'lsa, qismlar ham o'sha yerga tushadi
    async with session_factories[db_key]() as session:
        new_episode = Episode(anime_id=ani_id, episode=current_ep, file_id=file_id)
        session.add(new_episode)
        await session.commit()

    await msg.reply_text(
        f"📥 <b>{current_ep}-qism</b> [{db_key.upper()}] bazasiga saqlandi.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Tugatish", callback_data="finish_add")]])
    )
    return VIDEO 

# handlers/anime.py faylining eng oxiriga qo'shing:

async def finish_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jarayonni yopish va kutish rejimidan chiqish"""
    query = update.callback_query
    await query.answer("Jarayon yakunlandi!")
    
    # Foydalanuvchi ma'lumotlarini tozalaymiz
    context.user_data.clear()
    
    await query.edit_message_text(
        "✅ <b>Barcha qismlar muvaffaqiyatli saqlandi.</b>\n"
        "Admin panelga qaytishingiz mumkin.",
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def publish_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kanalga jo'natish tugmasi uchun (Hozircha faqat jarayonni yopadi)"""
    query = update.callback_query
    await query.answer("Kanalga yuborish navbatga qo'yildi...")
    
    # Bu yerda kelajakda kanalga post qilish funksiyasini chaqirishingiz mumkin
    context.user_data.clear()
    
    await query.edit_message_text(
        "🚀 <b>Anime bazaga olindi va kanalga navbatga qo'yildi.</b>",
        parse_mode="HTML"
    )
    return ConversationHandler.END










