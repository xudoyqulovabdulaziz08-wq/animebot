from sqlalchemy import func, select
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from database.db import async_session
from database.models import Anime, Episode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters


POSTER, DATA, VIDEO,  = range(3)
# ===================================================================================


async def show_anime_details(update: Update, context: ContextTypes.DEFAULT_TYPE, anime_id: int):
    is_callback = update.callback_query is not None
    target = update.callback_query.message if is_callback else update.message

    async with async_session() as session:
        # Anime va uning epizodlari sonini bitta so'rovda olish (optimizatsiya)
        stmt = select(Anime).where(Anime.anime_id == anime_id)
        res = await session.execute(stmt)
        anime = res.scalar_one_or_none()

        if not anime:
            msg = "❌ Kechirasiz, bu anime haqida ma'lumot topilmadi."
            if is_callback: await update.callback_query.answer(msg)
            else: await target.reply_text(msg)
            return

        # Ko'rishlar sonini oshirish (Ixtiyoriy lekin tavsiya etiladi)
        anime.views_week += 1
        await session.commit()

        geren = anime.genre if anime.genre else "Noma'lum"
        yil =  anime.year if anime.year else "Noma'lum"
        fandubn = anime.fandub if anime.fandub else "Noma'lum"
        langn = anime.lang if anime.lang else "O'zbek"
        qismn = anime.episodes_count if anime.episodes_count else "Qismlar tez orada qo'shiladi"
        haftan = anime.views_week if anime.views_week else 0
        holatin = "Tugallangan" if anime.is_completed else "Davom etmoqda"
        reyting = f"{anime.rating_sum / anime.rating_count:.1f}" if anime.rating_count > 0 else "Hali reyting berilmagan"
        if len(description) > 500: # 500 belgidan uzun bo'lsa, qisqartiramiz
            description = description[:500].rsplit(' ', 1)[0] + "..."

        caption = (
            f"🎬 <b>{anime.name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎭 <b>Janr:</b> {geren}\n"
            f"📅 <b>Yil:</b> {yil}\n"
            f"🎙 <b>Fandub:</b> {fandubn}\n"
            f"🌐 <b>Til:</b> {langn}\n"
            f"👁 <b>Ko‘rishlar:</b> {haftan}\n"
            f"▶️ <b>Qismlar:</b> {qismn}\n"
            f"📊 <b>Reyting:</b> ⭐ {reyting}\n"
            f"✅ <b>Holati:</b> {holatin}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📢 <b>Kanal:</b> <a href='https://t.me/aninovuz'>@aninovuz</a>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📖 <b>Qisqacha mazmuni:</b>\n<i>{description}</i>"
        )

        buttons = [
            [InlineKeyboardButton("🎞 Qismlarni ko'rish", callback_data=f"show_episodes_{anime_id}")],
            [
                InlineKeyboardButton("🌟 Sevimlilar", callback_data=f"fav_{anime_id}"),
                InlineKeyboardButton("✍️ Sharhlar", callback_data=f"comments_{anime_id}")
            ],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="main_menu")]
        ]
        keyboard = InlineKeyboardMarkup(buttons)

        try:
            if is_callback:
                # Agar callback bo'lsa, xabarni o'chirib yangisini yuborish o'rniga, 
                # foydalanuvchiga "yuklanmoqda" effekti uchun answer query yuboramiz
                await update.callback_query.answer()
            
            if anime.poster_id:
                await target.get_bot().send_photo(
                    chat_id=target.chat_id,
                    photo=anime.poster_id,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            else:
                await target.get_bot().send_message(
                    chat_id=target.chat_id,
                    text=caption,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            
            # Eski ro'yxatni o'chirish
            if is_callback:
                await update.callback_query.message.delete()

        except Exception as e:
            print(f"Xatolik: {e}")
            await target.reply_text("⚠️ Ma'lumotni yuklashda xatolik yuz berdi.")



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

async def start_add_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """1-qadam: Poster so'rash"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🎬 <b>Yangi anime qo'shish.</b>\n\n"
        "1. Birinchi bo'lib anime <b>Posteri</b>ni (rasm yoki fayl ko'rinishida) yuboring:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Bekor qilish", callback_data="adm_ani_ctrl")]])
    )
    return POSTER

async def get_poster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Posterni file_id ko'rinishida olish (Rasm yoki Hujjat)"""
    msg = update.message
    
    if msg.photo:
        # Eng sifatli rasm IDsi
        file_id = msg.photo[-1].file_id
    elif msg.document and msg.document.mime_type.startswith('image/'):
        # Hujjat ko'rinishida yuborilgan rasm IDsi
        file_id = msg.document.file_id
    else:
        await msg.reply_text("❌ Iltimos, faqat rasm yuboring!")
        return POSTER

    context.user_data['poster_id'] = file_id
    
    await msg.reply_text(
        "✅ Poster qabul qilindi.\n\n"
        "2. Endi ma'lumotlarni quyidagi formatda yuboring:\n\n"
        "<code>Nomi | Tili | Janri | Yili | Tavsif</code>\n\n"
        "<i>Eslatma: Janrlarni vergul bilan ajratib yozing. Tavsif ixtiyoriy.</i>",
        parse_mode="HTML"
    )
    return DATA

import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler



# ===================================================================================



async def get_anime_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ma'lumotlarni pars qilish, bazaga yozish va video kutishga o'tish"""
    raw_text = update.message.text
    # Ma'lumotlarni '|' belgisi orqali ajratamiz
    parts = [p.strip() for p in raw_text.split('|')]
    
    if len(parts) < 4:
        await update.message.reply_text(
            "❌ <b>Format noto'g'ri!</b>\n\n"
            "Iltimos, namunadagidek yuboring:\n"
            "<code>Nomi | Tili | Janri | Yili | Tavsif</code>",
            parse_mode="HTML"
        )
        return DATA

    # Ma'lumotlarni o'zgaruvchilarga olamiz
    name = parts[0]
    lang = parts[1]
    genre = parts[2]
    year = parts[3]
    description = parts[4] if len(parts) > 4 else "Tavsif mavjud emas."

    # 💾 BAZAGA YOZISH (anime_list jadvali)
    try:
        async with async_session() as session:
            new_anime = Anime(
                name=name,
                poster_id=context.user_data.get('poster_id'), # get_poster dan kelgan ID
                lang=lang,
                genre=genre,
                year=year,
                description=description,
                is_completed=False
            )
            session.add(new_anime)
            await session.commit()
            await session.refresh(new_anime)
            
            # Bazadan olingan IDni saqlaymiz
            ani_id = new_anime.anime_id

        # Kelajakda videolarni bog'lash uchun context da saqlaymiz
        context.user_data['current_anime_id'] = ani_id
        context.user_data['last_ep_num'] = 0
        context.user_data['anime_name'] = name # Xabarda chiqarish uchun

        keyboard = [
            [InlineKeyboardButton("✅ Jarayonni tugatish", callback_data="finish_add")],
            [InlineKeyboardButton("📢 Kanalga jo'natish", callback_data="publish_to_channel")]
        ]
        
        await update.message.reply_text(
            f"✅ <b>'{html.escape(name)}'</b> muvaffaqiyatli saqlandi!\n"
            f"🆔 ID: <code>{ani_id}</code>\n\n"
            "📹 Endi ketma-ket <b>videolarni</b> yuboring.\n"
            "<i>Bot videolarni caption (izoh)siz qabul qiladi.</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        # Endi VIDEO kutish holatiga o'tamiz
        return VIDEO

    except Exception as e:
        await update.message.reply_text(f"❌ Bazaga yozishda xatolik yuz berdi: {e}")
        return ConversationHandler.END



# ===================================================================================



async def get_episodes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Videolarni cheksiz qabul qilish"""
    msg = update.message
    ani_id = context.user_data.get('current_anime_id')
    
    # 1. Video yoki Document ekanini tekshirish
    file_id = None
    if msg.video:
        file_id = msg.video.file_id
    elif msg.document and msg.document.mime_type.startswith('video/'):
        file_id = msg.document.file_id
    
    if not file_id:
        await msg.reply_text("❌ Iltimos, faqat video yoki video-fayl yuboring!")
        return VIDEO

    # 2. Qism raqamini aniqlash (+1)
    context.user_data['last_ep_num'] += 1
    current_ep = context.user_data['last_ep_num']

    # 3. Bazaga (Episode) saqlash
    async with async_session() as session:
        new_episode = Episode(
            anime_id=ani_id,
            episode=current_ep,
            file_id=file_id # Caption (tasnif) bu yerda avtomatik o'chib ketadi
        )
        session.add(new_episode)
        await session.commit()

    # 4. Tasdiqlash xabari
    keyboard = [
        [InlineKeyboardButton("✅ Jarayonni tugatish", callback_data="finish_add")],
        [InlineKeyboardButton("📢 Kanalga jo'natish", callback_data="publish_to_channel")]
    ]
    
    await msg.reply_text(
        f"📥 <b>{current_ep}-qism</b> qabul qilindi va bazaga saqlandi.\n"
        "Keyingi qismni yuboring yoki tugatish tugmasini bosing.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return VIDEO



# ===================================================================================



async def finish_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jarayonni yopish va kutish rejimidan chiqish"""
    query = update.callback_query
    await query.answer("Jarayon yakunlandi!")
    
    context.user_data.clear()
    await query.edit_message_text("✅ Barcha qismlar saqlandi. Admin panelga qaytishingiz mumkin.")
    return ConversationHandler.END



# ===================================================================================



async def publish_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kanalga jo'natish (Hozircha faqat jarayonni yopadi)"""
    query = update.callback_query
    await query.answer("Tez orada kanalga yuboriladi...")
    
    # Bu yerda kanalga post qilish funksiyasini chaqirish mumkin
    context.user_data.clear()
    await query.edit_message_text("🚀 Anime bazaga olindi va kanalga navbatga qo'yildi.")
    return ConversationHandler.END









