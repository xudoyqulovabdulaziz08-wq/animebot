import logging
from typing import Any, Optional

from aiogram import Router, F, html
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramNetworkError,
)

from services.anime_service import AnimeService

logger = logging.getLogger("filler_vip_episode")
router = Router()

class BulkVIPFillerStates(StatesGroup):
    waiting_for_range = State()


# =======================================================
# 🧰 YORDAMCHI FUNKSIYALAR
# =======================================================
async def safe_answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False) -> None:
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


# =========================================================
# 1. BITTALIK VIP EPIZOD FILLER STATUSINI ALMASHTIRISH
# =========================================================
@router.callback_query(F.data.startswith("toggle_vip_filler:"))
async def toggle_vip_episode_filler_handler(callback: CallbackQuery, session: Any):
    try:
        _, anime_id_str, ep_num_str, back_page_str = callback.data.split(":")
        anime_id = int(anime_id_str)
        ep_num = int(ep_num_str)
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov formati!", show_alert=True)
        return

    try:
        service = AnimeService(session=session)
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"toggle_vip_filler: anime olishda xato: {e}", exc_info=True)
        await safe_answer(callback, "❌ Tizimda xatolik yuz berdi.", show_alert=True)
        return

    if not anime:
        await safe_answer(callback, "❌ Anime topilmadi!", show_alert=True)
        return

    episodes = anime.get("episodes", [])
    target_ep = next((ep for ep in episodes if ep.get("episode") == ep_num), None)
    
    if not target_ep:
        await safe_answer(callback, "❌ VIP Qism topilmadi!", show_alert=True)
        return

    # 🔥 Epizodda haqiqatan ham VIP stream borligini tekshiramiz
    has_vip = any(stream.get("is_vip") for stream in target_ep.get("streams", []))
    if not has_vip:
        await safe_answer(callback, "❌ Ushbu qismda VIP video mavjud emas!", show_alert=True)
        return

    # Hozirgi filler holatini teskarisiga o'zgartiramiz
    new_status = not target_ep.get("is_filler", False)
    
    try:
        # Bazada yangilash
        await service.set_episode_filler(anime_id, ep_num, is_filler=new_status)
    except Exception as e:
        logger.error(f"toggle_vip_filler: saqlashda xato: {e}", exc_info=True)
        await safe_answer(callback, "❌ Saqlashda xatolik yuz berdi!", show_alert=True)
        return
    
    status_label = "Filler 🌀" if new_status else "Canon ✅"
    await safe_answer(callback, f"✅ {ep_num}-VIP qism holati '{status_label}' ga o'zgartirildi!")

    # UI tugmalarini va xabarni yangilash
    try:
        from handlers.admin_panel.admin_anime.episode.main_vip_episode import show_specific_vip_episode_handler
        
        updated_callback = callback.model_copy(
            update={"data": f"show_vip_ep:{anime_id}:{ep_num}:{back_page_str}"}
        )
        await show_specific_vip_episode_handler(updated_callback, session)

    except ImportError:
        logger.error("show_specific_vip_episode_handler import qilib bo'lmadi.")
    except Exception as e:
        logger.error(f"VIP UI yangilashda xato: {e}", exc_info=True)