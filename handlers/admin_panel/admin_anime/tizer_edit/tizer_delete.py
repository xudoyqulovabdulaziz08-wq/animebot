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
    new_photo_id: Optional[str] = None,
) -> bool:
    """
    Xabarni FAQAT TAHRIRLASH orqali yangilaydi (yangi xabar yubormaydi, oxirgi
    zaxira holati bundan mustasno).

    - new_photo_id berilsa: media RASMga almashtiriladi (edit_media). Bu, masalan,
      tizer (video) o'chirilgach, xabarni animening posteriga qaytarish uchun kerak —
      Telegram edit_media orqali video->rasm turini almashtirishga ruxsat beradi.
    - berilmasa: xabar hozir qanday turda bo'lsa (video/rasm/hujjat yoki matn),
      o'sha turga MOS usul (caption yoki text) bilan yangilanadi — media o'zgarmaydi.

    Qaytaradi: True — muvaffaqiyatli, False — hech qanday usul ishlamadi
    (bu holatda chaqiruvchi qo'shimcha fallback bera oladi).
    """
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
            logger.warning(f"edit_media muvaffaqiyatsiz, caption/text tahrirlash sinaladi: {e}")
        except Exception as e:
            logger.error(f"edit_media kutilmagan xato: {e}", exc_info=True)

    is_media = bool(getattr(message, "photo", None) or getattr(message, "video", None) or getattr(message, "document", None))
    primary = message.edit_caption if is_media else message.edit_text
    fallback = message.edit_text if is_media else message.edit_caption
    primary_kwargs = {"caption": caption} if is_media else {"text": caption}
    fallback_kwargs = {"text": caption} if is_media else {"caption": caption}

    try:
        await primary(reply_markup=reply_markup, parse_mode="HTML", **primary_kwargs)
        return True
    except TelegramForbiddenError:
        return False
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return True
        logger.warning(f"Asosiy tahrirlash usuli muvaffaqiyatsiz, zaxira sinaladi: {e}")
    except Exception as e:
        logger.error(f"Asosiy tahrirlashda kutilmagan xato: {e}", exc_info=True)

    try:
        await fallback(reply_markup=reply_markup, parse_mode="HTML", **fallback_kwargs)
        return True
    except TelegramForbiddenError:
        return False
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return True
        logger.warning(f"Zaxira tahrirlash usuli ham muvaffaqiyatsiz: {e}")
    except Exception as e:
        logger.error(f"Zaxira tahrirlashda kutilmagan xato: {e}", exc_info=True)

    # 🟢 Bu yerga faqat HECH QANDAY tahrirlash usuli ishlamasa yetib keladi
    # (masalan xabar butunlay o'chirilgan bo'lsa) — admin xabarsiz qolmasligi
    # uchun so'nggi, chinakam oxirgi chora.
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
# 1️⃣ "🗑️ O'chirish" TUGMASI — TASDIQLASHNI SO'RAYDI (hali o'chirmaydi)
# =======================================================
@router.callback_query(F.data.startswith("tizer_delete:"))
async def confirm_tizer_delete_handler(callback: CallbackQuery, session: Any) -> None:
    await safe_answer(callback)

    try:
        anime_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    confirm_text = (
        f"⚠️ <b>Tizerni o‘chirishni tasdiqlang</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Ushbu animening tizerini butunlay o‘chirmoqchimisiz?\n\n"
        f"🛑 <i>Bu amalni ortga qaytarib bo‘lmaydi.</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, o‘chirilsin", callback_data=f"tizer_delete_confirm:{anime_id}", style="success"),
            InlineKeyboardButton(text="❌ Yo‘q, bekor qilish", callback_data=f"tizer_delete_cancel:{anime_id}", style="danger"),
        ]
    ])

    # Xabar hozir video (tizer) sifatida ko'rsatilmoqda — faqat caption/tugmalar
    # o'zgaradi, video o'sha-o'sha turadi (new_photo_id berilmaydi).
    await _safe_update_message(callback.message, confirm_text, kb)


# =======================================================
# 2️⃣ "❌ Yo'q" — BEKOR QILISH, TIZER KO'RISH EKRANIGA QAYTISH
# =======================================================
@router.callback_query(F.data.startswith("tizer_delete_cancel:"))
async def cancel_tizer_delete_handler(callback: CallbackQuery, session: Any) -> None:
    await safe_answer(callback, "Bekor qilindi.")

    try:
        anime_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        return

    try:
        service = AnimeService(session=session)
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ cancel_tizer_delete: anime olishda xato: {e}", exc_info=True)
        anime = None

    if not anime:
        await safe_send(callback.message, text="❌ Anime topilmadi.")
        return

    raw_title = anime.get("title") or "Nomsiz anime"
    title = html.escape(str(raw_title))
    description = html.escape(str(anime.get("description") or ""))
    caption = f"🎬 <b>{title}</b> — Tizer\n\n{description}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ O'chirish", callback_data=f"tizer_delete:{anime_id}", style="danger")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"tizer_edit:{anime_id}", style="danger")]
    ])

    # Video hali ham o'sha-o'sha turibdi — faqat caption/tugmalarni qaytaramiz
    await _safe_update_message(callback.message, caption, kb)


# =======================================================
# 3️⃣ "✅ Ha" — HAQIQIY O'CHIRISH VA ANIME KARTASIGA QAYTISH (FAQAT EDIT)
# =======================================================
@router.callback_query(F.data.startswith("tizer_delete_confirm:"))
async def execute_tizer_delete_handler(callback: CallbackQuery, session: Any) -> None:
    try:
        anime_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    try:
        service = AnimeService(session=session)
        ok = await service.delete_tizer(anime_id)
    except Exception as e:
        logger.error(f"❌ Tizerni o'chirishda xato: {e}", exc_info=True)
        ok = False

    if ok:
        await safe_answer(callback, "🗑 Tizer muvaffaqiyatli o'chirildi!", show_alert=True)
    else:
        await safe_answer(callback, "❌ Tizerni o'chirishda xatolik yuz berdi.", show_alert=True)

    # 🟢 MUHIM: bu yerdan boshlab "view_anime_details"ni chaqirmaymiz — u
    # DELETE+YANGI XABAR yuboradi, bu esa video ko'rsatilgandan keyin qaytishda
    # UX'ni buzadi (video hali ham osilib qolgan holatda ko'rinishi mumkin).
    # Shuning uchun bir xil karta (build_anime_card) chaqirilib, natija shu
    # xabarning O'ZIGA edit_media orqali (video->rasm) qo'yiladi.
    try:
        service = AnimeService(session=session)
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ execute_tizer_delete: anime qayta yuklashda xato: {e}", exc_info=True)
        anime = None

    if not anime:
        await _safe_update_message(
            callback.message,
            "❌ Anime topilmadi yoki o'chirilgan.",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Ro'yxatga qaytish", callback_data="list_anime_page:1", style="danger")]
            ])
        )
        return

    caption, kb = await build_anime_card(session, anime, anime_id, page=1)
    poster_id = anime.get("poster_id")

    updated = await _safe_update_message(callback.message, caption, kb, new_photo_id=poster_id)

    if not updated:
        await safe_send(callback.message, text="⚠️ Ekranni yangilashda muammo yuz berdi. Iltimos, ro'yxatga qaytadan kiring.")