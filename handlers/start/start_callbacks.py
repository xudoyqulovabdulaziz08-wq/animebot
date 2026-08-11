import logging
from typing import Any
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from services.user_service import UserService
from services.anime_service import AnimeService
from services.navigation import NavigationManager
from utils.page_renderer import open_page
from handlers.start.helpers import send_or_edit_start_menu

logger = logging.getLogger("StartCallbackRouter")

router = Router()

@router.callback_query(lambda c: c.data == "back_to_start")
async def back_to_start_handler(callback: CallbackQuery, session: Any = None):
    user_id = callback.from_user.id
    username = callback.from_user.username or "do'stim"
    await send_or_edit_start_menu(callback, user_id, username, session=session)


@router.callback_query(F.data.startswith("check_sub"))
async def check_sub_callback_handler(
    callback: CallbackQuery, 
    session: Any, 
    state: FSMContext, 
    user_service: UserService
):
    await callback.answer("🎉 Rahmat, obuna muvaffaqiyatli tasdiqlandi!", show_alert=True)
    user_id = callback.from_user.id
    username = callback.from_user.username or "do'stim"
    
    try:
        await callback.message.delete()
    except Exception:
        pass

    data_parts = callback.data.split(":")
    
    if len(data_parts) > 1 and data_parts[1].startswith("anime_"):
        anime_param = data_parts[1]
        try:
            anime_id = int(anime_param.split("_")[1])
            service = AnimeService(session=session)
            anime = await service.get_anime(anime_id)
            
            if anime:
                title = anime.get("title", "Nomsiz anime")
                caption = f"🎬 <b>{title}</b>\n\nObuna tasdiqlandi! Qismlarni tomosha qilishingiz mumkin."
                
                user_anime_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📹 Qismlarni tomosha qilish", callback_data=f"show_episodes_user:{anime_id}", style="primary")],
                    [InlineKeyboardButton(text="⬅️ Bosh menyuga qaytish", callback_data="back_to_start", style="danger")]
                ])
                
                poster_id = anime.get("poster_id")
                if poster_id:
                    await callback.message.answer_photo(photo=poster_id, caption=caption, reply_markup=user_anime_kb, parse_mode="HTML")
                else:
                    await callback.message.answer(text=caption, reply_markup=user_anime_kb, parse_mode="HTML")
                return
        except Exception as ex:
            logger.error(f"❌ Check sub ichida animeni yuklashda xato: {ex}")

    await send_or_edit_start_menu(callback.message, user_id, username, session=session)


@router.callback_query(F.data == "back_global")
async def global_back_handler(
    callback: CallbackQuery, 
    state: FSMContext, 
    session: Any = None, 
    user_service: UserService = None, 
    user: dict = None
):
    nav = NavigationManager(state)
    prev_step = await nav.pop()
    
    await open_page(
        event=callback, 
        page=prev_step["page"], 
        params=prev_step.get("params", {}),
        session=session,
        user_service=user_service,
        state=state,
        user=user
    )