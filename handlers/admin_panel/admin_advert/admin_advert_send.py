import asyncio
import logging
from typing import Any
from aiogram import Router, html, types, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from services.user_service import UserService
from utils.keyboard_utils import make_button, make_keyboard

router = Router()
logger = logging.getLogger("AdminVIP")


class AdminAdvertSG(StatesGroup):
    waiting_for_ad = State()
    waiting_for_btn_text = State()
    waiting_for_btn_url = State()
    waiting_for_btn_style = State()

# ---------------------------------------------------------
# 0. REKLAMA MENYUSIGA KIRISH (admin_advert)
# ---------------------------------------------------------

@router.callback_query(F.data == "admin_advert")
async def process_admin_advert_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    # Har safar reklama menyusiga kirganda oldingi qolib ketgan kesh(state)larni tozalaymiz
    await state.clear() 

    advert_kb = make_keyboard([
        [make_button(text="🌍 Hammaga (User, VIP, Admin)", callback_data="send_adv:all", style="primary")],
        [make_button(text="💎 Faqat VIP foydalanuvchilarga", callback_data="send_adv:vip", style="primary")],
        [make_button(text="👤 Faqat oddiy foydalanuvchilarga", callback_data="send_adv:user", style="primary")],
        [make_button(text="🛠 Faqat Adminlarga", callback_data="send_adv:admin", style="primary")],
        [make_button(text="⬅️ Orqaga", callback_data="admin_panel", style="danger")]
    ])

    await callback.message.edit_text(
        text="📢 <b>Reklama va Bildirishnomalar yuborish bo'limi</b>\n\n"
             "<i>Ushbu bo'lim orqali bot foydalanuvchilariga reklama, aksiya yoki texnik "
             "xabarlarni yuborishingiz mumkin.</i>\n\n"
             "✨ Xabar yubormoqchi bo'lgan maqsadli (target) guruhni tanlang:",
        reply_markup=advert_kb,
        parse_mode="HTML"
    )
# ---------------------------------------------------------
# 1. TARGET GURUHNI TANLASH VA XABAR KUTISH
# ---------------------------------------------------------

@router.callback_query(F.data.startswith("send_adv:"))
async def process_select_advert_target(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    parts = callback.data.split(":")
    target_group = parts[1]

    group_titles = {
        "all": "🌍 Hammaga (User, VIP, Admin)",
        "vip": "💎 Faqat VIP foydalanuvchilarga",
        "user": "👤 Faqat oddiy foydalanuvchilarga",
        "admin": "🛠 Faqat Adminlarga"
    }
    title = group_titles.get(target_group, "Noma'lum")

    # State'ga boshlang'ich ma'lumotlarni va bo'sh tugmalar ro'yxatini (buttons=[]) saqlaymiz
    await state.update_data(
        target_group=target_group, 
        group_title=title, 
        main_msg_id=callback.message.message_id,
        buttons=[] 
    )
    await state.set_state(AdminAdvertSG.waiting_for_ad)

    cancel_kb = make_keyboard([
        [make_button(text="❌ Bekor qilish", callback_data="admin_advert", style="danger")]
    ])

    await callback.message.edit_text(
        text=f"🎯 Target guruh: <b>{title}</b>\n\n"
             f"📥 <b>Iltimos, reklama postini yuboring:</b>\n"
             f"<b>Eslatma:</b> Quyidagi kodni nusxalashingiz mumkin:\n"
             f"<code>&lt;a href='https://t.me/Aninovuz'&gt;matn&lt;/a&gt;</code>\n"
             f"<i>(Matn, rasm, video yoki fayl bo'lishi mumkin.)</i>",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )


# ---------------------------------------------------------
# 2. XABARNI QABUL QILISH VA KONSTRUCTOR INTERFEYSI
# ---------------------------------------------------------

@router.message(AdminAdvertSG.waiting_for_ad)
async def process_receive_advert_message(message: Message, state: FSMContext):
    await state.update_data(ad_message_id=message.message_id, ad_chat_id=message.chat.id)
    await show_advert_preview(message.bot, message.chat.id, state)


async def show_advert_preview(bot, chat_id: int, state: FSMContext):
    """Admin uchun reklama prevyusi va tugma boshqaruvi panelini ko'rsatadi"""
    data = await state.get_data()
    main_msg_id = data.get("main_msg_id")
    title = data.get("group_title")
    buttons_data = data.get("buttons", [])

    # Yasalgan inline tugmalarni biriktiramiz
    preview_rows = []
    for btn in buttons_data:
        preview_rows.append([
            make_button(text=btn['text'], url=btn['url'], style=btn.get('style'))
        ])

    # Boshqaruv tugmalari
    control_rows = [
        [make_button(text="➕ Inline Tugma Qo'shish", callback_data="adv_add_btn", style="success")],
    ]
    
    if buttons_data:
        control_rows.append([make_button(text="🗑 Tugmalarni tozalash", callback_data="adv_clear_btns", style="danger")])

    control_rows.append([
        make_button(text="🚀 Tarqatishni boshlash", callback_data="adv_confirm:yes", style="primary"),
        make_button(text="❌ Bekor qilish", callback_data="adv_confirm:no", style="danger")
    ])

    kb = make_keyboard(preview_rows + control_rows)

    text = (
        f"⚙️ <b>REKLAMA KONSTRUKTORI</b>\n\n"
        f"🎯 Target: <b>{title}</b>\n"
        f"🔘 Qo'shilgan tugmalar: <b>{len(buttons_data)} ta</b>\n\n"
        f"<i>Quyidagi <b>➕ Inline Tugma Qo'shish</b> tugmasi orqali xabaringiz ostiga rangli havola tugmalarini biriktirishingiz mumkin.</i>"
    )

    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=main_msg_id,
            text=text, reply_markup=kb, parse_mode="HTML"
        )
    except Exception:
        msg = await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb, parse_mode="HTML")
        await state.update_data(main_msg_id=msg.message_id)


# ---------------------------------------------------------
# 3. TUGMA YARATISH FSM BOSQICHLARI (NOMI -> URL -> STYLE)
# ---------------------------------------------------------

@router.callback_query(F.data == "adv_add_btn")
async def start_add_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminAdvertSG.waiting_for_btn_text)
    
    cancel_kb = make_keyboard([[make_button(text="❌ Bekor qilish", callback_data="adv_cancel_btn_creation", style="danger")]])
    await callback.message.edit_text(
        text="📝 <b>Tugma nomini kiriting:</b>\n\n<i>Masalan: 🎬 Animelarni tomosha qilish</i>",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )

@router.message(AdminAdvertSG.waiting_for_btn_text)
async def process_btn_text(message: Message, state: FSMContext):
    # Admin xabarini tozalab boramiz
    try: await message.delete() 
    except Exception: pass

    await state.update_data(temp_btn_text=message.text)
    await state.set_state(AdminAdvertSG.waiting_for_btn_url)

    data = await state.get_data()
    cancel_kb = make_keyboard([[make_button(text="❌ Bekor qilish", callback_data="adv_cancel_btn_creation", style="danger")]])

    await message.bot.edit_message_text(
        chat_id=message.chat.id, message_id=data['main_msg_id'],
        text=f"🔗 Tugma nomi: <b>{message.text}</b>\n\n<b>Endi tugma bosilganda o'tiladigan URL manzilni yuboring:</b>\n<i>Masalan: https://t.me/Aninovuz</i>",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )

@router.message(AdminAdvertSG.waiting_for_btn_url)
async def process_btn_url(message: Message, state: FSMContext):
    try: await message.delete() 
    except Exception: pass

    url = message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
        # Noto'g'ri URL
        return

    await state.update_data(temp_btn_url=url)
    await state.set_state(AdminAdvertSG.waiting_for_btn_style)

    data = await state.get_data()

    style_kb = make_keyboard([
        [make_button(text="🔵 Ko'k (Primary)", callback_data="btn_style:primary")],
        [make_button(text="🟢 Yashil (Success)", callback_data="btn_style:success")],
        [make_button(text="🔴 Qizil (Danger)", callback_data="btn_style:danger")],
        [make_button(text="⚪️ Oddiy (Style siz)", callback_data="btn_style:none")],
    ])

    await message.bot.edit_message_text(
        chat_id=message.chat.id, message_id=data['main_msg_id'],
        text=f"🎨 Tugma uchun **rang (style)** ni tanlang:",
        reply_markup=style_kb,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("btn_style:"), AdminAdvertSG.waiting_for_btn_style)
async def process_btn_style(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    style_val = callback.data.split(":")[1]
    style = None if style_val == "none" else style_val

    data = await state.get_data()
    buttons = data.get("buttons", [])

    # Yangi tugmani saqlaymiz
    buttons.append({
        "text": data['temp_btn_text'],
        "url": data['temp_btn_url'],
        "style": style
    })

    await state.update_data(buttons=buttons)
    await state.set_state(AdminAdvertSG.waiting_for_ad) # Qaytadan konstruktor holatiga
    await show_advert_preview(callback.bot, callback.message.chat.id, state)

@router.callback_query(F.data == "adv_clear_btns")
async def clear_buttons(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Tugmalar tozalandi!")
    await state.update_data(buttons=[])
    await show_advert_preview(callback.bot, callback.message.chat.id, state)

@router.callback_query(F.data == "adv_cancel_btn_creation")
async def cancel_btn_creation(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Tugma qo'shish bekor qilindi.")
    await state.set_state(AdminAdvertSG.waiting_for_ad)
    await show_advert_preview(callback.bot, callback.message.chat.id, state)


# ---------------------------------------------------------
# 4. TARQATISHNI TASDIQLASH VA PROCESS
# ---------------------------------------------------------

@router.callback_query(F.data.startswith("adv_confirm:"))
async def process_final_advert_decision(callback: CallbackQuery, state: FSMContext, user_service: UserService):
    decision = callback.data.split(":")[1]
    data = await state.get_data()

    if decision == "no":
        await callback.answer("Reklama bekor qilindi.")
        try: await callback.bot.delete_message(chat_id=data['ad_chat_id'], message_id=data['ad_message_id'])
        except Exception: pass
        await state.clear()
        
        back_kb = make_keyboard([[make_button(text="⬅️ Orqaga", callback_data="admin_advert")]])
        await callback.message.edit_text("❌ Reklama bekor qilindi.", reply_markup=back_kb)
        return

    target_group = data.get("target_group")
    buttons_data = data.get("buttons", [])

    # Tayyor tugmalar klaviaturasini yasaymiz
    reply_markup = None
    if buttons_data:
        rows = []
        for btn in buttons_data:
            rows.append([make_button(text=btn['text'], url=btn['url'], style=btn.get('style'))])
        reply_markup = make_keyboard(rows)

    await callback.answer("🚀 Tarqatish boshlandi!")

    user_ids = await user_service.get_target_user_ids(target_group)
    if not user_ids:
        await callback.message.edit_text("⚠️ Bu guruhda foydalanuvchi topilmadi.")
        await state.clear()
        return

    asyncio.create_task(
        run_advert_broadcast(
            bot=callback.bot, user_ids=user_ids, target_group=target_group,
            from_chat_id=data['ad_chat_id'], ad_message_id=data['ad_message_id'],
            main_msg_id=data['main_msg_id'], state=state, reply_markup=reply_markup
        )
    )

    await callback.message.edit_text(
        text="🚀 <b>Reklama orqa fonda tarqatila boshlandi!</b>\n\n"
             "Bot foydalanuvchilarga xizmat ko'rsatishda davom etadi.",
        parse_mode="HTML"
    )



async def run_advert_broadcast(bot, user_ids, target_group, from_chat_id, ad_message_id, main_msg_id, state, reply_markup=None):
    """Orqa fonda xabarlarni tarqatadi (HTML teglarni avtomatik qo'llaydi)"""
    success_count = 0
    fail_count = 0

    # 1. Admin yuborgan asl xabarni olamiz
    try:
        # Xabarni nusxalamasdan, uning obyektini olamiz (forward yoki do'stona usulda)
        # Aiogram 3 da xabar obyektini parse qilish uchun
        source_message = await bot.forward_message(chat_id=from_chat_id, from_chat_id=from_chat_id, message_id=ad_message_id)
        await bot.delete_message(chat_id=from_chat_id, message_id=source_message.message_id)
    except Exception:
        source_message = None

    for uid in user_ids:
        for attempt in range(2):
            try:
                # Agar xabar faqat MATN bo'lsa va unda HTML teglar bo'lsa:
                if source_message and source_message.text:
                    await bot.send_message(
                        chat_id=uid,
                        text=source_message.text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )
                # Agar RASM, VIDEO yoki FAYL bo'lsa:
                elif source_message and source_message.caption:
                    await bot.copy_message(
                        chat_id=uid,
                        from_chat_id=from_chat_id,
                        message_id=ad_message_id,
                        parse_mode="HTML",
                        reply_markup=reply_markup
                    )
                # Boshqa barcha standart holatlar uchun:
                else:
                    await bot.copy_message(
                        chat_id=uid,
                        from_chat_id=from_chat_id,
                        message_id=ad_message_id,
                        reply_markup=reply_markup
                    )

                success_count += 1
                break

            except TelegramRetryAfter as flood_err:
                await asyncio.sleep(flood_err.retry_after)
                continue
            except Exception:
                fail_count += 1
                break

        await asyncio.sleep(0.05)

    # Admin xabarini tozalash va hisobot berish
    try:
        await bot.delete_message(chat_id=from_chat_id, message_id=ad_message_id)
    except Exception:
        pass

    await state.clear()

    back_kb = make_keyboard([[make_button(text="⬅️ Reklama bo'limiga qaytish", callback_data="admin_advert")]])
    report_text = (
        f"📊 <b>Reklama tarqatish yakunlandi!</b>\n\n"
        f"🎯 Target guruh: <code>{target_group.upper()}</code>\n"
        f"✅ Muvaffaqiyatli yetkazildi: <code>{success_count} ta</code>\n"
        f"❌ Yetkazilmadi: <code>{fail_count} ta</code>"
    )

    try:
        await bot.edit_message_text(chat_id=from_chat_id, message_id=main_msg_id, text=report_text, reply_markup=back_kb, parse_mode="HTML")
    except Exception:
        pass