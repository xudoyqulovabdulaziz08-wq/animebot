import logging
import asyncio
from typing import Any, Dict, Optional

from aiogram import Router, F, html
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramNetworkError,
)

from services.anime_service import AnimeService

logger = logging.getLogger("add_vip_episode")
router = Router()

class AddEpisodeStates(StatesGroup):
    waiting_for_vip_videos = State()




# =======================================================
# 🧰 YORDAMCHI FUNKSIYALAR (Telegramning turli xatolaridan himoya)
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


async def safe_send(message: Message, **kwargs) -> Optional[Message]:
    """message.answer()ni xavfsiz chaqiradi — bloklangan admin yoki tarmoq xatosida crash bermaydi."""
    try:
        return await message.answer(**kwargs)
    except TelegramRetryAfter as e:
        logger.warning(f"Flood control: retry_after={e.retry_after}")
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError) as e:
        logger.warning(f"Xabar yuborishda xato: {e}")
    except Exception as e:
        logger.error(f"Xabar yuborishda kutilmagan xato: {e}", exc_info=True)
    return None


def _calc_next_episode(episodes: list) -> int:
    """
    🟢 TUZATILDI: avval len(episodes)+1 edi — agar biror epizod o'chirilgan bo'lsa
    (masalan 10 tadan 5-chisi), bu hisoblash noto'g'ri raqamga to'g'ri kelib,
    MAVJUD epizodni ustidan yozib yuborishi mumkin edi. Endi eng katta mavjud
    epizod raqamidan +1 qilib hisoblanadi — bu har doim xavfsiz keyingi raqam.
    """
    if not episodes:
        return 1
    max_ep = max((ep.get("episode", 0) for ep in episodes), default=0)
    return max_ep + 1



_video_locks: Dict[int, asyncio.Lock] = {}
_debounce_tasks: Dict[int, asyncio.Task] = {}


def _get_lock(user_id: int) -> asyncio.Lock:
    lock = _video_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _video_locks[user_id] = lock
    return lock


def _cancel_debounce(user_id: int) -> None:
    task = _debounce_tasks.pop(user_id, None)
    if task and not task.done():
        task.cancel()


# =======================================================
# 1. "QISM QO'SHISH" TUGMASI BOSILGANDA
# =======================================================
@router.callback_query(F.data.startswith("add_vip_episode:"))
async def start_add_episode(callback: CallbackQuery, state: FSMContext, session: Any):
    await safe_answer(callback)

    try:
        anime_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    try:
        service = AnimeService(session=session)
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"start_add_episode: anime olishda xato: {e}", exc_info=True)
        await safe_answer(callback, "❌ Tizimda xatolik yuz berdi.", show_alert=True)
        return

    if not anime:
        await safe_answer(callback, "❌ Anime topilmadi!", show_alert=True)
        return

    episodes = anime.get("episodes", [])
    next_ep = _calc_next_episode(episodes)

    if callback.message:
        await safe_delete(callback.message)

    # Har bir yangi urinishda eski debounce jarayonini tozalab boshlaymiz
    _cancel_debounce(callback.from_user.id)

    await state.set_state(AddEpisodeStates.waiting_for_vip_videos)
    await state.update_data(anime_id=anime_id, video_list=[], next_ep=next_ep)

    anime_title = html.quote(str(anime.get("title", "Anime")))

    text = (
        f"🎬 {html.bold(anime_title)} animesiga vip qism qo‘shish\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📹 Iltimos, qism videolarini ketma-ketlikda tashlang.\n"
        f"ℹ️ Tizim avtomatik ravishda {html.code(f'{next_ep}-qismdan')} boshlab raqamlaydi.\n\n"
        f"⚠️ {html.italic('Bir nechta videoni belgilab birdaniga tashlashingiz ham mumkin.')}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga (Bekor qilish)", callback_data=f"view_vip_episodes_list:{anime_id}:1", style="danger")]
    ])

    await safe_send(callback.message, text=text, reply_markup=kb, parse_mode="HTML")

