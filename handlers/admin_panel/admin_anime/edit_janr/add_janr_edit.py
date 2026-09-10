import logging
import html
from typing import Any, Optional
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

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

async def _safe_edit_by_id(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup
) -> bool:
    """Message ID bo'yicha xabarni xavfsiz tahrirlash (text hamda caption bilan ishlash)."""
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup, parse_mode="HTML"
        )
        return True
    except TelegramBadRequest as e:
        err = str(e).lower()
        if "message is not modified" in err:
            return True
        if "there is no text in the message to edit" in err or "message to edit not found" in err:
            try:
                await bot.edit_message_caption(
                    chat_id=chat_id, message_id=message_id, caption=text, reply_markup=reply_markup, parse_mode="HTML"
                )
                return True
            except TelegramBadRequest as e2:
                if "message is not modified" in str(e2).lower():
                    return True
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Xabarni ID bo'yicha tahrirlashda xato: {e}")
    return False

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
        logger.error(f"Xabar yuborishda kutilmagan xato: {e}", exc_info=True)
    return False

class TempGenreStates(StatesGroup):
    waiting_genres = State()  # Janrlar matnini kutish
    confirm_save = State()     # Tasdiqlash oynasi


# ================= 1. JANR QO'SHISH MENYUSI =================
@router.callback_query(F.data == "add_janr_edit")
async def add_janr_edit_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(TempGenreStates.waiting_genres)
    await state.update_data(main_msg_id=callback.message.message_id)
    
    text = (
        "🎭 <b>Janr qo'shish</b>\n\n"
        "Iltimos, bazaga qo‘shmoqchi bo‘lgan janrlarni <b>'vergul'</b> orqali ajratib yuboring.\n\n"
        "📌 Masalan: <b>Comedy, Action, Drama</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="janr_menu", style="danger")]
    ])
    
    await safe_answer(callback)
    await _safe_update_message(callback.message, caption=text, reply_markup=kb)


# ================= 2. TEXT QABUL QILISH VA FORMATLASH =================
@router.message(TempGenreStates.waiting_genres, F.text)
async def process_raw_genres(message: Message, state: FSMContext):
    await safe_delete(message)
    
    state_data = await state.get_data()
    main_msg_id = state_data.get("main_msg_id")
    
    raw_text = message.text
    # Janr nomlarini tozalab, sarlavha ko'rinishiga keltiramiz
    genres_list = [
        html.escape(g.strip().strip("'\"").title()) 
        for g in raw_text.split(",") 
        if g.strip()
    ]
    # Takrorlangan ismlarni olib tashlaymiz
    genres_list = list(dict.fromkeys(genres_list))
    
    kb_retry = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="janr_menu", style="danger")]
    ])
    
    if not genres_list:
        err_text = (
            "❌ <b>Hech qanday janr aniqlanmadi!</b>\n\n"
            "Iltimos, janrlarni vergul bilan ajratgan holda qayta yuboring."
        )
        if main_msg_id:
            await _safe_edit_by_id(message.bot, message.chat.id, main_msg_id, err_text, kb_retry)
        return

    await state.update_data(parsed_genres=genres_list)
    await state.set_state(TempGenreStates.confirm_save)
    
    preview_genres = "\n".join([f"🎭 {g}" for g in genres_list])
    
    text = (
        "📝 <b>Quyidagi janrlar bazaga saqlashga tayyorlandi:</b>\n\n"
        f"{preview_genres}\n\n"
        "👇 Tasdiqlash uchun quyidagi tugmani bosing:"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Bazaga saqlash", callback_data="db_save_quick_genres", style="success")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="janr_menu", style="danger")]
    ])
    
    if main_msg_id:
        await _safe_edit_by_id(message.bot, message.chat.id, main_msg_id, text, kb)


# ================= 3. YAKUNIY BAZAGA SAQLASH =================
@router.callback_query(TempGenreStates.confirm_save, F.data == "db_save_quick_genres")
async def save_genres_to_db(callback: CallbackQuery, state: FSMContext, session: Any):
    data = await state.get_data()
    genres_list: list[str] = data.get("parsed_genres", [])
    await state.clear()
    
    await safe_answer(callback, "⏳ Bazaga yozilmoqda...")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="janr_menu", style="primary")]
    ])
    
    try:
        anime_service = AnimeService(session)
        added_count, skipped_genres = await anime_service.add_quick_genres(genres_list)
        
        result_text = "✅ <b>Janrlar muvaffaqiyatli yakunlandi!</b>\n\n"
        result_text += f"➕ <b>Yangi qo‘shilganlar:</b> {added_count} ta\n"
        
        if skipped_genres:
            skipped_str = ", ".join(skipped_genres)
            result_text += "⚠️ <b>Bazada allaqachon bor bo‘lganlar (tashlab ketildi):</b>\n"
            result_text += f"<code>{skipped_str}</code>\n"
            
        result_text += "\n💡 Endi anime yuklash jarayonida ushbu janrlarni tanlashingiz mumkin."
        
        await _safe_update_message(
            callback.message, 
            caption=result_text, 
            reply_markup=kb
        )
        
    except Exception as e:
        logger.error(f"Janrlarni saqlashda xatolik: {e}", exc_info=True)
        err_msg = f"❌ Janrlarni saqlashda xatolik yuz berdi: <code>{html.escape(str(e))}</code>"
        
        await _safe_update_message(
            callback.message, 
            caption=err_msg, 
            reply_markup=kb
        )