import logging
import html
from typing import Optional

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from services.comment_service import CommentService
from services.anime_service import AnimeService

logger = logging.getLogger("view_comments")
router = Router()

PAGE_SIZE = 10  # bir "sahifa"dagi index tugmalari soni (2 qator x 5)


# =======================================================
# 🧰 YORDAMCHI FUNKSIYALAR (boshqa fayllardagi bilan bir xil naqsh)
# =======================================================
async def safe_answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False) -> None:
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


def get_view_comments_keyboard(
    anime_id: int,
    total_count: int,
    current_index: int,
    comment_id: int,
    replies_count: int = 0,
    page_size: int = PAGE_SIZE,
) -> InlineKeyboardMarkup:
    keyboard = []

    # 1. Joriy index qaysi "sahifa"ga tegishli ekanini aniqlaymiz
    page_start = (current_index // page_size) * page_size
    page_end = min(page_start + page_size, total_count)

    # 2. Index tugmalari — 5 tadan qatorga
    row = []
    for i in range(page_start, page_end):
        is_active = i == current_index
        row.append(
            InlineKeyboardButton(
                text=f"• {i + 1} •" if is_active else str(i + 1),
                callback_data=f"view_comm:{anime_id}:{i}",
                style="success" if is_active else None
            )
        )
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # 3. "Sahifalar orasida" navigatsiya (◀️ Oldingi | 📄 1/2 | Keyingi▶️)
    total_pages = (total_count + page_size - 1) // page_size
    if total_pages > 1:
        current_page = page_start // page_size
        nav_row = []
        if current_page > 0:
            nav_row.append(
                InlineKeyboardButton(
                    text="◀️ Oldingi",
                    callback_data=f"view_comm:{anime_id}:{page_start - page_size}",
                    style="primary"
                )
            )
        nav_row.append(
            InlineKeyboardButton(
                text=f"📄 {current_page + 1}/{total_pages}",
                callback_data="noop",
                style="primary"
            )
        )
        if page_end < total_count:
            nav_row.append(
                InlineKeyboardButton(
                    text="Keyingi▶️",
                    callback_data=f"view_comm:{anime_id}:{page_end}",
                    style="primary"
                )
            )
        keyboard.append(nav_row)

    # 4. Javob yozish / javoblarni ko'rish
    keyboard.append([
        InlineKeyboardButton(
            text="↩️ Javob yozish",
            callback_data=f"reply_to:{anime_id}:{comment_id}",
            style="primary"
        ),
        InlineKeyboardButton(
            text=f"💬 {replies_count} ta javob",
            callback_data=f"reply_all_commend:{comment_id}:{anime_id}",
            style="primary"
        )
    ])

    # 5. Orqaga
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"anime_comment:{anime_id}", style="danger")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# =======================================================
# 📄 "SAHIFA KO'RSATKICHI" TUGMASI — hech narsa qilmaydi
# =======================================================
@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery) -> None:
    await safe_answer(callback)


# =======================================================
# 💬 IZOHLARNI KO'RISH (kirish nuqtasi va index bo'yicha sahifalash)
# =======================================================
@router.callback_query(F.data.startswith("view_comments:") | F.data.startswith("view_comm:"))
async def view_comments_handler(callback: CallbackQuery, session) -> None:
    try:
        parts = callback.data.split(":")
        anime_id = int(parts[1])
        current_index = int(parts[2]) if len(parts) > 2 and parts[2] else 0
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    comment_service = CommentService(session=session)
    anime_service = AnimeService(session=session)

    try:
        # 1. Animening BARCHA izohlari ID ro'yxatini olamiz (Kesh / DB)
        comment_ids = await comment_service.get_anime_comment_ids(anime_id)
        total_comments = len(comment_ids)

        if total_comments == 0:
            await safe_answer(
                callback,
                "💬 Bu anime uchun hali izohlar yo'q.\n"
                "✍️ Birinchi bo'lib fikringizni qoldiring!",
                show_alert=True
            )
            return

        # 2. Index chegarasini to'g'rilash (chegaradan chiqib ketmasligi uchun)
        if current_index >= total_comments:
            current_index = total_comments - 1
        elif current_index < 0:
            current_index = 0

        # 3. Hozirgi index'dagi izohning ANIQ ID'sini olamiz va tafsilotini yuklaymiz
        target_comment_id = comment_ids[current_index]
        comment = await comment_service.get_comment_by_id(target_comment_id)

        if not comment:
            await safe_answer(callback, "Izoh topilmadi yoki o'chirilgan.", show_alert=True)
            return

        # 4. Ma'lumotlarni tayyorlash
        anime = await anime_service.get_anime(anime_id)
        replies_count = comment.get("replies_count", 0)
        anime_title = anime.get("title", "Anime") if isinstance(anime, dict) else getattr(anime, "title", "Anime")

        author = comment.get("user") or {}
        user_name = author.get("username") or author.get("full_name") or "Foydalanuvchi"

        text = (
            f"💬 <b>Izohlar ko'rish ({current_index + 1}/{total_comments})</b>\n\n"
            f"🎬 {html.escape(str(anime_title))}\n"
            f"📃 Jami: {total_comments} ta izoh\n\n"
            f"👤 {html.escape(str(user_name))}\n"
            f"<blockquote expandable>{html.escape(str(comment.get('text', '')))}</blockquote>\n"
        )
        
        # Bu yerda klaviaturani chaqirib message'ni edit qilasiz...

        keyboard = get_view_comments_keyboard(
            anime_id=anime_id,
            total_count=total_comments,
            current_index=current_index,
            comment_id=comment["id"],
            replies_count=replies_count
        )

        try:
            if callback.message.photo or callback.message.document:
                await callback.message.edit_caption(caption=text, reply_markup=keyboard, parse_mode="HTML")
            else:
                await callback.message.edit_text(text=text, reply_markup=keyboard, parse_mode="HTML")
        except TelegramBadRequest as e:
            err_msg = str(e).lower()
            if "message is not modified" in err_msg:
                pass
            elif "there is no caption" in err_msg or "message has no caption" in err_msg:
                try:
                    await callback.message.edit_text(text=text, reply_markup=keyboard, parse_mode="HTML")
                except TelegramBadRequest as e2:
                    if "message is not modified" not in str(e2).lower():
                        logger.error(f"❌ view_comments fallback edit xatosi: {e2}")
            elif "message to edit not found" in err_msg or "message can't be edited" in err_msg:
                try:
                    await callback.message.answer(text=text, reply_markup=keyboard, parse_mode="HTML")
                except (TelegramBadRequest, TelegramForbiddenError) as e2:
                    logger.warning(f"view_comments: yangi xabar yuborilmadi: {e2}")
            else:
                logger.error(f"❌ view_comments edit xatosi: {e}")
        except TelegramForbiddenError:
            pass

        await safe_answer(callback)

    except Exception as e:
        logger.error(f"❌ view_comments_handler kutilmagan xatolik: {e}", exc_info=True)
        await safe_answer(callback, "❌ Tizimda xatolik yuz berdi.", show_alert=True)