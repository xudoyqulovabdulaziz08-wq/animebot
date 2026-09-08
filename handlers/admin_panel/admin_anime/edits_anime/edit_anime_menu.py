import logging
import html
from typing import Any, Optional
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter

from handlers.admin_panel.admin_anime.anime_karta import build_anime_card
from services.anime_service import AnimeService

router = Router()
logger = logging.getLogger(__name__)









# =======================================================
# 🧰 YORDAMCHI FUNKSIYALAR (Telegram xatolaridan himoya)
# =======================================================
async def safe_answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False) -> None:
    """CallbackQuery'ga xavfsiz javob berish (kutilgan xatoliklarni yutish)."""
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "query is too old" not in msg and "query id is invalid" not in msg and "response timeout expired" not in msg:
            logger.warning(f"safe_answer xatosi: {e}")
    except TelegramForbiddenError:
        pass
    except Exception as e:
        logger.warning(f"safe_answer kutilmagan xato: {e}")

async def safe_delete(message: Message) -> None:
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    except Exception as e:
        logger.warning(f"Xabarni o'chirishda kutilmagan xato: {e}")

async def safe_send(message: Message, **kwargs) -> Optional[Message]:
    try:
        return await message.answer(**kwargs)
    except TelegramRetryAfter as e:
        logger.warning(f"Flood control: retry_after={e.retry_after}")
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError) as e:
        logger.warning(f"Xabar yuborishda xato: {e}")
    except Exception as e:
        logger.error(f"Xabar yuborishda kutilmagan xato: {e}", exc_info=True)
    return None


async def _safe_update_message(
    message: Any,
    caption: str,
    reply_markup: InlineKeyboardMarkup,
    poster_id: Optional[str] = None
) -> bool:
    """Xabarni ishonchli usulda yangilash zanjiri."""
    if poster_id:
        try:
            new_media = InputMediaPhoto(media=poster_id, caption=caption, parse_mode="HTML")
            await message.edit_media(media=new_media, reply_markup=reply_markup)
            return True
        except TelegramForbiddenError:
            return False
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return True
        except Exception:
            pass
        
        try:
            await message.edit_caption(caption=caption, reply_markup=reply_markup, parse_mode="HTML")
            return True
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return True
        except Exception:
            pass
    else:
        try:
            await message.edit_text(text=caption, reply_markup=reply_markup, parse_mode="HTML")
            return True
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return True
        except Exception:
            pass
        
        try:
            await message.edit_caption(caption=caption, reply_markup=reply_markup, parse_mode="HTML")
            return True
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return True
        except Exception:
            pass

    try:
        await message.delete()
    except Exception:
        pass
    
    try:
        await message.answer(text=caption, reply_markup=reply_markup, parse_mode="HTML")
        return True
    except Exception as e:
        logger.error(f"Yangi xabar yuborishda xato: {e}", exc_info=True)
    return False











@router.callback_query(F.data.startswith("edit_anime:"))
async def process_edit_anime_menu(callback: CallbackQuery, session: Any):
    """Anime tahrirlash menyusini ko'rsatish handleri."""
    # 1. Callback'ga darhol va xavfsiz javob beramiz
    await safe_answer(callback, "Tahrirlash menyusi...")

    # 2. Callback datadan anime_id ni xavfsiz ajratib olamiz
    try:
        anime_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await safe_answer(callback, "🚨 Noto'g'ri anime ID!", show_alert=True)
        return

    # 3. Anime xizmatidan ma'lumotlarni yuklaymiz
    service = AnimeService(session=session)
    try:
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ Tahrirlash menyusida animeni yuklashda xato: {e}", exc_info=True)
        anime = None

    if not anime:
        await safe_answer(callback, "❌ Anime topilmadi yoki o‘chirilgan!", show_alert=True)
        return

    # 4. HTML teg xatoliklariga qarshi animening nomini tozalaymiz
    raw_title = anime.get("title") or "Nomsiz anime"
    anime_title = html.escape(str(raw_title))

    # 5. Qisqa va tartibli tugmalar paneli
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Nomi(english)", callback_data=f"edit_fields:{anime_id}", style="primary"),
            InlineKeyboardButton(text="📅 Yili", callback_data=f"edit_field:year:{anime_id}", style="primary")
        ],
        [
            InlineKeyboardButton(text="🌐 Tili", callback_data=f"edit_field:lang:{anime_id}", style="primary"),
            InlineKeyboardButton(text="🔮 Janr", callback_data=f"edit_genre_menu:{anime_id}", style="primary")
        ],
        [
            InlineKeyboardButton(text="📝 Tasnif", callback_data=f"edit_field:desc:{anime_id}", style="primary"),
            InlineKeyboardButton(text="🖼 Poster", callback_data=f"edit_field:poster:{anime_id}", style="primary")
        ],
        [
            InlineKeyboardButton(text="🎙️ Dubber", callback_data=f"edit_field:dubber:{anime_id}", style="primary")
        ],
        [
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"v_anime:{anime_id}:1", style="danger")
        ]
    ])

    # 6. Sarlavha matni
    text = (
        f"⚙️ <b>Siz anime tahrirlash bo'limidasiz!</b>\n"
        f"🎬 Tanlangan anime: <u>{anime_title}</u>\n\n"
        f"<i>Iltimos, o'zgartirmoqchi bo'lgan ma'lumotingizni quyidagi qisqa tugmalardan tanlang:</i>"
    )

    # 7. Xabarni yordamchi funksiya orqali xavfsiz yangilash
    poster_id = anime.get("poster_id")
    success = await _safe_update_message(
        message=callback.message,
        caption=text,
        reply_markup=kb,
        poster_id=poster_id
    )

    if not success:
        logger.warning(f"ID:{anime_id} anime tahrirlash menyusini yangilashda xatolik yuz berdi.")

