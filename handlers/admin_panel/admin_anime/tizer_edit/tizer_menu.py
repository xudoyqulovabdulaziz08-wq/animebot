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



@router.callback_query(F.data.startswith("tizer_edit:"))
async def tizer_edit_handler(callback: CallbackQuery, session: Any):
    # 1. Interfeys qotib qolmasligi uchun darhol va xavfsiz javob beramiz
    await safe_answer(callback)
    
    # 2. Callback datadan anime ID ni xavfsiz ajratib olish
    try:
        anime_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return
    
    # 3. DB/Cache dan animeni xavfsiz yuklaymiz
    service = AnimeService(session=session)
    try:
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ Tahrirlash uchun anime yuklashda xato yuz berdi: {e}", exc_info=True)
        anime = None

    if not anime:
        try:
            await callback.message.answer("❌ Anime topilmadi yoki o‘chirilgan!")
            await safe_delete(callback.message)
        except Exception:
            pass
        return

    # 4. HTML parsing xatoliklariga qarshi anime nomini himoyalaymiz
    raw_title = anime.get("title_uz") or anime.get("title") or "Nomsiz anime"
    title = html.quote(str(raw_title))
    
    # Tizer holatini tekshirish
    trailer_id = anime.get("trailer_id")
    status_icon = "✅" if trailer_id else "❌"
    status_text = "Yuklangan" if trailer_id else "Yuklanmagan"

    # 5. Caption (rasm ostidagi matn) tayyorlash
    caption = (
        f"🎬 <b>{title}</b>\n\n"
        f"📼 Tizer holati: {status_icon} <b>{status_text}</b>\n\n"
        f"👇 Quyidagi tugmalar orqali tizerni boshqarishingiz mumkin:"
    )

    # 6. Dinamik klaviatura tayyorlash
    buttons = [
        [InlineKeyboardButton(text="🎬 Yangilash / Yuklash", callback_data=f"tizer_editer:{anime_id}")]
    ]
    
    # Agar baza (yoki keshda) tizer mavjud bo'lsa, 'Ko'rish' va 'O'chirish' tugmalari chiqadi
    if trailer_id:
        buttons.append([
            InlineKeyboardButton(text="▶️ Ko'rish", callback_data=f"tizer_view:{anime_id}"),
            InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"tizer_delete:{anime_id}"),
        ])
        
    # Asosiy anime boshqaruv menyusiga qaytish tugmasi (callback_data o'zingizning orqaga qaytish handleringizga moslang)
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"v_anime:{anime_id}")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    # 7. Xabarni xavfsiz yangilash (sizning yordamchi funksiyangiz orqali)
    # poster_id=None berilmoqda, chunki rasm o'zgarmaydi, faqat caption va keyboard o'zgaradi.
    success = await _safe_update_message(
        message=callback.message,
        caption=caption,
        reply_markup=kb,
        poster_id=None 
    )
    
    if not success:
        logger.warning(f"ID:{anime_id} anime tizer menyusiga o'tishda xabar yangilanmadi.")