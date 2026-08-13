
import html
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
# Service va yordamchi funksiyalaringiz
from services.comment_service import CommentService

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


logger = logging.getLogger(__name__)
router = Router()







async def safe_answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False) -> None:
    """
    callback.answer()ni xavfsiz chaqiradi.
    Bitta callback_query FAQAT BIR MARTA javob olishi mumkin — ikkinchi marta
    chaqirilsa yoki so'rov "eskirgan" bo'lsa, Telegram xato qaytaradi.
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
        pass
    except Exception as e:
        logger.warning(f"callback.answer kutilmagan xato: {e}")








def get_reply_all_comments_keyboard(
    comment_id: int,
    anime_id: int,
    total_count: int,
    current_index: int,
    current_reply_id: int,
    reply_to_reply_count: int = 0
) -> InlineKeyboardMarkup:
    """
    💬 Izohning barcha javoblarini (replies) ko'rish uchun maxsus klaviaturasi
    """
    keyboard: list[list[InlineKeyboardButton]] = []

    # 1. ↩️ Javob yozish | 💬 X ta javob
    row1 = [
        InlineKeyboardButton(
            text="↩️ Javob yozish",
            callback_data=f"reply_to:{current_reply_id}:{anime_id}",

        ),
        InlineKeyboardButton(
            text=f"💬 {reply_to_reply_count} ta javob",
            callback_data=f"reply_all_commend:{current_reply_id}:{anime_id}" if reply_to_reply_count > 0 else "noop"
        )
    ]
    keyboard.append(row1)

    # 2. Raqamli tugmalar (1 | 2 | 3) - har bir javob uchun
    if total_count > 1:
        num_buttons = []
        for i in range(total_count):
            # Joriy tanlangan sahifani alohida ajratib ko'rsatamiz: [ 1 ]
            btn_text = f"[{i + 1}]" if i == current_index else f"{i + 1}"
            cb_data = "noop" if i == current_index else f"rep_all_page:{comment_id}:{anime_id}:{i}"
            num_buttons.append(InlineKeyboardButton(text=btn_text, callback_data=cb_data))
        
        # Agar raqamlar ko'p bo'lsa (masalan 5 tadan ortiq), qatorlarga bo'lamiz
        chunk_size = 5
        for i in range(0, len(num_buttons), chunk_size):
            keyboard.append(num_buttons[i:i + chunk_size])

    # 3. ◀️ Oldingi | 📄 Page | Keyingi ▶️
    if total_count > 1:
        prev_index = current_index - 1
        next_index = current_index + 1

        prev_cb = f"rep_all_page:{comment_id}:{anime_id}:{prev_index}" if prev_index >= 0 else "noop"
        next_cb = f"rep_all_page:{comment_id}:{anime_id}:{next_index}" if next_index < total_count else "noop"

        row_nav = [
            InlineKeyboardButton(text="◀️ Oldingi", callback_data=prev_cb),
            InlineKeyboardButton(text=f"📄 {current_index + 1}/{total_count}", callback_data="noop"),
            InlineKeyboardButton(text="Keyingi ▶️", callback_data=next_cb)
        ]
        keyboard.append(row_nav)

    # 4. ⬅️ Orqaga
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"view_comments:{anime_id}:0")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)









# from utils.helpers import safe_answer  # o'zingizning safe_answer funksiyangiz

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data.startswith(("reply_all_commend:", "rep_all_page:")))
async def handle_reply_all_comments(callback: CallbackQuery, session: AsyncSession):
    # 1. callback_data xavfsiz parse qilish
    try:
        parts = callback.data.split(":")
        comment_id = int(parts[1])
        anime_id = int(parts[2])
        current_index = int(parts[3]) if len(parts) > 3 and parts[3] else 0
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    comment_service = CommentService(session)

    try:
        # 2. Ota-izoh (Parent Comment) ma'lumotlarini kesh/bazadan olish
        parent_comment = await comment_service.get_comment_by_id(comment_id)
        if not parent_comment:
            await safe_answer(callback, "❌ Ota-izoh topilmadi yoki o'chirilgan.", show_alert=True)
            return

        # 3. Shu ota-izohga yozilgan BARCHA javoblarni olish
        replies = await comment_service.get_comment_replies(comment_id, limit=50, offset=0)

        # Javoblar yo'qligini tekshirish
        if not replies:
            await safe_answer(
                callback,
                "💬 Hozircha bu izohga hech kim javob yozmagan.",
                show_alert=True
            )
            return

        total_replies = len(replies)

        # Index chegarasini to'g'rilash
        if current_index >= total_replies:
            current_index = total_replies - 1
        elif current_index < 0:
            current_index = 0

        # Joriy tanlangan javob obyekti
        current_reply = replies[current_index]
        current_reply_id = current_reply.get("id")

        # Ushbu javobning o'ziga ham javob berilganmi (nested reply count)
        reply_to_reply_count = await comment_service.get_comment_replies_count(current_reply_id)

        # Foydalanuvchi ma'lumotlarini tayyorlash
        parent_author = parent_comment.get("user") or {}
        parent_author_name = (
            parent_author.get("username")
            or parent_author.get("full_name")
            or "Foydalanuvchi"
        )
        parent_text = parent_comment.get("text", "")

        reply_author = current_reply.get("user") or {}
        reply_author_name = (
            reply_author.get("username")
            or reply_author.get("full_name")
            or "Foydalanuvchi"
        )
        reply_text = current_reply.get("text", "")

        # 4. UI uchun matn shakllantirish (HTML escape bilan)
        text_lines = [
            f"↩️ <b>{html.escape(parent_author_name)} ga javoblar</b>\n",
            f"<i>{html.escape(reply_text)}</i>\n",
            f"<blockquote expandable>┌─────────────────────────┐\n"
            f"│ 👤 {html.escape(parent_author_name)}\n"
            f"│ {html.escape(parent_text)}\n"
            f"└─────────────────────────┘</blockquote>\n",
            f"💬 <b>Javob {current_index + 1}/{total_replies}</b>"
        ]

        caption = "\n".join(text_lines)

        # 5. Klaviaturani tayyorlash
        keyboard = get_reply_all_comments_keyboard(
            comment_id=comment_id,
            anime_id=anime_id,
            total_count=total_replies,
            current_index=current_index,
            current_reply_id=current_reply_id,
            reply_to_reply_count=reply_to_reply_count
        )

        await safe_answer(callback)

        # 6. Xabarni xavfsiz tahrirlash / yangilash
        try:
            if callback.message.photo:
                await callback.message.edit_caption(
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    text=caption,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
        except TelegramBadRequest as e:
            error_msg = str(e).lower()
            if "message is not modified" in error_msg:
                pass  # Xabar o'zgarmagan bo'lsa inkor qilamiz
            elif "message to edit not found" in error_msg or "message can't be edited" in error_msg:
                try:
                    await callback.message.answer(text=caption, reply_markup=keyboard, parse_mode="HTML")
                except (TelegramBadRequest, TelegramForbiddenError) as e2:
                    logger.warning(f"handle_reply_all_comments: yangi xabar yuborilmadi: {e2}")
            else:
                logger.error(f"❌ TelegramBadRequest yuz berdi: {e}")
        except TelegramForbiddenError:
            pass

    except Exception as err:
        logger.error(f"❌ Javoblarni olishda xatolik: {err}", exc_info=True)
        await safe_answer(callback, "❌ Tizimda xatolik yuz berdi.", show_alert=True)