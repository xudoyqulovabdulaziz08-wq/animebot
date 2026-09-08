import logging
import html
import math
from sqlalchemy import select
from typing import Any, Optional
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext

from database.models import Genre
from services.anime_service import AnimeService
from aiogram.fsm.state import StatesGroup, State

router = Router()
logger = logging.getLogger(__name__)


# =======================================================
# 🧰 YORDAMCHI FUNKSIYALAR (Telegram xatolaridan himoya)
# =======================================================
async def safe_answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False) -> None:
    """CallbackQuery'ga xavfsiz javob berish (kutilgan xatoliklarni yutish)."""
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "query is too old" not in msg and "query id is invalid" not in msg and "response timeout expired" not in msg:
            logger.warning(f"safe_answer xatosi: {e}")
    except TelegramForbiddenError:
        pass
    except Exception as e:
        logger.warning(f"safe_answer kutilmagan xato: {e}")

async def safe_delete(message: Message) -> None:
    """Xabarni xavfsiz o'chirish."""
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    except Exception as e:
        logger.warning(f"Xabarni o'chirishda kutilmagan xato: {e}")

async def safe_send(message: Message, **kwargs) -> Optional[Message]:
    """Xabarni xavfsiz yuborish."""
    try:
        return await message.answer(**kwargs)
    except TelegramRetryAfter as e:
        logger.warning(f"Flood control: retry_after={e.retry_after}")
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError) as e:
        logger.warning(f"Xabar yuborishda xato: {e}")
    except Exception as e:
        logger.error(f"Xabar yuborishda kutilmagan xato: {e}", exc_info=True)
    return None

async def _safe_update_message(
    message: Any,
    caption: str,
    reply_markup: InlineKeyboardMarkup,
    poster_id: Optional[str] = None
) -> bool:
    """Xabarni ishonchli usulda yangilash zanjiri."""
    if poster_id:
        try:
            new_media = InputMediaPhoto(media=poster_id, caption=caption, parse_mode="HTML")
            await message.edit_media(media=new_media, reply_markup=reply_markup)
            return True
        except TelegramForbiddenError:
            return False
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return True
        except Exception:
            pass
        
        try:
            await message.edit_caption(caption=caption, reply_markup=reply_markup, parse_mode="HTML")
            return True
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return True
        except Exception:
            pass
    else:
        try:
            await message.edit_text(text=caption, reply_markup=reply_markup, parse_mode="HTML")
            return True
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return True
        except Exception:
            pass
        
        try:
            await message.edit_caption(caption=caption, reply_markup=reply_markup, parse_mode="HTML")
            return True
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return True
        except Exception:
            pass

    try:
        await message.delete()
    except Exception:
        pass
    
    try:
        await message.answer(text=caption, reply_markup=reply_markup, parse_mode="HTML")
        return True
    except Exception as e:
        logger.error(f"Xabar yuborishda kutilmagan xato: {e}", exc_info=True)
    return False


class EditAnimeStates(StatesGroup):
    waiting_for_dubbers = State()           # Dubberlarni tanlash holati
    waiting_for_confirmation = State()      # ❓ Tasdiqlash holati (Ha/Yo'q)


PER_PAGE = 10


# =====================================================================
# 🛠 YORDAMCHI FUNKSIYA: Dubberlar uchun Paginatsiya va Tugmalarni yasash
# =====================================================================
async def get_admin_dubbers_edit_markup(
    session: Any, 
    anime_id: int, 
    selected_dubbers: list[int], 
    page: int = 1
) -> InlineKeyboardMarkup:
    from database.models import Dubber  # Circular import oldini olish uchun
    
    stmt = select(Dubber).order_by(Dubber.name)
    result = await session.execute(stmt)
    dubbers = result.scalars().all()
    
    total_items = len(dubbers)
    total_pages = math.ceil(total_items / PER_PAGE) if total_items > 0 else 1
    
    start_idx = (page - 1) * PER_PAGE
    end_idx = start_idx + PER_PAGE
    current_dubbers = dubbers[start_idx:end_idx]
    
    keyboard = []
    row = []
    
    for dubber in current_dubbers:
        is_selected = dubber.id in selected_dubbers
        tick = "✅ " if is_selected else ""
        btn_style = "success" if is_selected else "default"
        
        row.append(InlineKeyboardButton(
            text=f"{tick}{dubber.name}",
            callback_data=f"adm_d_tog:{dubber.id}:{page}", # Admin dubber toggle prefiksi
            style=btn_style
        ))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    # Sahifalash (Paginatsiya) tugmalari
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"adm_d_page:{page-1}", style="primary"))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="none", style="primary"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"adm_d_page:{page+1}", style="primary"))
        
    if nav_row:
        keyboard.append(nav_row)
        
    # Boshqaruv tugmalari
    keyboard.append([
        InlineKeyboardButton(text="✅ Tanlanganlarni saqlash", callback_data="adm_d_save", style="success")
    ])
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data=f"force_refresh_edit:{anime_id}", style="danger")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# =====================================================================
# 📑 1-QADAM: "🎙️ Dubber" tugmasi bosilganda oynani ochish
# =====================================================================
@router.callback_query(F.data.startswith("edit_field:dubber:"))
async def edit_anime_dubbers_start(callback: CallbackQuery, state: FSMContext, session: Any):
    anime_id = int(callback.data.split(":")[2])
    
    # Animening joriy ma'lumotlarini yuklab olamiz
    service = AnimeService(session=session)
    anime_data = await service.get_anime(anime_id)
    
    # Hozirgi tanlangan dubber IDlarini list shaklida yig'amiz
    current_dubbers = anime_data.get("dubbers", []) if anime_data else []
    
    # Ma'lumotlarni holat keshiga (FSM) joylaymiz
    await state.update_data(edit_anime_id=anime_id, selected_dubbers=current_dubbers)
    await state.set_state(EditAnimeStates.waiting_for_dubbers)
    
    kb = await get_admin_dubbers_edit_markup(session, anime_id, current_dubbers, page=1)
    
    await safe_answer(callback)
    caption_text = (
        "🎙️ <b>Anime dubberlarini tahrirlash:</b>\n\n"
        "Ovoz bergan dubberlarni tanlang (tanlanganlar yashil rangga kiradi) va saqlash tugmasini bosing:"
    )
    await _safe_update_message(callback.message, caption=caption_text, reply_markup=kb)


# =====================================================================
# 📑 1.5-QADAM: Paginatsiya va Dubber tugmalari bosilganda (Toggle mantiqi)
# =====================================================================
@router.callback_query(EditAnimeStates.waiting_for_dubbers, F.data.startswith("adm_d_tog:"))
async def process_dubber_toggle(callback: CallbackQuery, state: FSMContext, session: Any):
    _, dubber_id_str, page_str = callback.data.split(":")
    dubber_id = int(dubber_id_str)
    page = int(page_str)
    
    state_data = await state.get_data()
    anime_id = state_data.get("edit_anime_id")
    selected_dubbers = list(state_data.get("selected_dubbers", []))
    
    # Agar dubber ro'yxatda bo'lsa o'chiramiz, bo'lmasa qo'shamiz
    if dubber_id in selected_dubbers:
        selected_dubbers.remove(dubber_id)
    else:
        selected_dubbers.append(dubber_id)
        
    await state.update_data(selected_dubbers=selected_dubbers)
    
    # Klaviaturani poster ostida yangilaymiz
    kb = await get_admin_dubbers_edit_markup(session, anime_id, selected_dubbers, page=page)
    await safe_answer(callback)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.warning(f"Dubber toggleda reply_markup xatosi: {e}")
    except Exception as e:
        logger.warning(f"Dubber toggleda kutilmagan xato: {e}")


# =====================================================================
# 📑 1.5-QADAM: Paginatsiya (Keyingi / Oldingi sahifaga o'tish)
# =====================================================================
@router.callback_query(EditAnimeStates.waiting_for_dubbers, F.data.startswith("adm_d_page:"))
async def process_dubber_page_change(callback: CallbackQuery, state: FSMContext, session: Any):
    page = int(callback.data.split(":")[1])
    state_data = await state.get_data()
    anime_id = state_data.get("edit_anime_id")
    selected_dubbers = state_data.get("selected_dubbers", [])
    
    kb = await get_admin_dubbers_edit_markup(session, anime_id, selected_dubbers, page=page)
    await safe_answer(callback)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.warning(f"Dubber paginatsiyasida reply_markup xatosi: {e}")
    except Exception as e:
        logger.warning(f"Dubber paginatsiyasida kutilmagan xato: {e}")


@router.callback_query(F.data == "none")
async def process_none_callback(callback: CallbackQuery):
    await safe_answer(callback)


# =====================================================================
# 📑 2-QADAM: Saqlash bosilganda tasdiqlash oynasiga o'tish
# =====================================================================
@router.callback_query(EditAnimeStates.waiting_for_dubbers, F.data == "adm_d_save")
async def process_dubbers_save_confirmation(callback: CallbackQuery, state: FSMContext, session: Any):
    from database.models import Dubber  # Circular import oldini olish uchun
    
    state_data = await state.get_data()
    selected_dubbers = state_data.get("selected_dubbers", [])
    
    # Tanlangan dubberlarning nomlarini chiroyli ko'rsatish uchun DBdan olamiz
    if selected_dubbers:
        stmt = select(Dubber).where(Dubber.id.in_(selected_dubbers)).order_by(Dubber.name)
        result = await session.execute(stmt)
        dubber_objects = result.scalars().all()
        dubber_names = ", ".join([d.name for d in dubber_objects])
    else:
        dubber_names = "<i>Hech qanday dubber tanlanmadi</i>"
        
    confirm_text = (
        f"❓ <b>Anime dubberlari o'zgartirilsinmi?</b>\n\n"
        f"🎙️ <b>Yangi tanlangan dublyaj jamoasi:</b>\n"
        f"<blockquote>{dubber_names}</blockquote>\n"
        f"Ushbu o'zgarishlarni tasdiqlaysizmi?"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha", callback_data="confirm_dubber_db:yes", style="success"),
            InlineKeyboardButton(text="❌ Yo'q", callback_data="confirm_dubber_db:no", style="danger")
        ]
    ])
    
    await state.set_state(EditAnimeStates.waiting_for_confirmation)
    await safe_answer(callback)
    await _safe_update_message(callback.message, caption=confirm_text, reply_markup=kb)


# =====================================================================
# 📑 3-QADAM: Tasdiqlash (Ha / Yo'q) bosilganda yakuniy yozish
# =====================================================================
@router.callback_query(EditAnimeStates.waiting_for_confirmation, F.data.startswith("confirm_dubber_db:"))
async def save_or_cancel_anime_dubbers(callback: CallbackQuery, state: FSMContext, session: Any):
    action = callback.data.split(":")[1]
    state_data = await state.get_data()
    anime_id = state_data.get("edit_anime_id")
    selected_dubbers = state_data.get("selected_dubbers", [])
    
    # ❌ AGAR ADMIN "YO'Q" DESA
    if action == "no":
        await safe_answer(callback, "O'zgarishlar bekor qilindi.", show_alert=True)
        await state.clear()
        
        cloned_callback = callback.model_copy(update={"data": f"edit_anime:{anime_id}"})
        from handlers.admin_panel.admin_anime.edits_anime.edit_anime_menu import process_edit_anime_menu
        await process_edit_anime_menu(cloned_callback, session)
        return

    # ✅ AGAR ADMIN "HA" DESA (Bazaga yozish)
    await safe_answer(callback, "Dubberlar bazaga yozilmoqda...")
    
    success = False
    try:
        service = AnimeService(session=session)
        # Oldingi qadamda service qatlamiga qo'shgan yangi xavfsiz metodimizni chaqiramiz
        success = await service.update_dubbers(anime_id=anime_id, dubber_ids=selected_dubbers)
    except Exception as e:
        logger.error(f"🚨 DB Update Dubbers critically failed: {e}")

    await state.clear()

    if not success:
        error_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⚙️ Orqaga qaytish", callback_data=f"force_refresh_edit:{anime_id}", style="danger")
        ]])
        await _safe_update_message(
            message=callback.message,
            caption="❌ <b>Xatolik:</b> Dubberlarni saqlashda texnik xato yuz berdi.",
            reply_markup=error_kb
        )
        return

    # Muvaffaqiyatli xabar va FSMni tozalab bosh menyuga qaytish
    cloned_callback = callback.model_copy(update={"data": f"edit_anime:{anime_id}"})
    from handlers.admin_panel.admin_anime.edits_anime.edit_anime_menu import process_edit_anime_menu
    await process_edit_anime_menu(cloned_callback, session)