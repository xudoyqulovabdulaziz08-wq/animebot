import logging
from aiogram.fsm.state import State, StatesGroup

from typing import Any
from aiogram import Router, F, html
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from sqlalchemy import select
import math

from database.models import Genre
from services.anime_service import AnimeService

logger = logging.getLogger(__name__)
router = Router()













class AddAnimeStates(StatesGroup):
    poster = State()       # 1. Birinchi poster (Rasm/Video)
    info_line = State()    # 2. Nomi | Yili | Tili (Bitta qatorda)
    genres = State()       # 3. Janrlar (Paginatsiya + Multi-select + style="success")
    dubber = State()      # 4. Dubber 
    description = State()  # 4. Tasnif (Description)
    confirm_save = State() # 5. Bazaga saqlashni tasdiqlash







# ================= PAGINATSIYALIK JANRLAR KEYBOARDY =================
async def get_genres_paginated_markup(
    session: Any, 
    selected_genres: list[int], 
    page: int = 1, 
    per_page: int = 20
) -> InlineKeyboardMarkup:
    """Janrlarni 20 tadan bo'lib, 2 qatorda chiqaradi. Tanlanganlar yashil (success) bo'ladi."""
    stmt = select(Genre).order_by(Genre.name)
    result = await session.execute(stmt)
    genres = result.scalars().all()
    
    total_items = len(genres)
    total_pages = math.ceil(total_items / per_page) if total_items > 0 else 1
    
    # Joriy sahifadagi janrlarni kesib olamiz
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    current_genres = genres[start_idx:end_idx]
    
    keyboard = []
    row = []
    
    # Janr tugmalarini 2 qatordan joylashtirish (Jami max 20 ta)
    for genre in current_genres:
        is_selected = genre.id in selected_genres
        tick = "✅ " if is_selected else ""
        
        # Agar tanlangan bo'lsa style="success" (yashil), bo'lmasa standart (default)
        btn_style = "success" if is_selected else "default"
        
        row.append(InlineKeyboardButton(
            text=f"{tick}{genre.name}",  # Ortiqcha vergul olib tashlandi
            callback_data=f"g_tog:{genre.id}:{page}", # Sahifani yo'qotmaslik uchun callbackga qo'shamiz
            style=btn_style  # Siz aytgandek argument sifatida uzatildi
        ))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    # Paginatsiya boshqaruvi (Oldingi | Keyingi)
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"g_page:{page-1}", style="primary"))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="none"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"g_page:{page+1}"))
        
    if nav_row:
        keyboard.append(nav_row)
        
    # Tasdiqlash va Bekor qilish boshqaruvi
    keyboard.append([
        InlineKeyboardButton(text="📥 Janrlarni tasdiqlash", callback_data="g_submit", style="success")
    ])
    keyboard.append([
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_anime", style="danger")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)





async def get_dubber_paginated_markup(
    session: Any, 
    selected_dubbers: list[int], 
    page: int = 1, 
    per_page: int = 20
) -> InlineKeyboardMarkup:
    """🎙 Dubberlarni 20 tadan bo'lib, 2 qatorda chiqaradi. Tanlanganlar yashil (success) bo'ladi."""
    from database.models import Dubber  # Circular import oldini olish uchun kechikib import
    
    stmt = select(Dubber).order_by(Dubber.name)
    result = await session.execute(stmt)
    dubbers = result.scalars().all()
    
    total_items = len(dubbers)
    total_pages = math.ceil(total_items / per_page) if total_items > 0 else 1
    
    # Joriy sahifadagi dubberlarni kesib olamiz
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    current_dubbers = dubbers[start_idx:end_idx]
    
    keyboard = []
    row = []
    
    # Dubber tugmalarini 2 qatordan joylashtirish (Jami max 20 ta)
    for dubber in current_dubbers:
        is_selected = dubber.id in selected_dubbers
        tick = "✅ " if is_selected else ""
        
        # Agar tanlangan bo'lsa style="success" (yashil), bo'lmasa standart (default)
        btn_style = "success" if is_selected else "default"
        
        row.append(InlineKeyboardButton(
            text=f"{tick}{dubber.name}",
            callback_data=f"d_tog:{dubber.id}:{page}",  # Sahifani yo'qotmaslik uchun callbackga qo'shamiz
            style=btn_style
        ))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    # Paginatsiya boshqaruvi (Oldingi | Keyingi)
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"d_page:{page-1}"))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="none"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"d_page:{page+1}"))
        
    if nav_row:
        keyboard.append(nav_row)
        
    # Tasdiqlash va Bekor qilish boshqaruvi
    keyboard.append([
        InlineKeyboardButton(text="📥 Dubberlarni tasdiqlash", callback_data="d_submit", style="success")
    ])
    keyboard.append([
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_anime", style="danger")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ================= 1. PROCESSSNI BOSHLASH: POSTER SO‘RASH =================
@router.callback_query(F.data == "add_anime")
async def start_add_anime(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AddAnimeStates.poster)
    
    text = (
        f"🎬 {html.bold('Yangi anime qo‘shish bosqichi')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"1️⃣ Birinchi bo‘lib, animening {html.bold('Posterini')} (Rasm yoki Video xabar) yuboring.\n\n"
        f"⚠️ {html.bold('Muhim tavsiyalar (UX):')}\n"
        f"• Imkon qadar faqat {html.underline('portret')} formatdagi ({html.bold('3:4')} yoki {html.bold('2:3')} nisbatda) rasmlardan foydalaning.\n"
        f"• Gorizontal yoki kvadrat rasmlar bot interfeysida chiroyli chiqmasligi mumkin.\n"
        f"• Yuklanayotgan fayl sifati yuqori ekanligiga ishonch hosil qiling."
    )
    
    await callback.message.edit_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_anime", style="danger")]
        ]),
        parse_mode="HTML"
    )




# ================= 2. POSTERNI QABUL QILISH -> INFO LINE SO‘RASH =================
@router.message(AddAnimeStates.poster, F.photo | F.video)
async def process_poster(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id if message.photo else message.video.file_id
    await state.update_data(poster_id=file_id)
    
    await state.set_state(AddAnimeStates.info_line)
    
    example = html.code("Naruto | 2002 | O‘zbekcha, Yaponcha")
    
    text = (
        f"📸 {html.bold('Poster qabul qilindi!')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"2️⃣ Endi anime asosiy ma'lumotlarini quyidagi {html.underline('shablonda')} bitta qator qilib yuboring:\n\n"
        f"👉 {html.bold('Nomi | Yili | Tili')}\n\n"
        f"⚠️ {html.bold('Eslatma:')} Har bir ma'lumotni ajratish uchun {html.bold('|')} (tik chiziq) belgisidan foydalaning. "
        f"Tillarni esa vergul bilan ajratishingiz mumkin.\n\n"
        f"📌 {html.bold('Namuna:')} {example}"
    )
    
    await message.answer(
        text=text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_anime", style="danger")]
        ]),
        parse_mode="HTML"
    )







# ================= 3. INFO LINE'NI AJRATIB OLISH -> JANR TANLASHGA O‘TISH =================
@router.message(AddAnimeStates.info_line, F.text)
async def process_info_line(message: Message, state: FSMContext, session: Any):
    text_data = message.text
    
    # Xatolik yuz berganda qayta-qayta ishlatiladigan bekor qilish tugmasi
    error_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_anime", style="danger")]
    ])
    
    if "|" not in text_data:
        await message.answer(
            text=f"❌ {html.bold('Format noto‘g‘ri!')}\n\n"
                 f"Iltimos, ma'lumotlarni so‘ralganidek {html.code('|')} belgisi orqali ajratib yuboring.\n"
                 f"📌 Namuna: {html.code('Naruto | 2002 | O‘zbekcha')}",
            reply_markup=error_kb,
            parse_mode="HTML"
        )
        return
        
    parts = [p.strip() for p in text_data.split("|")]
    if len(parts) < 3 or not parts[0] or not parts[1] or not parts[2]:
        await message.answer(
            text=f"❌ {html.bold('Ma’lumotlar yetarli emas!')}\n\n"
                 f"Nomi, Yili va Tilini to‘liq va bo‘sh joy qoldirmasdan kiriting.\n"
                 f"📌 Namuna: {html.code('Naruto | 2002 | O‘zbekcha')}",
            reply_markup=error_kb,
            parse_mode="HTML"
        )
        return
        
    title, year_str, languages_str = parts[0], parts[1], parts[2]
    
    # Yil faqat raqamdan iboratligini tekshirish
    if not year_str.isdigit():
        await message.answer(
            text=f"❌ {html.bold('Yil noto‘g‘ri kiritildi!')}\n\n"
                 f"Yil qismiga faqat raqam yozilishi kerak! (Masalan: {html.code('2024')})",
            reply_markup=error_kb,
            parse_mode="HTML"
        )
        return
        
    year = int(year_str)
    # Yil chegarasini tekshirish (1900 - 2050)
    if not (1900 <= year <= 2050):
        await message.answer(
            text=f"❌ {html.bold('Yil chegarasi xato!')}\n\n"
                 f"Kiritilgan yil {html.bold('1900')} va {html.bold('2050')} oralig‘ida bo‘lishi shart!",
            reply_markup=error_kb,
            parse_mode="HTML"
        )
        return
        
    # Tillarni vergul orqali ajratib list qilib olamiz
    languages = [l.strip() for l in languages_str.split(",") if l.strip()]
    
    await state.update_data(
        title=title,
        year=year,
        languages=languages,
        selected_genres=[]  # Janrlar uchun bo'sh ro'yxat ochamiz
    )
    
    await state.set_state(AddAnimeStates.genres)
    markup = await get_genres_paginated_markup(session, selected_genres=[], page=1)
    
    text = (
        f"📝 {html.bold('Asosiy ma’lumotlar tasdiqlandi!')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"3️⃣ {html.bold('Janrlarni tanlash bosqichi')}\n\n"
        f"Quyidagi ro‘yxatdan anime janrlarini tanlang (Har bir sahifada  janr bor). "
        f"Tanlangan janrlar {html.italic('yashil rangga')} kiradi.\n\n"
        f"⏳ Tugatgach, pastdagi {html.underline('Janrlarni tasdiqlash')} tugmasini bosing:"
    )
    
    await message.answer(
        text=text,
        reply_markup=markup,
        parse_mode="HTML"
    )






# ================= 4. JANRLAR DINAMIK TOGGLE (MULTIPLE SELECT) =================
@router.callback_query(AddAnimeStates.genres, F.data.startswith("g_tog:"))
async def toggle_genre(callback: CallbackQuery, state: FSMContext, session: Any):
    await callback.answer()
    _, genre_id_str, page_str = callback.data.split(":")
    genre_id = int(genre_id_str)
    page = int(page_str)
    
    state_data = await state.get_data()
    selected_genres: list[int] = state_data.get("selected_genres", [])
    
    if genre_id in selected_genres:
        selected_genres.remove(genre_id)
    else:
        selected_genres.append(genre_id)
        
    await state.update_data(selected_genres=selected_genres)
    
    # O'sha turgan sahifasidagi keyboardni yangilaymiz
    markup = await get_genres_paginated_markup(session, selected_genres, page=page)
    try:
        await callback.message.edit_reply_markup(reply_markup=markup)
    except Exception:
        pass

# ================= 5. JANRLAR PAGINATSIYASI (PAGE ALMASHISH) =================
@router.callback_query(AddAnimeStates.genres, F.data.startswith("g_page:"))
async def change_genre_page(callback: CallbackQuery, state: FSMContext, session: Any):
    await callback.answer()
    page = int(callback.data.split(":")[1])
    
    state_data = await state.get_data()
    selected_genres: list[int] = state_data.get("selected_genres", [])
    
    markup = await get_genres_paginated_markup(session, selected_genres, page=page)
    try:
        await callback.message.edit_reply_markup(reply_markup=markup)
    except Exception:
        pass




# ================= 6. JANRLAR TASDIQLANDI ->  =================
@router.callback_query(AddAnimeStates.genres, F.data == "g_submit")
async def submit_genres(callback: CallbackQuery, state: FSMContext, session: Any):
    # 1. Interfeys qotib qolmasligi uchun darhol javob beramiz
    await callback.answer("Janrlar tasdiqlandi!")
    
    # 2. Keyingi bosqich FSM holatiga o'tamiz
    await state.set_state(AddAnimeStates.dubber)
    
    # 3. Dubberlar uchun klaviaturani chaqiramiz (To'g'ri argument: selected_dubbers=[])
    markup = await get_dubber_paginated_markup(session, selected_dubbers=[], page=1)
    
    text = (
        f"📝 {html.bold('Janrlar tasdiqlandi')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"3️⃣ {html.bold('Dubber tanlash bosqichi')}\n\n"
        f"Quyidagi ro‘yxatdan ushbu animega ovoz bergan dubberlarni tanlang. "
        f"Tanlangan dubberlar {html.italic('yashil rangga')} kiradi.\n\n"
        f"⏳ Tugatgach, pastdagi {html.underline('Dubberlarni tasdiqlash')} tugmasini bosing:"
    )
    
    # 4. TO'G'RI YECHIM: Xabarni tahrirlab tugmalarni chiqaramiz
    await callback.message.edit_text(
        text=text,
        reply_markup=markup,
        parse_mode="HTML"
    )

    
    
# =====================================================================
# 🎙️ 7. DUBBERLAR DINAMIK TOGGLE (MULTIPLE SELECT)
# =====================================================================
@router.callback_query(AddAnimeStates.dubber, F.data.startswith("d_tog:"))
async def toggle_dubber(callback: CallbackQuery, state: FSMContext, session: Any):
    await callback.answer()
    _, dubber_id_str, page_str = callback.data.split(":")
    dubber_id = int(dubber_id_str)
    page = int(page_str)
    
    state_data = await state.get_data()
    selected_dubbers: list[int] = state_data.get("selected_dubbers", [])
    
    # Ro'yxatda bo'lsa o'chiramiz, bo'lmasa qo'shamiz
    if dubber_id in selected_dubbers:
        selected_dubbers.remove(dubber_id)
    else:
        selected_dubbers.append(dubber_id)
        
    await state.update_data(selected_dubbers=selected_dubbers)
    
    # O'sha turgan sahifasidagi tugmalarni yangilaymiz
    markup = await get_dubber_paginated_markup(session, selected_dubbers, page=page)
    try:
        await callback.message.edit_reply_markup(reply_markup=markup)
    except Exception:
        pass


# =====================================================================
# 🎙️ 8. DUBBERLAR PAGINATSIYASI (PAGE ALMASHISH)
# =====================================================================
@router.callback_query(AddAnimeStates.dubber, F.data.startswith("d_page:"))
async def change_dubber_page(callback: CallbackQuery, state: FSMContext, session: Any):
    await callback.answer()
    page = int(callback.data.split(":")[1])
    
    state_data = await state.get_data()
    selected_dubbers: list[int] = state_data.get("selected_dubbers", [])
    
    markup = await get_dubber_paginated_markup(session, selected_dubbers, page=page)
    try:
        await callback.message.edit_reply_markup(reply_markup=markup)
    except Exception:
        pass


# =====================================================================
# 📥 9. DUBBERLARNI TASDIQLASH -> TASNIF (DESCRIPTION) BOSQICHIGA O'TISH
# =====================================================================
@router.callback_query(AddAnimeStates.dubber, F.data == "d_submit")
async def submit_dubbers(callback: CallbackQuery, state: FSMContext, session: Any):
    await callback.answer("Dubberlar tasdiqlandi!")
    
    # FSM holatini Tasnif (Description) kiritish holatiga o'tkazamiz
    await state.set_state(AddAnimeStates.description)
    
    text = (
        f"📝 {html.bold('Dubberlar tasdiqlandi')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"4️⃣ {html.bold('Tasnif (Description) kiritish bosqichi')}\n\n"
        f"Iltimos, anime haqida batafsil ma'lumot beruvchi matn (tavsif) yuboring.\n\n"
        f"⚠️ {html.italic('Tavsif qisqa, tushunarli va imlo xatolarsiz bo\'lishi tavsiya etiladi.')}"
    )
    
    # Agar media (poster) ostida bo'lsa edit_caption, oddiy matn bo'lsa edit_text
    try:
        await callback.message.edit_text(text=text, parse_mode="HTML")
    except Exception:
        await callback.message.edit_caption(caption=text, parse_mode="HTML")

# ================= 7. TASNIF QABUL QILINDI -> BAZAGA SAQLASH RUXSATI (CONFIRMATION) =================
# ================= 7. TASNIF QABUL QILINDI -> BAZAGA SAQLASH RUXSATI (CONFIRMATION) =================
@router.message(AddAnimeStates.description, F.text)
async def process_description(message: Message, state: FSMContext, session: Any):
    await state.update_data(description=message.text)
    await state.set_state(AddAnimeStates.confirm_save)
    
    data = await state.get_data()
    selected_genre_ids = data.get("selected_genres", [])
    selected_dubber_ids = data.get("selected_dubbers", [])  # 🎙️ Yangi: Tanlangan dubberlar ID ro'yxati
    
    # 🔮 Janr nomlarini bazadan olish
    genre_names = []
    if selected_genre_ids:
        stmt = select(Genre).where(Genre.id.in_(selected_genre_ids))
        res = await session.execute(stmt)
        genres = res.scalars().all()
        genre_names = [g.name for g in genres]
    
    # 🎙️ Dubber nomlarini bazadan olish
    dubber_names = []
    if selected_dubber_ids:
        from database.models import Dubber  # Circular import oldini olish uchun kechikib import
        stmt = select(Dubber).where(Dubber.id.in_(selected_dubber_ids))
        res = await session.execute(stmt)
        dubbers = res.scalars().all()
        dubber_names = [d.name for d in dubbers]
    
    genres_str = ", ".join(genre_names) if genre_names else "Tanlanmagan ⚠️"
    dubbers_str = ", ".join(dubber_names) if dubber_names else "Tanlanmagan ⚠️"  # 🎙️ Dubberlar satri
    languages_str = ", ".join(data.get('languages', [])) if data.get('languages') else "Tanlanmagan ⚠️"

    # Premium UX uslubida daxshat ramkali dizayn (Dubberlar ramkasi ulandi)
    preview_text = (
        f"╔══════════════════╗\n"
        f"    🎬 <b>{data.get('title', 'Nomsiz')}</b>\n"
        f"╚══════════════════╝\n\n"
        f"📌 <b>Anime haqida ma'lumot:</b>\n"
        f"╔══════════════════╗\n"
        f"├ 📅 Yil: <b>{data.get('year', '—')}</b>\n"
        f"├ ▶️ Qism: <b>Yangi (0)</b> \n"
        f"├ 🌐 Til: <b>{languages_str}</b>\n"
        f"├ 🎙 Dubber: <b>{dubbers_str}</b>\n"
        f"╚══════════════════╝\n"
        f"╔══════════════════╗\n"
        f" 🔮 Janrlar: <i>{genres_str}</i>\n"
        f"╚══════════════════╝\n"
        
        f"📝 <b>Tavsif:</b>\n"
        f"<blockquote expandable>{data.get('description', 'Tavsif kiritilmagan.')}</blockquote>\n\n"
        f"❓ <b>Barcha ma’lumotlar to‘g‘rimi? Bazaga saqlansinmi?</b>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Ha, saqlansin", callback_data="db_save_anime", style="success"),
            InlineKeyboardButton(text="🔴 Yo‘q, bekor qilinsin", callback_data="admin_anime", style="danger")
        ]
    ])
    
    poster_id = data.get('poster_id')
    
    # Rasm, Video yoki oddiy Matn ko'rinishida xavfsiz yuborish (Fallback tizimi)
    if poster_id:
        try:
            # Avval rasm sifatida urinib ko'ramiz
            await message.answer_photo(
                photo=poster_id, 
                caption=preview_text, 
                reply_markup=kb, 
                parse_mode="HTML"
            )
        except Exception:
            try:
                # Agar o'xshamasa video sifatida urinib ko'ramiz
                await message.answer_video(
                    video=poster_id, 
                    caption=preview_text, 
                    reply_markup=kb, 
                    parse_mode="HTML"
                )
            except Exception:
                # Agar media ID umuman xato bo'lsa bot qotmasdan matnni o'zini yuboradi
                await message.answer(
                    text=f"⚠️ (Media yuklab bo'lmadi)\n\n{preview_text}", 
                    reply_markup=kb, 
                    parse_mode="HTML"
                )
    else:
        # Agar poster_id umuman yo'q bo'lsa faqat matnni yuboramiz
        await message.answer(
            text=preview_text, 
            reply_markup=kb, 
            parse_mode="HTML"
        )

# ================= 8. YAKUNIY SAQLASH -> QISM QO‘SHISH YOKI ORTGA TUGMALARI =================
@router.callback_query(AddAnimeStates.confirm_save, F.data == "db_save_anime")
async def save_anime_to_db(callback: CallbackQuery, state: FSMContext, session: Any):
    # Interfeys qotib qolmasligi uchun darhol javob beramiz
    await callback.answer("Anime bazaga saqlanmoqda...")
    
    data = await state.get_data()
    service = AnimeService(session=session)
    
    try:
        # AnimeService mantiqan tranzaksiyani saqlaydi va keshni yangilaydi
        anime = await service.create_anime(
            title=data.get("title"),
            poster_id=data.get("poster_id"),
            year=data.get("year"),
            is_completed=False,
            genres=data.get("selected_genres", []),
            dubbers=data.get("selected_dubbers", []),  # 🎙️ Dubberlar ro'yxati muvaffaqiyatli uzatildi
            description=data.get("description"),
            languages=data.get("languages", [])
        )
        
        anime_id = anime["anime_id"]
        
        # ✅ TO'G'RI JOYLAShUV: Faqat muvaffaqiyatli saqlangandan keyin FSM tozalanadi
        await state.clear()  
        
        success_text = (
            f"🎉 {html.bold('Muvaffaqiyatli saqlandi!')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🚀 {html.bold('Anime bazaga muvaffaqiyatli qo‘shildi.')}\n\n"
            f"🆔 {html.bold('Anime kodi:')} {html.code(anime_id)}\n"
            f"🎬 {html.bold('Nomi:')} {html.underline(anime['title'])}\n\n"
            f"👇 Quyidagi tugma orqali ushbu animega seriyalarni (qismlarni) ketma-ket yuklashingiz mumkin:"
        )
        
        success_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📹 Qism qo‘shish", callback_data=f"add_episode:{anime_id}", style="success"),
                InlineKeyboardButton(text="⬅️ Anime menyusi", callback_data="admin_anime")
            ]
        ])
        
        await callback.message.edit_caption(
            caption=success_text, 
            reply_markup=success_kb, 
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"🚨 Anime saqlashda xatolik: {e}")
        
        # Xatolik yuz berganda adminga qayta harakat qilish tugmasi chiqariladi
        error_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                # Agar saqlanmay qolsa, FSM tozalanmagani uchun admin "Qayta urinish" imkoniga ega bo'ladi
                InlineKeyboardButton(text="🔄 Qayta urinish", callback_data="db_save_anime", style="success"),
                InlineKeyboardButton(text="⬅️ Bosh menyuga", callback_data="admin_anime", style="danger")
            ]
        ])
        
        await callback.message.edit_caption(
            caption=f"❌ {html.bold('Bazaga saqlashda xatolik yuz berdi:')}\n\n"
                    f"⚠️ {html.code(str(e))}\n\n"
                    f"Tizim keshini yo'qotmaslik uchun ma'lumotlar saqlab qolindi. Qayta urinib ko'rishingiz mumkin.",
            reply_markup=error_kb,
            parse_mode="HTML"
        )
# ================= BEKOR QILISH HANDLERI =================



