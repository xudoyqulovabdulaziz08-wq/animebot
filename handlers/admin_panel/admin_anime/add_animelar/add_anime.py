import logging
from aiogram.fsm.state import State, StatesGroup

from typing import Any
from aiogram import Router, F, html
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from sqlalchemy import select
import math

from database.models import Genre
from services.anime_service import AnimeService

logger = logging.getLogger(__name__)
router = Router()



class AddAnimeStates(StatesGroup):
    poster = State()       # 1. Birinchi poster (Rasm/Video)
    title = State()    
    genres = State()       # 3. Janrlar (Paginatsiya + Multi-select + style="success")
    dubber = State()      # 4. Dubber 
    description = State()  # 4. Tasnif (Description)
    confirm_save = State() # 5. Bazaga saqlashni tasdiqlash


