import logging
from typing import Any, Optional
from aiogram import Router, F, html
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter



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

@router.callback_query(F.data.startswith("tizer_view:"))
async def tizer_view(callback: CallbackQuery, session: Any):
    # 1. FUNKSIYA ISHGA TUSHGANINI TEKSHIRISH
    logger.info(f"👉 tizer_view ishga tushdi! Data: {callback.data}")
    await safe_answer(callback)
    
    try:
        parts = callback.data.split(":")
        if len(parts) < 2 or not parts[1].isdigit():
            await safe_answer(callback, text="❌ Noto'g'ri so'rov ma'lumoti!", show_alert=True)
            return
            
        anime_id = int(parts[1])
        
        anime_service = AnimeService(session)
        anime = await anime_service.get_anime(anime_id)

        if not anime:
            await safe_answer(callback, text="❌ Anime topilmadi.", show_alert=True)
            return

        trailer_id = anime.get("trailer_id")
        if not trailer_id:
            await safe_answer(callback, text="❌ Ushbu anime uchun tizer yuklanmagan.", show_alert=True)
            return

        title = anime.get("title") or "Nomsiz anime"
        description = anime.get("description") or ""
        caption = f"🎬 <b>{html.escape(title)}</b> — Tizer\n\n{html.escape(description)}"
        
        buttons = [
            [InlineKeyboardButton(text="🗑️ O'chirish", callback_data=f"tizer_delete:{anime_id}")],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"tizer_edit:{anime_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        try:
            # 1-urinish: Xabarni o'zida mediaga almashtirish
            new_media = InputMediaVideo(media=trailer_id, caption=caption, parse_mode="HTML")
            await callback.message.edit_media(media=new_media, reply_markup=reply_markup)
            logger.info("✅ Tizer videoga muvaffaqiyatli o'zgardi (edit_media).")
            
        except TelegramBadRequest as e:
            msg = str(e).lower()
            if "message is not modified" in msg:
                logger.info("⚠️ Xabar o'zgartirilmadi (avvaldan xuddi shunday edi).")
            else:
                logger.info("⚠️ Matnni videoga o'zgartirib bo'lmaydi. Xabarni o'chirib qayta yuboramiz...")
                
                # 2-urinish: Xabarni o'chirib, yangi video yuborish (XATOLIKKA QARSHI HIMOYALANGAN)
                try:
                    await safe_delete(callback.message)
                    await callback.message.answer_video(
                        video=trailer_id,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode="HTML"
                    )
                    logger.info("✅ Yangi video xabar muvaffaqiyatli yuborildi.")
                except Exception as inner_e:
                    logger.error(f"❌ Video yuborishda xatolik (File ID noto'g'ri bo'lishi mumkin!): {inner_e}", exc_info=True)
                    await callback.message.answer("❌ Tizer fayli (video) bilan bog'liq muammo bor. Fayl yaroqsiz bo'lishi mumkin.")
                    
    except Exception as e:
        logger.error(f"❌ tizer_view bajarilishida kutilmagan xato: {e}", exc_info=True)
        await safe_answer(callback, text="❌ Kutilmagan xatolik yuz berdi!", show_alert=True)