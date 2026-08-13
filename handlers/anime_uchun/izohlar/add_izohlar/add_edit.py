import logging
import html
from aiogram.fsm.context import FSMContext

from aiogram.types import (
    CallbackQuery, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton
)
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
)
from handlers.anime_uchun.izohlar.add_izohlar.add_izoh import(
    safe_answer,
    safe_delete,
    safe_call,
    CommentStates
)
from services.anime_service import AnimeService
from handlers.anime_uchun.izoh_anime import anime_comment_handler
from aiogram import Router, F



logger = logging.getLogger("edit_izholarim")
router = Router()



# =======================================================
# 4. ✏️ TAHRIRLASH TUGMASI (Qaytadan kiritish holatiga o'tkazish)
# =======================================================
@router.callback_query(F.data.startswith("edit_comment_input:"))
async def edit_comment_input_handler(callback: CallbackQuery, state: FSMContext, session):
    await safe_answer(callback)

    try:
        anime_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        return

    # Eskisini o'chiramiz
    if callback.message:
        await safe_delete(callback.message)

    try:
        anime_service = AnimeService(session=session)
        anime = await anime_service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"edit_comment_input_handler: anime olishda xato: {e}", exc_info=True)
        anime = None

    if not anime:
        await state.clear()
        return

    anime_title = anime.get("title", "Anime") if isinstance(anime, dict) else getattr(anime, "title", "Anime")

    text = (
        f"💬 <b>Izoh yozish</b>\n\n"
        f"🎬 <b>{html.escape(str(anime_title))}</b>\n\n"
        f"✍️ Fikringizni yuboring..."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Orqaga",
                    callback_data=f"cancel_comment_input:{anime_id}"
                )
            ]
        ]
    )

    try:
        prompt_msg = await callback.message.answer(text=text, reply_markup=keyboard, parse_mode="HTML")
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        logger.warning(f"edit_comment_input_handler: prompt yuborilmadi: {e}")
        await state.clear()
        return

    await state.set_state(CommentStates.waiting_for_comment)
    await state.update_data(
        anime_id=anime_id,
        anime_title=anime_title,
        prompt_message_id=prompt_msg.message_id
    )




# =======================================================
# 5. ❌ BEKOR QILISH / ORQAGA TUGMASI (FSM tozalash va ortga)
# =======================================================
@router.callback_query(F.data.startswith("cancel_comment_input:"))
async def cancel_comment_input_handler(callback: CallbackQuery, state: FSMContext, session):
    # 1. Callback answer beramiz (xavfsiz)
    await safe_answer(callback, "Jarayon bekor qilindi.")

    try:
        # FSM ma'lumotlarini olamiz
        data = await state.get_data()
        prompt_message_id = data.get("prompt_message_id")

        # 2. State'ni zudlik bilan tozalaymiz
        await state.clear()

        # 3. Agar alohida preview xabari (Text Message) bo'lsa va bu callback shunga tegishli bo'lsa:
        # Eski prompt xabarini xavfsiz o'chirishga urinib ko'ramiz
        if prompt_message_id and callback.message and prompt_message_id != callback.message.message_id:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=prompt_message_id
                )
            except (TelegramBadRequest, TelegramForbiddenError):
                pass

        # 4. Izohlar bo'limiga xavfsiz qaytamiz
        #    (anime_comment_handler ichida yana callback.answer() chaqirilishi mumkin)
        await safe_call(
            anime_comment_handler(callback, session),
            context="cancel_comment_input -> anime_comment_handler"
        )

    except Exception as e:
        logger.error(f"Cancel comment input handler error: {e}", exc_info=True)
        await state.clear()