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
    waiting_for_btn_style = State()
    waiting_for_url = State()
    waiting_for_url_position = State()
    waiting_for_btn_position = State()





# ---------------------------------------------------------
# HELPER: PREVYU VA MENYUNI KO'RSATISH FUNKSIYASI
# ---------------------------------------------------------
async def show_channel_post_preview(bot, chat_id: int, state: FSMContext):
    data = await state.get_data()
    main_msg_id = data.get("main_msg_id")
    buttons = data.get("buttons", [])
    link_data = data.get("link_data")  # {'text': '...', 'url': '...'}
    
    # Inline tugmalarni shakllantirish (Massiv qatorlari bo'yicha)
    inline_rows = []
    
    total_btn_count = 0
    for row in buttons:
        # Agar qator ro'yxat (list) bo'lsa (yangi ko'rinish: [[btn1, btn2], [btn3]])
        if isinstance(row, list):
            formatted_row = []
            for btn in row:
                formatted_row.append(
                    InlineKeyboardButton(
                        text=btn['text'], 
                        url=btn['url'], 
                        style=btn.get('style')
                    )
                )
                total_btn_count += 1
            if formatted_row:
                inline_rows.append(formatted_row)
                
        # Agar eski ko'rinishdagi oddiy ro'yxat bo'lsa ([btn1, btn2])
        elif isinstance(row, dict):
            inline_rows.append([
                InlineKeyboardButton(
                    text=row['text'], 
                    url=row['url'], 
                    style=row.get('style')
                )
            ])
            total_btn_count += 1

    # Boshqaruv tugmalari
    control_rows = [
        [
            InlineKeyboardButton(text="➕ Inline Tugma", callback_data="chan_adv_add_btn", style="success"),
            InlineKeyboardButton(text="➖ Tugmani o'chirish", callback_data="chan_adv_del_btn", style="danger")
        ],
        [
            InlineKeyboardButton(text="🔗 Link qo'shish", callback_data="chan_adv_add_link", style="success"),
            InlineKeyboardButton(text="🗑️ Link o'chirish", callback_data="chan_adv_del_link", style="danger")
        ],
        [
            InlineKeyboardButton(text="🚀 Kanalga yuborish", callback_data="chan_adv_send", style="primary")
        ],
        [  
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="chan_adv_cancel", style="danger")
        ]
    ]
    
    kb = InlineKeyboardMarkup(inline_keyboard=inline_rows + control_rows)
    
    # Ma'lumot matni
    info_text = (
        f"⚙️ <b>KANAL UCHUN POST KONSTRUKTORI</b>\n\n"
        f"📎 Fayl turi: <b>{data.get('file_type', 'Matn').upper()}</b>\n"
        f"🔘 Qo'shilgan inline tugmalar: <b>{total_btn_count} ta</b>\n"
        f"🔗 Biriktirilgan link: <b>{'Bor' if link_data else 'Yo\'q'}</b>\n\n"
        f"<i>Quyidagi tugmalar orqali postga inline tugma yoki text ichiga link biriktirishingiz mumkin.</i>"
    )

    try:
        if main_msg_id:
            await bot.edit_message_text(chat_id=chat_id, message_id=main_msg_id, text=info_text, reply_markup=kb, parse_mode="HTML")
        else:
            raise Exception("main_msg_id topilmadi")
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

        if not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
            cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="chan_adv_back_preview", style="danger")]
            ])
            await message.answer("❌ Noto'g'ri URL manzil!", reply_markup=cancel_kb)
            return

        # Vaqtinchalik saqlaymiz va joylashuv tanlash bosqichiga o'tamiz
        await state.update_data(temp_link_text=text, temp_link_url=url)
        await state.set_state(ChannelAdvertSG.waiting_for_url_position)

        data = await state.get_data()

        pos_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⬇️ Matn pastida", callback_data="link_pos:bottom", style="primary"),
                InlineKeyboardButton(text="⬆️ Matn tepasida", callback_data="link_pos:top", style="primary")
            ],
            [
                InlineKeyboardButton(text="↔️ Yonma-yon (Avvalgisi bilan)", callback_data="link_pos:side", style="success")
            ],
            [
                InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="chan_adv_back_preview", style="danger")
            ]
        ])

        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=data['main_msg_id'],
            text=f"🔗 <b>Havola:</b> <a href='{url}'>{html.escape(text)}</a>\n\n"
                 f"📍 <b>Ushbu havolani postning qaysi joyiga qo'shmoqchisiz?</b>",
            reply_markup=pos_kb,
            parse_mode="HTML"
        )
    else:
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="chan_adv_back_preview", style="danger")]
        ])
        await message.answer("❌ Xato format. Matn va havolani <b>|</b> belgisi bilan ajrating!\n<i>Masalan: Animelar | https://t.me/link</i>", reply_markup=cancel_kb, parse_mode="HTML")






@router.callback_query(F.data.startswith("link_pos:"), ChannelAdvertSG.waiting_for_url_position)
async def process_apply_link_position(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    pos_type = callback.data.split(":")[1]  # 'bottom', 'top', 'side'
    data = await state.get_data()

    text = data.get("temp_link_text")
    url = data.get("temp_link_url")
    current_caption = data.get("caption", "")

    new_html_link = f"<a href='{url}'>{html.escape(text)}</a>"

    # Mantiq bo'yicha matnga joylashtiramiz:
    if pos_type == "top":
        # Matnning eng tepasiga qo'shish
        updated_caption = f"{new_html_link}\n\n{current_caption}".strip()

    elif pos_type == "side":
        # Yonma-yon qo'shish (oxirgi qatorga ` • ` yoki ` | ` bilan ulaydi)
        if current_caption:
            updated_caption = f"{current_caption}  •  {new_html_link}"
        else:
            updated_caption = new_html_link

    else:  # bottom (boshlang'ich holat)
        # Matnning eng oxiriga yangi qatordan qo'shish
        updated_caption = f"{current_caption}\n\n{new_html_link}".strip()

    # Link statistikasi uchun ma'lumotni yangilaymiz
    link_list = data.get("link_list", [])
    link_list.append({"text": text, "url": url})

    await state.update_data(
        caption=updated_caption, 
        link_list=link_list,
        link_data={"text": text, "url": url} # mavjud mantiqlarni buzmaslik uchun
    )
    
    await state.set_state(ChannelAdvertSG.waiting_for_post)
    await show_channel_post_preview(callback.bot, callback.message.chat.id, state)




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

        if not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
            cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="chan_adv_back_preview", style="danger")]
            ])
            await message.answer("❌ Noto'g'ri URL manzil. Havola http://, https:// yoki tg:// bilan boshlanishi kerak!", reply_markup=cancel_kb)
            return

        # Vaqtinchalik matn va url-ni saqlab, rang tanlash bosqichiga o'tamiz
        await state.update_data(temp_chan_btn_text=text, temp_chan_btn_url=url)
        await state.set_state(ChannelAdvertSG.waiting_for_btn_style)

        data = await state.get_data()

        style_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔵 Ko'k (Primary)", callback_data="chan_btn_style:primary", style="primary")],
            [InlineKeyboardButton(text="🟢 Yashil (Success)", callback_data="chan_btn_style:success", style="success")],
            [InlineKeyboardButton(text="🔴 Qizil (Danger)", callback_data="chan_btn_style:danger", style="danger")],
            [InlineKeyboardButton(text="⚪️ Oddiy (Style siz)", callback_data="chan_btn_style:none")],
        ])

        await message.bot.edit_message_text(
            chat_id=message.chat.id, 
            message_id=data['main_msg_id'],
            text=f"📌 Tugma: <b>{text}</b>\n🔗 URL: <code>{url}</code>\n\n🎨 <b>Tugma uchun rang (style) tanlang:</b>",
            reply_markup=style_kb,
            parse_mode="HTML"
        )
    else:
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="chan_adv_back_preview", style="danger")]
        ])
        await message.answer("❌ Xato format. Tugma nomi va havolani <b>-</b> bilan ajrating!\n<i>Masalan: Kanalga o'tish - https://t.me/link</i>", reply_markup=cancel_kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("chan_btn_style:"), ChannelAdvertSG.waiting_for_btn_style)
async def process_save_chan_btn_style(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    style_val = callback.data.split(":")[1]
    style = None if style_val == "none" else style_val

    # Rangni vaqtinchalik xotiraga saqlaymiz
    await state.update_data(temp_chan_btn_style=style)
    await state.set_state(ChannelAdvertSG.waiting_for_btn_position)

    data = await state.get_data()
    buttons = data.get("buttons", [])

    pos_kb_buttons = [
        [InlineKeyboardButton(text="⬇️ Yangi qatordan (Pastga)", callback_data="chan_btn_pos:new_row", style="primary")]
    ]

    # Agar avval qo'shilgan tugmalar bo'lsagina "Yonma-yon" variantini ko'rsatamiz
    if buttons:
        pos_kb_buttons.append(
            [InlineKeyboardButton(text="↔️ Oxirgi tugma bilan yonma-yon", callback_data="chan_btn_pos:same_row", style="success")]
        )

    pos_kb_buttons.append(
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="chan_adv_back_preview", style="danger")]
    )

    pos_kb = InlineKeyboardMarkup(inline_keyboard=pos_kb_buttons)

    text = data.get("temp_chan_btn_text")
    url = data.get("temp_chan_btn_url")

    # Avvalgi xatolik (message to edit not found) takrorlanmasligi uchun try-except bilan edit qilamiz
    try:
        await callback.message.edit_text(
            text=f"📌 Tugma: <b>{text}</b>\n🔗 URL: <code>{url}</code>\n\n"
                 f"📍 <b>Tugmani qanday joylashtirmoqchisiz?</b>",
            reply_markup=pos_kb,
            parse_mode="HTML"
        )
    except Exception:
        new_msg = await callback.message.answer(
            text=f"📌 Tugma: <b>{text}</b>\n🔗 URL: <code>{url}</code>\n\n"
                 f"📍 <b>Tugmani qanday joylashtirmoqchisiz?</b>",
            reply_markup=pos_kb,
            parse_mode="HTML"
        )
        await state.update_data(main_msg_id=new_msg.message_id)




@router.callback_query(F.data.startswith("chan_btn_pos:"), ChannelAdvertSG.waiting_for_btn_position)
async def process_save_chan_btn_position(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    pos_type = callback.data.split(":")[1] # 'new_row' yoki 'same_row'
    data = await state.get_data()

    buttons = data.get("buttons", []) # Masalan: [[{'text': 'Btn1', 'url': '...'}]]
    
    new_btn = {
        "text": data['temp_chan_btn_text'],
        "url": data['temp_chan_btn_url'],
        "style": data.get('temp_chan_btn_style')
    }

    if pos_type == "same_row" and buttons:
        # Oxirgi qator ichiga qo'shamiz (yonma-yon bo'ladi)
        buttons[-1].append(new_btn)
    else:
        # Yangi qatordan alohida tugma qilib qo'shamiz
        buttons.append([new_btn])

    await state.update_data(buttons=buttons)
    await state.set_state(ChannelAdvertSG.waiting_for_post)
    await show_channel_post_preview(callback.bot, callback.message.chat.id, state)






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
    
    # FSM tozalaymiz
    await state.clear()
    
    # Orqaga qaytish tugmasi (chaninfo callbackingizga mos holatda)
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⬅️ Kanal menyusiga qaytish", 
            callback_data=f"chaninfo:{channel_db_id}:{page}", 
            style="primary"
        )]
    ])
    
    await callback.message.edit_text(
        text="❌ <b>Post tayyorlash bekor qilindi.</b>",
        reply_markup=back_kb,
        parse_mode="HTML"
    )






# 1. Inline tugmalarni tozalash / oxirgisini o'chirish
@router.callback_query(F.data == "chan_adv_del_btn")
async def process_del_btn(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    buttons = data.get("buttons", [])
    
    if not buttons:
        await callback.answer("⚠️ O'chirish uchun tugmalar yo'q!", show_alert=True)
        return
        
    buttons.pop()  # Oxirgi qo'shilgan tugmani o'chirish (yoki buttons.clear() qilsa ham bo'ladi)
    await state.update_data(buttons=buttons)
    await callback.answer("🗑️ Tugma o'chirildi")
    await show_channel_post_preview(callback.bot, callback.message.chat.id, state)







# 2. Qo'shilgan HTML Linkni matndan olib tashlash
@router.callback_query(F.data == "chan_adv_del_link")
async def process_del_link(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    link_data = data.get("link_data")
    
    if not link_data:
        await callback.answer("⚠️ O'chirish uchun link yo'q!", show_alert=True)
        return
        
    # Link ma'lumotlarini tozalaymiz
    caption = data.get("caption", "")
    text_to_remove = f"<a href='{link_data['url']}'>{html.escape(link_data['text'])}</a>"
    
    # Matn ichidan qo'shilgan HTML linkni olib tashlaymiz
    updated_caption = caption.replace(text_to_remove, "").strip()
    
    await state.update_data(caption=updated_caption, link_data=None)
    await callback.answer("🗑️ Link matndan olib tashlandi")
    await show_channel_post_preview(callback.bot, callback.message.chat.id, state)







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
        rows = [[InlineKeyboardButton(text=b['text'], url=b['url'], style=b.get('style'))] for b in buttons]
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