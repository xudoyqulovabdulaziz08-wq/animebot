import logging
import html
import math
from typing import Any, Optional
from sqlalchemy import select
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext



router = Router()
logger = logging.getLogger(__name__)

PER_PAGE = 10  # Har bir sahifada ko'rsatiladigan dubberlar soni


# =======================================================
# 🧰 YORDAMCHI FUNKSIYALAR (Telegram xatolaridan himoya)
# =======================================================
async def safe_answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False) -> None:
    """CallbackQuery'ga xavfsiz javob berish."""
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



# =====================================================================
# 🛠 YORDAMCHI FUNKSIYA: Janrlar Ro'yxati Tugmalarini Yasash
# =====================================================================
async def get_admin_genres_list_markup(
    session: Any, 
    page: int = 1
) -> InlineKeyboardMarkup:
    from database.models import Genre  # Circular import oldini olish uchun
    
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
        # Har bir janr tugmasi bosilganda o'sha janrning tahrirlash oynasiga o'tadi
        row.append(InlineKeyboardButton(
            text=f"🎭 {genre.name}",
            callback_data=f"edit_genre_detail:{genre.id}",
            style="default"
        ))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    # Paginatsiya (Sahifalash) tugmalari
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"list_edit_genre_page:{page-1}", style="primary"))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="none", style="primary"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"list_edit_genre_page:{page+1}", style="primary"))
        
    if nav_row:
        keyboard.append(nav_row)
        
    # Boshqaruv tugmalari
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Janr menyu", callback_data="janr_menu", style="danger")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.callback_query(F.data.startswith("list_edit_genre_page:"))
async def list_edit_genre_page_handler(callback: CallbackQuery, state: FSMContext, session: Any):
    await state.clear()
    
    # Callback data'dan sahifa raqamini xavfsiz ajratib olish
    try:
        page = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        page = 1
        
    await safe_answer(callback)
    
    # InlineKeyboardMarkup yaratish
    markup = await get_admin_genres_list_markup(
        session=session, 
        page=page
    )
    
    caption = (
        "🎙️ <b>Janrlar ro‘yxati</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Tahrirlamoqchi yoki ko‘rmoqchi bo‘lgan janr ustiga bosing.\n\n"
        "👇 <b>Mavjud janrlar:</b>"
    )
    
    # Xabarni bitta interfeys doirasida xavfsiz yangilash
    await _safe_update_message(
        message=callback.message,
        caption=caption,
        reply_markup=markup
    )