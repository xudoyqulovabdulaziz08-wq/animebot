


from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest

router = Router()


def get_history_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                text="⏺️ Tugatilgan",
                callback_data="history_completed",
                style="primary"
            ),
            InlineKeyboardButton(
                text="🕣 Ko‘rilmoqda",
                callback_data="history_watching",
                style="primary"
            )
        ],
        
        [
            InlineKeyboardButton(
                text="⬅️ Orqaga",
                callback_data="animelarim_cabinet",
                style="danger"
            )
        ]
    ]

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.callback_query(F.data == "cabinet_history")
async def show_watching_history(callback: CallbackQuery):

    caption = (
        "📜 <b>Ko‘rish tarixi</b>\n\n"
        "<blockquote >"
        "Bu bo‘limda ko‘rgan va hozir ko‘rayotgan "
        "animelaringiz saqlanadi."
        "</blockquote>\n\n"
        "Kerakli bo‘limni tanlang."
    )

    keyboard = get_history_keyboard()

    try:
        await callback.message.edit_caption(
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        await callback.answer()

    except TelegramBadRequest:
        await callback.answer()