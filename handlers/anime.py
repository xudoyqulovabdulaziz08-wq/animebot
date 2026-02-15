
from sqlalchemy import func, select
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from database.db import async_session
from database.models import Anime, Episode
from telegram.ext import ContextTypes

# ===================================================================================


async def show_anime_details(update: Update, context: ContextTypes.DEFAULT_TYPE, anime_id: int):
    
    is_callback = update.callback_query is not None
    target = update.callback_query.message if is_callback else update.message

    async with async_session() as session:
        stmt = select(Anime).where(Anime.anime_id == anime_id)
        res = await session.execute(stmt)
        anime = res.scalar_one_or_none()

        if not anime:
            await target.reply_text("❌ Kechirasiz, bu anime haqida ma'lumot topilmadi.")
            return
        description = anime.description or 'Mazmun qoshilmagan'
        if len(description) > 500:
            description = description[:500] + "..."
        # Matnni shakllantiramiz
        genren = anime.genre if anime.genre else "Noma'lum"
        yearn = anime.year if anime.year else "Noma'lum"
        fandubn = anime.fandub if anime.fandub else "Noma'lum"
        langn = anime.lang if anime.lang  else "O'zbek"
        caption = (
            f"🎬 <b>{anime.name}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎭 <b>Janr:</b> {genren}\n"
            f"📅 <b>Yil:</b> {yearn}\n"
            f"🎙 <b>Fandub:</b> {fandubn}\n"
            f"🌐 <b>Til:</b> {langn}\n"
            f"📊 <b>Reyting:</b> ⭐ {anime.rating_sum or 0}\n"
            f"✅ <b>Holati:</b> {'Tugallangan' if anime.is_completed else 'Davom etmoqda'}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 <b>Kanal:</b> <a href='https://t.me/aninovuz'>@aninovuz</a>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📖 <b>Qisqacha mazmuni:</b>\n{description}"
)

        # Tugmalar (Qismlar va Sevimlilar)
        buttons = [
            [InlineKeyboardButton("🎞 Qismlarni ko'rish", callback_data=f"show_episodes{anime_id}")],
            [
                InlineKeyboardButton("🌟 Sevimlilarga qo'shish", callback_data=f"fav_{anime_id}"),
                InlineKeyboardButton("❌ Yopish", callback_data="delete_msg")
            ]
        ]
        keyboard = InlineKeyboardMarkup(buttons)

        # Poster yuborish
        try:
            if anime.poster_id:
                await target.reply_photo(
                    photo=anime.poster_id,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            else:
                await target.reply_text(caption, reply_markup=keyboard, parse_mode="HTML")
            
            # Agar bu tugma bosish orqali kelgan bo'lsa, eski ro'yxatni o'chirib tashlaymiz
            if is_callback:
                await update.callback_query.message.delete()
        except Exception as e:
            print(f"Xatolik (Anime ko'rsatishda): {e}")
            await target.reply_text("⚠️ Xatolik: Rasmni yuborib bo'lmadi, lekin ma'lumotlar yuqorida.")



# ===================================================================================


async def show_episodes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data_parts = query.data.split("_")
    
    anime_id = int(data_parts[1])
    # Agar sahifa ko'rsatilmagan bo'lsa, 1-sahifadan boshlaymiz
    page = int(data_parts[2]) if len(data_parts) > 2 else 1
    
    items_per_page = 12 # 3 qator * 4 tadan = 12 ta qism

    async with async_session() as session:
        # Barcha qismlarni olamiz
        stmt = select(Episode).where(Episode.anime_id == anime_id).order_by(Episode.episode.asc())
        res = await session.execute(stmt)
        all_episodes = res.scalars().all()

        if not all_episodes:
            await query.answer("😔 Hozircha qismlar yuklanmagan.", show_alert=True)
            return

        total_episodes = len(all_episodes)
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        
        # Joriy sahifa uchun qismlarni qirqib olamiz
        current_page_episodes = all_episodes[start_idx:end_idx]

        buttons = []
        # 1. Qismlar tugmalari (3 qator, 4 tadan)
        row = []
        for ep in current_page_episodes:
            row.append(InlineKeyboardButton(f"{ep.episode}", callback_data=f"video_{ep.id}"))
            if len(row) == 4:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        # 2. Boshqaruv tugmalari (Oldingi, Keyingi, Tugatish)
        nav_buttons = []
        
        # "Oldingi" tugmasi (faqat 1-sahifadan katta bo'lsa chiqadi)
        if page > 1:
            nav_buttons.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"episodes_{anime_id}_{page-1}"))
        
        # "Tugatish" yoki "Orqaga" markazda
        nav_buttons.append(InlineKeyboardButton("❌ Tugatish", callback_data=f"info_{anime_id}"))

        # "Keyingi" tugmasi (agar yana qismlar bo'lsa chiqadi)
        if end_idx < total_episodes:
            nav_buttons.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"episodes_{anime_id}_{page+1}"))

        buttons.append(nav_buttons)

        # Sahifa haqida ma'lumot
        total_pages = (total_episodes + items_per_page - 1) // items_per_page
        caption = f"🎞 <b>Qismlar ro'yxati</b> (Sahifa: {page}/{total_pages})\n\n<i>Kerakli qismni tanlang:</i>"

        await query.edit_message_caption(
            caption=caption,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML"
        )

# ===================================================================================

async def video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # callback_data format: video_EPISODE_ID
    ep_db_id = int(query.data.split("_")[1])
    
    async with async_session() as session:
        # 1. Joriy qismni bazadan olamiz
        stmt = select(Episode).where(Episode.id == ep_db_id)
        res = await session.execute(stmt)
        current_ep = res.scalar_one_or_none()
        
        if not current_ep:
            await query.answer("❌ Video topilmadi!", show_alert=True)
            return

        # 2. Keyingi qism bormi yoki yo'qligini tekshiramiz
        next_ep_stmt = select(Episode).where(
            Episode.anime_id == current_ep.anime_id,
            Episode.episode == current_ep.episode + 1
        )
        next_res = await session.execute(next_ep_stmt)
        next_ep = next_res.scalar_one_or_none()

        # 3. Tugmalarni yasaymiz
        vid_buttons = []
        row = [InlineKeyboardButton("⬅️ Qismlar ro'yxati", callback_data=f"show_episodes_{current_ep.anime_id}")]
        
        if next_ep:
            row.append(InlineKeyboardButton("Keyingi qism ➡️", callback_data=f"video_{next_ep.id}"))
        
        vid_buttons.append(row)
        vid_buttons.append([InlineKeyboardButton("❌ Yopish", callback_data="delete_msg")])

        # 4. Videoni yuboramiz
        # Sarlavha (caption) uchun anime nomini ham olsak chiroyli chiqadi
        anime_stmt = select(Anime).where(Anime.anime_id == current_ep.anime_id)
        a_res = await session.execute(anime_stmt)
        anime = a_res.scalar_one_or_none()

        caption = f"🎬 <b>{anime.name}</b>\n🎞 <b>{current_ep.episode}-qism</b>\n\n📢 @aninovuz"

        await query.message.reply_video(
            video=current_ep.file_id,
            caption=caption,
            reply_markup=InlineKeyboardMarkup(vid_buttons),
            parse_mode="HTML"
        )
        await query.answer()



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
    
    # Callbackdan sahifa raqamini olamiz (masalan, list_0 -> 0)
    # Agar data faqat 'admin_list_anime' bo'lsa, page = 0 bo'ladi
    try:
        page = int(query.data.split('_')[-1])
    except (ValueError, IndexError):
        page = 0

    limit = 20
    offset = page * limit

    async with async_session() as session:
        # 1. Jami animelar sonini sanaymiz
        count_stmt = select(func.count(Anime.anime_id))
        total_res = await session.execute(count_stmt)
        total_count = total_res.scalar()

        # 2. Shu sahifa uchun animelarni olamiz (ID bo'yicha teskari tartibda)
        stmt = select(Anime).order_by(Anime.anime_id.desc()).offset(offset).limit(limit)
        res = await session.execute(stmt)
        animes = res.scalars().all()

    buttons = []
    # 20 ta anime tugmasi
    for anime in animes:
        buttons.append([InlineKeyboardButton(f"🆔 {anime.anime_id} | {anime.name}", callback_data=f"adm_v_{anime.anime_id}")])

    # Navigatsiya tugmalari (Oldingi / Keyingi)
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"admin_list_anime_{page - 1}"))
    if offset + limit < total_count:
        nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"admin_list_anime_{page + 1}"))
    
    if nav_row:
        buttons.append(nav_row)

    # Orqaga qaytish menyusi
    buttons.append([InlineKeyboardButton("⬅️ Anime Controlga qaytish", callback_data="adm_ani_ctrl")])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    text = (
        f"<b>📜 Bazadagi barcha animelar</b>\n\n"
        f"Jami: <b>{total_count}</b> ta\n"
        f"Sahifa: <b>{page + 1}</b>"
    )

    await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="HTML")


# ===================================================================================

async def admin_view_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # adm_v_123 -> 123
    anime_id = int(query.data.split('_')[-1])

    async with async_session() as session:
        # 1. Animeni olish
        stmt = select(Anime).where(Anime.anime_id == anime_id)
        res = await session.execute(stmt)
        anime = res.scalar_one_or_none()

        # 2. Shu animening qismlar sonini sanash
        ep_count_stmt = select(func.count(Episode.id)).where(Episode.anime_id == anime_id)
        ep_res = await session.execute(ep_count_stmt)
        ep_count = ep_res.scalar()

    if not anime:
        await query.edit_message_text("❌ Anime topilmadi!")
        return

    # Siz so'ragan ma'lumotlar formati
    text = (
        f"🆔 <b>ID:</b> <code>{anime.anime_id}</code>\n"
        f"🎬 <b>Nomi:</b> {anime.name}\n"
        f"🎞 <b>Qismlar soni:</b> {ep_count}\n"
        f"🌐 <b>Tili:</b> {anime.lang or 'Noma`lum'}\n"
        f"🎭 <b>Janri:</b> {anime.genre or 'Noma`lum'}\n"
        f"📅 <b>Yili:</b> {anime.year or 'Noma`lum'}\n"
        f"🎙 <b>Fandub:</b> {anime.fandub or 'Noma`lum'}\n"
        f"👁 <b>Haftalik ko'rilgan:</b> {anime.views_week}\n"
        f"⭐ <b>Reyting:</b> {anime.rating_sum / anime.rating_count if anime.rating_count > 0 else 0:.1f}\n"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎞 Epizodlarni boshqarish", callback_data=f"adm_ep_ctrl_{anime_id}")],
        [InlineKeyboardButton("⬅️ Ro'yxatga qaytish", callback_data="admin_list_anime_0")]
    ])

    await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="HTML")






