from sqlalchemy import select
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from db import async_session
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
            f"🎙 <b>Fandub:</b> {fandubn = anime.fandub if anime.fandub else "Noma'lum"}\n"
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


