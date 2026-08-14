
import html
import math
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
    page_replies_count: int,  # Shu sahifadagi javoblar soni (max 10)
    current_select_index: int, # Sahifa ichidagi tanlangan index (0-9)
    current_page: int,        # Hozirgi sahifa (0, 1, 2...)
    total_pages: int,         # Jami sahifalar soni
    current_reply_id: int,
    reply_to_reply_count: int = 0
) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    # ==================================================
    # 1-QATOR: Raqamli tugmalar (1 | 2 | 3 ... max 10 ta)
    # ==================================================
    if page_replies_count > 0:
        num_buttons = []
        
        for i in range(page_replies_count):
            is_active = i == current_select_index
            btn_text = f"• {i + 1} •" if i == current_select_index else f"{i + 1}"
            
            # Raqam bosilganda: shu sahifadagi (current_page) i-indexdagi reply tanlanadi
            cb_data = "noop" if i == current_select_index else f"rep_sel:{comment_id}:{anime_id}:{current_page}:{i}"
            num_buttons.append(
                InlineKeyboardButton(
                    text=btn_text, 
                    callback_data=cb_data, 
                    style="success" if is_active else None
                )
            )
        
        # 5 tadan qilib 2 qatorga bo'lamiz
        for i in range(0, len(num_buttons), 5):
            keyboard.append(num_buttons[i:i + 5])

    # ==================================================
    # 2-QATOR: Sahifalash (◀️ Oldingi | 📄 X/Y | Keyingi ▶️)
    # Faqat total_pages > 1 bo'lgandagina ko'rinadi!
    # ==================================================
    if total_pages > 1:
        prev_page = current_page - 1
        next_page = current_page + 1

        prev_cb = f"rep_page:{comment_id}:{anime_id}:{prev_page}:0" if prev_page >= 0 else "noop"
        next_cb = f"rep_page:{comment_id}:{anime_id}:{next_page}:0" if next_page < total_pages else "noop"

        row_nav = []
        if prev_page >= 0:
            row_nav.append(InlineKeyboardButton(text="◀️ Oldingi", callback_data=prev_cb, style="primary"))
        
        row_nav.append(InlineKeyboardButton(text=f"📄 {current_page + 1}/{total_pages}", callback_data="noop", style="primary"))
        
        if next_page < total_pages:
            row_nav.append(InlineKeyboardButton(text="Keyingi ▶️", callback_data=next_cb, style="primary"))

        keyboard.append(row_nav)

    # ==================================================
    # 3-QATOR: ↩️ Javob | 💬 X ta javob
    # ==================================================
    row_actions = [
        InlineKeyboardButton(
            text="↩️ Javob yozish",
            callback_data=f"reply_to:{current_reply_id}:{anime_id}",
            style="primary"
        ),
        InlineKeyboardButton(
            text=f"💬 {reply_to_reply_count} ta javob",
            callback_data=f"reply_all_commend:{current_reply_id}:{anime_id}" if reply_to_reply_count > 0 else "noop",
            style="primary"
        )
    ]
    keyboard.append(row_actions)

    # ==================================================
    # 4-QATOR: ⬅️ Orqaga
    # ==================================================
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"view_comments:{anime_id}:0", style="danger")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)








# from utils.helpers import safe_answer  # o'zingizning safe_answer funksiyangiz



@router.callback_query(F.data.startswith(("reply_all_commend:", "rep_page:", "rep_sel:")))
async def handle_reply_all_comments(callback: CallbackQuery, session: AsyncSession):
    try:
        parts = callback.data.split(":")
        comment_id = int(parts[1])
        anime_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 and parts[3] else 0
        select_index = int(parts[4]) if len(parts) > 4 and parts[4] else 0
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    comment_service = CommentService(session)

    try:
        # 1. Asosiy comment (Parent comment) ma'lumotlarini olish
        parent_comment = await comment_service.get_comment_by_id(comment_id)
        if not parent_comment:
            await safe_answer(callback, "❌ Asosiy izoh topilmadi.", show_alert=True)
            return

        # 2. Jami javoblar sonini olish va Sahifalarni (Pagination) hisoblash
        total_replies_count = await comment_service.get_comment_replies_count(comment_id)
        if total_replies_count == 0:
            await safe_answer(callback, "💬 Bu izohga hali javob yozilmagan.", show_alert=True)
            return

        PAGE_SIZE = 10
        total_pages = math.ceil(total_replies_count / PAGE_SIZE)

        # Sahifa chegaralarini to'g'rilash
        if page >= total_pages:
            page = total_pages - 1
        if page < 0:
            page = 0

        # 3. Shu sahifadagi (PAGE_SIZE = 10) javoblarni olish
        offset = page * PAGE_SIZE
        page_replies = await comment_service.get_comment_replies(
            comment_id=comment_id, 
            limit=PAGE_SIZE, 
            offset=offset
        )

        page_replies_count = len(page_replies)
        if select_index >= page_replies_count:
            select_index = page_replies_count - 1
        if select_index < 0:
            select_index = 0

        # 4. Tanlangan 1 ta reply va uning tafsilotlarini olish
        selected_reply = page_replies[select_index]
        selected_reply_id = selected_reply.get("id")

        # Tanlangan reply'ning o'ziga yozilgan replylar soni
        reply_to_reply_count = await comment_service.get_comment_replies_count(selected_reply_id)

        # --- MUALLIFLAR VA MATNLARNI TAYYORLASH ---
        # Parent (ota-izoh) muallifi
        parent_author = parent_comment.get("user") or {}
        parent_user_name = (
            parent_author.get("username")
            or parent_author.get("full_name")
            or "Noma'lum"
        )
        parent_text = parent_comment.get("text", "")

        # Tanlangan reply (javob) muallifi
        reply_author = selected_reply.get("user") or {}
        reply_user_name = (
            reply_author.get("username")
            or reply_author.get("full_name")
            or "Foydalanuvchi"
        )
        reply_text = selected_reply.get("text", "")

        # 5. UI MATN DIZAYNI
        caption = (
            f"↩️ <b>JAVOBLAR BO'LIMI</b>\n\n"
            f"📌 <b>{html.escape(parent_user_name)}</b> ning izohiga javob:\n"
            f"<blockquote expandable>{html.escape(parent_text)}</blockquote>\n\n"
            f"💬 <b>{html.escape(reply_user_name)}</b> yozdi:\n"
            f"<blockquote expandable>{html.escape(reply_text)}</blockquote>\n"
            f"📄 <b>Javob {select_index + 1}/{page_replies_count}</b> <i>(Jami: {total_replies_count} ta)</i>"
        )

        # 6. Klaviaturani yaratish
        keyboard = get_reply_all_comments_keyboard(
            comment_id=comment_id,
            anime_id=anime_id,
            page_replies_count=page_replies_count,
            current_select_index=select_index,
            current_page=page,
            total_pages=total_pages,
            current_reply_id=selected_reply_id,
            reply_to_reply_count=reply_to_reply_count
        )

        await safe_answer(callback)

        # Xabarni yangilash
        if callback.message.photo:
            await callback.message.edit_caption(caption=caption, reply_markup=keyboard, parse_mode="HTML")
        else:
            await callback.message.edit_text(text=caption, reply_markup=keyboard, parse_mode="HTML")

    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.error(f"TelegramBadRequest: {e}")
    except Exception as err:
        logger.error(f"❌ Javoblarni chiqarishda xatolik: {err}", exc_info=True)
        await safe_answer(callback, "❌ Tizimda xatolik yuz berdi.", show_alert=True)