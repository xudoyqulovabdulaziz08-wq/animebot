

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

@router.callback_query(F.data.startswith("list_anime_page:"))
async def process_anime_list_page(callback: CallbackQuery, session: Any):
    page = int(callback.data.split(":")[1])
    
    # Ma'lumotlarni bazadan/keshdan yuklaymiz
    markup, total_count = await get_anime_list_markup(session, page=page)
    
    text = (
        f"📋 {html.bold('Bazadagi animelar ro‘yxati')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Jami anime soni: {html.code(total_count)} ta\n"
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






async def get_anime_list_markup(session, page: int = 1, per_page: int = 10) -> tuple[InlineKeyboardMarkup, int]:
    from services.anime_service import AnimeService
    service = AnimeService(session=session)
    
    # 1. Keshdan yoki DB dan ma'lumotlarni xavfsiz yuklash
    try:
        all_anime = await service.list_anime()
        if not all_anime:  # Agar None kelsa, ishdan chiqmasligi uchun bo'sh ro'yxat
            all_anime = []
    except Exception as e:
        logger.error(f"❌ Anime ro'yxatini olishda xatolik: {e}")
        all_anime = []
        
    total_anime = len(all_anime)
    
    # 2. Agar anime umuman topilmasa
    if total_anime == 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="list_type_menu", style="danger")]
        ])
        return kb, 0

    # 3. Sahifalarni xavfsiz va qisqa yo'l bilan hisoblash
    total_pages = math.ceil(total_anime / per_page)
    # Page chegaradan chiqib ketmasligini bitta qatorda ta'minlaymiz:
    page = max(1, min(page, total_pages))

    # 4. Ro'yxatdan joriy sahifaga kerakli qismini kesib olish (Juda tez)
    start_idx = (page - 1) * per_page
    current_page_anime = all_anime[start_idx : start_idx + per_page]

    inline_keyboard = []

    # 5. Tugmalarni shakllantirish (Lug'at kalitlarini xavfsiz o'qish)
    for anime in current_page_anime:
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
        nav_row.append(InlineKeyboardButton(text="⛔️", callback_data="void", style="danger"))

    nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="void", style="primary"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"list_anime_page:{page+1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="⛔️", callback_data="void", style="danger"))

    inline_keyboard.append(nav_row)

    # 7. Ortga qaytish satri (style olib tashlandi, chunki Aiogram 3 oddiy tugmalarga rang bera olmaydi)
    inline_keyboard.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data="list_type_menu", style="danger")
    ])

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard), total_anime



@router.callback_query(F.data.startswith("del_anime:"))
async def confirm_delete_anime_handler(callback: CallbackQuery, session: Any):
    await callback.answer("Yuklanmoqda...")
    anime_id = int(callback.data.split(":")[1])
    
    confirm_text = (
        f"⚠️ {html.bold('DIQQAT! O‘chirishni tasdiqlang')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Ushbu animeni ro‘yxatdan butunlay o‘chirib tashlamoqchimisiz?\n\n"
        f"🛑 {html.italic('Bu amalni ortga qaytarib bo‘lmaydi! Animega tegishli barcha qismlar (seriyalar) ham bazadan o‘chib ketadi.')}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha,  o‘chirish", callback_data=f"burn_anime:{anime_id}", style="success"),
            InlineKeyboardButton(text="❌ bekor qilish", callback_data=f"v_anime:{anime_id}:1", style="danger")
        ]
    ])
    
    # Agar xabarda rasm yoki video bo'lsa, posterni saqlab faqat matnni o'zgartiramiz
    if callback.message.photo or callback.message.video:
        try:
            await callback.message.edit_caption(caption=confirm_text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
    else:
        try:
            await callback.message.edit_text(text=confirm_text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass