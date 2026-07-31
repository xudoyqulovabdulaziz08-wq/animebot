
from typing import Any
from aiogram import Router, html, types, F
from aiogram.fsm.state import StatesGroup, State

from services.anime_service import AnimeService
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message
from dotenv.main import logger
from aiogram.fsm.context import FSMContext
from handlers.search_menu.anime_card import send_anime_card
from config import config
POSTER_ID = config.RASM_ID

router = Router()




class SearchStates(StatesGroup):
    
    waiting_for_anime_name = State()

















@router.callback_query(lambda c: c.data == "search_by_name")
async def search_by_name(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    SEARCH_COVER = POSTER_ID
    
    
    text = (
        "🔎 <b>NOMI BO'YICHA QIDIRISH</b>\n"
        "═════════════════\n"
        "⚠️ Anime nomini aniq yuborsangiz qidiriv natijlari ham tez va aniq boladi\n\n"
        "✍️ Iltimos, qidirayotgan anime nomini  yozib yuboring.\n\n"
        
    )
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="search_menu", style="danger")]
        ]
    )
    
    try:
        # Eski xabarni yangi rasm va matnga silliqqina o'zgartiramiz
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

    # 🚀 UX INOVATSIYA: Aynan shu tahrirlangan xabar ID-sini va holatni saqlaymiz!
    await state.update_data(last_search_menu_id=callback.message.message_id)
    await state.set_state(SearchStates.waiting_for_anime_name)




@router.message(SearchStates.waiting_for_anime_name, F.text)
async def process_anime_name_search(message: Message, state: FSMContext, session: Any):
    search_query = message.text.strip().lower()
    
    # 🌟 Foydalanuvchiga jarayon ketayotganini bildirish
    
    
    # 1. Keshdan barcha animelarning qidiruv xaritasi (ID va Nomlari) olinadi
    from services.anime_service import AnimeService
    anime_service = AnimeService(session=session)
    search_map = await anime_service.get_search_map()
    
    # 2. Foydalanuvchi yozgan so'z qatnashgan barcha animelarni qidiramiz
    found_animes = []
    for anime_id, anime_title in search_map.items():
        if search_query in anime_title.lower():
            found_animes.append((anime_id, anime_title))
            
    # 🌟 UX TOZALASH: Barcha eski interfeys va matnlarni chatdan tozalaymiz
    user_data = await state.get_data()
    last_menu_id = user_data.get("last_search_menu_id")
    
    try:
       
        
        # Foydalanuvchi yozgan matnli xabarni o'chiramiz
        await message.delete()
        
        # Orqada qolib ketayotgan "NOMI BO'YICHA QIDIRISH" rasmli interfeysini o'chiramiz
        if last_menu_id:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=last_menu_id)
    except Exception as e:
        logger.warning(f"⚠️ Xabarlarni tozalashda xatolik (ehtimol allaqachon o'chgan): {e}")

    # 3. Agar hech qanday anime topilmasa
    if not found_animes:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔁 Qayta urinish", callback_data="search_by_name", style="success")],
                [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="search_menu", style="danger")]
            ]
        )
        await message.answer(
            text=f"🔍 <b>\"{message.text}\"</b> bo'yicha hech qanday anime topilmadi.\n\nQayta tekshirib ko'ring yoki boshqa nom kiriting.",
            reply_markup=kb,
            parse_mode="HTML"
        )
        return

    # 4. Agar anime(lar) topilsa, ularni tugma ko'rinishida generatsiya qilamiz
    buttons = []
    for anime_id, anime_title in found_animes[:15]: # Premium UX uchun maksimal 15 ta natija
        buttons.append([InlineKeyboardButton(
            text=f"🎬 {anime_title}", 
            callback_data=f"view_anime_detals_{anime_id}" # Biz boya yozgan daxshatli pleyer pultiga ulanadi
        )])
        
    # Pastiga bosh menyuga qaytish tugmasi
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="search_menu", style="danger")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(
        text=f"🎯 <b>Natijalar (Topildi: {len(found_animes)} ta):</b>\n\nQuyidagilardan o'zingizga kerakli fasl yoki filmni tanlang:",
        reply_markup=kb,
        parse_mode="HTML"
    )
    
    # Qidiruv yakunlangani uchun stateni tozalaymiz
    await state.clear()









@router.callback_query(F.data.startswith("view_anime_detals_"))
async def view_anime_details(callback: CallbackQuery, session: Any):
    """
    Nomi bo'yicha qidiruvdan so'ng tanlangan animeni universal dizaynda ko'rsatadi.
    Telegram API cheklovlariga va xabarlarni toza o'chirishga moslashtirildi.
    """
    # 1. Callback ma'lumotidan anime_id ni ajratib olamiz
    try:
        # split("_")[3] chunki data: "view_anime_detals_{id}" -> indexlar: 0:"view", 1:"anime", 2:"detals", 3:{id}
        anime_id = int(callback.data.split("_")[3])
    except (IndexError, ValueError):
        await callback.answer("⚠️ Ma'lumotni o'qishda xatolik yuz berdi!", show_alert=True)
        return

    # 2. Darhol foydalanuvchiga jarayon ketayotganini bildiramiz
    await callback.answer()

    # 3. Nomi bo'yicha qidiruv natijalari turgan eski xabarni (tugmalari bilan) o'chirib tashlaymiz
    try:
        await callback.message.delete()
    except Exception as e:
        logger.debug(f"Eski qidiruv ro'yxatini o'chirishda xatolik: {e}")

    # 4. Biznes mantiq qatlami orqali anime ma'lumotlarini olamiz
    from services.anime_service import AnimeService
    anime_service = AnimeService(session=session)
    anime = await anime_service.get_anime(anime_id)

    if not anime:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔁 Qayta urinish", callback_data="search_by_name", style="success")],
                [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="search_menu", style="danger")]
            ]
        )
        await callback.message.answer(
            text="❌ Kechirasiz, ushbu anime ma'lumotlar bazasidan topilmadi.",
            reply_markup=kb,
            parse_mode="HTML"
        )
        return

    # 🚀 DAXSHAT UNIVERSAL DIZAYNGA YUBORAMIZ:
    # ✅ TO'G'RILANDI: 3 ta argument to'liq uzatildi (message, anime, session)
    await send_anime_card(callback.message, anime, session)