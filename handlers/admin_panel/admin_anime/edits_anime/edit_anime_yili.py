
import logging
import html
from typing import Any, Optional
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext

from services.anime_service import AnimeService
from aiogram.fsm.state import StatesGroup, State
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
        logger.error(f"Yangi xabar yuborishda xato: {e}", exc_info=True)
    return False



class EditAnimeStates(StatesGroup):
    waiting_for_new_year = State()          # 📅 Yangi yilni kiritish holati
    waiting_for_confirmation = State()      # ❓ Tasdiqlash holati (Ha/Yo'q)


# =====================================================================
# 📑 1-QADAM: "📅 Yili" tugmasi bosilganda holatga (State) o'tkazish
# =====================================================================
@router.callback_query(F.data.startswith("edit_field:year:"))
async def edit_anime_year_start(callback: CallbackQuery, state: FSMContext):
    anime_id = int(callback.data.split(":")[2])
    
    # Kerakli ID larni holat keshiga yozib qo'yamiz
    await state.update_data(edit_anime_id=anime_id, main_msg_id=callback.message.message_id)
    await state.set_state(EditAnimeStates.waiting_for_new_year)
    
    text = (
        "📅 <b>Yangi chiqish yilini kiritish:</b>\n\n"
        "Iltimos, animening yangi yilini faqat son shaklida kiriting.\n"
        "<i>(Cheklov: 1800 - 2050 yillar oralig'ida bo'lishi kerak)</i>"
    )
    
    # Bekor qilish tugmasini qo'shish tavsiya etiladi (xavfsiz qaytish uchun)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"force_refresh_edit:{anime_id}", style="danger")]
    ])
    
    await safe_answer(callback, "Yil tahrirlash boshlandi")
    await _safe_update_message(callback.message, caption=text, reply_markup=kb)


# =====================================================================
# 📑 2-QADAM: Admin yangi yil yuborganda tekshirish (Validatsiya) va Ha/Yo'q so'rash
# =====================================================================
@router.message(EditAnimeStates.waiting_for_new_year, F.text)
async def process_new_anime_year(message: Message, state: FSMContext):
    input_text = message.text.strip()
    state_data = await state.get_data()
    
    anime_id = state_data.get("edit_anime_id")
    main_msg_id = state_data.get("main_msg_id")
    
    # 🗑 Toza interfeys uchun admin yuborgan xabarni darhol o'chiramiz
    await safe_delete(message)
    
    # Orqaga qaytish tugmasi (xato kiritsa qotib qolmasligi uchun)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"force_refresh_edit:{anime_id}", style="danger")]
    ])

    # 🛑 VALIDATSIYA: Kiritilgan matn faqat son ekanligini tekshiramiz
    if not input_text.isdigit():
        error_text = (
            "⚠️ <b>Xato kiritish!</b>\n\n"
            f"Siz kiritgan ma'lumot: <code>{input_text}</code>\n"
            "Iltimos, yilni faqat <b>butun son</b> shaklida yuboring! (Masalan: 2024)"
        )
        try:
            await message.bot.edit_message_caption(
                chat_id=message.chat.id, message_id=main_msg_id, caption=error_text, reply_markup=cancel_kb, parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Yil xatosi xabarida xato: {e}")
        return

    new_year = int(input_text)

    # 🛑 VALIDATSIYA: 1800 va 2050 oralig'ida ekanligini tekshiramiz
    if not (1800 <= new_year <= 2050):
        error_text = (
            "⚠️ <b>Yil oralig'i noto'g'ri!</b>\n\n"
            f"Siz kiritgan yil: <code>{new_year}</code>\n"
            "Yil faqat <b>1800 va 2050 yillar oralig'ida</b> bo'lishi shart!"
        )
        try:
            await message.bot.edit_message_caption(
                chat_id=message.chat.id, message_id=main_msg_id, caption=error_text, reply_markup=cancel_kb, parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Yil xatosi xabarida xato: {e}")
        return

    # Validatsiyadan o'tsa, keshga saqlaymiz
    await state.update_data(new_anime_year=new_year)
    
    # Tasdiqlash tugmalari
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha", callback_data="confirm_year_edit:yes", style="success"),
            InlineKeyboardButton(text="❌ Yo'q", callback_data="confirm_year_edit:no", style="danger")
        ]
    ])
    
    confirm_text = (
        f"❓ <b>Anime chiqish yili o'zgartirilsinmi?</b>\n\n"
        f"📅 Yangi yil: <code>{new_year}</code>"
    )
    
    # Tasdiqlash holatiga o'tkazib, tepadagi poster matnini o'zgartiramiz
    await state.set_state(EditAnimeStates.waiting_for_confirmation)
    try:
        await message.bot.edit_message_caption(
            chat_id=message.chat.id,
            message_id=main_msg_id,
            caption=confirm_text,
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Yilni tasdiqlash xabarida xato: {e}")


# =====================================================================
# 📑 3-QADAM: Yil tasdiqlanganda (Ha yoki Yo'q) bosilishi
# =====================================================================
@router.callback_query(EditAnimeStates.waiting_for_confirmation, F.data.startswith("confirm_year_edit:"))
async def save_or_cancel_anime_year(callback: CallbackQuery, state: FSMContext, session: Any):
    action = callback.data.split(":")[1]
    state_data = await state.get_data()
    
    anime_id = state_data.get("edit_anime_id")
    new_year = state_data.get("new_anime_year")
    
    # ❌ AGAR ADMIN "YO'Q" DEB BEKOR QILSA
    if action == "no":
        await safe_answer(callback, "Tahrirlash bekor qilindi.", show_alert=True)
        await state.clear()
        
        await safe_delete(callback.message)
            
        cloned_callback = callback.model_copy(update={"data": f"edit_anime:{anime_id}"})
        from handlers.admin_panel.admin_anime.edit_anime import process_edit_anime_menu
        await process_edit_anime_menu(cloned_callback, session)
        return

    # ✅ AGAR ADMIN "HA" DEB TASDIQLASA
    await safe_answer(callback, "Bazaga yozilmoqda...")
    
    success = False
    try:
        service = AnimeService(session=session)
        success = await service.update_anime(
            anime_id=anime_id, 
            update_data={"year": new_year}
        )
    except Exception as e:
        logger.error(f"DB Update Year error: {e}")

    await state.clear()

    if not success:
        error_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⚙️ Tahrirlashga qaytish", callback_data=f"force_refresh_edit:{anime_id}", style="danger")
        ]])
        await _safe_update_message(
            message=callback.message,
            caption="❌ <b>Xatolik:</b> Yil ma'lumotini saqlashda texnik xato yuz berdi.",
            reply_markup=error_kb
        )
        return

    # Muvaffaqiyatli xabar va refresh tugmasi
    success_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Tahrirlashga qaytish", callback_data=f"force_refresh_edit:{anime_id}", style="danger")]
    ])
    
    await _safe_update_message(
        message=callback.message,
        caption=f"✅ <b>Anime chiqish yili muvaffaqiyatli o'zgartirildi!</b>\n\n📅 Yangi yil: <code>{new_year}</code>",
        reply_markup=success_kb
    )