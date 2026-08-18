import logging
from typing import Any, Optional
from aiogram import Router, F, html
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError

from services.anime_service import AnimeService
from handlers.admin_panel.admin_anime.list_anime1 import get_episode_list_markup

router = Router()
logger = logging.getLogger(__name__)


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


async def _safe_update_message(
    message: Any,
    caption: str,
    reply_markup: InlineKeyboardMarkup,
    poster_id: Optional[str] = None
) -> bool:
 
    if poster_id:
        # Xabar media (rasm) bo'lishi kutilmoqda — avval edit_media, keyin edit_caption
        try:
            new_media = InputMediaPhoto(media=poster_id, caption=caption, parse_mode="HTML")
            await message.edit_media(media=new_media, reply_markup=reply_markup)
            return True
        except TelegramForbiddenError:
            return False
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return True
            logger.warning(f"edit_media muvaffaqiyatsiz bo'ldi, edit_caption sinaladi: {e}")
        except Exception as e:
            logger.error(f"edit_media kutilmagan xato: {e}", exc_info=True)

        try:
            await message.edit_caption(caption=caption, reply_markup=reply_markup, parse_mode="HTML")
            return True
        except TelegramForbiddenError:
            return False
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return True
            logger.warning(f"edit_caption ham muvaffaqiyatsiz bo'ldi: {e}")
        except Exception as e:
            logger.error(f"edit_caption kutilmagan xato: {e}", exc_info=True)
    else:
        # Xabar matn ko'rinishida bo'lishi kutilmoqda — avval edit_text, keyin edit_caption
        try:
            await message.edit_text(text=caption, reply_markup=reply_markup, parse_mode="HTML")
            return True
        except TelegramForbiddenError:
            return False
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return True
            logger.warning(f"edit_text muvaffaqiyatsiz bo'ldi, edit_caption sinaladi: {e}")
        except Exception as e:
            logger.error(f"edit_text kutilmagan xato: {e}", exc_info=True)

        try:
            await message.edit_caption(caption=caption, reply_markup=reply_markup, parse_mode="HTML")
            return True
        except TelegramForbiddenError:
            return False
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return True
            logger.warning(f"edit_caption ham muvaffaqiyatsiz bo'ldi: {e}")
        except Exception as e:
            logger.error(f"edit_caption kutilmagan xato: {e}", exc_info=True)

    try:
        await message.delete()
    except Exception:
        pass
    try:
        await message.answer(text=caption, reply_markup=reply_markup, parse_mode="HTML")
        return True
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError) as e:
        logger.warning(f"Yangi xabar yuborib bo'lmadi: {e}")
    except Exception as e:
        logger.error(f"Yangi xabar yuborishda kutilmagan xato: {e}", exc_info=True)
    return False


@router.callback_query(F.data.startswith("burn_ep:"))
async def confirm_delete_episode_handler(callback: CallbackQuery, session: Any):
    await safe_answer(callback)

    try:
        parts = callback.data.split(":")
        anime_id = int(parts[1])
        ep_num = int(parts[2])
        back_page = int(parts[3])
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    # 🟢 TUZATILDI: avval bu chaqiruv try/except'siz edi — DB/kesh xatosi
    # chiqsa handler yalang'och exception bilan yiqilardi.
    try:
        service = AnimeService(session=session)
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ confirm_delete_episode_handler: anime olishda xato: {e}", exc_info=True)
        await safe_answer(callback, "❌ Anime ma'lumotlarini yuklashda xatolik yuz berdi.", show_alert=True)
        return

    if not anime:
        await safe_answer(callback, "❌ Anime topilmadi!", show_alert=True)
        return

    title = html.quote(str(anime.get("title") or "Nomsiz anime"))
    poster_id = anime.get("poster_id")

    caption = (
        f"⚠️ {html.bold('DIQQAT! QISMNI O‘CHIRISH')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎬 Anime: <b>{title}</b>\n"
        f"🔢 O‘chirilayotgan qism: {html.bold(f'{ep_num}-qism')}\n\n"
        f"🛑 {html.italic('Ushbu amalni ortga qaytarib bo‘lmaydi! Ushbu qism ma’lumotlar bazasidan hamda kesh xotirasidan butunlay o‘chib ketadi.')}\n\n"
        f"Haqiqatdan ham ushbu qismni o‘chirmoqchimisiz?"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, o‘chirilsin", callback_data=f"real_burn_ep:{anime_id}:{ep_num}:{back_page}"),
            InlineKeyboardButton(text="❌ Yo‘q, bekor qilish", callback_data=f"show_ep:{anime_id}:{ep_num}:{back_page}")
        ]
    ])

    await _safe_update_message(callback.message, caption, kb, poster_id)


@router.callback_query(F.data.startswith("real_burn_ep:"))
async def execute_delete_episode_handler(callback: CallbackQuery, session: Any):
    try:
        parts = callback.data.split(":")
        anime_id = int(parts[1])
        ep_num = int(parts[2])
        back_page = int(parts[3])
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    service = AnimeService(session=session)

    try:
        ok = await service.delete_episode(anime_id=anime_id, episode_num=ep_num)
    except Exception as e:
        logger.error(f"❌ Epizod o'chirish handlerida xato: {e}", exc_info=True)
        ok = False

    if ok:
        await safe_answer(callback, f"🗑 {ep_num}-qism muvaffaqiyatli o‘chirildi!", show_alert=True)
    else:
        await safe_answer(callback, "❌ Xatolik: Qism allaqachon o‘chirilgan bo‘lishi mumkin!", show_alert=True)

    try:
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ real_burn_ep: anime qayta yuklashda xato: {e}", exc_info=True)
        anime = None

    episodes = anime.get("episodes", []) if anime else []
    raw_title = anime.get("title", "Nomsiz anime") if anime else "Nomsiz anime"
    title = html.quote(str(raw_title))

    caption = (
        f"╔══════════════════╗\n"
        f"  🎬 <b>{title}</b>\n"
        f"╚══════════════════╝\n\n"
        f"📹 Ro‘yxatdan kerakli qismni tanlang.\n"
        f"💡 {html.italic('Tanlangan qism videosi va uni boshqarish tugmalari shu yerning o‘zida ochiladi.')}"
    )

    try:
        markup = await get_episode_list_markup(anime_id=anime_id, episodes=episodes, page=back_page)
    except Exception as e:
        logger.error(f"❌ get_episode_list_markup xatosi: {e}", exc_info=True)
        # Ro'yxat yasalmasa ham, admin hech bo'lmasa qayta urinish tugmasini ko'radi
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Qayta urinish", callback_data=f"show_ep:{anime_id}:{ep_num}:{back_page}")]
        ])

    poster_id = anime.get("poster_id") if anime else None
    updated = await _safe_update_message(callback.message, caption, markup, poster_id)

    if not updated:
        # 🟢 YANGI: hech qanday usul ishlamadi — admin butunlay xabarsiz
        # qolmasligi uchun so'nggi, eng oddiy urinish.
        try:
            await callback.message.answer(
                "⚠️ Ro'yxatni yangilashda muammo yuz berdi. Iltimos, ro'yxatga qaytadan kiring."
            )
        except Exception as e:
            logger.error(f"❌ Oxirgi fallback xabar ham yuborilmadi: {e}", exc_info=True)