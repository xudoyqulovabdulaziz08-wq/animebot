import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from handlers.menu.reklama.texts import ADVERTISE_MAIN_TEXT, ADVERTISE_SUBMIT_TEXT
from handlers.menu.reklama.keyboards import get_advertise_main_kb, get_advertise_submit_kb

router = Router()
logger = logging.getLogger("ReklamaRouter")

async def _safe_edit_caption(callback: CallbackQuery, caption: str, reply_markup):
    try:
        await callback.message.edit_caption(
            caption=caption,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.error(f"❌ Kutilmagan BadRequest xatoligi: {e}")
    except Exception as e:
        logger.error(f"❌ Tizimda xatolik yuz berdi: {e}")

@router.callback_query(F.data == "advertise")
async def advertise_menu(callback: CallbackQuery):
    await callback.answer()
    await _safe_edit_caption(callback, ADVERTISE_MAIN_TEXT, get_advertise_main_kb())

@router.callback_query(F.data == "advertise_submit")
async def advertise_submit(callback: CallbackQuery):
    await callback.answer()
    await _safe_edit_caption(callback, ADVERTISE_SUBMIT_TEXT, get_advertise_submit_kb())