import logging
from typing import Any, Optional
from aiogram import Router, F, html
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from services.anime_service import AnimeService

router = Router()
logger = logging.getLogger(__name__)


async def safe_answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False) -> None:
    """Telegramda eskirgan callback xatolarining oldini olish uchun xavfsiz javob."""
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


@router.callback_query(F.data.startswith("manage_episodes:"))
async def manage_episodes_handler(callback: CallbackQuery, session: Any):
    # Interfeys qotib qolmasligi uchun darhol va xavfsiz javob beramiz
    await safe_answer(callback, "Yuklanmoqda...")
    
    try:
        anime_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return
    
    # 1. DB/Cache dan animeni xavfsiz yuklaymiz
    service = AnimeService(session=session)
    try:
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ Tahrirlash uchun anime yuklashda xato yuz berdi: {e}", exc_info=True)
        anime = None

    if not anime:
        try:
            await callback.message.answer("❌ Anime topilmadi yoki o‘chirilgan!")
        except Exception:
            pass
        return

    # HTML parsing xatoliklariga qarshi anime nomini himoyalaymiz
    raw_title = anime.get("title", "Nomsiz anime")
    title = html.quote(str(raw_title))
    
    episodes = anime.get("episodes", [])
    episodes_count = len(episodes)

    # 2. Qismlar boshqaruvi uchun maxsus dizayn
    caption = (
        f"╔══════════════════╗\n"
        f"  ⚙️ <b>Qismlarni boshqarish</b>\n"
        f"╚══════════════════╝\n\n"
        f"🎬 Anime: <b>{title}</b>\n"
        f"🔢 Mavjud qismlar soni: <b>{episodes_count} ta</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 {html.italic('Quyidagi tugmalar orqali ushbu animening qismlarini qo‘shishingiz, o‘chirishingiz yoki fayllarini yangilashingiz mumkin.')}"
    )

    # 3. Dinamik inline tugmalar ierarxiyasi (style=... parametrlari olib tashlandi!)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Qism qo‘shish", callback_data=f"add_episode:{anime_id}", style="success")
        ],
        [
            InlineKeyboardButton(text="▶️ Qismlarni ko‘rish", callback_data=f"view_episodes_list:{anime_id}", style="primary")
        ],
        [
            InlineKeyboardButton(text="💎 VIP qismlar", callback_data=f"vip:{anime_id}", style="primary")
        ],
        [
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"v_anime:{anime_id}:1", style="danger")
        ]
    ])

    # 4. Posterni o'chirmasdan, uning ostidagi matn va tugmalarni silliq yangilash
    try:
        # Agar xabarda media (photo/video) bo'lsa, caption va reply_markup o'zgaradi
        await callback.message.edit_caption(caption=caption, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "message is not modified" in msg:
            return  # Eski ma'lumot tursa, xato bermaydi
        
        # Agar xabar faqat matndan iborat bo'lsa (poster_id bo'lmagan holatda fallback)
        try:
            await callback.message.edit_text(text=caption, reply_markup=kb, parse_mode="HTML")
        except TelegramBadRequest as err:
            if "message is not modified" not in str(err).lower():
                logger.warning(f"edit_text orqali ham tahrirlab bo'lmadi: {err}")
        except Exception as err:
            logger.error(f"❌ Panelni yangilashda xato: {err}", exc_info=True)
    except Exception as e:
        logger.error(f"❌ Kutilmagan tahrirlash xatosi: {e}", exc_info=True)