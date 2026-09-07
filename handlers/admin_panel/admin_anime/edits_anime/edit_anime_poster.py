
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
    waiting_for_new_poster = State()        # 🖼 Yangi poster qabul qilish holati
    waiting_for_confirmation = State()      # ❓ Tasdiqlash holati (Ha/Yo'q)


# =====================================================================
# 📑 1-QADAM: "🖼 Poster" tugmasi bosilganda holatga (State) o'tkazish
# =====================================================================
@router.callback_query(F.data.startswith("edit_field:poster:"))
async def edit_anime_poster_start(callback: CallbackQuery, state: FSMContext):
    anime_id = int(callback.data.split(":")[2])
    
    # Kelajakda o'chirish yoki tahrirlash uchun ID larni saqlaymiz
    await state.update_data(edit_anime_id=anime_id, main_msg_id=callback.message.message_id)
    await state.set_state(EditAnimeStates.waiting_for_new_poster)
    
    text = (
        "🖼 <b>Yangi anime posterini (rasm) yuklash:</b>\n\n"
        "Iltimos, animening yangi posterini botga rasm (Photo) ko'rinishida yuboring.\n"
        "<i>(Eslatma: Rasm fayl (Document) shaklida emas, oddiy rasm formatida bo'lsin!)</i>"
    )
    
    # Orqaga qaytish tugmasi
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"force_refresh_edit:{anime_id}", style="danger")]
    ])
    
    await safe_answer(callback, "Poster tahrirlash boshlandi")
    await _safe_update_message(callback.message, caption=text, reply_markup=kb)


# =====================================================================
# 📑 2-QADAM: Admin yangi rasm yuborganda uni ushlash va tasdiqlash so'rash
# =====================================================================
@router.message(EditAnimeStates.waiting_for_new_poster, F.photo)
async def process_new_anime_poster(message: Message, state: FSMContext):
    # Eng yuqori sifatli rasm file_id sini olamiz
    new_poster_id = message.photo[-1].file_id
    state_data = await state.get_data()
    
    anime_id = state_data.get("edit_anime_id")
    main_msg_id = state_data.get("main_msg_id")
    
    # ❌ ADMIN YUBORGAN RASMNI O'CHIRMAYMIZ (Telegram serverida yaroqli qolishi uchun)
    # 🗑 Tepadagi bot yuborgan yo'riqnoma xabarini o'chiramiz
    try:
        await message.bot.delete_message(chat_id=message.chat.id, message_id=main_msg_id)
    except Exception:
        pass
        
    # Yangi rasm ID sini state-ga saqlaymiz
    await state.update_data(new_anime_poster=new_poster_id)
    
    # Tasdiqlash tugmalari
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha", callback_data="confirm_poster_edit:yes", style="success"),
            InlineKeyboardButton(text="❌ Yo'q", callback_data="confirm_poster_edit:no", style="danger")
        ]
    ])
    
    confirm_text = "❓ <b>Ushbu rasm anime uchun yangi poster etib belgilansinmi?</b>"
    
    await state.set_state(EditAnimeStates.waiting_for_confirmation)
    
    # Yangi xabar qilib pastdan tasdiqlash uchun rasm ko'rinishida yuboramiz
    try:
        confirm_msg = await message.answer_photo(
            photo=new_poster_id,
            caption=confirm_text,
            reply_markup=kb,
            parse_mode="HTML"
        )
        await state.update_data(confirm_msg_id=confirm_msg.message_id)
    except Exception as e:
        logger.error(f"Poster tasdiqlash xabarini yuborishda xato: {e}")


# =====================================================================
# 📑 3-QADAM: Poster tasdiqlanganda (Ha yoki Yo'q) bosilishi
# =====================================================================
@router.callback_query(EditAnimeStates.waiting_for_confirmation, F.data.startswith("confirm_poster_edit:"))
async def save_or_cancel_anime_poster(callback: CallbackQuery, state: FSMContext, session: Any):
    action = callback.data.split(":")[1]
    state_data = await state.get_data()
    
    anime_id = state_data.get("edit_anime_id")
    new_poster = state_data.get("new_anime_poster")
    
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
    await safe_answer(callback, "Poster yangilanmoqda...")
    
    success = False
    try:
        service = AnimeService(session=session)
        # Keshni tozalash va invalidation AnimeService'ning update_anime qismi ichida xavfsiz bajariladi
        success = await service.update_anime(
            anime_id=anime_id, 
            update_data={"poster_id": str(new_poster)}
        )
    except Exception as e:
        logger.error(f"🚨 Poster yangilashda DB/Sessiya xatosi: {e}")

    await state.clear()

    if not success:
        error_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⚙️ Tahrirlashga qaytish", callback_data=f"force_refresh_edit:{anime_id}", style="danger")
        ]])
        await _safe_update_message(
            message=callback.message,
            caption="❌ <b>Xatolik:</b> Posterni saqlashda texnik xato yuz berdi.",
            reply_markup=error_kb
        )
        return

    # Tasdiqlash xabarini toza interfeys uchun o'chiramiz
    await safe_delete(callback.message)
    
    # Yangilangan toza ma'lumot (yangi poster_id) bilan menyuni qayta chizamiz
    cloned_callback = callback.model_copy(update={"data": f"edit_anime:{anime_id}"})
    from handlers.admin_panel.admin_anime.edit_anime import process_edit_anime_menu
    await process_edit_anime_menu(cloned_callback, session)