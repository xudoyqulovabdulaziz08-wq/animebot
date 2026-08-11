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






def get_my_comments_keyboard(
    anime_id: int, 
    total_count: int, 
    current_index: int, 
    comment_id: int, 
    replies_count: int = 0  # <--- Yangi parametr
) -> InlineKeyboardMarkup:
    keyboard = []
    
    # 1. Sahifalash tugmalari (1, 2, 3...)
    page_buttons = []
    for i in range(total_count):
        is_active = i == current_index
        
        page_buttons.append(
            InlineKeyboardButton(
                text = f"• {i + 1} •" if i == current_index else str(i + 1),
                callback_data=f"my_comm:{anime_id}:{i}",
                style="success" if is_active else None
            )
        )
    if page_buttons:
        keyboard.append(page_buttons)

    # 2. Amal tugmalari (Javoblar, O'chirish va Tahrirlash)
    keyboard.append([
        InlineKeyboardButton(
            text=f"💬 {replies_count} ta javob",  # <--- Dinamik qiymat joylandi
            callback_data=f"reply_comm:{comment_id}:{anime_id}", 
            style="primary"
        )
    ])
    keyboard.append([
        InlineKeyboardButton(text="🗑️ O‘chirish", callback_data=f"del_comm:{comment_id}:{anime_id}", style="danger"),
        InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"edit_comm:{comment_id}", style="success")
    ])

    # 3. Orqaga tugmasi
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"anime_comment:{anime_id}", style="danger")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)



def get_comment_replies_keyboard(
    anime_id: int, 
    comment_id: int, 
    total_count: int, 
    current_index: int
) -> InlineKeyboardMarkup:
    keyboard = []
    
    # 1. Sahifalash tugmalari (1, 2, 3...)
    if total_count > 1:
        page_buttons = []
        for i in range(total_count):
            text = f"• {i + 1} •" if i == current_index else str(i + 1)
            page_buttons.append(
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"rep_page:{comment_id}:{anime_id}:{i}"
                )
            )
        keyboard.append(page_buttons)

    # 2. Orqaga tugmasi (Asosiy izohga qaytaradi)
    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ Orqaga", 
            callback_data=f"my_comm:{anime_id}:{current_index}", 
            style="danger"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.callback_query(lambda c: c.data.startswith(("my_comm:", "my_comments:")))
async def handle_my_comments(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    anime_id = int(parts[1])
    current_index = int(parts[2]) if len(parts) > 2 else 0
    user_id = callback.from_user.id

    comment_service = CommentService(session)
    anime_service = AnimeService(session=session)
    
    # 1. Parallel ravishda anime ma'lumoti va foydalanuvchi izohlari sonini olamiz
    anime, total_comments = await asyncio.gather(
        anime_service.get_anime(anime_id),
        comment_service.get_user_comments_count(anime_id, user_id)
    )

    if total_comments == 0:
        await callback.answer(
        "💬 Bu yerda hali sizning izohingiz yo‘q.\n"
        "✍️ Birinchi bo‘lib fikringizni qoldiring!",
            show_alert=True
        )
        return

    # Index chegaradan chiqmasligi uchun
    if current_index >= total_comments:
        current_index = total_comments - 1
    elif current_index < 0:
        current_index = 0

    # Index bo'yicha joriy izohni olamiz
    comment = await comment_service.get_user_comment_by_index(anime_id, user_id, current_index)
    if not comment:
        await callback.answer("Izoh topilmadi.", show_alert=True)
        return

    # 🟢 SHU YERGA QO'SHILADI: Ushbu izohga yozilgan javoblar sonini await qilib olamiz
    replies_count = await comment_service.get_comment_replies_count(comment["id"])

    anime_title = anime.get("title", "Anime") if isinstance(anime, dict) else getattr(anime, "title", "Anime")

    # Matnni shakllantirish
    text_lines = [
        "💬 <b>Izohlarim</b>\n",
        f"🎬 <b>{anime_title}</b>\n"
    ]

    if comment.get("parent"):
        parent_author = comment["parent"]["author_name"]
        parent_text = comment["parent"]["text"]
        text_lines.append(f"↩️ <i>{parent_author} ning izohiga javob:</i>")
        text_lines.append(f"┗<blockquote expandable><i>\"{parent_text}\"</i></blockquote>\n")

    text_lines.append(f"💬 <b>Izoh {current_index + 1}/{total_comments}</b>\n")
    text_lines.append(f"<blockquote expandable>{comment['text']}</blockquote>")

    caption = "\n".join(text_lines)

    # 🟢 replies_count parametringiz get_my_comments_keyboard ichiga beriladi
    keyboard = get_my_comments_keyboard(
        anime_id=anime_id,
        total_count=total_comments,
        current_index=current_index,
        comment_id=comment["id"],
        replies_count=replies_count  # <--- Shu yerda uzatiladi
    )

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
        if "message is not modified" not in e.message.lower():
            raise e

    await callback.answer()







@router.callback_query(F.data.startswith(("reply_comm:", "rep_page:")))
async def handle_comment_replies(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    
    # callback_data parse qilish: rep_page bo'lsa indeks keladi, bo'lmasa 0-indeks
    comment_id = int(parts[1])
    anime_id = int(parts[2])
    current_index = int(parts[3]) if len(parts) > 3 else 0

    comment_service = CommentService(session)

    # 1. Parallel ravishda asosiy izohni va javoblar ro'yxatini olamiz
    parent_comment, replies = await asyncio.gather(
        comment_service.get_comment_by_id(comment_id),
        comment_service.get_comment_replies(comment_id, limit=50, offset=0)
    )

    # ⚠️ 1-Talab: Agar javoblar bo'lmasa, Alert beriladi
    if not replies:
        await callback.answer(
            "💬 Hozircha bu izohingizga hech kim javob yozmagan.",
            show_alert=True
        )
        return

    total_replies = len(replies)

    # Index chegaradan chiqib ketmasligini ta'minlaymiz
    if current_index >= total_replies:
        current_index = total_replies - 1
    elif current_index < 0:
        current_index = 0

    # Joriy tanlangan javob
    current_reply = replies[current_index]
    
    # Javob bergan foydalanuvchi nomi va matni
    reply_user_name = current_reply.get("user", {}).get("full_name") or current_reply.get("user", {}).get("username") or "Foydalanuvchi"
    reply_text = current_reply.get("text", "")
    parent_text = parent_comment.get("text", "") if parent_comment else ""

    # 💬 Dizayn bo'yicha matnni shakllantirish
    text_lines = [
        "↩️ <b>Sizning izohingizga javoblar</b>\n",
        f"“<i>{parent_text}</i>”\n",
        f"👤 <b>{reply_user_name}</b>\n",
        f"<blockquote expandable>{reply_text}</blockquote>",
        f"\n💬 <b>Javob {current_index + 1}/{total_replies}</b>"
    ]

    caption = "\n".join(text_lines)

    # Keyboard yasash
    keyboard = get_comment_replies_keyboard(
        anime_id=anime_id,
        comment_id=comment_id,
        total_count=total_replies,
        current_index=current_index
    )

    # Xabarni yangilash
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
        if "message is not modified" not in e.message.lower():
            raise e

    await callback.answer()




# 1-BOSQICH: O'chirish tugmasi bosilganda tasdiqlash oynasiga o'tkazish
@router.callback_query(F.data.startswith("del_comm:"))
async def handle_delete_comment_ask(callback: CallbackQuery):
    parts = callback.data.split(":")
    comment_id = int(parts[1])
    anime_id = int(parts[2])

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
        if "message is not modified" not in e.message.lower():
            raise e

    await callback.answer()






@router.callback_query(F.data.startswith("del_comm_confirm:"))
async def handle_delete_comment_confirm(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    comment_id = int(parts[1])
    anime_id = int(parts[2])
    user_id = callback.from_user.id

    comment_service = CommentService(session)

    # 1. Bazadan va keshdan o'chiramiz
    success = await comment_service.delete_comment(
        comment_id=comment_id, 
        user_id=user_id, 
        anime_id=anime_id
    )

    if not success:
        await callback.answer("❌ Izohni o'chirib bo'lmadi yoki u allaqachon o'chirilgan.", show_alert=True)
    else:
        await callback.answer("🗑 Izoh muvaffaqiyatli o'chirildi!", show_alert=True)

    # 2. Qolgan barcha ishlarni (sonini tekshirish va xabarni edit qilishni) 
    # handle_my_comments funksiyasiga topshiramiz
    callback.data = f"my_comm:{anime_id}:0"
    await handle_my_comments(callback, session)