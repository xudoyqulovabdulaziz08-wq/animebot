import logging
import html
from typing import Any, Optional
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from services.anime_service import AnimeService

router = Router()
logger = logging.getLogger(__name__)


class EditAnimeStates(StatesGroup):
    waiting_for_new_name_en = State()
    waiting_for_confirmation_en = State()    # Yangi nomni kiritish holati inglizcha



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


# =====================================================================
# 📑 1-QADAM: "en Englishcha" tugmasi bosilganda
# =====================================================================
@router.callback_query(F.data.startswith("edit_field:title_en:"))
async def edit_anime_title_en_start(callback: CallbackQuery, state: FSMContext):
    try:
        anime_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("🚨 Xato ID!", show_alert=True)
        return
    
    # State'ga ma'lumotlarni saqlaymiz
    await state.update_data(edit_anime_id=anime_id, main_msg_id=callback.message.message_id)
    await state.set_state(EditAnimeStates.waiting_for_new_name_en)
    
    # Orqaga qaytish tugmasi (agar admin fikridan qaytsa)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data=f"force_refresh_edit:{anime_id}", style="danger")]
    ])
    
    text = (
        "✍️ <b>Yangi Englishcha nom kiritish:</b>\n\n"
        "Iltimos, animening yangi nomini yozib, xabar shaklida yuboring."
    )
    
    await callback.answer("Englishcha nomni tahrirlash...")
    
    try:
        await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Sarlavha o'zgartirishda xato (Media bo'lmasligi mumkin): {e}")
        try:
            await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass




# =====================================================================
# 📑 2-QADAM: Admin yangi nom yuborganda uni ushlash
# =====================================================================
@router.message(EditAnimeStates.waiting_for_new_name_en, F.text)
async def process_new_anime_name_en(message: Message, state: FSMContext):
    # HTML xatolarini oldini olish uchun matnni xavfsiz holatga keltiramiz
    new_name = html.escape(message.text.strip())
    state_data = await state.get_data()
    
    main_msg_id = state_data.get("main_msg_id")
    
    # 🗑 Admin yuborgan xabarni tozalaymiz
    try:
        await message.delete()
    except Exception:
        pass
        
    await state.update_data(new_anime_title_en=new_name)
    await state.set_state(EditAnimeStates.waiting_for_confirmation_en)
    
    # ❌ style="success" kabi parametrlar Aiogram v3 da InlineKeyboardButton uchun ISHLAMAYDI. Olib tashlandi.
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha", callback_data="confirm_edit_en:yes", style="success"),
            InlineKeyboardButton(text="❌ Yo'q", callback_data="confirm_edit_en:no", style="danger")
        ]
    ])
    
    confirm_text = (
        f"❓ <b>Haqiqatdan ham englishcha nom quyidagiga o'zgartirilsinmi?</b>\n\n"
        f"📝 Yangi nom: <code>{new_name}</code>"
    )
    
    try:
        await message.bot.edit_message_caption(
            chat_id=message.chat.id,
            message_id=main_msg_id,
            caption=confirm_text,
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception:
        # Agar rasm bo'lmasa, edit_message_text ishlatiladi
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=main_msg_id,
                text=confirm_text,
                reply_markup=kb,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Tasdiqlash xabarini chiqarishda xato: {e}")


# =====================================================================
# 📑 3-QADAM: Tasdiqlash (Ha / Yo'q)
# =====================================================================
@router.callback_query(EditAnimeStates.waiting_for_confirmation_en, F.data.startswith("confirm_edit_en:"))
async def save_or_cancel_anime_title_en(callback: CallbackQuery, state: FSMContext, session: Any):
    action = callback.data.split(":")[1]
    state_data = await state.get_data()
    
    anime_id = state_data.get("edit_anime_id")
    new_name = state_data.get("new_anime_title_en")
    
    # ❌ AGAR "YO'Q" DEB RAD ETILSA
    if action == "no":
        await callback.answer("Tahrirlash bekor qilindi ❌", show_alert=False)
        await state.clear()
        
        # Asosiy menyuga qaytarish
        cloned_callback = callback.model_copy(update={"data": f"edit_fields:{anime_id}"})
        # Bu yerda siz edit_fields_callback'ni to'g'ridan-to'g'ri chaqirishingiz mumkin:
        # (Lekin doira import (circular import) bo'lmasligi uchun fayl tuzilishiga e'tibor bering)
        from handlers.admin_panel.admin_anime.edit_anime import edit_fields_callback
        await edit_fields_callback(cloned_callback, session)
        return

    # ✅ AGAR "HA" DEB TASDIQLANSA
    await callback.answer("Saqlanmoqda... ⏳")
    
    service = AnimeService(session=session)
    try:
        # DIQQAT: Biz bazaga "title_en" ni uzatayapmiz. Service buni to'g'ri qabul qilishi kerak!
        success = await service.update_anime(anime_id=anime_id, update_data={"title_en": new_name})
    except Exception as e:
        logger.error(f"DB Update error title_en: {e}", exc_info=True)
        success = False

    if not success:
        kb_error = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Ortga", callback_data=f"edit_fields:{anime_id}", style="danger")
        ]])
        await callback.message.edit_caption(
            caption="❌ <b>Texnik xatolik:</b> Ma'lumotni bazaga saqlashning iloji bo'lmadi.",
            reply_markup=kb_error,
            parse_mode="HTML"
        )
        await state.clear()
        return

    # Muvaffaqiyatli saqlandi
    kb_success = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Tahrirlash menyusiga qaytish", callback_data=f"edit_fields:{anime_id}", style="primary")]
    ])
    
    await callback.message.edit_caption(
        caption=f"✅ <b>Anime inglizcha nomi muvaffaqiyatli yangilandi!</b>\n\n✨ Yangi nom: <code>{new_name}</code>",
        reply_markup=kb_success,
        parse_mode="HTML"
    )
    await state.clear()

# =====================================================================
# 📑 4-QADAM: Majburiy qaytish handler (Cancel qilinganda)
# =====================================================================
@router.callback_query(F.data.startswith("force_refresh_edit:"))
async def force_refresh_edit_menu(callback: CallbackQuery, state: FSMContext, session: Any):
    await state.clear() # Holatni tozalaymiz
    anime_id = int(callback.data.split(":")[1])
    
    cloned_callback = callback.model_copy(update={"data": f"edit_fields:{anime_id}"})
    from handlers.admin_panel.admin_anime.edit_anime import edit_fields_callback
    await edit_fields_callback(cloned_callback, session)
