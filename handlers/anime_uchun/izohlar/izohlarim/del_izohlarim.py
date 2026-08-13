
import logging
import html
from typing import Optional

from aiogram import Router, F, types
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramNetworkError,
)
from handlers.anime_uchun.izohlar.izohlarim.edit_izohlarim import (
    safe_answer,
    safe_call,
    safe_delete
)
from handlers.anime_uchun.izoh_anime import anime_comment_handler
from services.comment_service import CommentService
from services.anime_service import AnimeService
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.fsm.state import State, StatesGroup
from config import config

logger = logging.getLogger("izohlarim_del")
router = Router()
CREATOR_ID = config.CREATOR_ID












# 1-BOSQICH: O'chirish tugmasi bosilganda tasdiqlash oynasiga o'tkazish
@router.callback_query(F.data.startswith("del_comm:"))
async def handle_delete_comment_ask(callback: CallbackQuery):
    try:
        parts = callback.data.split(":")
        comment_id = int(parts[1])
        anime_id = int(parts[2])
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    text = "⚠️ <b>Rostdan ham ushbu izohni o‘chirmoqchimisiz?</b>\n\n<i>Ushbu amalni ortga qaytarib bo‘lmaydi!</i>"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, o‘chirish", callback_data=f"del_comm_confirm:{comment_id}:{anime_id}", style="success"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"my_comm:{anime_id}:0", style="danger")
        ]
    ])

    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
    except TelegramBadRequest as e:
        # 🟢 TUZATILDI: avval "raise e" bilan xato qayta ko'tarilib, callback.answer()
        # hech qachon bajarilmasdan handler ichida "yutilmagan" xatoga aylanardi —
        # endi boshqa handlerlar kabi faqat log qilinadi, tugma "osilib qolmaydi".
        err_msg = str(e).lower()
        if "message is not modified" not in err_msg:
            logger.warning(f"handle_delete_comment_ask edit xatosi: {e}")
    except TelegramForbiddenError:
        pass
    except Exception as e:
        logger.error(f"handle_delete_comment_ask kutilmagan xatolik: {e}", exc_info=True)

    await safe_answer(callback)


@router.callback_query(F.data.startswith("del_comm_confirm:"))
async def handle_delete_comment_confirm(callback: CallbackQuery, session: AsyncSession):
    try:
        parts = callback.data.split(":")
        comment_id = int(parts[1])
        anime_id = int(parts[2])
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    user_id = callback.from_user.id
    comment_service = CommentService(session)

    # 1. Bazadan va keshdan o'chiramiz
    try:
        success = await comment_service.delete_comment(
            comment_id=comment_id,
            user_id=user_id,
            anime_id=anime_id
        )
    except Exception as err:
        logger.error(f"❌ Izohni o'chirishda xatolik: {err}", exc_info=True)
        await safe_answer(callback, "❌ Tizimda xatolik yuz berdi.", show_alert=True)
        return

    if not success:
        await safe_answer(callback, "❌ Izohni o'chirib bo'lmadi yoki u allaqachon o'chirilgan.", show_alert=True)
        return

    # 2. Alert chiqarish
    await safe_answer(callback, "🗑 Izohingiz muvaffaqiyatli o'chirildi!", show_alert=True)

    # 3. Qolgan izohlar sonini tekshirish
    try:
        total_comments = await comment_service.get_user_comments_count(anime_id, user_id)
    except Exception as e:
        logger.error(f"❌ Qolgan izohlar sonini olishda xatolik: {e}", exc_info=True)
        return

    # 4. Agar izohlar qolmagan bo'lsa -> Izohlar bosh sahifasiga qaytamiz
    if total_comments == 0:
        new_callback = callback.model_copy(update={"data": f"anime_comments:{anime_id}"})
        await safe_call(
            anime_comment_handler(new_callback, session),
            context="del_comm_confirm -> anime_comment_handler"
        )
        return

    # 5. Boshqa izohlar bo'lsa -> Keyingi/oldingi izohni ko'rsatamiz
    from handlers.anime_uchun.izohlar.izohlarim.edit_izohlarim import handle_my_comments
    
    new_callback = callback.model_copy(update={"data": f"my_comm:{anime_id}:0"})
    await safe_call(
        handle_my_comments(new_callback, session),
        context="del_comm_confirm -> handle_my_comments"
    )