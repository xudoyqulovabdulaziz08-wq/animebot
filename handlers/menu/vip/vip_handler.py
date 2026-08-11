import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from services.user_service import UserService
from handlers.menu.vip.texts import get_vip_info_text, RATES_TEXT, get_checkout_data
from handlers.menu.vip.keyboards import get_vip_menu_kb, get_vip_rates_kb, get_checkout_kb

router = Router()
logger = logging.getLogger("UserVipMenu")

async def _safe_edit_caption(callback: CallbackQuery, caption: str, reply_markup):
    try:
        await callback.message.edit_caption(
            caption=caption,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.error(f"❌ Kutilmagan BadRequest: {e}")
    except Exception as e:
        logger.error(f"❌ Umumiy xatolik: {e}")

@router.callback_query(F.data == "buy_vip")
async def buy_vip_menu(callback: CallbackQuery, user_service: UserService):
    await callback.answer()
    user_data = await user_service.get_user(callback.from_user.id)
    user_data = user_service._ensure_fresh_vip_status(user_data)
    
    is_vip = user_data.get("is_vip", False)
    text = get_vip_info_text(is_vip, user_data.get("vip_expire_date"))
    kb = get_vip_menu_kb(is_vip)
    
    await _safe_edit_caption(callback, text, kb)

@router.callback_query(F.data == "purchase_vip")
async def vip_payed(callback: CallbackQuery, user_service: UserService):
    await callback.answer()
    user_data = await user_service.get_user(callback.from_user.id)
    user_data = user_service._ensure_fresh_vip_status(user_data)
    
    title = "🔄 <b>VIP obunangizni uzaytirish uchun...</b>\n\n" if user_data.get("is_vip") else "🛒 <b>VIP status sotib olish uchun...</b>\n\n"
    caption = f"{title}{RATES_TEXT}<i>👇 Kerakli muddat tugmasini bosing:</i>"
    
    await _safe_edit_caption(callback, caption, get_vip_rates_kb())

@router.callback_query(F.data.startswith("purchases_vip:"))
async def process_vip_checkout(callback: CallbackQuery):
    await callback.answer()
    months = callback.data.split(":")[1]
    
    caption, admin_url = get_checkout_data(months, callback.from_user.id)
    await _safe_edit_caption(callback, caption, get_checkout_kb(admin_url))