import logging
import html
from typing import Optional

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramNetworkError
)
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message
)
from aiogram.fsm.context import FSMContext
from aiogram import Router, F
from services.comment_service import CommentService
from services.anime_service import AnimeService
from aiogram.fsm.state import State, StatesGroup

from handlers.anime_uchun.izoh_anime import anime_comment_handler
from config import config

logger = logging.getLogger("izohlarim_qoshish")
router = Router()
CREATOR_ID = config.CREATOR_ID


class CommentStates(StatesGroup):
    waiting_for_comment = State()  # Text kiritish kutilmoqda



# =======================================================
# 🧰 YORDAMCHI FUNKSIYALAR (Telegramning turli xatolaridan himoya)
# =======================================================
async def safe_answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False) -> None:
    """
    callback.answer()ni xavfsiz chaqiradi.
    Bitta callback_query FAQAT BIR MARTA javob olishi mumkin — ikkinchi marta
    chaqirilsa yoki so'rov "eskirgan" bo'lsa, Telegram xato qaytaradi.
    Bu funksiya o'sha kutilgan xatolarni yutib yuboradi, kutilmaganlarini logga yozadi.
    """
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "query is too old" in msg or "query id is invalid" in msg or "response timeout expired" in msg:
            pass
        else:
            logger.warning(f"callback.answer xatosi: {e}")
    except TelegramForbiddenError:
        # Foydalanuvchi botni bloklagan — hech narsa qilib bo'lmaydi
        pass
    except Exception as e:
        logger.warning(f"callback.answer kutilmagan xato: {e}")




async def safe_call(coro, *, context: str = "") -> None:
    """
    Boshqa handlerni (masalan anime_comment_handler) xavfsiz chaqiradi.
    U ichida yana callback.answer()/edit_message chaqirishi mumkin — bunday
    holatlarda kelib chiqadigan "kutilgan" Telegram xatolarini yutib yuboradi.
    """
    try:
        await coro
    except TelegramForbiddenError:
        pass
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "query is too old" in msg or "query id is invalid" in msg or "message is not modified" in msg:
            pass
        else:
            logger.warning(f"{context or 'safe_call'} TelegramBadRequest: {e}")
    except TelegramRetryAfter as e:
        logger.warning(f"{context or 'safe_call'}: flood control, retry_after={e.retry_after}")
    except TelegramNetworkError as e:
        logger.warning(f"{context or 'safe_call'}: tarmoq xatosi: {e}")
    except Exception as e:
        logger.error(f"{context or 'safe_call'} kutilmagan xato: {e}", exc_info=True)


async def safe_delete(message: Message) -> None:
    """Xabarni xavfsiz o'chiradi — allaqachon o'chirilgan/ruxsat yo'q holatlarni yutadi."""
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    except Exception as e:
        logger.warning(f"Xabarni o'chirishda kutilmagan xato: {e}")




# =======================================================
# 1. "IZOH YOZISH" TUGMASI BOSILGANDA (State set va Prompt)
# =======================================================
@router.callback_query(F.data.startswith("add_comment:"))
async def start_add_comment_handler(callback: CallbackQuery, state: FSMContext, session):
    # 1. Ruxsat tekshiruvi (callback.answer'dan oldin bajariladi)
    if callback.from_user.id != CREATOR_ID:
        await safe_answer(callback, "🛑 Izohlar funksiyasi tez orada ishga tushadi.", show_alert=True)
        return

    # 2. Double-click va tugma "qotib qolishi" oldini olish uchun darhol answer beramiz
    await safe_answer(callback)

    # 3. FSM race-condition: Agar foydalanuvchi allaqachon shu holatda bo'lsa, qayta ishlatmaymiz
    current_state = await state.get_state()
    if current_state == CommentStates.waiting_for_comment.state:
        return

    try:
        anime_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        return

    try:
        anime_service = AnimeService(session=session)
        anime = await anime_service.get_anime(anime_id)

        if not anime:
            await safe_answer(callback, "❌ Anime topilmadi.", show_alert=True)
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
                        callback_data=f"cancel_comment_input:{anime_id}",
                        style="danger"
                    )
                ]
            ]
        )

        message = callback.message
        if not message:
            return

        # 4. FSM holatini EDIT'dan oldin o'rnatamiz (DB/Telegram sekinlashganda input yo'qolmasligi uchun)
        await state.set_state(CommentStates.waiting_for_comment)

        # 5. Xabarni yangilash (Media/Text xavfsiz tahriri)
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
                # Eski xabarni tahrirlab bo'lmasa — yangi xabar yuboramiz
                prompt_msg = await message.answer(text=text, reply_markup=keyboard, parse_mode="HTML")
            else:
                raise

        # Context ma'lumotlarini saqlaymiz
        await state.update_data(
            anime_id=anime_id,
            anime_title=anime_title,
            prompt_message_id=prompt_msg.message_id
        )

    except TelegramForbiddenError:
        await state.clear()
    except TelegramBadRequest as e:
        logger.warning(f"Add comment TelegramBadRequest: {e}")
        await state.clear()
    except (TelegramRetryAfter, TelegramNetworkError) as e:
        logger.warning(f"Add comment tarmoq/flood xatosi: {e}")
        await state.clear()
    except Exception as e:
        logger.error(f"Add comment handler error: {e}", exc_info=True)
        await state.clear()
        await safe_answer(callback, "❌ Xatolik yuz berdi, qayta urinib ko'ring.", show_alert=True)






# =======================================================
# 2. USER MATN YUBORGANDA (Kutish va User xabarini o'chirish)
# =======================================================
@router.message(CommentStates.waiting_for_comment, F.text)
async def process_comment_input(message: Message, state: FSMContext, session):
    data = await state.get_data()
    anime_id = data.get("anime_id")
    anime_title = data.get("anime_title")
    prompt_message_id = data.get("prompt_message_id")

    # 1. State ma'lumotlari yo'qolgan bo'lsa (masalan bot qayta ishga tushgan) — xavfsiz to'xtaymiz
    if not anime_id or not prompt_message_id:
        await state.clear()
        await safe_delete(message)
        return

    raw_text = message.text.strip() if message.text else ""

    # 2. Bo'sh yoki juda qisqa izohni rad etamiz
    if not raw_text:
        await safe_delete(message)
        return

    # 3. Text uzunligini tekshirish
    if len(raw_text) > 1000:
        await safe_delete(message)
        try:
            await message.answer("⚠️ Izoh juda uzun! Maksimal 1000 ta belgi yuborishingiz mumkin.")
        except (TelegramBadRequest, TelegramForbiddenError):
            pass
        return

    # Foydalanuvchi yuborgan xabarni o'chirib, chatni toza tutamiz
    await safe_delete(message)

    safe_comment_text = html.escape(raw_text)
    safe_anime_title = html.escape(str(anime_title))

    # FSM ga izoh matnini saqlaymiz
    await state.update_data(comment_text=raw_text)

    preview_text = (
        f"💬 <b>Izohingiz</b>\n\n"
        f"<blockquote expandable>{safe_comment_text}</blockquote>\n\n"
        f"🎬 <b>{safe_anime_title}</b>\n\n"
        f"Izohingizni yuborasizmi?"
    )

    confirm_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yuborish", callback_data=f"confirm_send_comment:{anime_id}", style="success"),
                InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"edit_comment_input:{anime_id}", style="success")
            ],
            [
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_comment_input:{anime_id}", style="danger")
            ]
        ]
    )

    # 🎯 MUHIM QISM: Yangi xabar yubormaymiz!
    # Dastlabki POSTERLI xabar caption'ini tahrirlaymiz — barcha yo'llar muvaffaqiyatsiz
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






@router.message(CommentStates.waiting_for_comment)
async def process_comment_input_invalid(message: Message) -> None:
    """Izoh kutilayotgan holatda matndan boshqa turdagi xabar (rasm, ovoz va h.k.) kelsa."""
    await safe_delete(message)
    try:
        await message.answer("✍️ Iltimos, izohni faqat matn ko'rinishida yuboring.")
    except (TelegramBadRequest, TelegramForbiddenError):
        pass






# =======================================================
# 3. ✅ YUBORISH TUGMASI (DB ga yozish va keshni tozalash)
# =======================================================
@router.callback_query(F.data.startswith("confirm_send_comment:"))
async def confirm_send_comment_handler(callback: CallbackQuery, state: FSMContext, session):
    try:
        anime_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    data = await state.get_data()
    comment_text = data.get("comment_text")

    # 1. State va text validatsiyasi
    if not comment_text:
        await safe_answer(callback, "⚠️ Izoh topilmadi!", show_alert=True)
        await state.clear()
        return

    # 🔒 Qayta bosish (double-click) natijasida ikkita izoh yozilib ketmasligi uchun
    #    state'ni DB yozuvidan OLDIN tozalaymiz — takroriy so'rov comment_text topmay to'xtaydi.
    await state.clear()

    try:
        comment_service = CommentService(session=session)
        await comment_service.add_comment(
            anime_id=anime_id,
            user_id=callback.from_user.id,
            text=comment_text,
        )

        # 2. Yagona va muvaffaqiyatli alert chiqarish
        await safe_answer(callback, "✅ Izohingiz muvaffaqiyatli yuborildi!", show_alert=True)

        # 3. Izohlar bo'limiga qaytamiz.
        #    anime_comment_handler ichida yana callback.answer() bo'lishi mumkin —
        #    safe_call shu holatdagi "already answered" xatosini yutib yuboradi.
        await safe_call(
            anime_comment_handler(callback, session),
            context="confirm_send_comment -> anime_comment_handler"
        )

    except Exception as e:
        logger.error(f"Izohni saqlashda xatolik: {e}", exc_info=True)
        await safe_answer(callback, "❌ Izohni saqlashda xatolik yuz berdi.", show_alert=True)

