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

logger = logging.getLogger("add_episode")
router = Router()


class AddEpisodeStates(StatesGroup):
    waiting_for_videos = State()  # Videolarni qabul qilish holati


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
@router.callback_query(F.data.startswith("add_episode:"))
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

    # Faqat VIP qismlarni hisobga olamiz
    all_episodes = anime.get("episodes", [])
    regular_episodes = [
        ep for ep in all_episodes 
        if not any(stream.get("is_vip") for stream in ep.get("streams", []))
    ]
    next_ep = _calc_next_episode(regular_episodes)

    if callback.message:
        await safe_delete(callback.message)

    # Har bir yangi urinishda eski debounce jarayonini tozalab boshlaymiz
    _cancel_debounce(callback.from_user.id)

    await state.set_state(AddEpisodeStates.waiting_for_videos)
    await state.update_data(anime_id=anime_id, video_list=[], next_ep=next_ep)

    anime_title = html.quote(str(anime.get("title", "Anime")))

    text = (
        f"🎬 {html.bold(anime_title)} animesiga qism qo‘shish\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📹 Iltimos, qism videolarini ketma-ketlikda tashlang.\n"
        f"ℹ️ Tizim avtomatik ravishda {html.code(f'{next_ep}-qismdan')} boshlab raqamlaydi.\n\n"
        f"⚠️ {html.italic('Bir nechta videoni belgilab birdaniga tashlashingiz ham mumkin.')}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga (Bekor qilish)", callback_data=f"v_anime:{anime_id}:1", style="danger")]
    ])

    await safe_send(callback.message, text=text, reply_markup=kb, parse_mode="HTML")


# =======================================================
# 2. VIDEO QABUL QILISH (Debounce — 1.5s kutib, guruhlab yig'ish)
# =======================================================
@router.message(AddEpisodeStates.waiting_for_videos, F.video)
async def collect_anime_videos_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lock = _get_lock(user_id)

    async with lock:
        try:
            current_data = await state.get_data()
        except Exception as e:
            logger.error(f"collect_anime_videos_handler: state o'qishda xato: {e}", exc_info=True)
            return

        video_list = current_data.get("video_list", [])
        video_list.append(message.video.file_id)

        try:
            await state.update_data(video_list=video_list)
        except Exception as e:
            logger.error(f"collect_anime_videos_handler: state yozishda xato: {e}", exc_info=True)
            return

        # Avvalgi debounce taymerini bekor qilamiz (Task FSM'da EMAS, alohida lug'atda)
        _cancel_debounce(user_id)

        loop = asyncio.get_running_loop()
        _debounce_tasks[user_id] = loop.create_task(
            wait_and_finish_collection(message, state, user_id)
        )


@router.message(AddEpisodeStates.waiting_for_videos)
async def collect_anime_videos_invalid(message: Message) -> None:
    """Video kutilayotgan holatda boshqa turdagi xabar (matn, rasm va h.k.) kelsa."""
    await safe_send(message, text="📹 Iltimos, faqat VIDEO ko'rinishida yuboring.")


async def wait_and_finish_collection(message: Message, state: FSMContext, user_id: int) -> None:
    try:
        # 1.5 soniya yangi xabarlar kelishini kutamiz (debounce)
        await asyncio.sleep(1.5)

        data = await state.get_data()
        video_list = data.get("video_list", [])
        anime_id = data.get("anime_id")
        next_ep = data.get("next_ep", 1)

        if not video_list or not anime_id:
            return

        total_added = len(video_list)
        end_ep = next_ep + total_added - 1

        summary_text = (
            f"📦 {html.bold('Videolar muvaffaqiyatli qabul qilindi!')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📥 Jami yuklangan fayllar: {html.bold(str(total_added))} ta\n"
            f"🔢 Qismlar oralig‘i: {html.code(f'{next_ep}-qismdan')} -> {html.code(f'{end_ep}-qismgacha')}\n\n"
            f"✨ Endi quyidagi amallardan birini tanlang:"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="💾 Faqat bazaga saqlash", callback_data=f"save_episodes_db:{anime_id}", style="primary"),
                InlineKeyboardButton(text="📢 Kanalga e‘lon qilish", callback_data=f"publish_episodes_chan:{anime_id}", style="primary")
            ],
            [
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"v_anime:{anime_id}:1", style="danger")
            ]
        ])

        await safe_send(message, text=summary_text, reply_markup=kb, parse_mode="HTML")

    except asyncio.CancelledError:
        # Taymer bekor qilindi (1.5 soniya ichida yangi video kelgani uchun) — normal holat
        pass
    except Exception as e:
        logger.error(f"wait_and_finish_collection kutilmagan xato: {e}", exc_info=True)
    finally:
        _debounce_tasks.pop(user_id, None)


# =======================================================
# 3. ✅ BAZAGA SAQLASH (har bir video alohida, bittasi xato bersa ham davom etadi)
# =======================================================
@router.callback_query(F.data.startswith("save_episodes_db:"), AddEpisodeStates.waiting_for_videos)
async def save_episodes_to_database(callback: CallbackQuery, state: FSMContext, session: Any):
    await safe_answer(callback, "Saqlash boshlandi...")

    data = await state.get_data()
    video_list = data.get("video_list", [])
    anime_id = data.get("anime_id")
    next_ep = data.get("next_ep", 1)

    if not video_list or not anime_id:
        await safe_send(callback.message, text="❌ Saqlash uchun videolar topilmadi. Jarayon bekor qilindi.")
        await state.clear()
        _cancel_debounce(callback.from_user.id)
        return


    await state.clear()
    _cancel_debounce(callback.from_user.id)

    if hasattr(session, "_ensure_session"):
        await session._ensure_session()

    service = AnimeService(session=session)

    success_count = 0
    failed_episodes: list[int] = []


    for index, file_id in enumerate(video_list):
        current_episode_num = next_ep + index
        try:
            ok = await service.add_episode(
                anime_id=anime_id,
                episode_num=current_episode_num,
                file_id=file_id,
                dub_group="default", # 👈 Agar alohida dublyaj guruhi bo'lsa nomini yozing
                is_vip=False
            )
            if ok:
                success_count += 1
            else:
                failed_episodes.append(current_episode_num)
        except Exception as e:
            logger.error(
                f"❌ VIP Epizod saqlashda xatolik: anime_id={anime_id}, episode={current_episode_num}: {e}",
                exc_info=True
            )
            failed_episodes.append(current_episode_num)


    if callback.message:
        await safe_delete(callback.message)

    if failed_episodes:
        failed_str = ", ".join(str(n) for n in failed_episodes)
        final_text = (
            f"⚠️ {html.bold('Qisman saqlandi')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ Muvaffaqiyatli saqlandi: {html.bold(str(success_count))} ta\n"
            f"❌ Xato berdi: {html.bold(str(len(failed_episodes)))} ta (qism: {html.code(failed_str)})\n\n"
            f"Xato bergan qismlarni qayta yuklab ko'ring."
        )
    else:
        final_text = (
            f"✅ {html.bold('Muvaffaqiyatli saqlandi!')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Bazaga jami {html.bold(str(success_count))} ta yangi qism qo‘shildi."
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⬅️ Anime kartasi", callback_data=f"v_anime:{anime_id}:1")
        ]
    ])

    await safe_send(callback.message, text=final_text, reply_markup=kb, parse_mode="HTML")