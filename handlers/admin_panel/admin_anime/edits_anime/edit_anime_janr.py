
import logging
import html
import math
from select import select
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




class EditAnimeStates(StatesGroup):
    waiting_for_genres = State()            # Janrlarni tanlash holati
    waiting_for_confirmation = State()      # ❓ Tasdiqlash holati (Ha/Yo'q)





PER_PAGE = 10  # Bir sahifada ko'rinadigan janrlar soni (Chiroyli joylashishi uchun)

# =====================================================================
# 🛠 YORDAMChI FUNKSIYA: Rangli Tugmalar va Paginatsiya Klasini yasash
# =====================================================================
async def get_admin_genres_edit_markup(
    session: Any, 
    anime_id: int, 
    selected_genres: list[int], 
    page: int = 1
) -> InlineKeyboardMarkup:
    stmt = select(Genre).order_by(Genre.name)
    result = await session.execute(stmt)
    genres = result.scalars().all()
    
    total_items = len(genres)
    total_pages = math.ceil(total_items / PER_PAGE) if total_items > 0 else 1
    
    start_idx = (page - 1) * PER_PAGE
    end_idx = start_idx + PER_PAGE
    current_genres = genres[start_idx:end_idx]
    
    keyboard = []
    row = []
    
    for genre in current_genres:
        is_selected = genre.id in selected_genres
        tick = "✅ " if is_selected else ""
        btn_style = "success" if is_selected else "default"
        
        row.append(InlineKeyboardButton(
            text=f"{tick}{genre.name}",
            callback_data=f"adm_g_tog:{genre.id}:{page}", # Admin uchun maxsus prefiks
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
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"adm_g_page:{page-1}", style="primary"))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="none", style="primary"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"adm_g_page:{page+1}", style="primary"))
        
    if nav_row:
        keyboard.append(nav_row)
        
    # Boshqaruv tugmalari
    keyboard.append([
        InlineKeyboardButton(text="✅ Tanlanganlarni saqlash", callback_data="adm_g_save", style="success")
    ])
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data=f"force_refresh_edit:{anime_id}", style="danger")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# =====================================================================
# 📑 1-QADAM: "🔮 Janr" tugmasi bosilganda oynani ochish
# =====================================================================
@router.callback_query(F.data.startswith("edit_genre_menu:"))
async def edit_anime_genres_start(callback: CallbackQuery, state: FSMContext, session: Any):
    anime_id = int(callback.data.split(":")[1])
    
    # Animening joriy janrlarini xizmat orqali yuklab olamiz
    service = AnimeService(session=session)
    anime_data = await service.get_anime(anime_id)
    
    # Hozirgi tanlangan janr IDlarini list shaklida yig'amiz
    current_genres = anime_data.get("genres", []) if anime_data else []
    
    # Ma'lumotlarni holat keshiga joylaymiz
    await state.update_data(edit_anime_id=anime_id, selected_genres=current_genres)
    await state.set_state(EditAnimeStates.waiting_for_genres)
    
    kb = await get_admin_genres_edit_markup(session, anime_id, current_genres, page=1)
    
    await callback.answer()
    await callback.message.edit_caption(
        caption="🔮 <b>Anime janrlarini tahrirlash:</b>\n\nJanrlarni tanlang (tanlanganlar yashil rangga kiradi) va saqlash tugmasini bosing:",
        reply_markup=kb,
        parse_mode="HTML"
    )


# =====================================================================
# 📑 1.5-QADAM: Paginatsiya va Janr tugmalari bosilganda (Toggle mantiqi)
# =====================================================================
@router.callback_query(EditAnimeStates.waiting_for_genres, F.data.startswith("adm_g_tog:"))
async def process_genre_toggle(callback: CallbackQuery, state: FSMContext, session: Any):
    _, genre_id_str, page_str = callback.data.split(":")
    genre_id = int(genre_id_str)
    page = int(page_str)
    
    state_data = await state.get_data()
    anime_id = state_data.get("edit_anime_id")
    selected_genres = list(state_data.get("selected_genres", []))
    
    # Agar janr ro'yxatda bo'lsa o'chiramiz, bo'lmasa qo'shamiz
    if genre_id in selected_genres:
        selected_genres.remove(genre_id)
    else:
        selected_genres.append(genre_id)
        
    await state.update_data(selected_genres=selected_genres)
    
    # Klaviaturani rasm ostida yangilaymiz (Media edit bo'lib poster joyida qoladi)
    kb = await get_admin_genres_edit_markup(session, anime_id, selected_genres, page=page)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except:
        pass
    await callback.answer()


@router.callback_query(EditAnimeStates.waiting_for_genres, F.data.startswith("adm_g_page:"))
async def process_genre_page_change(callback: CallbackQuery, state: FSMContext, session: Any):
    page = int(callback.data.split(":")[1])
    state_data = await state.get_data()
    anime_id = state_data.get("edit_anime_id")
    selected_genres = state_data.get("selected_genres", [])
    
    kb = await get_admin_genres_edit_markup(session, anime_id, selected_genres, page=page)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except:
        pass
    await callback.answer()


# =====================================================================
# 📑 2-QADAM: Saqlash bosilganda tasdiqlash oynasiga o'tish (Siz aytgan qism)
# =====================================================================
@router.callback_query(EditAnimeStates.waiting_for_genres, F.data == "adm_g_save")
async def process_genres_save_confirmation(callback: CallbackQuery, state: FSMContext, session: Any):
    state_data = await state.get_data()
    anime_id = state_data.get("edit_anime_id")
    selected_genres = state_data.get("selected_genres", [])
    
    # Tanlangan janrlarning nomlarini chiroyli qilib ko'rsatish uchun bazadan nomlarini olamiz
    if selected_genres:
        stmt = select(Genre).where(Genre.id.in_(selected_genres)).order_by(Genre.name)
        result = await session.execute(stmt)
        genre_objects = result.scalars().all()
        genre_names = ", ".join([g.name for g in genre_objects])
    else:
        genre_names = "<i>Hech qanday janr tanlanmadi</i>"
        
    confirm_text = (
        f"❓ <b>Anime janrlari o'zgartirilsinmi?</b>\n\n"
        f"🔮 <b>Yangi tanlangan janrlar:</b>\n"
        f"<blockquote>{genre_names}</blockquote>\n"
        f"Ushbu o'zgarishlarni tasdiqlaysizmi?"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha", callback_data="confirm_genre_db:yes", style="success"),
            InlineKeyboardButton(text="❌ Yo'q", callback_data="confirm_genre_db:no", style="danger")
        ]
    ])
    
    await state.set_state(EditAnimeStates.waiting_for_confirmation)
    await callback.answer()
    await callback.message.edit_caption(caption=confirm_text, reply_markup=kb, parse_mode="HTML")


# =====================================================================
# 📑 3-QADAM: Tasdiqlash (Ha / Yo'q) bosilganda yakuniy yozish
# =====================================================================
@router.callback_query(EditAnimeStates.waiting_for_confirmation, F.data.startswith("confirm_genre_db:"))
async def save_or_cancel_anime_genres(callback: CallbackQuery, state: FSMContext, session: Any):
    action = callback.data.split(":")[1]
    state_data = await state.get_data()
    anime_id = state_data.get("edit_anime_id")
    selected_genres = state_data.get("selected_genres", [])
    
    # ❌ AGAR ADMIN "YO'Q" DESA
    if action == "no":
        await callback.answer("O'zgarishlar bekor qilindi.", show_alert=True)
        await state.clear()
        
        cloned_callback = callback.model_copy(update={"data": f"edit_anime:{anime_id}"})
        from handlers.admin_panel.admin_anime.edit_anime import process_edit_anime_menu
        await process_edit_anime_menu(cloned_callback, session)
        return

    # ✅ AGAR ADMIN "HA" DESA (Bazaga yozish)
    await callback.answer("Janrlar bazaga yozilmoqda...")
    
    try:
        service = AnimeService(session=session)
        # Yuqorida qo'shgan yangi xavfsiz metodimizni chaqiramiz
        success = await service.update_genres(anime_id=anime_id, genre_ids=selected_genres)
        
        if success:
            if hasattr(session, "expire_all"):
                session.expire_all()
            elif hasattr(session, "_session") and hasattr(session._session, "expire_all"):
                session._session.expire_all()
    except Exception as e:
        logger.error(f"🚨 DB Update Genres critically failed: {e}")
        success = False

    if not success:
        await callback.message.edit_caption(
            caption="❌ <b>Xatolik:</b> Janrlarni saqlashda texnik xato yuz berdi.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⚙️ Orqaga qaytish", callback_data=f"force_refresh_edit:{anime_id}", style="danger")
            ]]),
            parse_mode="HTML"
        )
        await state.clear()
        return

    # Muvaffaqiyatli xabar va FSMni tozalab bosh menyuga qaytish
    await state.clear()
    
    cloned_callback = callback.model_copy(update={"data": f"edit_anime:{anime_id}"})
    from handlers.admin_panel.admin_anime.edit_anime import process_edit_anime_menu
    await process_edit_anime_menu(cloned_callback, session)