import math
import logging
from typing import Any, Optional
from aiogram import Router, F, html
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from services.anime_service import AnimeService

router = Router()
logger = logging.getLogger(__name__)

async def safe_answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False) -> None:
    """Telegramda 'query is too old' kabi xatolarni ushlab qoluvchi funksiya."""
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "query is too old" not in msg and "query id is invalid" not in msg and "response timeout expired" not in msg:
            logger.warning(f"safe_answer xatosi: {e}")
    except TelegramForbiddenError:
        pass
    


async def get_vip_episode_list_markup(anime_id: int, episodes: list, page: int = 1, per_page: int = 12) -> InlineKeyboardMarkup:
    """VIP qismlar ro'yxatini sahifalash va klaviaturani yasash."""
    total_episodes = len(episodes)
    
    # Agar VIP qismlar hali mavjud bo'lmasa
    if total_episodes == 0:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⛔️ VIP qismlar mavjud emas", callback_data="void", style="primary")],
            [InlineKeyboardButton(text="➕ VIP qism qo'shish", callback_data=f"add_vip_episode:{anime_id}", style="success")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"manage_episodes:{anime_id}", style="danger")]
        ])

    total_pages = math.ceil(total_episodes / per_page)
    page = max(1, min(page, total_pages))

    # Joriy sahifaga mos qismlarni kesib olish
    start_idx = (page - 1) * per_page
    current_page_episodes = episodes[start_idx : start_idx + per_page]

    inline_keyboard = []
    row = []

    # VIP qismlarni grid (3 tadan) ko'rinishida joylash
    for ep in current_page_episodes:
        ep_num = ep.get("episode")
        is_filler = ep.get("is_filler", False)
        
        # Filler bo'lsa 🌀 stikeri, oddiy VIP bo'lsa 👑 stikeri
        icon = "🌀" if is_filler else "👑"
        
        row.append(InlineKeyboardButton(
            text=f"{icon} {ep_num} ▶️", 
            callback_data=f"show_vip_ep:{anime_id}:{ep_num}:{page}"
        ))
        
        if len(row) == 3:
            inline_keyboard.append(row)
            row = []
            
    if row:
        inline_keyboard.append(row)

    # Paginatsiya (Navigatsiya) satri
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"view_vip_episodes_page:{anime_id}:{page-1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="⛔️", callback_data="void", style="primary"))

    nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="void", style="primary"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"view_vip_episodes_page:{anime_id}:{page+1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="⛔️", callback_data="void", style="primary"))

    inline_keyboard.append(nav_row)

    # VIP qism qo'shish tugmasi (Qismlar bo'lganda ham pastda chiqadi)
    inline_keyboard.append([
        InlineKeyboardButton(text="➕ VIP qism qo'shish", callback_data=f"add_vip_episode:{anime_id}", style="success")
    ])

    # Ortga qaytish satri
    inline_keyboard.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"manage_episodes:{anime_id}", style="danger")
    ])

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


@router.callback_query(F.data.startswith("view_vip_episodes_list:") | F.data.startswith("view_vip_episodes_page:"))
async def view_vip_episodes_list_handler(callback: CallbackQuery, session: Any):
    await safe_answer(callback, "VIP qismlar yuklanmoqda...")
    
    try:
        parts = callback.data.split(":")
        anime_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 1
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov formati!", show_alert=True)
        return

    service = AnimeService(session=session)
    try:
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"Anime bazadan olinishida xato yuz berdi: {e}")
        anime = None
    
    if not anime:
        try:
            await callback.message.answer("❌ Anime topilmadi!")
        except Exception:
            pass
        return

    raw_title = anime.get("title", "Nomsiz anime")
    title = html.quote(str(raw_title))
    
    # Faqat VIP qismlarni ajratib olish
    all_episodes = anime.get("episodes", [])
    vip_episodes = [ep for ep in all_episodes if ep.get("is_vip")]

    caption = (
        f"╔══════════════════╗\n"
        f" 👑 <b>{title} (VIP)</b>\n"
        f"╚══════════════════╝\n\n"
        f"👑 VIP qismlar ro‘yxati. Kerakli qismni tanlang.\n"
        f"💡 {html.italic('Tanlangan VIP qism videosi va uni boshqarish tugmalari shu yerda ochiladi.')}\n\n"
        f"📌 <b>Eslatma:</b> 🌀 <i>belgisi turgan qismlar filler hisoblanadi.</i>"
    )

    markup = await get_vip_episode_list_markup(anime_id=anime_id, episodes=vip_episodes, page=page)

    try:
        await callback.message.edit_caption(caption=caption, reply_markup=markup, parse_mode="HTML")
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "message is not modified" in msg:
            return
        try:
            await callback.message.edit_text(text=caption, reply_markup=markup, parse_mode="HTML")
        except TelegramBadRequest as err:
            if "message is not modified" not in str(err).lower():
                logger.warning(f"edit_text orqali yangilash amalga oshmadi: {err}")
    except Exception as e:
        logger.error(f"Kutilmagan xato: {e}")