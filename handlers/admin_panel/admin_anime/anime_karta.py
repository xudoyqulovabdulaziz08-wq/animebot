import logging
import html
import math
from typing import Any, Optional
from sqlalchemy import select
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext

from database.models import Genre, Dubber
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
    """Xabarni xavfsiz o'chirish."""
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    except Exception as e:
        logger.warning(f"Xabarni o'chirishda kutilmagan xato: {e}")

async def safe_send(message: Message, **kwargs) -> Optional[Message]:
    """Xabarni xavfsiz yuborish."""
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
    """Xabarni ishonchli usulda yangilash zanjiri (Miltillashsiz edit qilish)."""
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
        logger.error(f"Xabar yuborishda kutilmagan xato: {e}", exc_info=True)
    return False


NAV_CACHE = {}

# =======================================================
# 🎬 ANIME KARTASINI YASASH (Optimallashtirilgan & Escaped)
# =======================================================
async def build_anime_card(session: Any, anime: dict, anime_id: int, page: int = 1, source: str = "all"):
    """
    🎬 Anime kartasi uchun caption va klaviaturani yasaydi.
    Barcha matnlar HTML injection'dan xavfsizlantirilgan va DB so'rovlari yengillashtirilgan.
    """
    title = html.escape(str(anime.get("title") or "Nomsiz anime"))
    anime_id_val = anime.get("anime_id", anime_id)
    year = html.escape(str(anime.get("year") or "—"))
    description = html.escape(str(anime.get("description") or "Tavsif kiritilmagan."))
    episodes_count = len(anime.get("episodes", []))

    languages = anime.get("languages", [])
    languages_str = html.escape(", ".join(languages)) if languages else "Mavjud emas"

    # Janrlarni yuklash (Agar service tayyor nomlarni bermagan bo'lsa, faqat Name ustunini olamiz)
    genre_names = anime.get("genre_names")
    if genre_names is None:
        genre_ids = anime.get("genres", [])
        if genre_ids:
            try:
                res = await session.execute(select(Genre.name).where(Genre.id.in_(genre_ids)))
                genre_names = res.scalars().all()
            except Exception as e:
                logger.error(f"❌ Janrlarni yuklashda xato: {e}")
                genre_names = []
        else:
            genre_names = []
    genres_str = html.escape(", ".join(genre_names)) if genre_names else "Mavjud emas"

    # Dubberlarni yuklash (Faqat Name ustuni yuklanadi)
    dubber_names = anime.get("dubber_names")
    if dubber_names is None:
        dubber_ids = anime.get("dubbers", [])
        if dubber_ids:
            try:
                res = await session.execute(select(Dubber.name).where(Dubber.id.in_(dubber_ids)))
                dubber_names = res.scalars().all()
            except Exception as e:
                logger.error(f"❌ Dubberlarni yuklashda xato: {e}")
                dubber_names = []
        else:
            dubber_names = []
    dubbers_str = html.escape(", ".join(dubber_names)) if dubber_names else "Mavjud emas"

    is_finished = anime.get("is_finished", False)
    if is_finished:
        finished_btn_text = "🟢 Tugallandi"
        finished_btn_style = "success"
    else:
        finished_btn_text = "🟡 Davom etmoqda"
        finished_btn_style = "primary"

    caption = (
        f"╔══════════════════╗\n"
        f"    🎬 <b>{title}</b>\n"
        f"╚══════════════════╝\n\n"
        f"📌 <b>Anime haqida ma'lumot:</b>\n"
        f"╔══════════════════╗\n"
        f"├ 🆔 Kod: <code>#{anime_id_val}</code>\n"
        f"├ 📅 Yil: <b>{year}</b>\n"
        f"├ ▶️ Qism: <b>{episodes_count}</b> \n"
        f"├ 🌐 Til: <b>{languages_str}</b>\n"
        f"├ 🎙 Dubber: <b>{dubbers_str}</b>\n"
        f"╚══════════════════╝\n"
        f"╔══════════════════╗\n"
        f"  🔮 Janrlar: <i>{genres_str}</i>\n"
        f"╚══════════════════╝\n\n"
        f"📝 <b>Tavsif:</b>\n"
        f"<blockquote expandable>{description}</blockquote>"
    )
    # Orqaga qaytish yo'nalishini aniqlash
    back_routes = {
        "all": f"list_anime_page:{page}",
        "contine": f"list_anime_contine_page:{page}",
        "end": f"list_anime_end_page:{page}"
    }
    back_callback = back_routes.get(source, f"list_anime_page:{page}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📹 Qism tahrirlash", callback_data=f"manage_episodes:{anime_id}", style="primary"),
            InlineKeyboardButton(text="🗑 O‘chirish", callback_data=f"del_anime:{anime_id}", style="danger")
        ],
        [
            InlineKeyboardButton(text=finished_btn_text, callback_data=f"anime_end:{anime_id}", style=finished_btn_style),
            InlineKeyboardButton(text="🎯 Anime turi", callback_data=f"anime_type:{anime_id}", style="primary"),
        ],
        [
            InlineKeyboardButton(text="🎬 Tizer edit", callback_data=f"tizer_edit:{anime_id}", style="primary"),
            InlineKeyboardButton(text="🧩 Anime edit", callback_data=f"edit_anime:{anime_id}", style="primary")
        ],
        [
            InlineKeyboardButton(text="🆔 MAL ID", callback_data=f"mal_id:{anime_id}", style="primary"),
            InlineKeyboardButton(text="📢 E‘lon qilish", callback_data=f"publish_episodes_chan:{anime_id}", style="primary")
        ],
        [
            InlineKeyboardButton(text="⬅️ Ro‘yxatga qaytish", callback_data=back_callback, style="danger")
        ]
    ])

    return caption, kb


# =======================================================
# 👁 ANIME DETALLARINI KO'RISH HANDLERI
# =======================================================
@router.callback_query(F.data.startswith("v_anime:"))
async def view_anime_details(callback: CallbackQuery, session: Any):
    data_parts = callback.data.split(":")
    user_id = callback.from_user.id
    
    if len(data_parts) < 2 or not data_parts[1].isdigit():
        await safe_answer(callback, "❌ Noto'g'ri anime ID!", show_alert=True)
        return
        
    anime_id = int(data_parts[1])
    
    # 📌 NAVIGATSIYA KESHINI TEKSHIRISH
    # 1. Agar tugmadan page va source kelsa keshni yangilaymiz
    if len(data_parts) >= 4:
        page = int(data_parts[2]) if data_parts[2].isdigit() else 1
        source = data_parts[3]
        NAV_CACHE[user_id] = {"page": page, "source": source}
    else:
        # 2. Agar sub-funksiyalardan (edit, tizer...) qaytgan bo'lsa, keshdan tiklaymiz
        cached_nav = NAV_CACHE.get(user_id, {"page": 1, "source": "all"})
        page = cached_nav["page"]
        source = cached_nav["source"]
        
    service = AnimeService(session=session)
    
    try:
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ Anime yuklashda xato: {e}")
        anime = None
        
    if not anime:
        await safe_answer(callback, "❌ Anime topilmadi yoki o‘chirilgan!", show_alert=True)
        return

    caption, kb = await build_anime_card(session, anime, anime_id, page=page, source=source)
    await safe_answer(callback)

    poster_id = anime.get("poster_id")
    
    await _safe_update_message(
        message=callback.message,
        caption=caption,
        reply_markup=kb,
        poster_id=poster_id
    )



