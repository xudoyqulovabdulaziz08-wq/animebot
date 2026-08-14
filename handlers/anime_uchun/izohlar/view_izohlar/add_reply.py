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
# 1. "↩️ JAVOB YOZISH" TUGMASI BOSILGANDA (State set va Prompt)
#    callback_data: "reply_to:<comment_id>:<anime_id>"
#    Eslatma: comment_id bu asosiy izoh HAM, javobning o'zi (reply) HAM bo'lishi mumkin —
#    ikkalasi ham xavfsiz, chunki CommentService.add_comment allaqachon 2-daraja
#    tekislash (flattening) logikasiga ega: agar siz javobning javobiga yozsangiz,
#    u avtomatik asosiy (root) izohga bog'lanadi — cheksiz ichma-ich thread paydo bo'lmaydi.
# =======================================================
@router.callback_query(F.data.startswith("reply_to:"))
async def start_add_reply_handler(callback: CallbackQuery, state: FSMContext, session):
    # 1. Double-click va tugma "qotib qolishi" oldini olish uchun darhol answer beramiz
    await safe_answer(callback)

    try:
        parts = callback.data.split(":")
        comment_id = int(parts[1])
        anime_id = int(parts[2])
    except (IndexError, ValueError):
        return

    # 2. FSM race-condition: Agar foydalanuvchi allaqachon shu holatda bo'lsa, qayta ishlatmaymiz
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

        # 3. FSM holatini EDIT'dan oldin o'rnatamiz (DB/Telegram sekinlashganda input yo'qolmasligi uchun)
        await state.set_state(ReplyStates.waiting_for_reply)

        # 4. Xabarni yangilash (Media/Text xavfsiz tahriri)
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

        # Context ma'lumotlarini saqlaymiz
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
# 2. USER MATN YUBORGANDA (Kutish va User xabarini o'chirish)
# =======================================================
@router.message(ReplyStates.waiting_for_reply, F.text)
async def process_reply_input(message: Message, state: FSMContext, session):
    data = await state.get_data()
    comment_id = data.get("comment_id")
    anime_id = data.get("anime_id")
    prompt_message_id = data.get("prompt_message_id")

    # 1. State ma'lumotlari yo'qolgan bo'lsa (masalan bot qayta ishga tushgan) — xavfsiz to'xtaymiz
    if not comment_id or not anime_id or not prompt_message_id:
        await state.clear()
        await safe_delete(message)
        return

    raw_text = message.text.strip() if message.text else ""

    # 2. Bo'sh izohni rad etamiz
    if not raw_text:
        await safe_delete(message)
        return

    # 3. Text uzunligini tekshirish
    if len(raw_text) > 1000:
        await safe_delete(message)
        try:
            await message.answer("⚠️ Javob juda uzun! Maksimal 1000 ta belgi yuborishingiz mumkin.")
        except (TelegramBadRequest, TelegramForbiddenError):
            pass
        return

    # Foydalanuvchi yuborgan xabarni o'chirib, chatni toza tutamiz
    await safe_delete(message)

    safe_reply_text = html.escape(raw_text)

    # FSM ga javob matnini saqlaymiz
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

    # Dastlabki xabar caption'ini tahrirlaymiz — barcha yo'llar muvaffaqiyatsiz
    # bo'lsa ham foydalanuvchi "osilib qolmasligi" uchun oxirgi chora sifatida yangi xabar yuboramiz.
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
        err = str(e).lower()
        if "message is not modified" in err:
            return
    except TelegramForbiddenError:
        await state.clear()
        return
    except Exception as e:
        logger.warning(f"edit_message_caption kutilmagan xato: {e}")

    # Fallback 1: caption emas, matnli xabar bo'lishi mumkin
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
        err = str(e).lower()
        if "message is not modified" in err:
            return
        logger.warning(f"edit_message_text ham muvaffaqiyatsiz: {e}")
    except TelegramForbiddenError:
        await state.clear()
        return
    except Exception as e:
        logger.error(f"Fallback edit text error: {e}")

    # Fallback 2: ikkalasi ham ishlamasa — foydalanuvchi osilib qolmasligi uchun yangi xabar yuboramiz
    try:
        new_msg = await message.answer(text=preview_text, reply_markup=confirm_keyboard, parse_mode="HTML")
        await state.update_data(prompt_message_id=new_msg.message_id)
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        logger.error(f"Preview xabarini yuborib bo'lmadi: {e}")
        await state.clear()


@router.message(ReplyStates.waiting_for_reply)
async def process_reply_input_invalid(message: Message) -> None:
    """Javob kutilayotgan holatda matndan boshqa turdagi xabar (rasm, ovoz va h.k.) kelsa."""
    await safe_delete(message)
    try:
        await message.answer("✍️ Iltimos, javobni faqat matn ko'rinishida yuboring.")
    except (TelegramBadRequest, TelegramForbiddenError):
        pass


# =======================================================
# 3. ✅ YUBORISH TUGMASI (DB ga yozish)
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

    # 1. State va text validatsiyasi
    if not reply_text:
        await safe_answer(callback, "⚠️ Javob topilmadi!", show_alert=True)
        await state.clear()
        return

    # 🔒 Qayta bosish (double-click) natijasida ikkita javob yozilib ketmasligi uchun
    #    state'ni DB yozuvidan OLDIN tozalaymiz — takroriy so'rov reply_text topmay to'xtaydi.
    await state.clear()

    try:
        comment_service = CommentService(session=session)
        # parent_id = comment_id — agar bu izoh o'zi allaqachon javob (reply) bo'lsa ham,
        # xavfsiz: CommentService.add_comment buni avtomatik asosiy izohga tekislaydi
        # (2-daraja chekловi), shu sabab cheksiz ichma-ich thread paydo bo'lmaydi.
        added = await comment_service.add_comment(
            anime_id=anime_id,
            user_id=callback.from_user.id,
            text=reply_text,
            parent_id=comment_id,
        )

        if added is None:
            await safe_answer(callback, "❌ Bu izohga endi javob yozib bo'lmaydi.", show_alert=True)
            return

        # 2. Yagona va muvaffaqiyatli alert chiqarish
        await safe_answer(callback, "✅ Javobingiz muvaffaqiyatli yuborildi!", show_alert=True)

        # 3. Izohlar bo'limiga qaytamiz.
        #    handle_reply_all_comments ichida yana callback.answer() bo'lishi mumkin —
        #    safe_call shu holatdagi "already answered" xatosini yutib yuboradi.
        await safe_call(
            handle_reply_all_comments(callback, session),
            context="confirm_send_reply -> handle_reply_all_comments"
        )

    except Exception as e:
        logger.error(f"Javobni saqlashda xatolik: {e}", exc_info=True)
        await safe_answer(callback, "❌ Javobni saqlashda xatolik yuz berdi.", show_alert=True)


# =======================================================
# 4. ✏️ TAHRIRLASH TUGMASI (Qaytadan kiritish holatiga o'tkazish)
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

    # Eskisini o'chiramiz
    if callback.message:
        await safe_delete(callback.message)

    try:
        comment_service = CommentService(session=session)
        original_comment = await comment_service.get_comment_by_id(comment_id)
    except Exception as e:
        logger.error(f"edit_reply_input_handler: izohni olishda xato: {e}", exc_info=True)
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
                    callback_data=f"cancel_reply_input:{comment_id}:{anime_id}"
                )
            ]
        ]
    )

    try:
        prompt_msg = await callback.message.answer(text=text, reply_markup=keyboard, parse_mode="HTML")
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        logger.warning(f"edit_reply_input_handler: prompt yuborilmadi: {e}")
        await state.clear()
        return

    await state.set_state(ReplyStates.waiting_for_reply)
    await state.update_data(
        comment_id=comment_id,
        anime_id=anime_id,
        prompt_message_id=prompt_msg.message_id
    )


# =======================================================
# 5. ❌ BEKOR QILISH / ORQAGA TUGMASI (FSM tozalash va ortga)
# =======================================================
@router.callback_query(F.data.startswith("cancel_reply_input:"))
async def cancel_reply_input_handler(callback: CallbackQuery, state: FSMContext, session):
    await safe_answer(callback, "Jarayon bekor qilindi.")

    try:
        data = await state.get_data()
        prompt_message_id = data.get("prompt_message_id")

        await state.clear()

        if prompt_message_id and callback.message and prompt_message_id != callback.message.message_id:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=prompt_message_id
                )
            except (TelegramBadRequest, TelegramForbiddenError):
                pass

        await safe_call(
            handle_reply_all_comments(callback, session),
            context="cancel_reply_input -> handle_reply_all_comments"
        )

    except Exception as e:
        logger.error(f"Cancel reply input handler error: {e}", exc_info=True)
        await state.clear()