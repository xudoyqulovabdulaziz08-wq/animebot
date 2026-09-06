import logging
from typing import Any, Optional
from aiogram import Router, F, html
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo, Message
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
    """Tizerni ko'rish tugmasi bosilganda ishlaydi (Rasm -> Videoga o'zgardi)."""
    await safe_answer(callback)
    
    # 1. Callback data'dan FAQAT anime_id ni ajratib olamiz (tizer_view:12)
    parts = callback.data.split(":")
    if len(parts) < 2 or not parts[1].isdigit():
        await safe_answer(callback, text="❌ Noto'g'ri so'rov ma'lumoti!", show_alert=True)
        return
        
    anime_id = int(parts[1])
    
    # 2. AnimeService orqali anime ma'lumotlarini (dict ko'rinishida) olamiz
    anime_service = AnimeService(session)
    anime = await anime_service.get_anime(anime_id)

    if not anime:
        await safe_answer(callback, text="❌ Anime topilmadi.", show_alert=True)
        return

    # 3. Tizer (trailer_id) mavjudligini tekshiramiz
    trailer_id = anime.get("trailer_id")
    if not trailer_id:
        await safe_answer(callback, text="❌ Ushbu anime uchun tizer yuklanmagan.", show_alert=True)
        return

    # 4. Sarlavha va matnni shakllantirish (dict kalitlaridan olamiz)
    title = anime.get("title") or "Nomsiz anime"
    description = anime.get("description") or ""
    
    caption = f"🎬 <b>{html.escape(title)}</b> — Tizer\n\n{html.escape(description)}"
    
    # 5. Inline klaviatura (O'chirish va Orqaga bitta joyda)
    buttons = [
        [InlineKeyboardButton(text="🗑️ O'chirish", callback_data=f"tizer_delete:{anime_id}")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"tizer_edit:{anime_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    # 6. Mediadi (InputMediaVideo) orqali xavfsiz yangilaymiz
    try:
        new_media = InputMediaVideo(media=trailer_id, caption=caption, parse_mode="HTML")
        await callback.message.edit_media(media=new_media, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "message is not modified" in msg:
            pass
        else:
            # Agar Telegram edit_media orqali rasmdan videoga o'tkazishni bloklasa:
            await safe_delete(callback.message)
            await callback.message.answer_video(
                video=trailer_id,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"tizer_view bajarilishida kutilmagan xato: {e}", exc_info=True)