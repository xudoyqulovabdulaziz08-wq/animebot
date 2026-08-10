import logging
import html
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from handlers.anime_uchun.izoh_anime import anime_comment_handler
from services.comment_service import CommentService
from services.anime_service import AnimeService
from aiogram.fsm.state import State, StatesGroup
from config import config

logger = logging.getLogger("izohlarim_edit")
router = Router()
CREATOR_ID = config.CREATOR_ID