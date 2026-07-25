import logging
import asyncio
from aiogram import Router, F, html
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from services.user_service import UserService  # O'zingizning service yo'lingiz

logger = logging.getLogger("CabinetHandler")
router = Router()






@router.callback_query(F.data == "cabinet")
@router.callback_query(F.data.startswith("refresh_web_code:"))
async def open_cabinet_handler(callback: CallbackQuery, user_service: UserService):
    user_id = callback.from_user.id
    user_data = await user_service.get_user(callback.from_user.id)
    user_data = user_service._ensure_fresh_vip_status(user_data)
    
    is_vip = user_data.get("is_vip", False)
    vip_expire = user_data.get("vip_expire_date") # ISO string formatda keladi

    current_data = callback.data
    # Yuklanish holati anomal ko'rinmasligi uchun chiroyli eslatma
    await callback.answer("⏳ Shaxsiy kabinet yuklanmoqda...")

    # 1. Tranzaksiyaviy va keshga mos biznes mantiqi orqali kodni generatsiya qilamiz
    try:
        if current_data.startswith("refresh_web_code:"):
            # Agar foydalanuvchi "Parolni yangilash" tugmasini bosgan bo'lsa
            password = await user_service.refresh_web_auth_code(user_id)
            alert_text = "🔄 Yangi xavfsiz parol yaratildi va bazada yangilandi!"
        else:
            # Oddiy kabinetga kirish tugmasi bosilganda
            password = await user_service.generate_web_auth_code(user_id)
            alert_text = None

    except Exception as err:
        logger.error(f"❌ Shaxsiy kabinet mantiqida xatolik (user_id={user_id}): {err}")
        password = None

    # 2. Agar bazadan yoki servisdan kod kelmasa (Favqulodda holat uchun xavfsizlik)
    if not password:
        await callback.message.answer(
            "❌ Kechirasiz, ayni vaqtda shaxsiy kabinet tizimi vaqtincha ishlamayapti.\n"
            "Tizimda texnik ishlar olib borilayotgan bo'lishi mumkin. Birozdan so'ng qayta urinib ko'ring."
        )
        return

    status = "💎 VIP" if is_vip else "👤 Oddiy"

    cabinet_text = (
        f"👤 <b>SHAXSIY KABINET</b>\n\n"

        f"🌐 <b>Aninov.uz</b> saytiga kirish uchun:\n\n"

        f"🆔 <b>Telegram ID</b>\n"
        f"<code>{user_id}</code>\n\n"

        f"🔑 <b>Bir martalik parol</b>\n"
        f"<code>{password}</code>\n\n"

        f"💎 <b>Status:</b> {status}\n\n"

        f"⏳ <i>Parol 15 daqiqa amal qiladi.</i>\n"
        f"📋 <i>ID yoki parol ustiga bosib nusxalashingiz mumkin.</i>"
    )

    # 4. Inline tugmalar (Faqat bitta joyda chiroyli joylashuv)
    cabinet_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Parolni yangilash",
                    callback_data=f"refresh_web_code:{user_id}",
                    style="primary"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💎 VIP bo'limi",
                    callback_data="buy_vip",
                    style="success"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Bosh menyu",
                    callback_data="back_to_start",
                    style="danger"
                )
            ]
        ]
    )

    # 5. Media Edit (Rasm caption-ini tahrirlash) orqali oynani yangilash
    try:
        await callback.message.edit_caption(
            caption=cabinet_text,
            reply_markup=cabinet_keyboard,
            parse_mode="HTML"
        )
        
        # Agar parol yangilangan bo'lsa, foydalanuvchiga tepadan chiroyli bildirishnoma (toast) chiqaramiz
        if alert_text:
            await callback.answer(alert_text, show_alert=True)
            
    except Exception as edit_error:
        logger.debug(f"Media caption edit dynamic fallback triggered: {edit_error}")
        # Agar qandaydir sabab bilan rasm captionini tahrirlab bo'lmasa, yangi xabar ko'rinishida yuboradi
        await callback.message.answer(
            text=cabinet_text,
            reply_markup=cabinet_keyboard,
            parse_mode="HTML"
        )