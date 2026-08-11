from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from .texts import ADMIN_URL

def get_advertise_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Reklama berish", callback_data="advertise_submit", style="success")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_start", style="danger")]
        ]
    )

def get_advertise_submit_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Bog'lanish", url=ADMIN_URL, style="success")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="advertise", style="danger")]
        ]
    )