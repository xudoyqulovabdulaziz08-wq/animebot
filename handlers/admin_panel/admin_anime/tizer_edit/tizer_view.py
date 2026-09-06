import logging
from typing import Any, Optional
from aiogram import Router, F, html
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter



from services.anime_service import AnimeService

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
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    except Exception as e:
        logger.warning(f"Xabarni o'chirishda kutilmagan xato: {e}")

async def safe_send(message: Message, **kwargs) -> Optional[Message]:
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
        logger.error(f"Yangi xabar yuborishda xato: {e}", exc_info=True)
    return False

@router.callback_query(F.data.startswith("tizer_view:"))
async def tizer_view(callback: CallbackQuery, session: Any):
    """Tizerni ko'rish tugmasi bosilganda ishlaydi."""
    # Callback data'dan anime_id va tizer_id ni ajratib oling
    _, anime_id, tizer_id = callback.data.split(":")
    
    # Anime va tizer ma'lumotlarini olish
    anime_service = AnimeService(session)
    anime = await anime_service.get_anime_by_id(anime_id)
    tizer = await anime_service.get_tizer_by_id(tizer_id)

    if not anime or not tizer:
        await safe_answer(callback, text="Anime yoki tizer topilmadi.", show_alert=True)
        return

    # Tizer ma'lumotlarini tayyorlash
    caption = f"<b>{html.escape(anime.title)}</b>\n\n{html.escape(tizer.description)}"
    
    # Inline klaviatura yaratish
    buttons = [
        
        [InlineKeyboardButton(text="🗑️ O'chirish", callback_data=f"tizer_delete:{anime_id}:{tizer_id}", style="danger")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"tizer_edit:{anime_id}", style="danger")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    # Xabarni yangilash yoki yangi xabar yuborish
    success = await _safe_update_message(
        message=callback.message,
        caption=caption,
        reply_markup=reply_markup,
        poster_id=tizer.poster_id
    )

    if not success:
        await safe_answer(callback, text="Xabarni yangilashda xato yuz berdi.", show_alert=True)