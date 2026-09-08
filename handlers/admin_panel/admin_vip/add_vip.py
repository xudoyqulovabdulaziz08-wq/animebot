import logging
import asyncio
from typing import Any
from datetime import datetime, timedelta, timezone
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.models import UserStatus, DBUser
from services.user_service import UserService
from database.cache import cache_manager

logger = logging.getLogger("AdminVIP")
router = Router()



# 1. VIP amallari uchun holatlar zanjiri
class AdminVIPStates(StatesGroup):
    wait_for_user_id = State()        # ID raqam kutish bosqichi
    wait_for_confirmation = State()   # Muddat tanlash va tasdiqlash bosqichi




# 2. "➕ VIP qo‘shish" tugmasi bosilganda
@router.callback_query(F.data == "add_vip")
async def process_add_vip_click(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminVIPStates.wait_for_user_id)
    
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_vip_panel", style="danger")]
    ])
    
    await callback.message.edit_text(
        text="🆔 <b>Iltimos, ELITE status bermoqchi bo'lgan foydalanuvchining Telegram ID raqamini yuboring:</b>\n\n"
             "<i>Masalan: 123456789</i>",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )
    await state.update_data(bot_msg_id=callback.message.message_id)
    await callback.answer()








@router.message(AdminVIPStates.wait_for_user_id, ~F.text.isdigit())
async def process_invalid_user_id(message: Message, state: FSMContext):
    # Admin yozgan noto'g'ri xabarni darhol o'chirib tashlaymiz
    try:
        await message.delete()
    except Exception:
        pass

    state_data = await state.get_data()
    bot_msg_id = state_data.get("bot_msg_id")

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_vip_panel", style="danger")]
    ])
    
    # Yangi xabar yubormasdan, eski bot xabarini tahrirlaymiz! (Chat toza turadi)
    if bot_msg_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=bot_msg_id,
                text="⚠️ <b>Xato format!</b> ID raqami faqat sonlardan iborat bo'lishi kerak.\n"
                     "Iltimos, qaytadan faqat raqamlarni yuboring:",
                reply_markup=cancel_kb,
                parse_mode="HTML"
            )
        except Exception:
            pass









# 5. 🔥 TUZATISH: To'g'ri ID kelganda keyingi holatga (State) o'tkazamiz
# 4. 🔥 To'g'ri ID kelganda — HAMMA O'LIK XABARLARNI O'CHIRISH
@router.message(AdminVIPStates.wait_for_user_id, F.text.isdigit())
async def process_valid_user_id(message: Message, state: FSMContext, session: Any):
    user_id = int(message.text)
    
    # 💾 Keshdan bot yuborgan eski xabar ID sini olamiz
    state_data = await state.get_data()
    bot_msg_id = state_data.get("bot_msg_id")

    # 🗑 UX Tozalash: Admin yozgan xabarni (ID raqamni) chatdan o'chiramiz
    try:
        await message.delete()
    except Exception:
        pass

    # 🗑 UX Tozalash: Botning "ID yuboring" degan eski xabarini ham o'chiramiz
    if bot_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=bot_msg_id)
        except Exception:
            pass

    # Bazadan qidirish amali
    try:
        user_service = UserService(session=session)
        user_data = await user_service.get_user(user_id=user_id)
    except Exception as e:
        logger.error(f"ELITE tekshiruvida user qidirishda xato: {e}")
        error_msg = await message.answer("❌ Qidirishda texnik xatolik yuz berdi.")
        await state.update_data(bot_msg_id=error_msg.message_id)
        return

    # User topilmasa
    if not user_data:
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_vip_panel", style="danger")]
        ])
        # Yangi toza xabar chiqarib, uning ID sini keshga yozamiz
        new_error = await message.answer(
            text=f"❌ <b>ID: {user_id}</b> raqamli foydalanuvchi tizimda mavjud emas!\n"
                 f"Iltimos, qayta kiriting:",
            reply_markup=cancel_kb,
            parse_mode="HTML"
        )
        await state.update_data(bot_msg_id=new_error.message_id)
        return

    # Foydalanuvchi topilsa, yangi holatga o'tamiz
    await state.update_data(target_user_id=user_id)
    await state.set_state(AdminVIPStates.wait_for_confirmation)
    
    username = user_data.get("username") or "Foydalanuvchi"
    current_status = user_data.get("status", "user")

    duration_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 1 Oylik", callback_data="set_vip_duration:1", style="primary"),
            InlineKeyboardButton(text="📅 2 Oylik", callback_data="set_vip_duration:2", style="primary")
        ],
        [
            InlineKeyboardButton(text="📅 3 Oylik", callback_data="set_vip_duration:3", style="primary"),
            InlineKeyboardButton(text="📅 6 Oylik", callback_data="set_vip_duration:6", style="primary")
        ],
        [
            InlineKeyboardButton(text="📆 1 Yillik", callback_data="set_vip_duration:12", style="primary")
        ],
        [
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_vip_panel", style="danger")
        ]
    ])

    await message.answer(
        text=f"🔍 <b>Foydalanuvchi topildi!</b>\n\n"
             f"👤 <b>Nomi:</b> {username}\n"
             f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
             f"📊 <b>Joriy statusi:</b> <code>{current_status.upper()}</code>\n\n"
             f"✨ <i>Iltimos, ushbu foydalanuvchi uchun ELITE muddatini tanlang:</i>",
        reply_markup=duration_kb,
        parse_mode="HTML"
    )

















# 6. Muddat tugmalari bosilganda (Faqat shu holatda ishlaydi)
@router.callback_query(AdminVIPStates.wait_for_confirmation, F.data.startswith("set_vip_duration:"))
async def process_set_duration(callback: CallbackQuery, state: FSMContext):
    months = int(callback.data.split(":")[1])
    
    state_data = await state.get_data()
    target_user_id = state_data.get("target_user_id")
    
    if not target_user_id:
        await callback.answer("🚨 Xatolik: Foydalanuvchi ID topilmadi!", show_alert=True)
        await state.clear()
        return

    await state.update_data(selected_months=months)
    
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha", callback_data="confirm_vip_grant:yes", style="success"),
            InlineKeyboardButton(text="❌ Yo'q", callback_data="confirm_vip_grant:no", style="danger")
        ]
    ])

    duration_text = f"{months} oylik" if months < 12 else "1 yillik"

    await callback.message.edit_text(
        text=f"❓ <b>Tasdiqlash:</b>\n\n"
             f"Rostdan ham <code>{target_user_id}</code> ID raqamli foydalanuvchini "
             f"<b>{duration_text}</b> muddatga <b>ELITE</b> qilmoqchimisiz?",
        reply_markup=confirm_kb,
        parse_mode="HTML"
    )
    await callback.answer()













# 7. "Ha" yoki "Yo'q" bosilganda yakuniy amallar
@router.callback_query(AdminVIPStates.wait_for_confirmation, F.data.startswith("confirm_vip_grant:"))
async def process_vip_confirmation(callback: CallbackQuery, state: FSMContext, session: Any):
    decision = callback.data.split(":")[1]
    
    state_data = await state.get_data()
    target_user_id = state_data.get("target_user_id")
    months = state_data.get("selected_months")
    
    await state.clear()

    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 ELITE Panelga qaytish", callback_data="admin_vip_panel", style="danger")]
    ])

    if decision == "no":
        await callback.message.edit_text(
            text="❌ <b>ELITE status berish jarayoni admin tomonidan bekor qilindi.</b>",
            reply_markup=back_kb,
            parse_mode="HTML"
        )
        await callback.answer()
        return

    await callback.answer("⏳ ELITE status faollashtirilmoqda...", show_alert=False)

    try:
        days_to_add = months * 30
        expire_date = datetime.now(timezone.utc) + timedelta(days=days_to_add)

        from sqlalchemy import update
        stmt = (
            update(DBUser)
            .where(DBUser.user_id == target_user_id)
            .values(status=UserStatus.VIP, vip_expire_date=expire_date)
        )
        await session.execute(stmt)
        await session.commit()

        await cache_manager.invalidate("users", str(target_user_id), broadcast=True)
        await cache_manager.invalidate("sub_status", str(target_user_id), broadcast=True)

        formatted_date = expire_date.strftime("%d.%m.%Y %H:%M")
        duration_text = f"{months} oylik" if months < 12 else "1 yillik"

        await callback.message.edit_text(
            text=f"🚀 <b>Muvaffaqiyatli bajarildi!</b>\n\n"
                 f"👤 Foydalanuvchi: <code>{target_user_id}</code>\n"
                 f"💎 Status: <b>ELITE ({duration_text})</b>\n"
                 f"📅 Tugash muddati: <code>{formatted_date}</code> gacha belgilandi.\n\n"
                 f"<i>Kesh yangilandi.</i>",
            reply_markup=back_kb,
            parse_mode="HTML"
        )

        try:
            await callback.bot.send_message(
                chat_id=target_user_id,
                text=f"🎉 <b>Tabriklaymiz! Admin tomonidan sizga {duration_text} ELITE status taqdim etildi!</b>\n"
                     f"📅 ELITE muddati: <code>{formatted_date}</code> gacha faol. \n"
                     f"⚠️ Eslatib otamiz vaqt mintaqasi bizning soatdan 5 soat orqada bu bilan hech qanday muddat qoshmaydi yoki muddat kamaymaydi",
                parse_mode="HTML"
            )
        except Exception:
            pass

    except Exception as db_err:
        await session.rollback()
        logger.error(f"❌ ELITE status berishda xato: {db_err}")
        await callback.message.edit_text(
            text="❌ <b>Texnik xatolik:</b> ELITE status berish amalga oshmadi.",
            reply_markup=back_kb,
            parse_mode="HTML"
        )