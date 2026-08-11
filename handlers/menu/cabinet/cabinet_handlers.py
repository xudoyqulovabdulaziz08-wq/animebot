import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from services.user_service import UserService
from services.navigation import NavigationManager
from handlers.menu.cabinet.texts import get_cabinet_text, CABINET_ERROR_TEXT
from handlers.menu.cabinet.keyboards import get_cabinet_kb

router = Router()
logger = logging.getLogger("CabinetHandler")

@router.callback_query(F.data == "cabinet")
@router.callback_query(F.data.startswith("refresh_web_code:"))
async def open_cabinet_handler(
    callback: CallbackQuery, 
    user_service: UserService, 
    state: FSMContext = None
):
    user_id = callback.from_user.id
    user_data = await user_service.get_user(user_id)
    user_data = user_service._ensure_fresh_vip_status(user_data)

    if state and callback.data == "cabinet":
        nav = NavigationManager(state)
        await nav.push("cabinet")

    current_data = callback.data
    await callback.answer("⏳ Shaxsiy kabinet yuklanmoqda...")

    # Parol olish yoki yangilash
    try:
        if current_data.startswith("refresh_web_code:"):
            password = await user_service.refresh_web_auth_code(user_id)
            alert_text = "🔄 Yangi xavfsiz parol yaratildi va bazada yangilandi!"
        else:
            password = await user_service.generate_web_auth_code(user_id)
            alert_text = None
    except Exception as err:
        logger.error(f"❌ Shaxsiy kabinet mantiqida xatolik (user_id={user_id}): {err}")
        password = None

    if not password:
        await callback.message.answer(CABINET_ERROR_TEXT)
        return

    is_vip = user_data.get("is_vip", False)
    text = get_cabinet_text(user_id, password, is_vip)
    kb = get_cabinet_kb(user_id)

    # UI yangilash
    try:
        await callback.message.edit_caption(
            caption=text,
            reply_markup=kb,
            parse_mode="HTML"
        )
        if alert_text:
            await callback.answer(alert_text, show_alert=True)
            
    except Exception as edit_error:
        logger.debug(f"Media caption edit dynamic fallback triggered: {edit_error}")
        await callback.message.answer(
            text=text,
            reply_markup=kb,
            parse_mode="HTML"
        )