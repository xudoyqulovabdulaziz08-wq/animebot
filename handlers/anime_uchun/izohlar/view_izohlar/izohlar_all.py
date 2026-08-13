import logging
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message
)


logger = logging.getLogger("izohlar_wiev")


router = Router()





@router.callback_query(F.data.startswith("view_comments"))
async def wiev_comment_handler(callback: CallbackQuery, session):
    await callback.answer()