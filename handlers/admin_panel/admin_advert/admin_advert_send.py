import asyncio
import logging
from typing import Any
from aiogram import Router, html, types, F
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from services.user_service import UserService
from utils.keyboard_utils import make_button, make_keyboard, safe_link

router = Router()
logger = logging.getLogger("AdminVIP")


class AdminAdvertSG(StatesGroup):
    waiting_for_ad = State()


async def run_advert_broadcast(bot, user_ids, target_group, from_chat_id, ad_message_id, main_msg_id, state):
    """Orqa fonda xabarlarni tarqatadi, so'ngra admin postini o'chirib, asosiy oynani hisobotga tahrirlaydi"""

    success_count = 0
    fail_count = 0

    for uid in user_ids:
        # 🔁 Flood-control bilan xavfsiz jo'natish (Telegram RetryAfter'ni hurmat qilamiz)
        for attempt in range(2):
            try:
                await bot.copy_message(chat_id=uid, from_chat_id=from_chat_id, message_id=ad_message_id)
                success_count += 1
                break
            except TelegramRetryAfter as flood_err:
                logger.warning(f"⏳ FloodWait: {flood_err.retry_after}s kutilmoqda...")
                await asyncio.sleep(flood_err.retry_after)
                continue
            except Exception as e:
                fail_count += 1
                logger.debug(f"Broadcast error for user {uid}: {e}")
                break
        await asyncio.sleep(0.05)

    try:
        await bot.delete_message(chat_id=from_chat_id, message_id=ad_message_id)
    except Exception:
        pass

    await state.clear()

    back_kb = make_keyboard([
        [make_button(text="⬅️ Reklama bo'limiga qaytish", callback_data="admin_advert")]
    ])

    report_text = (
        f"📊 <b>Reklama tarqatish yakunlandi!</b>\n\n"
        f"🎯 Target guruh: <code>{target_group.upper()}</code>\n"
        f"✅ Muvaffaqiyatli yetkazildi: <code>{success_count} ta</code>\n"
        f"❌ Yetkazilmadi (Botni bloklaganlar): <code>{fail_count} ta</code>\n\n"
        f"✨ <i>Admin paneli toza saqlandi. Quyidagi tugma orqali ortga qaytishingiz mumkin:</i>"
    )

    try:
        await bot.edit_message_text(
            chat_id=from_chat_id, message_id=main_msg_id,
            text=report_text, reply_markup=back_kb, parse_mode="HTML"
        )
    except Exception:
        try:
            await bot.send_message(chat_id=from_chat_id, text=report_text, reply_markup=back_kb, parse_mode="HTML")
        except Exception:
            pass


@router.callback_query(F.data == "admin_advert")
async def process_admin_advert_menu(callback: CallbackQuery):
    await callback.answer()

    advert_kb = make_keyboard([
        [make_button(text="🌍 Hammaga (User, VIP, Admin)", callback_data="send_adv:all", style="primary")],
        [make_button(text="💎 Faqat VIP foydalanuvchilarga", callback_data="send_adv:vip", style="primary")],
        [make_button(text="👤 Faqat oddiy foydalanuvchilarga", callback_data="send_adv:user", style="primary")],
        [make_button(text="🛠 Faqat Adminlarga", callback_data="send_adv:admin", style="primary")],
        [make_button(text="⬅️ Orqaga", callback_data="admin_panel", style="danger")],
    ])

    await callback.message.edit_text(
        text="📢 <b>Reklama va Bildirishnomalar yuborish bo'limi</b>\n\n"
             "<i>Ushbu bo'lim orqali bot foydalanuvchilariga reklama, aksiya yoki texnik "
             "xabarlarni yuborishingiz mumkin.</i>\n\n"
             "✨ Xabar yubormoqchi bo'lgan maqsadli (target) guruhni tanlang:",
        reply_markup=advert_kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("send_adv:"))
async def process_select_advert_target(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    parts = callback.data.split(":")
    if len(parts) < 2:
        await callback.answer("❌ Noto'g'ri format!", show_alert=True)
        return
    target_group = parts[1]

    group_titles = {
        "all": "🌍 Hammaga (User, VIP, Admin)",
        "vip": "💎 Faqat VIP foydalanuvchilarga",
        "user": "👤 Faqat oddiy foydalanuvchilarga",
        "admin": "🛠 Faqat Adminlarga"
    }
    title = group_titles.get(target_group)
    if not title:
        await callback.answer("❌ Noma'lum target guruh!", show_alert=True)
        return

    await state.update_data(target_group=target_group, group_title=title, main_msg_id=callback.message.message_id)
    await state.set_state(AdminAdvertSG.waiting_for_ad)

    cancel_kb = make_keyboard([
        [make_button(text="❌ Bekor qilish", callback_data="admin_advert", style="danger")]
    ])

    await callback.message.edit_text(
        text=f"🎯 Target guruh: <b>{title}</b>\n\n"
             f"📥 <b>Iltimos, yubormoqchi bo'lgan reklama xabaringizni shu yerga yuboring...</b>\n\n"
             f"<i>(Matn, rasm, video, albom, hujjat yoki inline tugmali xabar bo'lishi mumkin.)</i>",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )


@router.message(AdminAdvertSG.waiting_for_ad)
async def process_receive_advert_message(message: Message, state: FSMContext):
    data = await state.get_data()
    main_msg_id = data.get("main_msg_id")
    title = data.get("group_title")

    await state.update_data(ad_message_id=message.message_id, ad_chat_id=message.chat.id)

    confirm_kb = make_keyboard([[
        make_button(text="✅ Ha, tarqatilsin", callback_data="adv_confirm:yes", style="primary"),
        make_button(text="❌ Yo'q, bekor qilinsin", callback_data="adv_confirm:no", style="danger"),
    ]])

    confirm_text = (
        f"❓ <b>Reklamani tasdiqlash</b>\n\n"
        f"🎯 Target guruh: <b>{title}</b>\n\n"
        f"Siz yuborgan reklama xabari muvaffaqiyatli qabul qilindi. "
        f"Ushbu xabarni barcha maqsadli foydalanuvchilarga tarqatishni tasdiqlaysizmi?"
    )

    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id, message_id=main_msg_id,
            text=confirm_text, reply_markup=confirm_kb, parse_mode="HTML"
        )
    except Exception:
        confirm_msg = await message.reply(text=confirm_text, reply_markup=confirm_kb, parse_mode="HTML")
        await state.update_data(main_msg_id=confirm_msg.message_id)


@router.callback_query(F.data.startswith("adv_confirm:"))
async def process_final_advert_decision(callback: CallbackQuery, state: FSMContext, user_service: UserService):
    parts = callback.data.split(":")
    if len(parts) < 2:
        await callback.answer("❌ Noto'g'ri format!", show_alert=True)
        return
    decision = parts[1]

    data = await state.get_data()
    main_msg_id = data.get("main_msg_id")
    ad_message_id = data.get("ad_message_id")
    ad_chat_id = data.get("ad_chat_id")

    if not all([main_msg_id, ad_message_id, ad_chat_id]):
        await callback.answer("⚠️ Sessiya eskirgan, qaytadan boshlang.", show_alert=True)
        await state.clear()
        return

    if decision == "no":
        await callback.answer("Reklama bekor qilindi.")
        try:
            await callback.bot.delete_message(chat_id=ad_chat_id, message_id=ad_message_id)
        except Exception:
            pass
        await state.clear()

        back_kb = make_keyboard([[make_button(text="⬅️ Orqaga", callback_data="admin_advert")]])
        await callback.message.edit_text(
            text="❌ <b>Reklama yuborish bekor qilindi.</b>\n\n"
                 "Siz yuborgan reklama xabari o'chirildi va panel toza saqlandi.",
            reply_markup=back_kb,
            parse_mode="HTML"
        )
        return

    target_group = data.get("target_group")
    await callback.answer("🚀 Tarqatish boshlandi!", show_alert=False)

    try:
        user_ids = await user_service.get_target_user_ids(target_group)
    except Exception as e:
        logger.error(f"❌ Foydalanuvchilar ro'yxatini olishda xato: {e}")
        await callback.message.edit_text("❌ Foydalanuvchilar ro'yxatini yuklashda xatolik yuz berdi.")
        await state.clear()
        return

    if not user_ids:
        await callback.message.edit_text("⚠️ Bu guruhda foydalanuvchi topilmadi.")
        await state.clear()
        return

    asyncio.create_task(
        run_advert_broadcast(
            bot=callback.bot, user_ids=user_ids, target_group=target_group,
            from_chat_id=ad_chat_id, ad_message_id=ad_message_id,
            main_msg_id=main_msg_id, state=state
        )
    )

    await callback.message.edit_text(
        text="🚀 <b>Reklama orqa fonda tarqatila boshladi!</b>\n\n"
             "Bot foydalanuvchilarga odatiy rejimda xizmat ko'rsatishda davom etadi.",
        parse_mode="HTML"
    )