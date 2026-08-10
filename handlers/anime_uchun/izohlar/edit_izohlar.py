import logging
import html
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from handlers.anime_uchun.izoh_anime import anime_comment_handler
from services.comment_service import CommentService
from services.anime_service import AnimeService
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.fsm.state import State, StatesGroup
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
                callback_data=f"my_comm:{anime_id}:{i}",
                style="primary"
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








@router.callback_query(lambda c: c.data.startswith("my_comm:") or c.data.startswith("my_comments:"))
async def handle_my_comments(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    anime_id = int(parts[1])
    current_index = int(parts[2]) if len(parts) > 2 else 0
    user_id = callback.from_user.id

    comment_service = CommentService(session)
    
    # Total count olish (Kesh orqali)
    total_comments = await comment_service.get_user_comments_count(anime_id, user_id)
    if total_comments == 0:
        await callback.answer("Siz ushbu animega hali izoh qoldirmagansiz.", show_alert=True)
        return

    # Aynan kerakli index'dagi izohni olish
    comment = await comment_service.get_user_comment_by_index(anime_id, user_id, current_index)
    if not comment:
        await callback.answer("Izoh topilmadi.", show_alert=True)
        return

    # Anime nomini olish (Loyiha modelingizga qarab)
    anime_title = comment.get("anime_title", "Anime")

    # Matnni tayyorlash
    caption = f"🗨️ <b>Izohlarim</b>\n\n"
    caption += f"🎬 <b>{anime_title}</b>\n\n"
    
    # Agar bu reply bo'lsa, ota-izoh matnini ham ko'rsatamiz
    if comment.get("parent"):
        parent_author = comment["parent"]["author_name"]
        parent_text = comment["parent"]["text"]
        caption += f"↩️ <i>{parent_author} ning izohiga javob:</i>\n"
        caption += f"┗ <i>\"{parent_text}\"</i>\n\n"

    caption += f"┌─────────────────────────┐\n"
    caption += f"│ 🗨️ <b>Izoh {current_index + 1}</b>\n"
    caption += f"│ {comment['text']}\n"
    caption += f"└─────────────────────────┘\n"

    # Agar ushbu izohga boshqalar javob yozgan bo'lsa
    replies_count = comment.get("replies_count", 0)
    if replies_count > 0:
        caption += f"\n💬 <b>{replies_count} ta javob</b>"

    keyboard = get_my_comments_keyboard(
        anime_id=anime_id,
        total_count=total_comments,
        current_index=current_index,
        comment_id=comment["id"]
    )

    await callback.message.edit_caption(
        caption=caption,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()