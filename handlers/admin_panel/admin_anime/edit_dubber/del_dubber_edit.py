import logging
import html
import math
from sqlalchemy import select
from typing import Any, Optional
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext

from database.models import Genre
from services.anime_service import AnimeService
from aiogram.fsm.state import StatesGroup, State
from handlers.admin_panel.admin_anime.edit_dubber.list_dubber_edit import get_admin_dubbers_list_markup
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



@router.callback_query(F.data.startswith("edit_dubber_detail:"))
async def edit_dubber_detail_handler(callback: CallbackQuery, state: FSMContext, session: Any) -> None:
    """Dubber tafsilotlarini ko'rsatish va o'chirish menyusiga o'tish."""
    await safe_answer(callback)
    
    # Callback data'dan ID ni xavfsiz ajratib olish
    try:
        dubber_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Noto'g'ri dubber ID", show_alert=True)
        return
        
    await state.update_data(dubber_id=dubber_id)
    
    # Bazadan dubber ma'lumotlarini olish
    from database.models import Dubber  # Circular import oldini olish uchun
    stmt = select(Dubber).where(Dubber.id == dubber_id)
    result = await session.execute(stmt)
    dubber = result.scalar_one_or_none()
    
    if not dubber:
        await callback.answer("❌ Dubber topilmadi yoki o'chirilgan!", show_alert=True)
        return
        
    # Matn qismi
    caption = (
        f"🎙️ <b>Dubber ma'lumotlari</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 <b>ID:</b> <code>{dubber.id}</code>\n"
        f"👤 <b>Ismi:</b> {html.escape(dubber.name)}\n\n"
        f"⚠️ <i>Diqqat: Dubberni o'chirish harakatini orqaga qaytarib bo'lmaydi.</i>"
    )
    
    # Tugmalar qismi
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🗑 O'chirish", 
                callback_data=f"delete_dubber_confirm:{dubber.id}", 
                style="danger"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Orqaga", 
                callback_data="list_edit_dubber_page:1", 
                style="primary"
            )
        ]
    ])
    
    # Xabarni bitta interfeysda yangilash
    await _safe_update_message(
        message=callback.message,
        caption=caption,
        reply_markup=kb
    )




# Tasdiqlash oynasini ko'rsatuvchi handler (Siz tashlagan kodning o'zgartirilgan holati)
@router.callback_query(F.data.startswith("delete_dubber_confirm:"))
async def delete_dubber_confirm_handler(callback: CallbackQuery, state: FSMContext, session: Any) -> None:
    await safe_answer(callback)
    
    # Callback data'dan ID ni xavfsiz ajratib olish
    try:
        dubber_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Noto'g'ri dubber ID", show_alert=True)
        return

    # Bazadan dubber ma'lumotlarini olish
    from database.models import Dubber  # Circular import oldini olish uchun
    stmt = select(Dubber).where(Dubber.id == dubber_id)
    result = await session.execute(stmt)
    dubber = result.scalar_one_or_none()

    if not dubber:
        await callback.answer("❌ Dubber topilmadi yoki o'chirilgan!", show_alert=True)
        return

    # Tasdiqlash matni va tugmalari
    caption = (
        f"⚠️ <b>Tasdiqlash</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Siz rostdan ham <b>{html.escape(dubber.name)}</b> dubberini o'chirib tashlamoqchimisiz?\n\n"
        f"<i>Bu amalni bekor qilib bo'lmaydi!</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            # "Ha" bosilsa, haqiqiy o'chirish handleriga o'tadi
            InlineKeyboardButton(
                text="✅ Ha, o'chirish", 
                callback_data=f"delete_dubber_action:{dubber.id}", 
                style="danger"
            ),
            # "Yo'q" bosilsa, dubber ma'lumotlari oynasiga qaytadi
            InlineKeyboardButton(
                text="❌ Yo'q, qaytish", 
                callback_data=f"edit_dubber_detail:{dubber.id}", 
                style="primary"
            )
        ]
    ])

    await _safe_update_message(
        message=callback.message,
        caption=caption,
        reply_markup=kb
    )


# Haqiqiy o'chirish amalini bajaruvchi handler
@router.callback_query(F.data.startswith("delete_dubber_action:"))
async def delete_dubber_action_handler(callback: CallbackQuery, state: FSMContext, session: Any) -> None:
    await safe_answer(callback)
    
    try:
        dubber_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Noto'g'ri dubber ID", show_alert=True)
        return

    from database.models import Dubber
    stmt = select(Dubber).where(Dubber.id == dubber_id)
    result = await session.execute(stmt)
    dubber = result.scalar_one_or_none()

    if not dubber:
        await callback.answer("❌ Dubber topilmadi yoki allaqachon o'chirilgan!", show_alert=True)
        return

    # Dubberni o'chirish va bazani saqlash
    await session.delete(dubber)
    await session.commit()

    # Keshni invalidatsiya qilish (tizimda ma'lumotlar yangilanishi uchun)
    try:
        from database.cache import cache_manager
        await cache_manager.invalidate("dubber", "all", broadcast=True)
    except Exception:
        pass

    await callback.answer("✅ Dubber muvaffaqiyatli o'chirildi!", show_alert=True)
    
    # ⚠️ TAYYOR FUNKSIYA CHAQIRILDI:
    markup = await get_admin_dubbers_list_markup(session=session, page=1)
    
    caption = (
        "🎙️ <b>Dubberlar ro‘yxati</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Tahrirlamoqchi yoki ko‘rmoqchi bo‘lgan dubber ustiga bosing.\n\n"
        "👇 <b>Mavjud dubberlar:</b>"
    )
    
    await _safe_update_message(
        message=callback.message,
        caption=caption,
        reply_markup=markup
    )