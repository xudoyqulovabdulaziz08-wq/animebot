# utils/keyboard_utils.py
from typing import Optional, List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import html

VALID_STYLES = {"primary", "success", "danger"}


def make_button(
    text: str,
    callback_data: Optional[str] = None,
    url: Optional[str] = None,
    style: Optional[str] = None,
) -> InlineKeyboardButton:
    """
    Xavfsiz inline tugma yaratish uchun yagona nuqta.
    callback_data yoki url — kamida bittasi berilishi shart (ikkalasi ham bo'lishi mumkin emas).
    style: 'primary' (ko'k), 'success' (yashil), 'danger' (qizil) yoki None.
    """
    if not callback_data and not url:
        raise ValueError("callback_data yoki url dan kamida bittasi berilishi kerak")
    if callback_data and url:
        raise ValueError("callback_data va url bir vaqtda berilishi mumkin emas")
    if style and style not in VALID_STYLES:
        raise ValueError(f"Noto'g'ri style: {style!r}. Ruxsat etilgan: {VALID_STYLES}")
    if callback_data and len(callback_data.encode()) > 64:
        raise ValueError(f"callback_data 64 bayt limitidan oshib ketdi: {callback_data!r}")

    kwargs = {"text": text}
    if callback_data:
        kwargs["callback_data"] = callback_data
    if url:
        kwargs["url"] = url
    if style:
        kwargs["style"] = style
    return InlineKeyboardButton(**kwargs)


def make_keyboard(rows: List[List[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    """Qatorlar ro'yxatidan InlineKeyboardMarkup yasaydi."""
    return InlineKeyboardMarkup(inline_keyboard=rows)


def safe_link(text: str, url: str) -> str:
    """
    <a href="...">matn</a> ko'rinishidagi HTML havolani XAVFSIZ (escape qilingan)
    shaklda yaratadi. Foydalanuvchi kiritgan matnda <, >, & belgilari bo'lsa ham
    parse_mode='HTML' xabarini buzmaydi — masalan foydalanuvchi ismi yoki anime
    tavsifi ichida shu belgilar bo'lsa, xabar yuborilmay xato qaytarilishining oldini oladi.
    """
    return html.link(value=text, link=url)


def set_button_style(button: InlineKeyboardButton, style: str) -> InlineKeyboardButton:
    """
    Mavjud tugmaning rangini o'zgartirib, YANGI nusxasini qaytaradi
    (InlineKeyboardButton immutable pydantic model, shuning uchun asl tugma o'zgarmaydi).
    """
    if style not in VALID_STYLES:
        raise ValueError(f"Noto'g'ri style: {style!r}. Ruxsat etilgan: {VALID_STYLES}")
    return button.model_copy(update={"style": style})