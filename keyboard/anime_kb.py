from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

async def anime_control_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Yangi Anime", callback_data="admin_add_anime"),
            InlineKeyboardButton("🎞 Yangi Epizod", callback_data="admin_add_episode")
        ],
        [
            InlineKeyboardButton("✏️ Tahrirlash", callback_data="admin_edit_anime"),
            InlineKeyboardButton("📜 Barcha Animelar", callback_data="admin_list_anime")
        ], # <-- Shu yerda vergul tushib qolgan edi
        [
            InlineKeyboardButton("🗑 Animeni o'chirish", callback_data="admin_delete_anime"),
            InlineKeyboardButton("🧨 Epizodni o'chirish", callback_data="admin_delete_episode")
        ],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_admin_main")]
    ])
    
    await query.edit_message_text(
        "<b>🎬 Anime Boshqaruv Markazi</b>\n\n"
        "<i>Bu bo'limda siz bazadagi kontentni to'liq nazorat qilishingiz mumkin. "
        "Kerakli amalni tanlang:</i>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
