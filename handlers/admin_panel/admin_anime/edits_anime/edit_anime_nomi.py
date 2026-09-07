import logging
import html
from typing import Any, Optional
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter

from handlers.admin_panel.admin_anime.list_anime1 import build_anime_card
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




@router.callback_query(F.data.startswith("edit_fields:"))
async def edit_fields_callback(callback: CallbackQuery, session: Any):
    """Anime sarlavhalarini (nomlarini) tahrirlash uchun til tanlash menyusi."""
    
    # 1. ID ni xavfsiz ajratib olish
    try:
        anime_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await safe_answer(callback, "🚨 Noto'g'ri anime ID!", show_alert=True)
        return

    # 2. AnimeService orqali ma'lumotni dict formatida yuklash[cite: 13]
    service = AnimeService(session=session)
    try:
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ Anime nomlarini yuklashda xato: {e}", exc_info=True)
        anime = None

    if not anime:
        await safe_answer(callback, "❌ Anime topilmadi yoki o‘chirilgan!", show_alert=True)
        return

    # 3. Sarlavhalarni dict ichidan to'g'ri tortib olish va HTML xatoliklaridan himoyalash[cite: 12]
    titles = anime.get("titles", {})
    raw_title_en = titles.get("en") or "Mavjud emas"
    raw_title_uz = titles.get("uz") or "Mavjud emas"

    title_en = html.escape(str(raw_title_en))
    title_uz = html.escape(str(raw_title_uz))

    # 4. Matnni to'g'ri formatlash (Set { } o'rniga String ( ) ishlatildi)
    text = (
        f"<b>📝 Nomni o'zgartirish</b>\n\n"
        f"🇬🇧 English nomi: <code>{title_en}</code>\n"
        f"🇺🇿 Uzbekcha nomi: <code>{title_uz}</code>\n\n"
        f"<i>Qaysi tilni o'zgartirmoqchisiz?</i>"
    )

    # 5. Tugmalarni xatosiz (style parametrisiz) yaratish
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 Uzbekcha", callback_data=f"edit_field:title_uz:{anime_id}", style="primary")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data=f"edit_field:title_en:{anime_id}", style="primary")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"edit_anime:{anime_id}", style="danger")]
    ])

    # 6. Javob berish va oynani xavfsiz yangilash (rasm saqlab qolinadi)
    await safe_answer(callback)
    
    poster_id = anime.get("poster_id")
    success = await _safe_update_message(
        message=callback.message, 
        caption=text, 
        reply_markup=kb,
        poster_id=poster_id
    )

    if not success:
        logger.warning(f"ID:{anime_id} anime nomi tahrirlash menyusini yangilashda xatolik yuz berdi.")