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

logger = logging.getLogger("filler_episode")
router = Router()

class BulkFillerStates(StatesGroup):
    waiting_for_range = State()


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
# 1. BITTALIK EPIZOD FILLER STATUSINI ALMASHTIRISH (TOGGLE)
# =========================================================
@router.callback_query(F.data.startswith("toggle_filler:"))
async def toggle_episode_filler_handler(callback: CallbackQuery, session: Any):
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
        logger.error(f"toggle_filler: anime olishda xato: {e}", exc_info=True)
        await safe_answer(callback, "❌ Tizimda xatolik yuz berdi.", show_alert=True)
        return

    if not anime:
        await safe_answer(callback, "❌ Anime topilmadi!", show_alert=True)
        return

    episodes = anime.get("episodes", [])
    target_ep = next((ep for ep in episodes if ep.get("episode") == ep_num), None)
    
    if not target_ep:
        await safe_answer(callback, "❌ Qism topilmadi!", show_alert=True)
        return

    # Hozirgi holatni teskarisiga o'zgartiramiz
    new_status = not target_ep.get("is_filler", False)
    
    try:
        # DB'da yangilash
        await service.set_episode_filler(anime_id, ep_num, is_filler=new_status)
    except Exception as e:
        logger.error(f"toggle_filler: saqlashda xato: {e}", exc_info=True)
        await safe_answer(callback, "❌ Saqlashda xatolik yuz berdi!", show_alert=True)
        return
    
    status_label = "Filler" if new_status else "Canon"
    await safe_answer(callback, f"✅ {ep_num}-qism holati '{status_label}' ga o'zgartirildi!")

    # Ekran ma'lumotlarini va tugmalarni yangilash uchun ko'rsatish handlerini xavfsiz chaqiramiz
    try:
        from handlers.admin_panel.admin_anime.episode.main_episode import show_specific_episode_handler
        
        # ✅ Pydantic v2 xavfsiz nusxalash (frozen ob'ektni o'zgartirish o'rniga yangi nusxa yaratamiz)
        updated_callback = callback.model_copy(
            update={"data": f"show_ep:{anime_id}:{ep_num}:{back_page_str}"}
        )
        await show_specific_episode_handler(updated_callback, session)

    except ImportError:
        logger.error("show_specific_episode_handler import qilib bo'lmadi.")
    except Exception as e:
        logger.error(f"UI yangilashda xato: {e}", exc_info=True)

# =========================================================
# 2. KO'P EPIZODLARNI BIR VAQTDA FILLER QILISH (RANGE FILLER)
# =========================================================
@router.callback_query(F.data.startswith("start_bulk_filler:"))
async def start_bulk_filler_handler(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)

    try:
        parts = callback.data.split(":")
        anime_id = int(parts[1])
        back_page = int(parts[2]) if len(parts) > 2 else 1
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov formati!", show_alert=True)
        return

    # Oldingi statelarni tozalaymiz
    await state.clear()
    await state.update_data(bulk_anime_id=anime_id, back_page=back_page)
    await state.set_state(BulkFillerStates.waiting_for_range)

    text = (
        f"✏️ {html.bold('Filler epizodlar oralig‘ini kiriting.')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Masalan: {html.code('10-25')} (10 dan 25-qismgacha barchasi filler bo'ladi).\n"
        f"Bekor qilish uchun tugmani bosing yoki {html.code('/cancel')} deb yozing."
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"v_anime:{anime_id}:{back_page}", style="danger")]
    ])

    if callback.message:
        await safe_delete(callback.message)
        await safe_send(callback.message, text=text, reply_markup=kb, parse_mode="HTML")


@router.message(BulkFillerStates.waiting_for_range)
async def process_bulk_filler_range(message: Message, state: FSMContext, session: Any):
    try:
        data = await state.get_data()
    except Exception as e:
        logger.error(f"State o'qishda xatolik: {e}", exc_info=True)
        return

    anime_id = data.get("bulk_anime_id")
    back_page = data.get("back_page", 1)
    text = message.text.strip() if message.text else ""

    # Bekor qilish buyrug'i tekshiruvi
    if text.lower() == "/cancel":
        await state.clear()
        await safe_send(message, text="Jarayon bekor qilindi.")
        return

    if not anime_id or "-" not in text:
        await safe_send(message, text=f"❌ Noto'g'ri format! Iltimos, {html.code('10-25')} shaklida kiriting:", parse_mode="HTML")
        return

    try:
        start_ep, end_ep = map(int, text.split("-"))
        if start_ep > end_ep:
            start_ep, end_ep = end_ep, start_ep
    except ValueError:
        await safe_send(message, text=f"❌ Faqat raqamlardan foydalaning (Masalan: {html.code('10-25')}):", parse_mode="HTML")
        return

    # Jarayon boshlanganini bildirish
    processing_msg = await safe_send(message, text="⏳ Barcha qismlar yangilanmoqda, kuting...")
    await state.clear()

    if hasattr(session, "_ensure_session"):
        await session._ensure_session()

    service = AnimeService(session=session)
    success_count = 0
    failed_episodes = []

    # Tsikl orqali xavfsiz yangilash
    for ep_num in range(start_ep, end_ep + 1):
        try:
            ok = await service.set_episode_filler(anime_id, ep_num, is_filler=True)
            if ok:
                success_count += 1
            else:
                failed_episodes.append(ep_num)
        except Exception as e:
            logger.error(f"❌ Ommaviy filler qilishda xato (Ep {ep_num}): {e}", exc_info=True)
            failed_episodes.append(ep_num)

    if processing_msg:
        await safe_delete(processing_msg)

    # Natijani xulosa qilib chiqarish
    if failed_episodes:
        failed_str = ", ".join(str(n) for n in failed_episodes[:10]) # Faqat 10 tasini ko'rsatamiz
        more_str = "..." if len(failed_episodes) > 10 else ""
        final_text = (
            f"⚠️ {html.bold('Qisman saqlandi')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ Filler qilindi: {html.bold(str(success_count))} ta\n"
            f"❌ Xato berdi: {html.bold(str(len(failed_episodes)))} ta ({html.code(failed_str + more_str)})"
        )
    else:
        final_text = (
            f"✅ {html.bold('Muvaffaqiyatli saqlandi!')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Jami {html.bold(str(success_count))} ta epizod ({start_ep}-{end_ep}) filler deb belgilandi."
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Anime kartasi", callback_data=f"v_anime:{anime_id}:{back_page}")]
    ])

    await safe_send(message, text=final_text, reply_markup=kb, parse_mode="HTML")


# =========================================================
# 3. ANIME FILLER EPIZODLARI RO'YXATINI KO'RISH
# =========================================================
@router.callback_query(F.data.startswith("list_fillers:"))
async def list_anime_fillers_handler(callback: CallbackQuery, session: Any):
    try:
        parts = callback.data.split(":")
        anime_id = int(parts[1])
        back_page = int(parts[2]) if len(parts) > 2 else 1
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    try:
        service = AnimeService(session=session)
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"list_fillers: anime olishda xato: {e}", exc_info=True)
        await safe_answer(callback, "❌ Tizim xatosi!", show_alert=True)
        return

    if not anime:
        await safe_answer(callback, "❌ Anime topilmadi!", show_alert=True)
        return

    episodes = anime.get("episodes", [])
    filler_eps = [ep.get("episode") for ep in episodes if ep.get("is_filler")]

    if not filler_eps:
        await safe_answer(callback, "ℹ️ Ushbu animeda filler epizodlar mavjud emas.", show_alert=True)
        return

    # Ro'yxatni chiroyli chiqarish
    filler_eps_str = ", ".join(map(str, sorted(filler_eps)))
    title = html.quote(str(anime.get("title", "Nomsiz anime")))

    text = (
        f"🎬 {html.bold(title)}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌀 {html.bold('Filler epizodlar ro‘yxati:')}\n\n"
        f"{html.code(filler_eps_str)}\n\n"
        f"Jami fillerlar: {html.bold(f'{len(filler_eps)} ta')}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"v_anime:{anime_id}:{back_page}", style="primary")]
    ])

    if callback.message:
        await safe_delete(callback.message)
        await safe_send(callback.message, text=text, reply_markup=kb, parse_mode="HTML")
    
    await safe_answer(callback)