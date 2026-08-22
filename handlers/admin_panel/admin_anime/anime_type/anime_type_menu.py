import logging
from typing import Any, Optional

from aiogram import Router, F, html
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramNetworkError,
)

from services.anime_service import AnimeService
from database.models import AnimeType

router = Router()
logger = logging.getLogger(__name__)

# callback_data tokeni -> AnimeType enum
_TYPE_TOKEN_MAP = {
    "TV_SERIES": AnimeType.TV_SERIES,
    "MOVIE": AnimeType.MOVIE,
    "OVA": AnimeType.OVA,
}

# Tugma matni va tartibi (token, ko'rinadigan nom)
_TYPE_BUTTONS = [
    ("TV_SERIES", "📺 TV Series"),
    ("MOVIE", "🎬 Movie"),
    ("OVA", "🎥 OVA"),
]


# =======================================================
# 🧰 YORDAMCHI FUNKSIYALAR (Telegram xatolaridan himoya)
# =======================================================
async def safe_answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False) -> None:
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "query is too old" in msg or "query id is invalid" in msg or "response timeout expired" in msg:
            pass
        else:
            logger.warning(f"callback.answer xatosi: {e}")
    except TelegramForbiddenError:
        pass
    except Exception as e:
        logger.warning(f"callback.answer kutilmagan xato: {e}")


async def safe_delete(message: Message) -> None:
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    except Exception as e:
        logger.warning(f"Xabarni o'chirishda kutilmagan xato: {e}")


async def safe_send(message: Message, text: str, **kwargs) -> Optional[Message]:
    try:
        return await message.answer(text=text, **kwargs)
    except TelegramRetryAfter as e:
        logger.warning(f"Flood control: retry_after={e.retry_after}")
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError) as e:
        logger.warning(f"Xabar yuborishda xato: {e}")
    except Exception as e:
        logger.error(f"Xabar yuborishda kutilmagan xato: {e}", exc_info=True)
    return None


async def _safe_edit_message(message: Message, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    """
    Anime kartasi rasm/video (caption) yoki oddiy matn bo'lishi mumkin — xabar
    turiga qarab TO'G'RI usul birinchi sinaladi, ikkinchisi zaxira sifatida,
    va hech biri ishlamasa yangi xabar yuborish bilan admin hech qachon
    "osilib" qolmaydi.
    """
    is_media = bool(message.photo or message.video or message.document)
    primary, fallback = (message.edit_caption, message.edit_text) if is_media else (message.edit_text, message.edit_caption)
    primary_kwargs = {"caption": text} if is_media else {"text": text}
    fallback_kwargs = {"text": text} if is_media else {"caption": text}

    try:
        await primary(reply_markup=reply_markup, parse_mode="HTML", **primary_kwargs)
        return
    except TelegramForbiddenError:
        return
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        logger.warning(f"_safe_edit_message: asosiy usul muvaffaqiyatsiz, zaxira sinaladi: {e}")
    except Exception as e:
        logger.error(f"_safe_edit_message: asosiy usulda kutilmagan xato: {e}", exc_info=True)

    try:
        await fallback(reply_markup=reply_markup, parse_mode="HTML", **fallback_kwargs)
        return
    except TelegramForbiddenError:
        return
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        logger.warning(f"_safe_edit_message: zaxira usul ham muvaffaqiyatsiz: {e}")
    except Exception as e:
        logger.error(f"_safe_edit_message: zaxira usulda kutilmagan xato: {e}", exc_info=True)

    # Oxirgi chora: eski xabarni o'chirib, yangisini yuboramiz
    try:
        await message.delete()
    except Exception:
        pass
    try:
        await message.answer(text=text, reply_markup=reply_markup, parse_mode="HTML")
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError) as e:
        logger.warning(f"_safe_edit_message: yangi xabar yuborib bo'lmadi: {e}")
    except Exception as e:
        logger.error(f"_safe_edit_message: yangi xabar yuborishda kutilmagan xato: {e}", exc_info=True)


def _build_type_menu(anime_id: int, current_type_value: Optional[str]) -> tuple[str, InlineKeyboardMarkup]:
    """Menyu matni va klaviaturasini joriy turga qarab yasaydi (mos tugma yashil bo'ladi)."""
    current_label = "Noma'lum"
    for token, label in _TYPE_BUTTONS:
        if _TYPE_TOKEN_MAP[token].value == current_type_value:
            current_label = label
            break

    text = (
        f"🎯 {html.bold('Anime turini tanlang')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Joriy tur: {html.bold(current_label)}\n\n"
        f"Kerakli turni tanlang — bazada darhol yangilanadi."
    )

    rows = []
    for token, label in _TYPE_BUTTONS:
        is_selected = _TYPE_TOKEN_MAP[token].value == current_type_value
        rows.append([
            InlineKeyboardButton(
                text=f"🟢 {label} (Tanlandi)" if is_selected else label,
                callback_data=f"set_anime_type:{anime_id}:{token}",
                style="success" if is_selected else "primary"
            )
        ])
    rows.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"v_anime:{anime_id}:1", style="danger")])

    return text, InlineKeyboardMarkup(inline_keyboard=rows)


# =======================================================
# 1️⃣ MENYUNI OCHISH (anime kartasidagi "🎯 Anime turi" tugmasi)
#    callback_data: "anime_type:<anime_id>"
# =======================================================
@router.callback_query(F.data.startswith("anime_type:"))
async def show_anime_type_menu(callback: CallbackQuery, session: Any):
    await safe_answer(callback)

    try:
        anime_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    # 🟢 TUZATILDI: avval anime'ning joriy turi UMUMAN tekshirilmasdan, faqat
    # oxirgi bosilgan tugma (FSM state) asosida "tanlangan" ko'rsatilardi.
    # Endi bazadan HAQIQIY joriy tur olinadi va shu asosda tugma yashil bo'ladi.
    try:
        service = AnimeService(session=session)
        current_type_value = await service.get_anime_type(anime_id)
    except Exception as e:
        logger.error(f"❌ show_anime_type_menu: type olishda xato: {e}", exc_info=True)
        await safe_answer(callback, "❌ Ma'lumotni yuklashda xatolik yuz berdi.", show_alert=True)
        return

    if current_type_value is None:
        await safe_answer(callback, "❌ Anime topilmadi!", show_alert=True)
        return

    text, kb = _build_type_menu(anime_id, current_type_value)
    await _safe_edit_message(callback.message, text, kb)


# =======================================================
# 2️⃣ TUR TANLANGANDA (bazaga yozish, ekranni yangilash, alert)
#    callback_data: "set_anime_type:<anime_id>:<tv_series|movie|ova>"
# =======================================================
@router.callback_query(F.data.startswith("set_anime_type:"))
async def set_anime_type_handler(callback: CallbackQuery, session: Any):
    try:
        _, anime_id_str, type_token = callback.data.split(":")
        anime_id = int(anime_id_str)
    except (ValueError, IndexError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    new_type = _TYPE_TOKEN_MAP.get(type_token)
    if new_type is None:
        await safe_answer(callback, "❌ Noma'lum anime turi!", show_alert=True)
        return

    try:
        service = AnimeService(session=session)
        ok = await service.update_anime_type(anime_id, new_type)
    except Exception as e:
        logger.error(f"❌ Anime turini yangilashda xato: {e}", exc_info=True)
        await safe_answer(callback, "❌ Turini yangilashda xatolik yuz berdi.", show_alert=True)
        return

    if not ok:
        await safe_answer(callback, "❌ Anime topilmadi yoki yangilanmadi!", show_alert=True)
        return

    # ✅ Muvaffaqiyat haqida alert
    await safe_answer(callback, f"✅ Anime turi '{new_type.value}' ga o'zgartirildi!", show_alert=True)

    # Ekranni YANGI (endi bazadagi) holatga mos qilib qayta chizamiz
    text, kb = _build_type_menu(anime_id, new_type.value)
    await _safe_edit_message(callback.message, text, kb)