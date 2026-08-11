import logging
import html
import asyncio
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from handlers.anime_uchun.izoh_anime import anime_comment_handler
from services.comment_service import CommentService
from services.anime_service import AnimeService
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from config import config

logger = logging.getLogger("izohlarim_edit")
router = Router()
CREATOR_ID = config.CREATOR_ID






def get_my_comments_keyboard(anime_id: int, total_count: int, current_index: int, comment_id: int) -> InlineKeyboardMarkup:
    keyboard = []
    
    # 1. Sahifalash tugmalari (1, 2, 3...)
    page_buttons = []
    for i in range(total_count):
        text = f"• {i + 1} •" if i == current_index else str(i + 1)
        page_buttons.append(
            InlineKeyboardButton(
                text=text,
                callback_data=f"my_comm:{anime_id}:{i}"
                
            )
        )
    if page_buttons:
        keyboard.append(page_buttons)

    # 2. Amal tugmalari (O'chirish va Tahrirlash)
    keyboard.append([
        InlineKeyboardButton(text="🗑️ O‘chirish", callback_data=f"del_comm:{comment_id}:{anime_id}", style="danger"),
        InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"edit_comm:{comment_id}", style="success")
    ])

    # 3. Orqaga tugmasi
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"anime_details:{anime_id}", style="danger")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)








@router.callback_query(lambda c: c.data.startswith(("my_comm:", "my_comments:")))
async def handle_my_comments(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    anime_id = int(parts[1])
    current_index = int(parts[2]) if len(parts) > 2 else 0
    user_id = callback.from_user.id

    comment_service = CommentService(session)
    
    # 1. Ketma-ket so'rovlarni async (parallel) bajarib vaqtni tejaymiz
    anime_service = AnimeService(session=session)
    anime, total_comments = await asyncio.gather(
        anime_service.get_anime(anime_id),
        comment_service.get_user_comments_count(anime_id, user_id)
    )

    if total_comments == 0:
        await callback.answer("Siz ushbu animega hali izoh qoldirmagansiz.", show_alert=True)
        return

    # Index chegaradan chiqib ketmasligini xavfsiz ta'minlaymiz
    if current_index >= total_comments:
        current_index = total_comments - 1
    elif current_index < 0:
        current_index = 0

    comment = await comment_service.get_user_comment_by_index(anime_id, user_id, current_index)
    if not comment:
        await callback.answer("Izoh topilmadi.", show_alert=True)
        return

    anime_title = anime.get("title", "Anime") if isinstance(anime, dict) else getattr(anime, "title", "Anime")

    # Matnni yig'ish (List orqali tezroq va toza shakllantiramiz)
    text_lines = [
        "💬 <b>Izohlarim</b>\n",
        f"🎬 <b>{anime_title}</b>\n"
    ]

    if comment.get("parent"):
        parent_author = comment["parent"]["author_name"]
        parent_text = comment["parent"]["text"]
        text_lines.append(f"↩️ <i>{parent_author} ning izohiga javob:</i>")
        text_lines.append(f"┗ <i>\"{parent_text}\"</i>\n")

    
    text_lines.append(f"💬 <b>Izoh {current_index + 1}/{total_comments}</b>\n")
    text_lines.append(f"<blockquote expandable>{comment['text']}</blockquote>")
    

    replies_count = comment.get("replies_count", 0)
    if replies_count > 0:
        text_lines.append(f"\n💬 <b>{replies_count} ta javob</b>")

    caption = "\n".join(text_lines)

    keyboard = get_my_comments_keyboard(
        anime_id=anime_id,
        total_count=total_comments,
        current_index=current_index,
        comment_id=comment["id"]
    )

    # 2. Xavfsiz tahrirlash (Xabar turi rasm yoki text ekanligiga qarab)
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
        # Bir xil xabar qayta bosilganda bot crash bo'lishining oldi olinadi
        if "message is not modified" not in e.message.lower():
            raise e

    await callback.answer()