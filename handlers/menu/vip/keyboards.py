from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_vip_menu_kb(is_vip: bool) -> InlineKeyboardMarkup:
    btn_text = "🔄 VIP uzaytirish" if is_vip else "💳 VIP olish"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, callback_data="purchase_vip", style="primary")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="cabinet", style="danger")]
    ])

def get_vip_rates_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 1 oylik", callback_data="purchases_vip:1", style="primary"),
            InlineKeyboardButton(text="📅 2 oylik", callback_data="purchases_vip:2", style="primary")
        ],
        [
            InlineKeyboardButton(text="📅 3 oylik", callback_data="purchases_vip:3", style="primary"),
            InlineKeyboardButton(text="📅 6 oylik", callback_data="purchases_vip:6", style="primary")
        ],
        [
            InlineKeyboardButton(text="👑 1 yillik (Eng zo'ri)", callback_data="purchases_vip:12", style="primary")
        ],
        [
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data="buy_vip", style="danger")
        ]
    ])

def get_checkout_kb(admin_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Bog'lanish", url=admin_url, style="success")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="purchase_vip", style="danger")]
    ])