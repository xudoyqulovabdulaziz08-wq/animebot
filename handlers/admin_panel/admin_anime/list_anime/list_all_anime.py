

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

async def process_anime_list_page(callback: CallbackQuery, session: Any):
    page = int(callback.data.split(":")[1])
    
    # 1. Telegram indikatorini darhol yopamiz
    await callback.answer()
    
    # 2. Ma'lumotlarni yuklaymiz
    markup, total_count = await get_anime_end_list_markup(session, page=page)
    
    text = (
        f"📋 {html.bold('Bazadagi animelar ro‘yxati')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Jami anime soni: {html.code(total_count)} ta\n"
        f"👇 Tafsilotlarini ko‘rish uchun kerakli animeni tanlang:"
    )
    
    # 3. Agar eski xabar media (rasm/video) bo'lsa: yangi xabar yuborib, eskisini o'chiramiz
    if callback.message.photo or callback.message.video:
        await callback.message.answer(text=text, reply_markup=markup, parse_mode="HTML")
        try:
            await callback.message.delete()
        except Exception as e:
            logger.warning(f"Media xabarni o'chirishda xatolik: {e}")
    
    # 4. Oddiy matnli xabar bo'lsa: tahrirlaymiz
    else:
        try:
            await callback.message.edit_text(text=text, reply_markup=markup, parse_mode="HTML")
        except TelegramBadRequest as e:
            # Matn va tugmalar bir xil bo'lsa chiqadigan xatolikni e'tiborsiz qoldiramiz
            if "message is not modified" in str(e):
                pass
            else:
                logger.error(f"Xabarni tahrirlashda xatolik: {e}")





async def get_anime_end_list_markup(session, page: int = 1, per_page: int = 10) -> tuple[InlineKeyboardMarkup, int]:
    from services.anime_service import AnimeService
    service = AnimeService(session=session)
    
    # 1. SQL offset-ni hisoblaymiz
    offset = (page - 1) * per_page

    # 2. Service-dan lug'at ko'rinishida ma'lumotni yuklaymiz
    try:
        data = await service.get_completed_animes(offset=offset, limit=per_page)
        total_anime = data.get("total_count", 0)
        animes = data.get("animes", [])
    except Exception as e:
        logger.error(f"❌ Anime ro'yxatini olishda xatolik: {e}")
        total_anime = 0
        animes = []
        
    # 3. Agar anime umuman topilmasa
    if total_anime == 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="list_type_menu")]
        ])
        return kb, 0

    # 4. Sahifalar sonini hisoblash
    total_pages = math.ceil(total_anime / per_page)
    page = max(1, min(page, total_pages))

    inline_keyboard = []

    # 5. Tugmalarni shakllantirish (animes ro'yxati bo'yicha)
    for anime in animes:
        anime_id = anime.get("anime_id")
        title = anime.get("title", "Nomsiz anime")
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
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"list_anime_page:{page-1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="⛔️", callback_data="void", style="primary"))

    nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="void", style="primary"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"list_anime_page:{page+1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="⛔️", callback_data="void", style="primary"))

    inline_keyboard.append(nav_row)

    # 7. Ortga qaytish satri
    inline_keyboard.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data="list_type_menu", style="danger")
    ])

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard), total_anime



