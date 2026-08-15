from aiogram import Router, html, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from dotenv.main import logger
from aiogram.fsm.context import FSMContext
router = Router()




@router.callback_query(lambda c: c.data == "admin_anime")
async def admin_anime(callback: CallbackQuery, state: FSMContext):
    # Tugma bosilganda yuqoridagi soat belgisini darhol o'chiramiz
    await callback.answer()
    
    
    # Umumiy dizayn tizimingizga mos, chiroyli va tartibli matn
    text = (
        f"📚 {html.bold('Anime boshqaruvi bo‘limi')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Ushbu bo‘lim orqali bazadagi animelarni tahrirlashingiz, "
        f"yangi kontent qo‘shishingiz yoki o‘chirishingiz mumkin.\n\n"
        f"👇 Kerakli amalni tanlang:"
    )
    
    # Telegram'ning yangi rang tizimiga moslangan tugmalar
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Anime qo‘shish", callback_data="add_anime", style="primary")],
            [InlineKeyboardButton(text="📋 Anime ro‘yxati", callback_data="list_type_menu", style="primary")], # Paginatsiya 1-sahifadan boshlanadi
            [InlineKeyboardButton(text="⬅️ Bosh panelga", callback_data="admin_panel", style="danger")]  
        ]
    )
    
    # 💡 UX ENGINIYERING ECHIMI: Xabar media (rasm/video) ekanligini tekshiramiz
    if callback.message.photo or callback.message.video:
        try:
            # Yakuniy posterli xabarni butunlay o'chirib tashlaymiz
            await callback.message.delete()
        except Exception:
            pass
        
        # Yangi toza matnli xabar ko'rinishida menyuni chiqaramiz
        await callback.message.answer(text=text, reply_markup=kb, parse_mode="HTML")
        return # Handler ishini shu yerda yakunlaydi

    # Agar xabar oddiy matn bo'lsa, edit_text silliq ishlayveradi
    try:
        await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            pass
        else:
            logger.error(f"❌ Anime bo'limida Telegram xatoligi: {e}")
    except Exception as e:
        logger.error(f"❌ Anime bo'limida kutilmagan xatolik: {e}")



@router.callback_query(lambda c: c.data == "list_type_menu")
async def list_type_menu_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    text = (
        f"📚 {html.bold('Anime ro‘yxati turi ')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Animelarni holatiga ko‘ra ko‘rish uchun "
        f"kerakli bo‘limni tanlang.\n\n"
        f"⚠️ Eslatib otamiz bu yerdagi harakatlarni orqaga qayatarib bo'lmaydi \n\n"
        f"👇 Bo‘limni tanlang:"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📚 Barcha animelar", callback_data="list_anime_page:1", style="primary")
            ],
            [
                InlineKeyboardButton(text="🟢 Tugallangan", callback_data="list_anime_end_page:1", style="primary"),
                InlineKeyboardButton(text="🟡 Davom etmoqda", callback_data="list_anime_contine_page:1", style="primary")
            ], # Paginatsiya 1-sahifadan boshlanadi
            [
                InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_anime", style="danger")
            ]  
        ]
    )
     # 💡 UX ENGINIYERING ECHIMI: Xabar media (rasm/video) ekanligini tekshiramiz
    if callback.message.photo or callback.message.video:
        try:
            # Yakuniy posterli xabarni butunlay o'chirib tashlaymiz
            await callback.message.delete()
        except Exception:
            pass
        
        # Yangi toza matnli xabar ko'rinishida menyuni chiqaramiz
        await callback.message.answer(text=text, reply_markup=kb, parse_mode="HTML")
        return # Handler ishini shu yerda yakunlaydi

    # Agar xabar oddiy matn bo'lsa, edit_text silliq ishlayveradi
    try:
        await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            pass
        else:
            logger.error(f"❌Anime royxat turi bo'limida Telegram xatoligi: {e}")
    except Exception as e:
        logger.error(f"❌Anime royxat turi kutilmagan xatolik: {e}")