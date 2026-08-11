import logging
from typing import Any
from aiogram import Router
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from services.user_service import UserService
from services.anime_service import AnimeService
from handlers.search.anime_card import send_anime_card
from config import config
from handlers.start.helpers import send_or_edit_start_menu

logger = logging.getLogger("StartCmdRouter")
CREATOR_ID = config.CREATOR_ID



router = Router()



@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, session: Any, user: dict, user_service: UserService, state: FSMContext):
    await state.clear()
    
    user_id = message.from_user.id
    username = message.from_user.username or "do'stim"
    user_status = user.get('status', 'user').lower()
    
    # 🚀 KANAL TUGMASIDAN PARAMETR KELGANDA
    if command.args:
        waiting_msg = await message.answer("🔍 Yuborilmoqda...")
        clean_args = command.args.strip().rstrip(",")
        
        anime_id = None
        
        # Agarda saytdan faqat raqam kelsa
        if clean_args.isdigit():
            anime_id = int(clean_args)
            
        # Agarda kanaldan anime_15 ko'rinishida kelsa
        elif clean_args.startswith("anime_"):
            try:
                anime_id = int(clean_args.split("_")[1])
            except ValueError:
                pass

        # Agar ID muvaffaqiyatli aniqlangan bo'lsa
        if anime_id is not None:
            try:
                from services.anime_service import AnimeService
                service = AnimeService(session=session)
                anime = await service.get_anime(anime_id)
                
                if anime:
                    await send_anime_card(waiting_msg, anime, session)
                    return
                else:
                    await waiting_msg.delete()
                    
            except Exception as ex:
                logger.error(f"❌ Deep link ishlashida xatolik: {ex}")
                try:
                    await waiting_msg.delete()
                except:
                    pass
        else:
            # Agar argument noto'g'ri formatda bo'lsa xabarni o'chirish
            try:
                await waiting_msg.delete()
            except:
                pass

    # Agarda oddiy start bo'lsa yoki anime topilmasa, asosiy menyuni chiqaradi
    await send_or_edit_start_menu(message, user_id, username)

    # Admin/Creator panellari
    if user_id == CREATOR_ID:
        creator_keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="⚙️ Creator Paneli"), KeyboardButton(text="🛠 Admin Paneli")]],
            resize_keyboard=True
        )
        await message.answer("👑 Tizim asoschisi! Barcha boshqaruv panellari faollashtirildi:", reply_markup=creator_keyboard)
        
    elif user_status == 'admin':
        admin_keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🛠 Admin Paneli")]],
            resize_keyboard=True
        )
        await message.answer("🛡 Tizim administratori tan olindi. Admin boshqaruv paneli faollashtirildi:", reply_markup=admin_keyboard)
