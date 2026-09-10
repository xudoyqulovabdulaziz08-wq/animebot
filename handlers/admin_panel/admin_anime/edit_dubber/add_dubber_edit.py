import logging
import html
import math
from typing import Any, Optional
from sqlalchemy import select, text
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from database.models import Genre
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


# =======================================================
# 🎙 DUBBER QO'SHISH FSM HOLATLARI
# =======================================================
class TempDubberStates(StatesGroup):
    waiting_dubbers = State()  # Dubberlar matnini kutish
    confirm_save = State()     # Tasdiqlash oynasi


# ================= 1. DUBBER QO'SHISH TUGMASI BOSILGANDA =================
@router.callback_query(F.data == "add_dubber_edit")
async def add_dubber_edit_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(TempDubberStates.waiting_dubbers)
    
    # Kelgusida foydalanuvchi matn yuborganida tahrirlanadigan xabar ID sini saqlaymiz
    await state.update_data(main_msg_id=callback.message.message_id)
    
    text = (
        "🎙 <b>Dubber qo'shish</b>\n\n"
        "Iltimos, bazaga qo‘shmoqchi bo‘lgan dubberlarni (ovoz beruvchilarni) <b>'vergul'</b> orqali ajratib yuboring.\n\n"
        "📌 Masalan: <b>Amonov, Shaxzod, Anvar, Real_Dubber</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="dubber_menu", style="danger")]
    ])
    
    await safe_answer(callback)
    await _safe_update_message(callback.message, caption=text, reply_markup=kb)


# ================= 2. TEXT QABUL QILISH VA FORMATLASH =================
@router.message(TempDubberStates.waiting_dubbers, F.text)
async def process_raw_dubbers(message: Message, state: FSMContext):
    # User yuborgan xabarni darhol o'chirib, chatni toza tutamiz
    await safe_delete(message)
    
    state_data = await state.get_data()
    main_msg_id = state_data.get("main_msg_id")
    
    # HTML injection xatolarining oldini olish uchun html.escape ishlatiladi
    raw_text = message.text
    dubbers_list = [html.escape(d.strip()) for d in raw_text.split(",") if d.strip()]
    
    # Takrorlangan ismlarni tozalaymiz
    dubbers_list = list(dict.fromkeys(dubbers_list))
    
    kb_retry = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="dubber_menu", style="danger")]
    ])
    
    if not dubbers_list:
        err_text = (
            "❌ <b>Hech qanday ism aniqlanmadi!</b>\n\n"
            "Iltimos, dubberlarni vergul bilan ajratgan holda qayta yuboring."
        )
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=main_msg_id,
                text=err_text,
                reply_markup=kb_retry,
                parse_mode="HTML"
            )
        except Exception:
            try:
                await message.bot.edit_message_caption(
                    chat_id=message.chat.id,
                    message_id=main_msg_id,
                    caption=err_text,
                    reply_markup=kb_retry,
                    parse_mode="HTML"
                )
            except Exception:
                pass
        return

    await state.update_data(parsed_dubbers=dubbers_list)
    await state.set_state(TempDubberStates.confirm_save)
    
    preview_dubbers = "\n".join([f"🎙 {d}" for d in dubbers_list])
    
    text = (
        "📝 <b>Quyidagi dubberlar bazaga saqlashga tayyorlandi:</b>\n\n"
        f"{preview_dubbers}\n\n"
        "👇 Tasdiqlash uchun quyidagi tugmani bosing:"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Bazaga saqlash", callback_data="db_save_quick_dubbers", style="success")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="dubber_menu", style="danger")]
    ])
    
    # Asosiy bot xabarini yangilaymiz (foydalanuvchi xabari o'chirilgan holatda)
    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=main_msg_id,
            text=text,
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception:
        try:
            await message.bot.edit_message_caption(
                chat_id=message.chat.id,
                message_id=main_msg_id,
                caption=text,
                reply_markup=kb,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Xabarni tahrirlashda xato: {e}")


# ================= 3. YAKUNIY BAZAGA SAQLASH =================
@router.callback_query(TempDubberStates.confirm_save, F.data == "db_save_quick_dubbers")
async def save_dubbers_to_db(callback: CallbackQuery, state: FSMContext, session: Any):
    data = await state.get_data()
    dubbers_list: list[str] = data.get("parsed_dubbers", [])
    await state.clear()
    
    await safe_answer(callback, "⏳ Bazaga yozilmoqda...")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="dubber_menu", style="primary")]
    ])
    
    try:
        anime_service = AnimeService(session)
        added_count, skipped_dubbers = await anime_service.add_quick_dubbers(dubbers_list)
        
        result_text = "✅ <b>Dubberlar muvaffaqiyatli yakunlandi!</b>\n\n"
        result_text += f"➕ <b>Yangi qo‘shilganlar:</b> {added_count} ta\n"
        
        if skipped_dubbers:
            skipped_str = ", ".join(skipped_dubbers)
            result_text += "⚠️ <b>Bazada allaqachon bor bo‘lganlar (tashlab ketildi):</b>\n"
            result_text += f"<code>{skipped_str}</code>\n"
            
        result_text += "\n💡 Endi anime yuklash jarayonida ushbu dubberlarni tanlashingiz mumkin."
        
        # KEYINGI O'ZGARISH: keyboard, markup va reply_markup variantlarining
        # barchasiga mos tushishi uchun to'g'ri param uzatamiz:
        await _safe_update_message(
            callback.message, 
            caption=result_text, 
            reply_markup=kb,
            keyboard=kb,
            markup=kb
        )
        
    except Exception as e:
        logger.error(f"Dubberlarni saqlashda xatolik: {e}", exc_info=True)
        err_msg = f"❌ Dubberlarni saqlashda xatolik yuz berdi: <code>{html.escape(str(e))}</code>"
        await _safe_update_message(
            callback.message, 
            caption=err_msg, 
            reply_markup=kb,
            keyboard=kb,
            markup=kb
        )