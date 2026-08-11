from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_cabinet_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Parolni yangilash",
                    callback_data=f"refresh_web_code:{user_id}",
                    style="success"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💎 VIP bo'limi",
                    callback_data="buy_vip",
                    style="primary"
                ),
                InlineKeyboardButton(
                    text="📚 Animelarim",
                    callback_data="animelarim_cabinet",
                    style="primary"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Bosh menyu",
                    callback_data="back_to_start",
                    style="danger"
                )
            ]
        ]
    )