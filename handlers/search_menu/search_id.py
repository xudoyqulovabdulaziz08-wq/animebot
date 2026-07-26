
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
        await callback.message.edit_caption(
            caption=text,
            parse_mode="HTML",
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
    
    # 🌟 "🔍 So'rov bajarilmoqda..." xabari yuboriladi (Bot qotib qolmasligi uchun)
    waiting_msg = await message.answer("🔍 So'rov bajarilmoqda...") 
    
    # Raqam ekanligini tekshirish
    if not raw_text.isdigit():
        try:
            await waiting_msg.delete()
            await message.delete()
        except:
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

    # 🌟 ANIME TOPILMASA: Chatni tozalab, yangi toza xato xabarini chiqaramiz
    if not anime:
        try:
            # 1. Vaqtinchalik "🔍 So'rov bajarilmoqda..." xabarini o'chiramiz
            await waiting_msg.delete()
            
            # 2. Foydalanuvchi yuborgan xato ID matnini o'chiramiz
            await message.delete()
            
            # 3. Orqada qolib ketgan "ID BO'YICHA QIDIRISH" rasmli interfeysini o'chiramiz
            if last_menu_id:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=last_menu_id)
        except Exception as e:
            logger.warning(f"⚠️ ID qidiruvida xabarlarni tozalashda xatolik: {e}")

        # Yangitdan toza xabar ko'rinishida xatolik oynasini yuboramiz
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

    # 🌟 ANIME TOPILSA: Tozalash mantig'ini yurgizib, kartani yuboramiz
    try:
        # Foydalanuvchi yozgan ID xabarini chatdan o'chiramiz (Netflix'da ortiqcha xabarlar turmaydi)
        await message.delete()
        
        # Eski "ID BO'YICHA QIDIRISH" rasmli interfeysini ham o'chiramiz
        if last_menu_id:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=last_menu_id)
    except Exception as e:
        logger.warning(f"⚠️ Anime topilganda eski xabarlarni o'chirishda xatolik: {e}")

    # 🚀 Universal funksiyaga o'chib ketishi uchun waiting_msg berib yuboriladi
    # send_anime_card funksiyasi o'sha vaqtinchalik xabarni o'chirib, o'rniga daxshatli posterni joylaydi!
    await send_anime_card(waiting_msg, anime, session)
    
    # Qidiruv muvaffaqiyatli tugagani uchun holatni tozalaymiz
    await state.clear()