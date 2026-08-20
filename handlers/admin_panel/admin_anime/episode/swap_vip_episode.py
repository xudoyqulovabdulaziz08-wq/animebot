import logging
from typing import Any, Optional
from aiogram import Router, F, html
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError

from services.anime_service import AnimeService
from handlers.admin_panel.admin_anime.episode.main_vip_episode import show_specific_vip_episode_handler

router = Router()
logger = logging.getLogger("swap_vip_episode")


class SwapVIPEpisodeStates(StatesGroup):
    waiting_for_new_video = State()


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


@router.callback_query(F.data.startswith("swap_vip_ep:"))
async def start_swap_vip_episode_handler(callback: CallbackQuery, state: FSMContext, session: Any):
    await safe_answer(callback)
    
    try:
        parts = callback.data.split(":")
        anime_id = int(parts[1])
        ep_num = int(parts[2])
        back_page = int(parts[3])
        dub_group = parts[4] if len(parts) > 4 else "default"
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    try:
        service = AnimeService(session=session)
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"start_swap_vip_episode_handler anime yuklashda xato: {e}", exc_info=True)
        await safe_answer(callback, "❌ Anime ma'lumotlarini yuklashda xatolik.", show_alert=True)
        return
    
    if not anime:
        await safe_answer(callback, "❌ Anime topilmadi!", show_alert=True)
        return

    await state.set_state(SwapVIPEpisodeStates.waiting_for_new_video)
    await state.update_data(
        anime_id=anime_id, 
        ep_num=ep_num, 
        back_page=back_page, 
        dub_group=dub_group
    )

    poster_id = anime.get("poster_id")
    raw_title = anime.get("title", "Nomsiz anime")
    title = html.quote(str(raw_title))

    caption = (
        f"🔄 <b>{title} — {ep_num}-VIP qismni almashtirish</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📹 Iltimos, ushbu VIP qism uchun **yangi videoni** yuboring (tashlang).\n\n"
        f"📥 {html.italic('Yangi video qabul qilingandan so‘ng, tizim sizdan yakuniy ruxsatni so‘raydi.')}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"show_vip_ep:{anime_id}:{ep_num}:{back_page}")]
    ])

    await _safe_update_message(callback.message, caption, kb, poster_id)


@router.message(SwapVIPEpisodeStates.waiting_for_new_video, F.video)
async def receive_new_vip_swap_video_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    anime_id = data.get("anime_id")
    ep_num = data.get("ep_num")
    
    if not anime_id or not ep_num:
        await state.clear()
        try:
            await message.answer("❌ Xatolik: Jarayon ma'lumotlari yo'qolgan. Iltimos, amalni boshidan boshlang.")
        except Exception:
            pass
        return
    
    new_file_id = message.video.file_id
    await state.update_data(new_file_id=new_file_id)

    caption = (
        f"⚠️ <b>VIP ALMASHTIRISHNI TASDIQLASH</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔢 Qism raqami: <b>{ep_num}-VIP qism</b>\n"
        f"📹 Yangi video fayli muvaffaqiyatli qabul qilindi.\n\n"
        f"🛑 {html.bold('DIQQAT!')} {html.italic('Ushbu VIP qismning eski videosi butunlay o‘chib ketadi va yangisiga almashadi. Ushbu amalni ortga qaytarib bo‘lmaydi.')}\n\n"
        f"Haqiqatdan ham ushbu VIP qism videosini yangilashni tasdiqlaysizmi?"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Almashtirilsin", callback_data="confirm_real_vip_swap"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_vip_swap_process")
        ]
    ])

    try:
        await message.answer(text=caption, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Yangi VIP videoni tasdiqlash xabari yuborilmadi: {e}", exc_info=True)


@router.callback_query(F.data == "cancel_vip_swap_process", SwapVIPEpisodeStates.waiting_for_new_video)
async def cancel_vip_swap_handler(callback: CallbackQuery, state: FSMContext, session: Any):
    data = await state.get_data()
    await state.clear()
    
    await safe_answer(callback, "Jarayon bekor qilindi.")
    
    anime_id = data.get('anime_id')
    ep_num = data.get('ep_num')
    back_page = data.get('back_page', 1)

    if not anime_id or not ep_num:
        return

    cloned_callback = callback.model_copy(
        update={"data": f"show_vip_ep:{anime_id}:{ep_num}:{back_page}"}
    )
    await show_specific_vip_episode_handler(cloned_callback, session=session)


@router.callback_query(F.data == "confirm_real_vip_swap", SwapVIPEpisodeStates.waiting_for_new_video)
async def execute_vip_swap_handler(callback: CallbackQuery, state: FSMContext, session: Any):
    data = await state.get_data()
    anime_id = data.get("anime_id")
    ep_num = data.get("ep_num")
    back_page = data.get("back_page", 1)
    new_file_id = data.get("new_file_id")
    dub_group = data.get("dub_group", "default")

    if not anime_id or not ep_num or not new_file_id:
        await safe_answer(callback, "❌ Xatolik: Jarayon ma'lumotlari to'liq emas!", show_alert=True)
        await state.clear()
        return

    service = AnimeService(session=session)
    
    try:
        ok = await service.update_episode_file(
            anime_id=anime_id,
            episode_num=ep_num,
            new_file_id=new_file_id,
            is_vip=True,
            dub_group=dub_group
        )
    except Exception as e:
        logger.error(f"❌ VIP almashtirishda xato yuz berdi: {e}", exc_info=True)
        ok = False

    await state.clear()

    if ok:
        await safe_answer(callback, f"✅ {ep_num}-VIP qism videosi muvaffaqiyatli almashtirildi!", show_alert=True)
    else:
        await safe_answer(callback, "❌ Tizimda xatolik yuz berdi, almashtirilmadi.", show_alert=True)

    cloned_callback = callback.model_copy(
        update={"data": f"show_vip_ep:{anime_id}:{ep_num}:{back_page}"}
    )
    await show_specific_vip_episode_handler(cloned_callback, session=session)