import html
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from typing import List, Dict, Any
from aiogram.fsm.state import State, StatesGroup
from services.channel_service import ChannelService

router = Router()

# ---------------------------------------------------------
# STATES (FSM)
# ---------------------------------------------------------
class ChannelAdvertSG(StatesGroup):
    waiting_for_post = State()
    waiting_for_btn = State()
    waiting_for_url = State()

# ---------------------------------------------------------
# HELPER: PREVYU VA MENYUNI KO'RSATISH FUNKSIYASI
# ---------------------------------------------------------
async def show_channel_post_preview(bot, chat_id: int, state: FSMContext):
    data = await state.get_data()
    main_msg_id = data.get("main_msg_id")
    buttons = data.get("buttons", [])
    link_data = data.get("link_data")  # {'text': '...', 'url': '...'}
    
    # Inline tugmalarni shakllantirish
    inline_rows = []
    for btn in buttons:
        inline_rows.append([InlineKeyboardButton(text=btn['text'], url=btn['url'])])
    
    # Boshqaruv tugmalari
    control_rows = [
        [
            InlineKeyboardButton(text="➕ Inline Tugma", callback_data="chan_adv_add_btn", style="success"),
            InlineKeyboardButton(text="🔗 HTML Link qo'shish", callback_data="chan_adv_add_link", style="primary")
        ],
        [
            InlineKeyboardButton(text="🚀 Kanalga yuborish", callback_data="chan_adv_send", style="primary"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="chan_adv_cancel", style="danger")
        ]
    ]
    
    kb = InlineKeyboardMarkup(inline_keyboard=inline_rows + control_rows)
    
    # Ma'lumot matni
    info_text = (
        f"⚙️ <b>KANAL UCHUN POST KONSTRUKTORI</b>\n\n"
        f"📎 Fayl turi: <b>{data.get('file_type', 'Matn').upper()}</b>\n"
        f"🔘 Qo'shilgan inline tugmalar: <b>{len(buttons)} ta</b>\n"
        f"🔗 Biriktirilgan link: <b>{'Bor' if link_data else 'Yo\'q'}</b>\n\n"
        f"<i>Quyidagi tugmalar orqali postga inline tugma yoki text ichiga link biriktirishingiz mumkin.</i>"
    )

    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=main_msg_id, text=info_text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        msg = await bot.send_message(chat_id=chat_id, text=info_text, reply_markup=kb, parse_mode="HTML")
        await state.update_data(main_msg_id=msg.message_id)


# ---------------------------------------------------------
# HANDLERLAR
# ---------------------------------------------------------

# 1. Start - Boshlash
@router.callback_query(F.data.startswith("channel_advert:"))
async def process_channel_advert_start(callback: CallbackQuery, state: FSMContext, session: Any):
    await callback.answer()
    
    _, channel_id_str, page_str = callback.data.split(":")
    channel_id = int(channel_id_str)
    page = int(page_str)

    service = ChannelService(session=session)
    channel = await service.get_channel(channel_id)

    if not channel:
        await callback.answer("❌ Kanal topilmadi!", show_alert=True)
        return

    await state.clear()
    await state.update_data(
        target_channel_id=channel.get('channel_id'),
        channel_db_id=channel_id,
        page=page,
        main_msg_id=callback.message.message_id,
        buttons=[]
    )
    await state.set_state(ChannelAdvertSG.waiting_for_post)

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"chaninfo:{channel_id}:{page}", style="danger")]
    ])

    await callback.message.edit_text(
        text=f"📢 <b>{channel.get('title')}</b> kanaliga post tayyorlash\n\n"
             f"📥 <b>Har qanday xabar (Rasm, Video, Fayl, Matn) yuboring:</b>",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )


# 2. Xabarni qabul qilish (File ID, Text va turini ajratish)
@router.message(ChannelAdvertSG.waiting_for_post)
async def process_receive_channel_media(message: Message, state: FSMContext):
    file_id = None
    file_type = "text"
    caption_or_text = message.caption or message.text or ""

    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    elif message.audio:
        file_id = message.audio.file_id
        file_type = "audio"
    elif message.voice:
        file_id = message.voice.file_id
        file_type = "voice"

    try: await message.delete()
    except Exception: pass

    await state.update_data(
        file_id=file_id,
        file_type=file_type,
        caption=caption_or_text
    )
    
    await show_channel_post_preview(message.bot, message.chat.id, state)


# 3. HTML Link (<a></a>) qo'shish so'rovi
@router.callback_query(F.data == "chan_adv_add_link")
async def process_add_html_link_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ChannelAdvertSG.waiting_for_url)
    
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="chan_adv_back_preview", style="danger")]
    ])
    
    await callback.message.edit_text(
        text="🔗 <b>Matnga HTML link biriktirish</b>\n\n"
             "Iltimos, havolani quyidagi formatda yuboring:\n"
             "<code>Matn | https://t.me/kanal_link</code>\n\n"
             "<i>Masalan: Animelarni ko'rish | https://t.me/Aninovuz</i>",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )

@router.message(ChannelAdvertSG.waiting_for_url)
async def process_save_html_link(message: Message, state: FSMContext):
    try: await message.delete()
    except Exception: pass

    if "|" in message.text:
        text, url = message.text.split("|", 1)
        text, url = text.strip(), url.strip()
        
        data = await state.get_data()
        current_caption = data.get("caption", "")
        
        # HTML <a href="..."></a> ko'rinishida matnga ulash
        html_link = f"<a href='{url}'>{html.escape(text)}</a>"
        updated_caption = f"{current_caption}\n\n{html_link}".strip()
        
        await state.update_data(caption=updated_caption, link_data={"text": text, "url": url})
        await state.set_state(ChannelAdvertSG.waiting_for_post)
        await show_channel_post_preview(message.bot, message.chat.id, state)
    else:
        await message.answer("❌ Xato format. Matn va havolani <b>|</b> belgisi bilan ajrating!", parse_mode="HTML")


# 4. Inline Tugma qo'shish
@router.callback_query(F.data == "chan_adv_add_btn")
async def process_add_btn_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ChannelAdvertSG.waiting_for_btn)
    
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="chan_adv_back_preview", style="danger")]
    ])
    
    await callback.message.edit_text(
        text="🔘 <b>Inline tugma qo'shish</b>\n\n"
             "Tugma nomi va havolani quyidagicha yuboring:\n"
             "<code>Tugma Nomi - https://t.me/link</code>",
        reply_markup=cancel_kb,
        parse_mode="HTML"
    )

@router.message(ChannelAdvertSG.waiting_for_btn)
async def process_save_inline_btn(message: Message, state: FSMContext):
    try: await message.delete()
    except Exception: pass

    if "-" in message.text:
        text, url = message.text.split("-", 1)
        text, url = text.strip(), url.strip()
        
        data = await state.get_data()
        buttons = data.get("buttons", [])
        buttons.append({"text": text, "url": url})
        
        await state.update_data(buttons=buttons)
        await state.set_state(ChannelAdvertSG.waiting_for_post)
        await show_channel_post_preview(message.bot, message.chat.id, state)
    else:
        await message.answer("❌ Xato format. Tugma nomi va havolani <b>-</b> bilan ajrating!", parse_mode="HTML")


# Prevyuga qaytish va Bekor qilishlar
@router.callback_query(F.data == "chan_adv_back_preview")
async def process_back_preview(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ChannelAdvertSG.waiting_for_post)
    await show_channel_post_preview(callback.bot, callback.message.chat.id, state)


@router.callback_query(F.data == "chan_adv_cancel")
async def process_adv_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Bekor qilindi")
    data = await state.get_data()
    channel_db_id = data.get("channel_db_id")
    page = data.get("page", 1)
    await state.clear()
    
    # Kanal ma'lumotlariga qaytarish
    await callback.message.edit_text("❌ Post tayyorlash bekor qilindi.")


# 5. KANALGA YUBORISH (FINAL)
@router.callback_query(F.data == "chan_adv_send")
async def process_send_post_to_channel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    
    target_channel_id = data.get("target_channel_id")
    file_id = data.get("file_id")
    file_type = data.get("file_type")
    caption = data.get("caption", "")
    buttons = data.get("buttons", [])
    channel_db_id = data.get("channel_db_id")
    page = data.get("page", 1)

    # Inline Keyboard tayyorlash
    reply_markup = None
    if buttons:
        rows = [[InlineKeyboardButton(text=b['text'], url=b['url'])] for b in buttons]
        reply_markup = InlineKeyboardMarkup(inline_keyboard=rows)

    success = False
    try:
        bot = callback.bot
        if file_type == "photo":
            await bot.send_photo(chat_id=target_channel_id, photo=file_id, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
        elif file_type == "video":
            await bot.send_video(chat_id=target_channel_id, video=file_id, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
        elif file_type == "document":
            await bot.send_document(chat_id=target_channel_id, document=file_id, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
        elif file_type == "audio":
            await bot.send_audio(chat_id=target_channel_id, audio=file_id, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
        else: # Text
            await bot.send_message(chat_id=target_channel_id, text=caption, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=True)
            
        success = True
    except Exception as e:
        print(f"Error sending to channel: {e}")

    await state.clear()

    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Kanalga qaytish", callback_data=f"chaninfo:{channel_db_id}:{page}", style="primary")]
    ])

    if success:
        await callback.message.edit_text("✅ <b>Post kanalga muvaffaqiyatli joylandi!</b>", reply_markup=back_kb, parse_mode="HTML")
    else:
        await callback.message.edit_text("❌ <b>Postni yuborishda xatolik!</b> Bot kanal admini ekanligini tekshiring.", reply_markup=back_kb, parse_mode="HTML")