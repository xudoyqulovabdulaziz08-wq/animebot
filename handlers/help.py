from aiogram import Router, html, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from dotenv.main import logger
from aiogram.fsm.context import FSMContext
from services.navigation import NavigationManager
router = Router()

@router.callback_query(lambda c: c.data == "support")
async def support_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await NavigationManager(state).push("support")
    
    # 🖼 Aloqa bo'limi uchun rasm (Startdagi rasmni qoldirdik, o'zgartirmoqchi bo'lsangiz yangi file_id qo'yasiz)
    support_image_file_id = "AgACAgIAAxkBAAI8tGo2zRs85gamwlBSbIpQSyz3hfQQAAKAGWsbZ6WxSaBJmU2Y6WwRAQADAgADdwADPAQ"
    
    text = (
        "<b>💬 Yordam markazi</b>\n\n"
        "⚠️ Savolingiz yoki muammoingiz bormi?\n\n"
        "Quyidagi tugma orqali support bilan bog'laning. Imkon qadar muammoni batafsil yozsangiz, tezroq yordam bera olamiz."
    )
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Bog'lanish", url="https://t.me/Khudoyqulov_pg", style="success")],
            # ⬇️ "Orqaga" tugmasi start.py faylidagi 'back_to_start' handleriga ulandi!
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_global", style="danger")]
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