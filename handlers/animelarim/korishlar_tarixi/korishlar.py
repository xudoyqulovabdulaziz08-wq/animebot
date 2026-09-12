import logging
from typing import Any, Optional

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from config import config

CREATOR_ID = config.CREATOR_ID
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
    message: Message,
    caption: str,
    reply_markup: InlineKeyboardMarkup,
    new_photo_id: Optional[str] = None,
) -> bool:
    """
    Xabarni FAQAT TAHRIRLASH orqali yangilaydi. 
    Agar tahrirlashning iloji bo'lmasa, o'chirib qayta yuboradi.
    """
    # 1. Agar yangi rasm ID berilgan bo'lsa va media almashtirish kerak bo'lsa
    if new_photo_id:
        try:
            new_media = InputMediaPhoto(media=new_photo_id, caption=caption, parse_mode="HTML")
            await message.edit_media(media=new_media, reply_markup=reply_markup)
            return True
        except TelegramForbiddenError:
            return False
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return True
            logger.warning(f"edit_media muvaffaqiyatsiz, oddiy tahrirlash sinaladi: {e}")
        except Exception as e:
            logger.error(f"edit_media kutilmagan xato: {e}", exc_info=True)

    # 2. Xabar turini aniqlash (Media yoki Oddiy matn)
    is_media = bool(message.photo or message.video or message.document or message.animation)

    # 3. Mos ravishda tahrirlashga urinish
    try:
        if is_media:
            await message.edit_caption(caption=caption, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await message.edit_text(text=caption, reply_markup=reply_markup, parse_mode="HTML")
        return True
    except TelegramForbiddenError:
        return False
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return True
        logger.warning(f"Tahrirlash usuli muvaffaqiyatsiz: {e}")
    except Exception as e:
        logger.error(f"Tahrirlashda kutilmagan xato: {e}", exc_info=True)

    # 🟢 4. Zaxira reja (Fallback): Hech qaysi tahrirlash ishlamasa
    try:
        await message.delete()
    except Exception:
        pass
        
    try:
        if new_photo_id:
            await message.answer_photo(photo=new_photo_id, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await message.answer(text=caption, reply_markup=reply_markup, parse_mode="HTML")
        return True
    except Exception as e:
        logger.error(f"Yangi xabar yuborishda xato: {e}", exc_info=True)
        
    return False


# =======================================================
# 🗂 KEYBOARD VA HANDLERLAR
# =======================================================

def get_history_keyboard() -> InlineKeyboardMarkup:
    """Tarix menyusi uchun klaviatura (style parametrlari olib tashlandi)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⏺️ Tugatilgan", callback_data="history_completed"),
                InlineKeyboardButton(text="🕣 Ko‘rilmoqda", callback_data="history_watching")
            ],
            [
                InlineKeyboardButton(text="⬅️ Orqaga", callback_data="animelarim_cabinet")
            ]
        ]
    )


@router.callback_query(F.data == "cabinet_history")
async def show_watching_history(callback: CallbackQuery):
    # 🔒 Ruxsat tekshiruvi
    if callback.from_user.id != CREATOR_ID:
        await callback.answer(
            text="🛑 Izohlar funksiyasi tez orada ishga tushadi.",
            show_alert=True
        )
        return
        
    caption = (
        "📜 <b>Ko‘rish tarixi</b>\n\n"
        "<blockquote>"
        "Bu bo‘limda ko‘rgan va hozir ko‘rayotgan "
        "animelaringiz saqlanadi."
        "</blockquote>\n\n"
        "Kerakli bo‘limni tanlang."
    )

    keyboard = get_history_keyboard()

    # Xabar turi va Telegram API xatolarini xavfsiz boshqarish
    await safe_answer(callback)
    
    if not callback.message:
        return
        
    await _safe_update_message(
        message=callback.message,
        caption=caption,
        reply_markup=keyboard
    )