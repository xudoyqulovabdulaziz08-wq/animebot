import logging
from typing import Any, Optional
from aiogram import Router, F, html
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError

from services.anime_service import AnimeService
# ✅ Import qismi VIP menu ro'yxatini yasaydigan funksiyaga o'zgartirildi
from handlers.admin_panel.admin_anime.episode.main_vip_episode import get_vip_episode_list_markup

router = Router()
logger = logging.getLogger("burn_vip_episode")


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


# ✅ Callback so'rovi 'burn_vip_ep:' ga o'zgartirildi
@router.callback_query(F.data.startswith("burn_vip_ep:"))
async def confirm_delete_vip_episode_handler(callback: CallbackQuery, session: Any):
    await safe_answer(callback)

    try:
        parts = callback.data.split(":")
        anime_id = int(parts[1])
        ep_num = int(parts[2])
        back_page = int(parts[3])
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    try:
        service = AnimeService(session=session)
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ confirm_delete_vip_episode_handler: anime olishda xato: {e}", exc_info=True)
        await safe_answer(callback, "❌ Anime ma'lumotlarini yuklashda xatolik yuz berdi.", show_alert=True)
        return

    if not anime:
        await safe_answer(callback, "❌ Anime topilmadi!", show_alert=True)
        return

    title = html.quote(str(anime.get("title") or "Nomsiz anime"))
    poster_id = anime.get("poster_id")

    # ✅ Matnlar VIP ga moslandi
    caption = (
        f"⚠️ {html.bold('DIQQAT! VIP QISMNI O‘CHIRISH')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎬 Anime: <b>{title}</b>\n"
        f"🔢 O‘chirilayotgan qism: {html.bold(f'{ep_num}-VIP qism')}\n\n"
        f"🛑 {html.italic('Ushbu amalni ortga qaytarib bo‘lmaydi! Ushbu VIP qism ma’lumotlar bazasidan hamda kesh xotirasidan butunlay o‘chib ketadi.')}\n\n"
        f"Haqiqatdan ham ushbu VIP qismni o‘chirmoqchimisiz?"
    )

    # ✅ Tugmalar callbacklari real_burn_vip_ep va show_vip_ep ga o'tkazildi
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ O‘chirilsin", callback_data=f"real_burn_vip_ep:{anime_id}:{ep_num}:{back_page}", style="primary"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"show_vip_ep:{anime_id}:{ep_num}:{back_page}", style="danger")
        ]
    ])

    await _safe_update_message(callback.message, caption, kb, poster_id)


# ✅ Bajarish callback'i 'real_burn_vip_ep:' ga o'tkazildi
@router.callback_query(F.data.startswith("real_burn_vip_ep:"))
async def execute_delete_vip_episode_handler(callback: CallbackQuery, session: Any):
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
        # ✅ is_vip=True parametri bilan faqat VIP videoni o'chirishni ta'minlaymiz
        ok = await service.delete_episode(anime_id=anime_id, episode_num=ep_num, is_vip=True)
    except Exception as e:
        logger.error(f"❌ VIP Epizod o'chirish handlerida xato: {e}", exc_info=True)
        ok = False

    if ok:
        await safe_answer(callback, f"🗑 {ep_num}-VIP qism muvaffaqiyatli o‘chirildi!", show_alert=True)
    else:
        await safe_answer(callback, "❌ Xatolik: VIP qism allaqachon o‘chirilgan bo‘lishi mumkin!", show_alert=True)

    try:
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ real_burn_vip_ep: anime qayta yuklashda xato: {e}", exc_info=True)
        anime = None

    episodes = anime.get("episodes", []) if anime else []
    raw_title = anime.get("title", "Nomsiz anime") if anime else "Nomsiz anime"
    title = html.quote(str(raw_title))

    caption = (
        f"╔══════════════════╗\n"
        f"  🎬 <b>{title}</b>\n"
        f"╚══════════════════╝\n\n"
        f"📹 Ro‘yxatdan kerakli VIP qismni tanlang.\n"
        f"💡 {html.italic('Tanlangan qism videosi va uni boshqarish tugmalari shu yerning o‘zida ochiladi.')}"
    )

    try:
        # ✅ VIP ro'yxat yasovchi funksiya ishlatildi
        markup = await get_vip_episode_list_markup(anime_id=anime_id, episodes=episodes, page=back_page)
    except Exception as e:
        logger.error(f"❌ get_vip_episode_list_markup xatosi: {e}", exc_info=True)
        # Fallback tugmasi VIP ga moslandi
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Qayta urinish", callback_data=f"show_vip_ep:{anime_id}:{ep_num}:{back_page}")]
        ])

    poster_id = anime.get("poster_id") if anime else None
    updated = await _safe_update_message(callback.message, caption, markup, poster_id)

    if not updated:
        try:
            await callback.message.answer(
                "⚠️ VIP Ro'yxatni yangilashda muammo yuz berdi. Iltimos, ro'yxatga qaytadan kiring."
            )
        except Exception as e:
            logger.error(f"❌ Oxirgi fallback xabar ham yuborilmadi: {e}", exc_info=True)