
import logging
import html
from typing import Any, Optional
from aiogram import Router, F
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
        logger.error(f"Yangi xabar yuborishda xato: {e}", exc_info=True)
    return False


# =======================================================
# 🎯 HANDLERS (O'CHIRISH VA TASDIQLASH)
# =======================================================

@router.callback_query(F.data.startswith("del_anime:"))
async def confirm_delete_anime_handler(callback: CallbackQuery, session: Any):
    """Animeni o'chirishni tasdiqlash oynasi."""
    await safe_answer(callback, "Yuklanmoqda...")
    anime_id = int(callback.data.split(":")[1])
    
    confirm_text = (
        f"⚠️ {html.bold('DIQQAT! O‘chirishni tasdiqlang')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Ushbu animeni ro‘yxatdan butunlay o‘chirib tashlamoqchimisiz?\n\n"
        f"🛑 {html.italic('Bu amalni ortga qaytarib bo‘lmaydi! Animega tegishli barcha qismlar (seriyalar) ham bazadan o‘chib ketadi.')}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, o‘chirish", callback_data=f"burn_anime:{anime_id}", style="success"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"v_anime:{anime_id}:1", style="danger")
        ]
    ])
    
    # Media yoki Oddiy text xabarlarni xavfsiz va bir xil tartibda tahrirlaymiz
    await _safe_update_message(
        message=callback.message,
        caption=confirm_text,
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("burn_anime:"))
async def execute_delete_anime_handler(callback: CallbackQuery, session: Any):
    """Animeni bazadan va keshdan to'liq o'chirish ijrosi."""
    await safe_answer(callback, "O'chirilmoqda...")
    anime_id = int(callback.data.split(":")[1])
    
    # Lazy sessionni uyg'otish kodi `AnimeService` ichida avtomatik ishlaydi
    service = AnimeService(session=session)
    
    ok = False
    try:
        ok = await service.delete_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ Anime o'chirishda jiddiy xatolik: {e}")

    # Eski posterli/mediali tasdiqlash xabarini o'chiramiz
    if callback.message:
        await safe_delete(callback.message)

    if ok:
        success_text = (
            f"🗑 {html.bold('Muvaffaqiyatli o‘chirildi!')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ Tanlangan anime, uning barcha qismlari ma’lumotlar bazasidan hamda kesh xotirasidan butunlay yo‘q qilindi."
        )
    else:
        success_text = (
            f"❌ {html.bold('Xatolik yuz berdi!')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ Ushbu animeni o‘chirishda xatolik yuz berdi. U allaqachon o‘chirilgan yoki tizimda ulanish uzilgan bo‘lishi mumkin."
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Animelar ro‘yxatiga", callback_data="list_anime_page:1", style="danger")]
    ])
    
    # Natija xabarini xavfsiz yuboramiz
    await safe_send(callback.message, text=success_text, reply_markup=kb, parse_mode="HTML")