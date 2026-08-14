import logging
import html

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from handlers.anime_uchun.izohlar.add_izohlar.add_izoh import (
    safe_answer,
    safe_delete,
    safe_call,
)
from handlers.anime_uchun.izohlar.view_izohlar.izoh_reply import handle_reply_all_comments
from services.comment_service import CommentService

logger = logging.getLogger("izohlarim_javob")
router = Router()


class ReplyStates(StatesGroup):
    waiting_for_reply = State()  # Javob matni kutilmoqda


# =======================================================
# 1. "↩️ JAVOB YOZISH" TUGMASI BOSILGANDA
# =======================================================
@router.callback_query(F.data.startswith("reply_to:"))
async def start_add_reply_handler(callback: CallbackQuery, state: FSMContext, session):
    await safe_answer(callback)

    try:
        parts = callback.data.split(":")
        comment_id = int(parts[1])
        anime_id = int(parts[2])
    except (IndexError, ValueError):
        return

    current_state = await state.get_state()
    if current_state == ReplyStates.waiting_for_reply.state:
        return

    try:
        comment_service = CommentService(session=session)
        original_comment = await comment_service.get_comment_by_id(comment_id)

        if not original_comment or original_comment.get("anime_id") != anime_id:
            await safe_answer(callback, "❌ Izoh topilmadi.", show_alert=True)
            return

        author = original_comment.get("user") or {}
        author_name = author.get("username") or author.get("full_name") or "Foydalanuvchi"
        original_text = original_comment.get("text", "")

        text = (
            f"↩️ <b>Javob yozish</b>\n\n"
            f"👤 <b>{html.escape(str(author_name))}</b>\n"
            f"<blockquote expandable>{html.escape(str(original_text))}</blockquote>\n\n"
            f"✍️ Javobingizni yuboring..."
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Bekor qilish",
                        callback_data=f"cancel_reply_input:{comment_id}:{anime_id}",
                        style="danger"
                    )
                ]
            ]
        )

        message = callback.message
        if not message:
            return

        await state.set_state(ReplyStates.waiting_for_reply)

        try:
            if message.photo or message.video or message.animation or message.document:
                prompt_msg = await message.edit_caption(caption=text, reply_markup=keyboard, parse_mode="HTML")
            else:
                prompt_msg = await message.edit_text(text=text, reply_markup=keyboard, parse_mode="HTML")
        except TelegramBadRequest as e:
            err = str(e).lower()
            if "message is not modified" in err:
                prompt_msg = message
            elif "message to edit not found" in err or "message can't be edited" in err:
                prompt_msg = await message.answer(text=text, reply_markup=keyboard, parse_mode="HTML")
            else:
                raise

        await state.update_data(
            comment_id=comment_id,
            anime_id=anime_id,
            prompt_message_id=prompt_msg.message_id
        )

    except TelegramForbiddenError:
        await state.clear()
    except TelegramBadRequest as e:
        logger.warning(f"Add reply TelegramBadRequest: {e}")
        await state.clear()
    except Exception as e:
        logger.error(f"Add reply handler error: {e}", exc_info=True)
        await state.clear()
        await safe_answer(callback, "❌ Xatolik yuz berdi, qayta urinib ko'ring.", show_alert=True)


# =======================================================
# 2. USER MATN YUBORGANDA
# =======================================================
@router.message(ReplyStates.waiting_for_reply, F.text)
async def process_reply_input(message: Message, state: FSMContext, session):
    data = await state.get_data()
    comment_id = data.get("comment_id")
    anime_id = data.get("anime_id")
    prompt_message_id = data.get("prompt_message_id")

    if not comment_id or not anime_id or not prompt_message_id:
        await state.clear()
        await safe_delete(message)
        return

    raw_text = message.text.strip() if message.text else ""

    if not raw_text:
        await safe_delete(message)
        return

    if len(raw_text) > 1000:
        await safe_delete(message)
        try:
            await message.answer("⚠️ Javob juda uzun! Maksimal 1000 ta belgi yuborishingiz mumkin.")
        except (TelegramBadRequest, TelegramForbiddenError):
            pass
        return

    await safe_delete(message)
    safe_reply_text = html.escape(raw_text)

    await state.update_data(reply_text=raw_text)

    preview_text = (
        f"↩️ <b>Javobingiz</b>\n\n"
        f"<blockquote expandable>{safe_reply_text}</blockquote>\n\n"
        f"Javobingizni yuborasizmi?"
    )

    confirm_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yuborish", callback_data=f"confirm_send_reply:{comment_id}:{anime_id}", style="success"),
                InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"edit_reply_input:{comment_id}:{anime_id}", style="success")
            ],
            [
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_reply_input:{comment_id}:{anime_id}", style="danger")
            ]
        ]
    )

    try:
        await message.bot.edit_message_caption(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            caption=preview_text,
            reply_markup=confirm_keyboard,
            parse_mode="HTML"
        )
        return
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
    except TelegramForbiddenError:
        await state.clear()
        return
    except Exception as e:
        logger.warning(f"edit_message_caption error: {e}")

    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            text=preview_text,
            reply_markup=confirm_keyboard,
            parse_mode="HTML"
        )
        return
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
    except TelegramForbiddenError:
        await state.clear()
        return
    except Exception as e:
        logger.error(f"edit_message_text error: {e}")

    try:
        new_msg = await message.answer(text=preview_text, reply_markup=confirm_keyboard, parse_mode="HTML")
        await state.update_data(prompt_message_id=new_msg.message_id)
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        logger.error(f"Preview message send error: {e}")
        await state.clear()


@router.message(ReplyStates.waiting_for_reply)
async def process_reply_input_invalid(message: Message) -> None:
    await safe_delete(message)
    try:
        await message.answer("✍️ Iltimos, javobni faqat matn ko'rinishida yuboring.")
    except (TelegramBadRequest, TelegramForbiddenError):
        pass


# =======================================================
# 3. ✅ YUBORISH TUGMASI (DB ga yozish va Javoblar bo'limiga qaytish)
# =======================================================
@router.callback_query(F.data.startswith("confirm_send_reply:"))
async def confirm_send_reply_handler(callback: CallbackQuery, state: FSMContext, session):
    try:
        parts = callback.data.split(":")
        comment_id = int(parts[1])
        anime_id = int(parts[2])
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    data = await state.get_data()
    reply_text = data.get("reply_text")

    if not reply_text:
        await safe_answer(callback, "⚠️ Javob topilmadi!", show_alert=True)
        await state.clear()
        return

    await state.clear()

    try:
        comment_service = CommentService(session=session)
        added = await comment_service.add_comment(
            anime_id=anime_id,
            user_id=callback.from_user.id,
            text=reply_text,
            parent_id=comment_id,
        )

        if added is None:
            await safe_answer(callback, "❌ Bu izohga endi javob yozib bo'lmaydi.", show_alert=True)
            return

        await safe_answer(callback, "✅ Javobingiz muvaffaqiyatli yuborildi!", show_alert=True)

        # 🚀 ASOSIY TUZATISH:
        # DB ga saqlangach, javob qaysi asosiy (root) izoh ostida ekanini aniqlaymiz.
        target_root_id = comment_id
        if isinstance(added, dict) and added.get("parent_id"):
            target_root_id = added["parent_id"]

        # Callback formatsiya: reply_all_commend:<root_comment_id>:<anime_id>:<page>:<index>
        # 9999:9999 berilsa, izohlar ro'yxati avtomatik ravishda eng oxirgi sahifa va eng yangi javobga o'tadi
        new_callback = callback.model_copy(
            update={"data": f"reply_all_commend:{target_root_id}:{anime_id}:9999:9999"}
        )

        await safe_call(
            handle_reply_all_comments(new_callback, session),
            context="confirm_send_reply -> handle_reply_all_comments"
        )

    except Exception as e:
        logger.error(f"Javobni saqlashda xatolik: {e}", exc_info=True)
        await safe_answer(callback, "❌ Javobni saqlashda xatolik yuz berdi.", show_alert=True)


# =======================================================
# 4. ✏️ TAHRIRLASH TUGMASI (Mavjud xabarni saqlagan holda tahrirlash)
# =======================================================
@router.callback_query(F.data.startswith("edit_reply_input:"))
async def edit_reply_input_handler(callback: CallbackQuery, state: FSMContext, session):
    await safe_answer(callback)

    try:
        parts = callback.data.split(":")
        comment_id = int(parts[1])
        anime_id = int(parts[2])
    except (IndexError, ValueError):
        return

    message = callback.message
    if not message:
        return

    try:
        comment_service = CommentService(session=session)
        original_comment = await comment_service.get_comment_by_id(comment_id)
    except Exception as e:
        logger.error(f"edit_reply_input_handler: {e}", exc_info=True)
        original_comment = None

    if not original_comment:
        await state.clear()
        return

    author = original_comment.get("user") or {}
    author_name = author.get("username") or author.get("full_name") or "Foydalanuvchi"
    original_text = original_comment.get("text", "")

    text = (
        f"↩️ <b>Javob yozish</b>\n\n"
        f"👤 <b>{html.escape(str(author_name))}</b>\n"
        f"<blockquote expandable>{html.escape(str(original_text))}</blockquote>\n\n"
        f"✍️ Javobingizni yuboring..."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Bekor qilish",
                    callback_data=f"cancel_reply_input:{comment_id}:{anime_id}",
                    style="danger"
                )
            ]
        ]
    )

    # 1. State holatini o'rnatamiz
    await state.set_state(ReplyStates.waiting_for_reply)

    # 2. Xabarni o'chirmasdan, bor xabarni edit qilamiz (Rasm bo'lsa edit_caption, matn bo'lsa edit_text)
    try:
        if message.photo or message.video or message.animation or message.document:
            prompt_msg = await message.edit_caption(caption=text, reply_markup=keyboard, parse_mode="HTML")
        else:
            prompt_msg = await message.edit_text(text=text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest as e:
        err = str(e).lower()
        if "message is not modified" in err:
            prompt_msg = message
        elif "message to edit not found" in err or "message can't be edited" in err:
            prompt_msg = await message.answer(text=text, reply_markup=keyboard, parse_mode="HTML")
        else:
            raise
    except TelegramForbiddenError:
        await state.clear()
        return

    await state.update_data(
        comment_id=comment_id,
        anime_id=anime_id,
        prompt_message_id=prompt_msg.message_id
    )


# =======================================================
# 5. ❌ BEKOR QILISH TUGMASI
# =======================================================
@router.callback_query(F.data.startswith("cancel_reply_input:"))
async def cancel_reply_input_handler(callback: CallbackQuery, state: FSMContext, session):
    await safe_answer(callback, "Jarayon bekor qilindi.")

    try:
        data = await state.get_data()
        prompt_message_id = data.get("prompt_message_id")
        comment_id = data.get("comment_id")
        anime_id = data.get("anime_id")

        try:
            parts = callback.data.split(":")
            if len(parts) > 2:
                comment_id = int(parts[1])
                anime_id = int(parts[2])
        except (IndexError, ValueError):
            pass

        await state.clear()

        if prompt_message_id and callback.message and prompt_message_id != callback.message.message_id:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=prompt_message_id
                )
            except (TelegramBadRequest, TelegramForbiddenError):
                pass

        if comment_id and anime_id:
            comment_service = CommentService(session=session)
            comm = await comment_service.get_comment_by_id(comment_id)
            root_id = comment_id
            if comm and comm.get("parent_id"):
                root_id = comm["parent_id"]

            # ❌ XATO: callback.data = f"reply_all_commend:{root_id}:{anime_id}:0:0"

            # ✅ TO'G'RI:
            new_callback = callback.model_copy(
                update={"data": f"reply_all_commend:{root_id}:{anime_id}:0:0"}
            )

            await safe_call(
                handle_reply_all_comments(new_callback, session),
                context="cancel_reply_input -> handle_reply_all_comments"
            )

    except Exception as e:
        logger.error(f"Cancel reply input handler error: {e}", exc_info=True)
        await state.clear()