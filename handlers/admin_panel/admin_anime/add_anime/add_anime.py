import logging
from aiogram.fsm.state import State, StatesGroup

from typing import Any
from aiogram import Router, F, html
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
import math

from database.models import Genre, Anime, Dubber, AnimeType
from services.anime_service import AnimeService

logger = logging.getLogger(__name__)
router = Router()



class AddAnimeStates(StatesGroup):
    poster = State()       # 1. Birinchi poster 
    title = State()
    info_line = State ()         
    genres = State()       # 3. Janrlar (Paginatsiya + Multi-select + style="success")
    dubber = State()      # 4. Dubber 
    description = State()  # 4. Tasnif (Description)
    tizzer = State()
    type_anime = State ()
    confirm_save = State() # 5. Bazaga saqlashni tasdiqlash





def normalize_title(text: str) -> str:
    """
    1. Standart apostroflarni (', `) o'zbekcha '‘' ga almashtiradi.
    2. Har bir so'zning birinchi harfini katta, qolganini kichik qiladi (Title Case).
    """
    if not text:
        return ""
    
    # 1. Apostroflarni almashtirish
    cleaned = text.replace("'", "‘").replace("`", "‘")
    
    # 2. Bosh harflarni katta, qolganini kichik qilish
    # (.title() o'rniga regex ishlatamiz, chunki apostrofdan keyingi harfni ham katta qilib yubormasligi uchun)
    cleaned = " ".join([word.capitalize() for word in cleaned.split()])
    
    return cleaned






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
        nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="none", style="primary"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"g_page:{page+1}", style="primary"))
        
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
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"d_page:{page-1}", style="primary"))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="none", style="primary"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"d_page:{page+1}", style="primary"))
        
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
        f"1️⃣ Birinchi bo‘lib, animening {html.bold('Posterini')} Rasm  yuboring.\n\n"
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



@router.message(AddAnimeStates.poster, F.photo )
async def process_poster(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id if message.photo else message.video.file_id
    await state.update_data(poster_id=file_id)
    
    await state.set_state(AddAnimeStates.title)
    
    example = html.code("Soyada ko‘tarilish | The eminence shadow")
    
    text = (
        f"📸 {html.bold('Poster qabul qilindi!')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"2️⃣ Endi anime nomini  quyidagi {html.underline('shablonda')} bitta qator qilib yuboring:\n\n"
        f"👉 {html.bold('O‘zbekcha | inglizcha nom ')}\n\n"
        f"⚠️ {html.bold('Eslatma:')} Har bir nomni ma'lumotni ajratish uchun {html.bold('|')} (tik chiziq) belgisidan foydalaning. "
        
        f"📌 {html.bold('Namuna:')} {example}"
    )
    
    await message.answer(
        text=text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_anime", style="danger")]
        ]),
        parse_mode="HTML"
    )



@router.message(AddAnimeStates.title, F.text)
async def process_title(message: Message, state: FSMContext):
    raw_text = message.text.strip()

    # '|' orqali o'zbekcha va inglizcha sarlavhani ajratamiz
    if "|" in raw_text:
        parts = [p.strip() for p in raw_text.split("|", 1)]
        title_uz = normalize_title(parts[0])
        title_en = normalize_title(parts[1])
    else:
        title_uz = normalize_title(raw_text)
        title_en = normalize_title(raw_text)

    await state.update_data(
        title_uz=title_uz,
        title_en=title_en
    )

    # Navbatdagi state: info_line
    await state.set_state(AddAnimeStates.info_line)

    example = html.code("2024 | O‘zbek tilida, Yapon tilida")

    text = (
        f"📝 {html.bold('Sarlavha saqlandi!')}\n"
        f"• O‘zbekcha: {html.bold(title_uz)}\n"
        f"• Inglizcha: {html.bold(title_en)}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"3️⃣ Endi anime ma'lumotlarini quyidagi {html.underline('shablonda')} yuboring:\n\n"
        f"👉 {html.bold('Yili | Tili')}\n\n"
        f"📌 {html.bold('Namuna:')} {example}"
    )

    await message.answer(
        text=text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_anime", style="danger")]
        ]),
        parse_mode="HTML"
    )




@router.message(AddAnimeStates.info_line, F.text)
async def process_info_line(message: Message, state: FSMContext, session: Any):
    text_data = message.text.strip()
    
    # Xatolik yuz berganda ishlatiladigan tugma
    error_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_anime", style="danger")]
    ])
    
    # Ajratuvchi belgi borligini tekshirish
    if "|" not in text_data:
        await message.answer(
            text=f"❌ {html.bold('Format noto‘g‘ri!')}\n\n"
                 f"Iltimos, ma'lumotlarni so‘ralganidek {html.code('|')} belgisi orqali ajratib yuboring.\n"
                 f"📌 Namuna: {html.code('2024 | O‘zbekcha, Yaponcha')}",
            reply_markup=error_kb,
            parse_mode="HTML"
        )
        return
        
    parts = [p.strip() for p in text_data.split("|", 1)]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        await message.answer(
            text=f"❌ {html.bold('Ma’lumotlar yetarli emas!')}\n\n"
                 f"Yili va Tilini to‘liq va bo‘sh joy qoldirmasdan kiriting.\n"
                 f"📌 Namuna: {html.code('2024 | O‘zbekcha, Yaponcha')}",
            reply_markup=error_kb,
            parse_mode="HTML"
        )
        return
        
    year_str, languages_str = parts[0], parts[1]
    
    # Yil raqamligini tekshirish
    if not year_str.isdigit():
        await message.answer(
            text=f"❌ {html.bold('Yil noto‘g‘ri kiritildi!')}\n\n"
                 f"Yil qismiga faqat raqam yozilishi kerak! (Masalan: {html.code('2024')})",
            reply_markup=error_kb,
            parse_mode="HTML"
        )
        return
        
    year = int(year_str)
    # Yil oralig'ini tekshirish (1900 - 2050)
    if not (1900 <= year <= 2050):
        await message.answer(
            text=f"❌ {html.bold('Yil chegarasi xato!')}\n\n"
                 f"Kiritilgan yil {html.bold('1900')} va {html.bold('2050')} oralig‘ida bo‘lishi shart!",
            reply_markup=error_kb,
            parse_mode="HTML"
        )
        return
        
    # Tillarni qayta ishlash: apostrof almashtirish + bosh harfni katta qilish
    languages = []
    for lang in languages_str.split(","):
        cleaned_lang = lang.strip().replace("'", "‘").replace("`", "‘")
        if cleaned_lang:
            # Har bir so'zning birinchi harfini katta qilish
            formatted_lang = " ".join([w.capitalize() for w in cleaned_lang.split()])
            languages.append(formatted_lang)
    
    # FSM xotirasiga saqlash
    await state.update_data(
        year=year,
        languages=languages,
        selected_genres=[]  # Janrlar uchun bo'sh ro'yxat
    )
    
    await state.set_state(AddAnimeStates.genres)
    markup = await get_genres_paginated_markup(session, selected_genres=[], page=1)
    
    text = (
        f"📝 {html.bold('Yil va til ma’lumotlari saqlandi!')}\n"
        f"• Yil: {html.bold(year)}\n"
        f"• Tillar: {html.bold(', '.join(languages))}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"4️⃣ {html.bold('Janrlarni tanlash bosqichi')}\n\n"
        f"Quyidagi ro‘yxatdan anime janrlarini tanlang. "
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
    # List nusxasini olamiz (immutability uchun)
    selected_genres: list[int] = list(state_data.get("selected_genres", []))
    
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
    selected_genres: list[int] = list(state_data.get("selected_genres", []))
    
    markup = await get_genres_paginated_markup(session, selected_genres, page=page)
    try:
        await callback.message.edit_reply_markup(reply_markup=markup)
    except TelegramBadRequest:
        # Agar tugmalar va keyboard o'zgarmagan bo'lsa Telegram xatolik beradi, shuni o'tkazib yuboramiz
        pass



# ================= 6. JANRLAR TASDIQLANDI -> DUBBERLAR =================
@router.callback_query(AddAnimeStates.genres, F.data == "g_submit")
async def submit_genres(callback: CallbackQuery, state: FSMContext, session: Any):
    state_data = await state.get_data()
    selected_genres: list[int] = list(state_data.get("selected_genres", []))

    # 1. Validation: Kamida 1 ta janr tanlangan bo'lishi kerak
    if not selected_genres:
        await callback.answer(
            "⚠️ Kamida bitta janr tanlashingiz kerak!", 
            show_alert=True
        )
        return

    # 2. Interfeys qotib qolmasligi uchun bildirishnoma
    await callback.answer("Janrlar tasdiqlandi!")
    
    # 3. FSM xotirasiga dubberlar ro'yxatini bo'sh holda tayyorlab qo'yamiz va state'ni o'zgartiramiz
    await state.update_data(selected_dubbers=[])
    await state.set_state(AddAnimeStates.dubber)
    
    # 4. Dubberlar paginatsiya klaviaturasini olamiz
    markup = await get_dubber_paginated_markup(session, selected_dubbers=[], page=1)
    
    text = (
        f"📝 {html.bold('Janrlar tasdiqlandi!')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"5️⃣ {html.bold('Dubberlarni tanlash bosqichi')}\n\n"
        f"Quyidagi ro‘yxatdan ushbu animega ovoz bergan dubberlarni tanlang. "
        f"Tanlangan dubberlar {html.italic('yashil rangga')} kiradi.\n\n"
        f"⏳ Tugatgach, pastdagi {html.underline('Dubberlarni tasdiqlash')} tugmasini bosing:"
    )
    
    # 5. Xabarni tahrirlaymiz
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
    # Immutability uchun list nusxasini olamiz
    selected_dubbers: list[int] = list(state_data.get("selected_dubbers", []))
    
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
    except TelegramBadRequest:
        pass


# =====================================================================
# 🎙️ 8. DUBBERLAR PAGINATSIYASI (PAGE ALMASHISH)
# =====================================================================
@router.callback_query(AddAnimeStates.dubber, F.data.startswith("d_page:"))
async def change_dubber_page(callback: CallbackQuery, state: FSMContext, session: Any):
    await callback.answer()
    
    page = int(callback.data.split(":")[1])
    
    state_data = await state.get_data()
    selected_dubbers: list[int] = list(state_data.get("selected_dubbers", []))
    
    markup = await get_dubber_paginated_markup(session, selected_dubbers, page=page)
    try:
        await callback.message.edit_reply_markup(reply_markup=markup)
    except TelegramBadRequest:
        pass




# =====================================================================
# 📥 9. DUBBERLARNI TASDIQLASH -> TASNIF (DESCRIPTION) BOSQICHIGA O'TISH
# =====================================================================
@router.callback_query(AddAnimeStates.dubber, F.data == "d_submit")
async def submit_dubbers(callback: CallbackQuery, state: FSMContext, session: Any):
    state_data = await state.get_data()
    selected_dubbers: list[int] = list(state_data.get("selected_dubbers", []))

    # 1. Validation (Kamida 1 ta dubber tanlangani tekshiriladi)
    if not selected_dubbers:
        await callback.answer(
            "⚠️ Kamida bitta dubber tanlashingiz kerak!", 
            show_alert=True
        )
        return

    await callback.answer("Dubberlar tasdiqlandi!")
    
    # 2. FSM holatini Description ga o'tkazamiz
    await state.set_state(AddAnimeStates.description)
    
    text = (
        f"📝 {html.bold('Dubberlar tasdiqlandi!')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"6️⃣ {html.bold('Tasnif (Description) kiritish bosqichi')}\n\n"
        f"Iltimos, anime haqida batafsil ma'lumot beruvchi matn (tavsif) yuboring.\n\n"
        f"⚠️ {html.italic('Tavsif qisqa, tushunarli va imlo xatolarsiz bo‘lishi tavsiya etiladi.')}"
    )
    
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_anime", style="danger")]
    ])
    
    try:
        await callback.message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        await callback.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")



# =====================================================================
# 📝 10. TASNIF QABUL QILINDI -> TIZZER (TREYLER) BOSQICHIGA O'TISH
# =====================================================================
@router.message(AddAnimeStates.description, F.text)
async def process_description(message: Message, state: FSMContext):
    # 1. Description'ni FSM holatiga saqlaymiz
    await state.update_data(description=message.text)
    
    # 2. Holatni Tizzer kiritish bosqichiga o'tkazamiz
    await state.set_state(AddAnimeStates.tizzer)
    
    text = (
        f"✅ {html.bold('Tasnif qabul qilindi!')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"7️⃣ {html.bold('Tizzer (Treyler) yuklash bosqichi')}\n\n"
        f"Anime uchun qisqacha tizzer (video formatida) yuboring.\n"
        f"Yoki avval yuklangan videoning <code>file_id</code> sini jo'nating.\n\n"
        f"📌 {html.italic('Agar bu anime uchun tizzer yo\'q bo\'lsa, O\'tkazib yuborish tugmasini bosing.')}"
    )
    
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data="skip_tizzer")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_anime")]
    ])
    
    await message.answer(text=text, reply_markup=reply_markup, parse_mode="HTML")



# =====================================================================
# 🎞 11. TIZZER QABUL QILISH (VIDEO YOKI SKIP)
# =====================================================================
@router.message(AddAnimeStates.tizzer, F.video)
async def process_tizzer(message: Message, state: FSMContext):
    # Video yuborilsa, uning ID sini olamiz
    await state.update_data(tizzer_id=message.video.file_id)
    await ask_anime_type(message, state) # Keyingi qadamga o'tamiz

@router.callback_query(AddAnimeStates.tizzer, F.data == "skip_tizzer")
async def skip_tizzer(callback: CallbackQuery, state: FSMContext):
    await state.update_data(tizzer_id=None) # Tizzer yo'q
    await ask_anime_type(callback.message, state)



async def ask_anime_type(message: Message, state: FSMContext, is_callback: bool = False):
    await state.set_state(AddAnimeStates.type_anime)
    
    text = (
        f"⚙️ {html.bold('8️⃣ Anime turini (formatini) tanlang:')}\n\n"
        f"Iltimos, quyidagi tugmalardan birini tanlang."
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📺 TV Series", callback_data="type_TV_SERIES")],
        [InlineKeyboardButton(text="🎬 Movie", callback_data="type_MOVIE")],
        [InlineKeyboardButton(text="📀 OVA", callback_data="type_OVA")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_anime", style="danger")]
    ])
    
    if is_callback:
        await message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text=text, reply_markup=kb, parse_mode="HTML")




# =====================================================================
# ⚙️ 12. ANIME TURINI TANLASH VA YAKUNIY TASDIQLASH (CONFIRMATION)
# =====================================================================
@router.callback_query(AddAnimeStates.type_anime, F.data.startswith("type_"))
async def process_type_anime(callback: CallbackQuery, state: FSMContext, session: Any):
    await callback.answer()
    
    # "type_TV_SERIES" -> "TV_SERIES"
    selected_type_key = callback.data.split("_", 1)[1]
    
    # AnimeType enum ga mos qiymatni olamiz
    anime_type_enum = AnimeType[selected_type_key]
    await state.update_data(anime_type=anime_type_enum.value)

    # State'dan ma'lumotlarni olish
    data = await state.get_data()
    
    # 💡 Sarlavhalarni formatlash
    title_uz = data.get("title_uz", "Nomsiz")
    title_en = data.get("title_en")
    title_display = f"{title_uz} | {title_en}" if title_en and title_uz != title_en else title_uz

    selected_genre_ids = data.get("selected_genres", [])
    selected_dubber_ids = data.get("selected_dubbers", [])

    genre_names = []
    if selected_genre_ids:
        res = await session.execute(select(Genre).where(Genre.id.in_(selected_genre_ids)))
        genre_names = [g.name for g in res.scalars().all()]

    dubber_names = []
    if selected_dubber_ids:
        res = await session.execute(select(Dubber).where(Dubber.id.in_(selected_dubber_ids)))
        dubber_names = [d.name for d in res.scalars().all()]

    genres_str = ", ".join(genre_names) if genre_names else "Tanlanmagan ⚠️"
    dubbers_str = ", ".join(dubber_names) if dubber_names else "Tanlanmagan ⚠️"
    languages_str = ", ".join(data.get('languages', [])) if data.get('languages') else "Tanlanmagan ⚠️"
    
    # 💡 trailer_id yoki tizzer_id ni bir xil kalit orqali tekshirish
    trailer_id = data.get("trailer_id") or data.get("tizzer_id")
    tizzer_status = "Mavjud ✅" if trailer_id else "Mavjud emas ❌"

    preview_text = (
        f"╔══════════════════╗\n"
        f"    🎬 <b>{title_display}</b>\n"
        f"╚══════════════════╝\n\n"
        f"📌 <b>Anime haqida ma'lumot:</b>\n"
        f"╔══════════════════╗\n"
        f"├ 📅 Yil: <b>{data.get('year', '—')}</b>\n"
        f"├ 📺 Turi: <b>{anime_type_enum.value}</b>\n"
        f"├ 🌐 Til: <b>{languages_str}</b>\n"
        f"├ 🎙 Dubber: <b>{dubbers_str}</b>\n"
        f"├ 🎞 Treyler: <b>{tizzer_status}</b>\n"
        f"╚══════════════════╝\n"
        f"╔══════════════════╗\n"
        f" 🔮 Janrlar: <i>{genres_str}</i>\n"
        f"╚══════════════════╝\n\n"
        f"📝 <b>Tavsif:</b>\n"
        f"<blockquote expandable>{data.get('description', 'Tavsif kiritilmagan.')}</blockquote>\n\n"
        f"❓ <b>Barcha ma’lumotlar to‘g‘rimi? Bazaga saqlansinmi?</b>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Saqlansin", callback_data="db_save_anime", style="success"),
            InlineKeyboardButton(text="🔴 Bekor qilinsin", callback_data="admin_anime", style="danger")
        ]
    ])

    await state.set_state(AddAnimeStates.confirm_save)
    poster_id = data.get('poster_id')

    if poster_id:
        try:
            await callback.message.answer_photo(
                photo=poster_id,
                caption=preview_text,
                reply_markup=kb,
                parse_mode="HTML"
            )
            await callback.message.delete()
        except Exception:
            await callback.message.answer(text=preview_text, reply_markup=kb, parse_mode="HTML")
    else:
        await callback.message.edit_text(text=preview_text, reply_markup=kb, parse_mode="HTML")


# =====================================================================
# 💾 13. ANIME'NI BAZAGA SAQLASH (DB SAVE HANDLER)
# =====================================================================
@router.callback_query(AddAnimeStates.confirm_save, F.data == "db_save_anime")
async def save_anime_to_db(callback: CallbackQuery, state: FSMContext, session: Any):
    await callback.answer("Anime bazaga saqlanmoqda...")
    
    data = await state.get_data()
    service = AnimeService(session=session)
    
    try:
        # 💡 Parametrlar yangi arxitekturaga moslandi
        anime = await service.create_anime(
            title_uz=data.get("title_uz"),
            title_en=data.get("title_en"),
            poster_id=data.get("poster_id"),
            year=data.get("year"),
            is_completed=False,
            genres=data.get("selected_genres", []),
            dubbers=data.get("selected_dubbers", []),
            description=data.get("description"),
            languages=data.get("languages", []),
            trailer_id=data.get("tizzer_id"),       # tizzer_id o'rniga trailer_id
            type=data.get("anime_type")             # type_anime o'rniga type
        )
        
        # 💡 "title" o'rniga "title_uz", "anime_id" o'rniga standart "id" tekshiriladi
        anime_id = anime.get("anime_id") if isinstance(anime, dict) else getattr(anime, "anime_id", None)
        anime_title = anime.get("title_uz") if isinstance(anime, dict) else getattr(anime, "title_uz", "Nomsiz")
        
        await state.clear()  
        
        success_text = (
            f"🎉 {html.bold('Muvaffaqiyatli saqlandi!')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🚀 {html.bold('Anime bazaga muvaffaqiyatli qo‘shildi.')}\n\n"
            f"🆔 {html.bold('Anime kodi:')} {html.code(anime_id)}\n"
            f"🎬 {html.bold('Nomi:')} {html.underline(anime_title)}\n\n"
            f"👇 Quyidagi tugma orqali ushbu animega seriyalarni (qismlarni) ketma-ket yuklashingiz mumkin:"
        )
        
        success_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📹 Qism qo‘shish", callback_data=f"add_episode:{anime_id}"),
                InlineKeyboardButton(text="⬅️ Anime menyusi", callback_data="admin_anime")
            ]
        ])
        
        try:
            await callback.message.edit_caption(caption=success_text, reply_markup=success_kb, parse_mode="HTML")
        except Exception:
            await callback.message.edit_text(text=success_text, reply_markup=success_kb, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"🚨 Anime saqlashda xatolik: {e}")
        
        
        error_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Qayta urinish", callback_data="db_save_anime", style="success"),
                InlineKeyboardButton(text="⬅️ Bosh menyuga", callback_data="admin_anime", style="danger")
            ]
        ])
        
        error_text = (
            f"❌ {html.bold('Bazaga saqlashda xatolik yuz berdi:')}\n\n"
            f"⚠️ {html.code(str(e))}\n\n"
            f"Tizim keshini yo'qotmaslik uchun ma'lumotlar saqlab qolindi. Qayta urinib ko'rishingiz mumkin."
        )
        
        try:
            await callback.message.edit_caption(
                caption=error_text,
                reply_markup=error_kb,
                parse_mode="HTML"
            )
        except Exception:
            await callback.message.edit_text(
                text=error_text,
                reply_markup=error_kb,
                parse_mode="HTML"
            )