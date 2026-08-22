import logging
from typing import Any, Optional

from aiogram import Router, F, html
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramNetworkError,
)
from aiogram.fsm.context import FSMContext

router = Router()

# 1. Logger to'g'ri sozlandi
logger = logging.getLogger(__name__)

# =======================================================
# 🧰 YORDAMCHI FUNKSIYALAR (Telegram xatolaridan himoya)
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

async def safe_delete(message: Message) -> None:
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
    except Exception as e:
        logger.warning(f"Xabarni o'chirishda kutilmagan xato: {e}")

async def safe_send(message: Message, text: str, **kwargs) -> Optional[Message]:
    try:
        return await message.answer(text=text, **kwargs)
    except TelegramRetryAfter as e:
        logger.warning(f"Flood control: retry_after={e.retry_after}")
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError) as e:
        logger.warning(f"Xabar yuborishda xato: {e}")
    except Exception as e:
        logger.error(f"Xabar yuborishda kutilmagan xato: {e}", exc_info=True)
    return None

# =======================================================
# 🎬 ANIME TYPE MENU
# =======================================================
@router.callback_query(F.data.startswith("anime_type:"))
async def process_anime_type(callback: CallbackQuery, state: FSMContext):
    await safe_answer(callback)
    
    # 1. Tanlangan turni ajratib olib, FSM state'ga saqlaymiz
    selected_type = callback.data.split(":")[1]
    await state.update_data(selected_type=selected_type) 
    
    text = (
        f"📚 {html.bold('Anime turini tanlang')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Anime turini tanlab, siz ushbu turdagi animelarni boshqarishingiz mumkin."
    )

    # 2. Qaysi tugma bosilgan bo'lsa, o'shanga yashil nuqta (🟢) qo'shamiz, qolganlariga odatiy belgi (🔹 yoki hech narsa)
    tv_text = "🟢 📺 TV Series (Tanlandi)" if selected_type == "tv_series" else "📺 TV Series"
    btn_style_tv = "success" if selected_type == "tv_series" else "primary"
    movie_text = "🟢 🎬 Movie (Tanlandi)" if selected_type == "movie" else "🎬 Movie"
    btn_style_movie = "success" if selected_type == "movie" else "primary"
    ova_text = "🟢 🎥 OVA (Tanlandi)" if selected_type == "ova" else "🎥 OVA"
    btn_style_ova = "success" if selected_type == "ova" else "primary"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            # Sizning style o'zgaruvchilaringiz joyida qoldirildi
            [InlineKeyboardButton(text=tv_text, callback_data="anime_type:tv_series", style=btn_style_tv)],
            [InlineKeyboardButton(text=movie_text, callback_data="anime_type:movie", style=btn_style_movie)],
            [InlineKeyboardButton(text=ova_text, callback_data="anime_type:ova", style=btn_style_ova)]
        ]
    )
    
    try:
        # Xabar turi tekshiriladi (Rasm/Video bo'lsa caption, aks holda text o'zgaradi)
        if callback.message.photo or callback.message.video or callback.message.document:
            await callback.message.edit_caption(
                caption=text, 
                reply_markup=kb, 
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                text=text, 
                reply_markup=kb, 
                parse_mode="HTML"
            )
    except TelegramBadRequest as e:
        # Foydalanuvchi bir xil tugmani qayta bosaversa, chiqadigan xato yashirildi
        if "message is not modified" in str(e).lower():
            pass
        else:
            logger.warning(f"Xabarni tahrirlashda xato: {e}")
    except Exception as e:
        logger.error(f"Anime turini tanlashda kutilmagan xatolik yuz berdi: {e}")