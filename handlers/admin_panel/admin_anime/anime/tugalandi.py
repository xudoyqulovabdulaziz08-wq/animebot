import logging
from typing import(
    Any, 
    Optional
)

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramNetworkError,
)
from aiogram.types import (
    CallbackQuery, 
    Message, 

)
from aiogram import Router, F, html
from services.anime_service import AnimeService
from handlers.admin_panel.admin_anime.list_anime1 import view_anime_details
logger = logging.getLogger("ended_episode")
router = Router()
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







@router.callback_query(F.data.startswith("anime_end:"))
async def toggle_anime_end_status(callback: CallbackQuery, session: Any):
    # 1. Xavfsiz ID o'qish
    data_parts = callback.data.split(":")
    if len(data_parts) < 2 or not data_parts[1].isdigit():
        await safe_answer(callback, "❌ Noto'g'ri anime ID!", show_alert=True)
        return
        
    anime_id = int(data_parts[1])

    # 2. DB/Cache dan animeni yuklash
    try:
        service = AnimeService(session=session)
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"anime_end: anime olishda xato: {e}", exc_info=True)
        await safe_answer(callback, "❌ Tizimda xatolik yuz berdi.", show_alert=True)
        return

    if not anime:
        await safe_answer(callback, "❌ Anime topilmadi yoki o'chirilgan!", show_alert=True)
        return

    # 3. Joriy holatni aniqlash va teskarisiga o'zgartirish (Toggle)
    current_status = anime.get("is_finished", False)
    new_status = not current_status
    
    # 4. Bazada yangilash
    try:
        # Sizning AnimeService xizmatingiz is_finished'ni to'g'ridan-to'g'ri yangilay oladi
        await service.update_anime(anime_id, {"is_finished": new_status})
    except Exception as e:
        logger.error(f"anime_end: saqlashda xato: {e}", exc_info=True)
        await safe_answer(callback, "❌ Holatni saqlashda xatolik yuz berdi!", show_alert=True)
        return
    
    # 5. Ekranga chiqadigan Alert xabari
    if new_status:
        alert_text = "✅ Bu anime tugallandi!"
    else:
        alert_text = "🔄 Bu anime endi davom etmoqda!"
        
    await safe_answer(callback, alert_text, show_alert=True)

    # 6. UI (Menyu) ni xavfsiz yangilash - Pydantic v2 `model_copy` yordamida
    try:
        # Eski view_anime_details funksiyasini chaqirish uchun callback ma'lumotini yangilaymiz
        # Bu yerda view_anime_details qaysi faylda bo'lsa shuni import qilasiz (agar boshqa faylda bo'lsa)
        # from your_module import view_anime_details 
        
        updated_callback = callback.model_copy(
            update={"data": f"v_anime:{anime_id}"}
        )
        
        # Yangilangan callback bilan asosiy menyuni qayta chizamiz
        await view_anime_details(updated_callback, session)

    except Exception as e:
        logger.error(f"anime_end UI yangilashda xato: {e}", exc_info=True)