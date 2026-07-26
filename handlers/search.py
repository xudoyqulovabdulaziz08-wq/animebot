from aiogram import Router, html, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from dotenv.main import logger
from aiogram.fsm.context import FSMContext
router = Router()

@router.callback_query(lambda c: c.data == "search_menu")
async def search_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    
    
    
    text = (
        "🔍 <b>ANIME QIDIRISH</b>\n\n"
        "Qidiruv menyusiga xush kelibsiz! 🌟\n\n"
        "<blockquote expandable>📝 Anime nomi bo'yicha qidirish tezkor</blockquote>\n"
        "<blockquote expandable>🔢 Anime ID raqami bo'yicha qidirish</blockquote>\n"
        "<blockquote expandable>🎭 Janr  bo'yicha animeni saralash </blockquote>\n\n"
        "👇 Qidiruv usulini tanlang."
    )
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Nomi ", callback_data="search_by_name", style="primary")],
            [
                InlineKeyboardButton(text="🔢 ID ", callback_data="search_by_id", style="primary"),
                InlineKeyboardButton(text="🎭 Janr", callback_data="search_by_genre", style="primary") 
            ],
            
            # ⬇️ "Orqaga" tugmasi start.py faylidagi 'back_to_start' handleriga ulandi!
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_start", style="danger")]
        ]
    )
    
    try:
        # Matn o'rniga Media va Klaviatura birga chiroyli edit bo'ladi
        await callback.message.edit_caption(
            caption=text,
            parse_mode="HTML",
            reply_markup=kb
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
        # Agar xabar allaqachon o'zgargan bo'lsa, xato bermaymiz, shunchaki o'tkazib yuboramiz
            pass
        else:
            # Boshqa jiddiy xatolik bo'lsa logga yozamiz
            logger.error(f"❌ Kutilmagan xatolik: {e}")
    except Exception as e:
        logger.error(f"❌ Tizimda xatolik yuz berdi: {e}")









