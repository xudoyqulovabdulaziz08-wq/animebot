import logging

from typing import Any, Optional
from aiogram import Router, F, html
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from services.anime_service import AnimeService

router = Router()
logger = logging.getLogger(__name__)

class AnimeTizerEditService(StatesGroup):
    waiting_for_trailer = State()  

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


@router.callback_query(F.data.startswith("tizer_editer:"))
async def tizzer_id_start_wating(callback: CallbackQuery, state: FSMContext, session: Any):
    # 1. Interfeys qotib qolmasligi uchun xavfsiz javob
    await safe_answer(callback)
    
    # 2. Callback datadan anime_id ni ajratib olish (oldingi xato to'g'irlandi)
    try:
        anime_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return
    
    # 3. FSM (State) ga o'tish va kelgusi qadam uchun anime_id ni saqlash
    # Shuningdek, panel xabarini ham saqlaymiz, video kelganda uni yangilash uchun
    await state.update_data(
        anime_id=anime_id, 
        panel_message_id=callback.message.message_id
    )
    await state.set_state(AnimeTizerEditService.waiting_for_trailer)
    
    # 4. Foydalanuvchiga ko'rsatma matni (Caption)
    text = (
        "🎬 <b>Tizer videosini yuboring.</b>\n\n"
        "📥 Iltimos, ushbu anime uchun tizerni (videoni) chatga yuboring yoki forward qiling.\n\n"
        "<i>(Jarayonni bekor qilish uchun pastdagi tugmani bosing)</i>"
    )
    
    # 5. Bekor qilish tugmasi (oldingi tizer_edit menyusiga qaytadi)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga (Bekor qilish)", callback_data=f"tizer_edit:{anime_id}")]
    ])
    
    # 6. Rasm ostidagi matn (caption) ni xavfsiz yangilash (rasm o'zgarmaydi)
    success = await _safe_update_message(
        message=callback.message,
        caption=text,
        reply_markup=kb,
        poster_id=None 
    )
    
    if not success:
        logger.warning(f"ID:{anime_id} anime tizer yuklash kutilmasiga o'tishda xabar yangilanmadi.")


@router.message(AnimeTizerEditService.waiting_for_trailer, F.video | F.document)
async def process_tizer_video(message: Message, state: FSMContext, session: Any):
    # 1. Video file_id ni xavfsiz ajratib olish
    if message.video:
        file_id = message.video.file_id
    elif message.document and message.document.mime_type and message.document.mime_type.startswith('video/'):
        file_id = message.document.file_id
    else:
        # Agar rasm yoki boshqa fayl tashlasa
        await safe_send(message, text="❌ Iltimos, faqat video formatdagi fayl yuboring!")
        return

    # 2. State'dan anime_id va eski panel xabari ID sini olish
    data = await state.get_data()
    anime_id = data.get("anime_id")
    panel_message_id = data.get("panel_message_id") # <-- Tepadagi xabar ID si
    
    if not anime_id:
        await safe_send(message, text="❌ Xatolik yuz berdi (Anime ID topilmadi). Iltimos, qaytadan urinib ko'ring.")
        await state.clear()
        return

    # 3. Bazaga saqlash
    service = AnimeService(session=session)
    try:
        # update_anime orqali trailer_id ni yangilaymiz
        await service.update_anime(anime_id=anime_id, update_data={"trailer_id": file_id})
        
        # 4. Chatni tozalash jarayoni
        # A) Foydalanuvchi yuborgan videoni o'chirish
        await safe_delete(message)
        
        # B) Tepadagi eski kutilma (panel) xabarini o'chirish
        if panel_message_id:
            try:
                await message.bot.delete_message(
                    chat_id=message.chat.id, 
                    message_id=panel_message_id
                )
            except Exception as e:
                logger.warning(f"Eski panel xabarini o'chirishda xatolik: {e}")
        
        # 5. State ni tozalaymiz
        await state.clear()
        
        # 6. Pastdan yangi, toza xabarni yuborish
        success_text = "✅ <b>Tizer muvaffaqiyatli saqlandi!</b>\n\nPastdagi tugma orqali orqaga qaytishingiz mumkin."
        success_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Tizer menyusiga qaytish", callback_data=f"tizer_edit:{anime_id}")]
        ])
        await safe_send(message, text=success_text, reply_markup=success_kb, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Tizer saqlashda xato: {e}", exc_info=True)
        await safe_send(message, text="❌ Tizerni saqlashda server xatoligi yuz berdi.")
        await state.clear()
    