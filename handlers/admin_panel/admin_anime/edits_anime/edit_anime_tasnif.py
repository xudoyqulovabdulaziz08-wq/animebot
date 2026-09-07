
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
    waiting_for_new_desc = State()          # 📝 Yangi tasnifni kiritish holati
    waiting_for_confirmation = State()      # ❓ Tasdiqlash holati (Ha/Yo'q)


# =====================================================================
# 📑 1-QADAM: "📝 Tasnif" tugmasi bosilganda holatga (State) o'tkazish
# =====================================================================
@router.callback_query(F.data.startswith("edit_field:desc:"))
async def edit_anime_desc_start(callback: CallbackQuery, state: FSMContext):
    anime_id = int(callback.data.split(":")[2])
    
    # Ma'lumotlarni holat keshiga yozib qo'yamiz
    await state.update_data(edit_anime_id=anime_id, main_msg_id=callback.message.message_id)
    await state.set_state(EditAnimeStates.waiting_for_new_desc)
    
    text = (
        "📝 <b>Yangi tasnif (tavsif) kiritish:</b>\n\n"
        "Iltimos, animening yangi tasnifini botga xabar shaklida yuboring.\n"
        "<i>(Xohlasangiz uzun matn yuborishingiz mumkin)</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"force_refresh_edit:{anime_id}", style="danger")]
    ])
    
    await safe_answer(callback, "Tasnif tahrirlash boshlandi")
    await _safe_update_message(callback.message, caption=text, reply_markup=kb)


# =====================================================================
# 📑 2-QADAM: Admin yangi tasnif yuborganda uni ushlash va Ha/Yo'q so'rash
# =====================================================================
@router.message(EditAnimeStates.waiting_for_new_desc, F.text)
async def process_new_anime_desc(message: Message, state: FSMContext):
    new_desc = message.text.strip()
    state_data = await state.get_data()
    
    anime_id = state_data.get("edit_anime_id")
    main_msg_id = state_data.get("main_msg_id")
    
    # Admin yuborgan xabarni xavfsiz o'chiramiz
    await safe_delete(message)
        
    await state.update_data(new_anime_desc=new_desc)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha", callback_data="confirm_desc_edit:yes", style="success"),
            InlineKeyboardButton(text="❌ Yo'q", callback_data="confirm_desc_edit:no", style="danger")
        ]
    ])
    
    preview_desc = new_desc[:200] + "..." if len(new_desc) > 200 else new_desc
    
    confirm_text = (
        f"❓ <b>Anime tasnifi o'zgartirilsinmi?</b>\n\n"
        f"📝 <b>Yangi tasnif:</b>\n"
        f"<blockquote expandable>{preview_desc}</blockquote>"
    )
    
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
        logger.error(f"Tasnifni tasdiqlash xabarida xato: {e}")


# =====================================================================
# 📑 3-QADAM: Tasnif tasdiqlanganda (Ha yoki Yo'q) bosilishi
# =====================================================================
@router.callback_query(EditAnimeStates.waiting_for_confirmation, F.data.startswith("confirm_desc_edit:"))
async def save_or_cancel_anime_desc(callback: CallbackQuery, state: FSMContext, session: Any):
    action = callback.data.split(":")[1]
    state_data = await state.get_data()
    
    anime_id = state_data.get("edit_anime_id")
    new_desc = state_data.get("new_anime_desc")
    
    # ❌ AGAR ADMIN "YO'Q" DEB BEKOR QILSA
    if action == "no":
        await safe_answer(callback, "Tahrirlash bekor qilindi.", show_alert=True)
        await state.clear()
        await safe_delete(callback.message)
            
        cloned_callback = callback.model_copy(update={"data": f"edit_anime:{anime_id}"})
        from handlers.admin_panel.admin_anime.edits_anime.edit_anime_menu import process_edit_anime_menu
        await process_edit_anime_menu(cloned_callback, session)
        return

    # ✅ AGAR ADMIN "HA" DEB TASDIQLASA
    await safe_answer(callback, "Bazaga yozilmoqda...")
    
    success = False
    try:
        service = AnimeService(session=session)
        success = await service.update_anime(
            anime_id=anime_id, 
            update_data={"description": new_desc}
        )
    except Exception as e:
        logger.error(f"DB Update Desc error: {e}")

    await state.clear()

    if not success:
        error_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⚙️ Tahrirlashga qaytish", callback_data=f"force_refresh_edit:{anime_id}", style="danger")
        ]])
        await _safe_update_message(
            message=callback.message,
            caption="❌ <b>Xatolik:</b> Tasnifni saqlashda texnik xato yuz berdi.",
            reply_markup=error_kb
        )
        return

    success_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Tahrirlashga qaytish", callback_data=f"force_refresh_edit:{anime_id}", style="danger")]
    ])
    
    await _safe_update_message(
        message=callback.message,
        caption="✅ <b>Anime tasnifi muvaffaqiyatli yangilandi!</b>",
        reply_markup=success_kb
    )


# =====================================================================
# 📑 4-QADAM: Majburiy qaytish handler (Cancel qilinganda)
# =====================================================================
@router.callback_query(F.data.startswith("force_refresh_edit:"))
async def force_refresh_edit_menu(callback: CallbackQuery, state: FSMContext, session: Any):
    await state.clear()
    await safe_answer(callback)
    anime_id = int(callback.data.split(":")[1])
    
    cloned_callback = callback.model_copy(update={"data": f"edit_anime:{anime_id}"})
    from handlers.admin_panel.admin_anime.edits_anime.edit_anime_menu import process_edit_anime_menu
    await process_edit_anime_menu(cloned_callback, session)