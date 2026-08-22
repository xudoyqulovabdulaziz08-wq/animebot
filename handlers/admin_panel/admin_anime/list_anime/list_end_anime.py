import math
import logging
from typing import Any
from aiogram import Router, F, html
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from services.anime_service import AnimeService

from aiogram.types import InputMediaVideo



from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton


logger = logging.getLogger(__name__)

router = Router()










@router.callback_query(F.data.startswith("list_anime_end_page:"))
async def process__end_anime_list_page(callback: CallbackQuery, session: Any):
    page = int(callback.data.split(":")[1])
    
    # Ma'lumotlarni bazadan/keshdan yuklaymiz
    markup, total_count = await get_anime_end_list_markup(session, page=page)
    
    text = (
        f"📋 {html.bold('Bazadagi tugallangan animelar ro‘yxati')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Tugallangan anime soni: {html.code(total_count)} ta\n"
        f"👇 Tafsilotlarini ko‘rish uchun kerakli animeni tanlang:"
    )
    
    # 💡 Agar bu handlerga rasm yoki video ostidagi tugmadan kelingan bo'lsa
    if callback.message.photo or callback.message.video:
        await callback.answer() # Yuklanish soatini darhol o'chiramiz
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text=text, reply_markup=markup, parse_mode="HTML")
    
    # Agar oddiy matnli xabardan bosilgan bo'lsa (Silliq o'tish)
    else:
        try:
            await callback.message.edit_text(text=text, reply_markup=markup, parse_mode="HTML")
            await callback.answer("Yuklanmoqda...") # Faqat muvaffaqiyatli editdan keyin soatni o'chiramiz
        except Exception:
            await callback.answer()







async def get_anime_end_list_markup(session: Any, page: int = 1, per_page: int = 10) -> tuple[InlineKeyboardMarkup, int]:
    from services.anime_service import AnimeService
    service = AnimeService(session=session)
    
    # 1. SQL offset-ni hisoblaymiz
    offset = (page - 1) * per_page

    # 2. Service orqali faqat joriy sahifa va jami sonni yuklaymiz
    try:
        data = await service.get_completed_animes(offset=offset, limit=per_page)
        total_anime = data.get("total_count", 0)
        animes = data.get("animes", [])
    except Exception as e:
        logger.error(f"❌ Tugallangan animelar ro'yxatini olishda xatolik: {e}")
        total_anime = 0
        animes = []
        
    # 3. Agar anime umuman topilmasa
    if total_anime == 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="list_type_menu", style="danger")]
        ])
        return kb, 0

    # 4. Sahifalar sonini va joriy sahifani hisoblash
    total_pages = math.ceil(total_anime / per_page)
    page = max(1, min(page, total_pages))

    inline_keyboard = []

    # 5. Tugmalarni shakllantirish
    for anime in animes:
        anime_id = anime.get("anime_id")
        
        # Titleni aniqlash (titles ro'yxatidan yoki asosiy kalitdan)
        titles = anime.get("titles", [])
        title = "Nomsiz anime"
        if titles and isinstance(titles, list):
            title = titles[0].get("title_name", title) if isinstance(titles[0], dict) else getattr(titles[0], "title_name", title)
        elif anime.get("title"):
            title = anime.get("title")

        year = anime.get("year", "—")
        
        inline_keyboard.append([
            InlineKeyboardButton(
                text=f"🎬 {title} ({year})", 
                callback_data=f"v_anime:{anime_id}:{page}"
            )
        ])

    # 6. Paginatsiya (Navigatsiya) satri
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"list_anime_end_page:{page-1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="⛔️", callback_data="void", style="primary"))

    nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="void", style="primary"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"list_anime_end_page:{page+1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="⛔️", callback_data="void", style="primary"))

    inline_keyboard.append(nav_row)

    # 7. Ortga qaytish satri
    inline_keyboard.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data="list_type_menu", style="danger")
    ])

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard), total_anime


