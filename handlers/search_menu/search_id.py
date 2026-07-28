
from typing import Any
from aiogram import Router, html, types, F
from aiogram.fsm.state import StatesGroup, State

from services.anime_service import AnimeService
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message
from dotenv.main import logger
from aiogram.fsm.context import FSMContext
from handlers.search_menu.anime_card import send_anime_card



router = Router()
# Qidiruv holatlarini belgilash
class SearchStates(StatesGroup):
    waiting_for_anime_id = State()






@router.callback_query(lambda c: c.data == "search_by_id")
async def search_by_id(callback: CallbackQuery, state: FSMContext): # state qo'shildi
    await callback.answer()
    SEARCH_COVER = "AgACAgIAAxkBAAFQCZRqZCQF0c5psFnoAiOw5BrIOWe2-wACTRZrG9sKKEvA-QJNWCdkVAEAAwIAA20AAz0E"
    
    
    text = (
   
        "   <b>ID BO'YICHA QIDIRISH</b>\n"
        "═════════════════\n"
        "🔢 Iltimos, qidirayotgan anime ID sini yozib yuboring.\n\n"
        "⚠️ <b>Eslatma:</b> ID raqamlardan iborat bo'lib, har bir anime uchun yagona bo'ladi!"
    )
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="search_menu", style="danger")] 
        ]
    )
    
    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=SEARCH_COVER,
                caption=text,
                parse_mode="HTML"
            ),
            reply_markup=kb
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            pass
        else:
            logger.error(f"❌ Kutilmagan xatolik: {e}")
    except Exception as e:
        logger.error(f"❌ Tizimda xatolik yuz berdi: {e}")

    # 🚀 MANA SHU QATOR QO'SHILDI: Bot foydalanuvchidan ID kelishini kutadi
    await state.update_data(last_search_menu_id=callback.message.message_id)
    await state.set_state(SearchStates.waiting_for_anime_id)
    



@router.message(SearchStates.waiting_for_anime_id, F.text)
async def process_anime_id_search(message: Message, state: FSMContext, session: Any):
    raw_text = message.text.strip().replace("#", "")
    
    # Raqam ekanligini tekshirish
    if not raw_text.isdigit():
        try:
            await message.delete()
        except Exception:
            pass
            
        await message.answer("⚠️ Iltimos, faqat raqamlardan iborat ID kiriting!")
        return

    anime_id = int(raw_text)
    
    # 1. Baza/Keshdan animeni qidiramiz
    from services.anime_service import AnimeService
    anime_service = AnimeService(session=session)
    anime = await anime_service.get_anime(anime_id)

    # Xotiradan eski qidiruv menyusi ID-sini olamiz
    user_data = await state.get_data()
    last_menu_id = user_data.get("last_search_menu_id")

    # 🌟 ANIME TOPILMASA
    if not anime:
        try:
            # Foydalanuvchi yuborgan xato ID xabarini o'chiramiz
            await message.delete()
            
            # Orqada qolib ketgan "ID BO'YICHA QIDIRISH" rasmli interfeysini o'chiramiz
            if last_menu_id:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=last_menu_id)
        except Exception as e:
            logger.warning(f"⚠️ ID qidiruvida xabarlarni tozalashda xatolik: {e}")

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔁 Qayta urinish", callback_data="search_by_id", style="success")],
                [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="search_menu", style="danger")]
            ]
        )
        
        await message.answer(
            text=f"❌ <b>#{anime_id}</b> kodli anime topilmadi!\n\nQayta tekshirib ko'ring yoki boshqa ID kiriting.",
            reply_markup=kb,
            parse_mode="HTML"
        )
        return

    # 🌟 ANIME TOPILSA: Chatni darhol tozalaymiz!
    try:
        # 1. Foydalanuvchi yuborgan ID xabarini (masalan, "#123") DARHOL o'chiramiz
        await message.delete()
    except Exception as e:
        logger.warning(f"⚠️ Foydalanuvchi xabarini o'chirishda xato: {e}")

    try:
        # 2. Eski "ID BO'YICHA QIDIRISH" rasmli interfeysini o'chiramiz
        if last_menu_id:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=last_menu_id)
    except Exception as e:
        logger.warning(f"⚠️ Eski menyuni o'chirishda xatolik: {e}")

    # 3. Karta yuboriladi
    await send_anime_card(message, anime, session)
    
    # State'ni tozalaymiz
    await state.clear()