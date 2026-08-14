import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from services.subscription_service import SubscriptionService
from config import config

logger = logging.getLogger("obunalarim")
router = Router()

CREATOR_ID = config.CREATOR_ID


@router.callback_query(F.data.startswith("anime_subscription:"))
async def anime_subscription_handler(callback: CallbackQuery, session: AsyncSession):
    # 🔒 Oddiy foydalanuvchilar uchun vaqtincha cheklov (Test rejimida)
    if callback.from_user.id != CREATOR_ID:
        await callback.answer(
            text="🛑 Obuna bo'lish funksiyasi tez orada ishga tushadi.",
            show_alert=True
        )
        return

    anime_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    # 1. ✅ SUBSCRIPTION SERVICE ORQALI TOGGLE QILISH
    sub_service = SubscriptionService(session=session)

    try:
        # True -> Obuna bo'lindi, False -> Obuna bekor qilindi
        is_subscribed = await sub_service.toggle_subscription(user_id=user_id, anime_id=anime_id)
    except Exception as err:
        logger.error(f"❌ Obunani toggle qilishda xatolik: {err}")
        await callback.answer(
            text="❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.",
            show_alert=True
        )
        return

    # 2. Xabar matni va yangi tugma nomini tayyorlash
    if is_subscribed:
        msg_text = "🔔 Ushbu animega muvaffaqiyatli obuna bo'ldingiz!\n\nYangi qismlar chiqqanda xabar beramiz."
        new_sub_text = "🔔 Obunadasiz ✓"
    else:
        msg_text = "🔕 Obuna bekor qilindi."
        new_sub_text = "🔔 Obuna"

    # 3. 🪄 TUGMANI EKRANDA DARHOL YANGILASH (EDIT REPLY MARKUP)
    if callback.message and callback.message.reply_markup:
        current_markup = callback.message.reply_markup
        new_inline_keyboard = []

        # Xabardagi barcha tugmalarni ko'rib chiqamiz
        for row in current_markup.inline_keyboard:
            new_row = []
            for button in row:
                # Aynan shu Obuna tugmasini topsak, matnini yangilaymiz
                if button.callback_data == callback.data:
                    new_row.append(
                        InlineKeyboardButton(
                            text=new_sub_text,
                            callback_data=button.callback_data,
                            style="primary"
                        )
                    )
                else:
                    new_row.append(button)
            new_inline_keyboard.append(new_row)

        # Klaviaturani almashtiramiz
        try:
            await callback.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(inline_keyboard=new_inline_keyboard)
            )
        except Exception as edit_err:
            logger.error(f"❌ Tugmani yangilashda xato: {edit_err}")

    # 4. Pop-up alert chiqarish
    await callback.answer(
        text=msg_text,
        show_alert=True
    )