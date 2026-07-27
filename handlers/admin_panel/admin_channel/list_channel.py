from dotenv.main import logger
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any
from aiogram import Router, html, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from datetime import datetime
from aiogram.fsm.state import StatesGroup, State
from services.channel_service import ChannelService

# ---------------------------------------------------------
# KANALGA REKLAMA YUBORISH FSM BOSQICHLARI
# ---------------------------------------------------------



router = Router()




def get_channels_keyboard(channels: List[Dict[str, Any]], page: int = 1, per_page: int = 5) -> InlineKeyboardMarkup:
    # Sahifa chegaralarini aniqlaymiz
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_channels = channels[start_idx:end_idx]
    
    keyboard = []
    
    # Har bir kanal uchun inline tugma (bosganda kanal info ochiladi)
    for ch in page_channels:
        # Agar kanal faol bo'lsa yashil, o'chiq bo'lsa qizil emoji bilan ajratamiz
        status_emoji = "🟢" if ch.get("is_active") else "🔴"
        keyboard.append([
            InlineKeyboardButton(
                text=f"{status_emoji} {ch.get('title')}", 
                callback_data=f"chaninfo:{ch.get('channel_id')}:{page}"
            )
        ])
        
    # Navigatsiya (Paginatsiya) tugmalari qatori
    nav_row = []
    total_pages = (len(channels) + per_page - 1) // per_page if channels else 1
    
    # Oldingi sahifa tugmasi
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"chanpage:{page - 1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="❌", callback_data="noop", style="danger")) # Bo'sh tugma
        
    # Joriy sahifa holati
    nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="noop", style="primary"))
    
    # Keyingi sahifa tugmasi
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"chanpage:{page + 1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="❌", callback_data="noop", style="danger"))
        
    keyboard.append(nav_row)
    
    # Orqaga qaytish bosh tugmasi (style="danger" o'z o'rnida)
    keyboard.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="admin_channel_menu", style="danger")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)









@router.callback_query(F.data == "list_channel")
@router.callback_query(F.data.startswith("chanpage:"))
async def list_channels(callback: CallbackQuery, session: Any):
    await callback.answer()
    
    # Sahifa raqamini aniqlaymiz (agar list_channel bo'lsa 1-sahifa)
    page = 1
    if callback.data.startswith("chanpage:"):
        page = int(callback.data.split(":")[-1])
        
    service = ChannelService(session=session)
    all_channels = await service.get_all_channels()
    
    # Faol kanallar sonini filtrlab hisoblaymiz
    active_count = sum(1 for ch in all_channels if ch.get("is_active"))
    total_count = len(all_channels)
    
    text = (
        f"📊 {html.bold('Kanallar statistikasi va ro‘yxati')}\n\n"
        f"📌 {html.bold('Barcha kanallar soni:')} {total_count} ta\n"
        f"✅ {html.bold('Faol kanallar soni:')} {active_count} ta\n\n"
        f"👇 {html.underline('Batafsil ma’lumot olish uchun kanal ustiga bosing:')}"
    )
    
    kb = get_channels_keyboard(all_channels, page=page)
    
    try:
        await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            pass


# Hech qanday amal bajarmaydigan bo'sh tugma uchun handler (Paginatsiya chiroyli turishi uchun)
@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    await callback.answer()





@router.callback_query(F.data.startswith("chaninfo:"))
async def show_channel_info(callback: CallbackQuery, session: Any):
    await callback.answer()
    
    # Callback ma'lumotlarini ajratib olamiz
    try:
        _, channel_id_str, page_str = callback.data.split(":")
        channel_id = int(channel_id_str)
        page = int(page_str)
    except ValueError:
        logger.error(f"❌ Callback data formatida xatolik: {callback.data}")
        return
    
    service = ChannelService(session=session)
    channel = await service.get_channel(channel_id)
    
    if not channel:
        try:
            await callback.message.edit_text(
                text="❌ Kanal ma'lumotlari topilmadi yoki u allaqachon o‘chirilgan.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Ro‘yxatga qaytish", callback_data=f"chanpage:{page}", style="danger")]
                ])
            )
        except TelegramBadRequest:
            pass
        return
        
    status_text = "🟢 Faol (Majburiy obuna tekshirilmoqda)" if channel.get("is_active") else "🔴 O‘chiq (Tekshirilmayapti)"
    
    # created_at xavfsiz formatlash (Slicing xatosini oldini olish)
    created_val = channel.get('created_at')
    if isinstance(created_val, str):
        formatted_date = created_val[:19].replace("T", " ")
    elif isinstance(created_val, datetime):
        formatted_date = created_val.strftime("%Y-%m-%d %H:%M:%S")
    else:
        formatted_date = "Noma'lum"
    
    text = (
        f"ℹ️ {html.bold('Kanal haqida batafsil ma’lumot')}\n\n"
        f"📣 {html.bold('Kanal nomi:')} {channel.get('title')}\n"
        f"🆔 {html.bold('Kanal ID:')} {html.code(channel.get('channel_id'))}\n"
        f"🔗 {html.bold('Havola (URL):')} {channel.get('url') if channel.get('url') else 'Yo‘q'}\n"
        f"⚙️ {html.bold('Holati:')} {status_text}\n"
        f"📅 {html.bold('Qo‘shilgan vaqti:')} {formatted_date}\n"
    )
    
    # Aynan shu kanalni boshqarish (O'chirish yoki Statusini o'zgartirish) tugmalari qo'shildi
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Holatni o‘zgartirish", callback_data=f"chantoggle:{channel_id}:{page}", style="primary"),
                InlineKeyboardButton(text="🗑 O‘chirish", callback_data=f"chandel:{channel_id}:{page}", style="danger")
            ],
            [
                InlineKeyboardButton(text="📢 Reklama", callback_data=f"channel_advert:{channel_id}:{page}", style="primary" )  
            ],
            [InlineKeyboardButton(text="⬅️ Ro‘yxatga qaytish", callback_data=f"chanpage:{page}", style="danger")]
        ]
    )
    
    try:
        await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            pass
        else:
            logger.error(f"❌ chaninfo ko'rsatishda xatolik: {e}")

            






@router.callback_query(F.data.startswith("chandel:"))
async def ask_delete_confirmation(callback: CallbackQuery, session: Any):
    await callback.answer()
    
    # Callback ma'lumotlarini ajratib olamiz (chandel:channel_id:current_page)
    _, channel_id_str, page_str = callback.data.split(":")
    channel_id = int(channel_id_str)
    page = int(page_str)
    
    service = ChannelService(session=session)
    channel = await service.get_channel(channel_id)
    
    if not channel:
        await callback.message.edit_text(
            text="❌ Kanal ma'lumotlari topilmadi yoki u allaqachon o‘chirilgan.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Ro‘yxatga qaytish", callback_data=f"chanpage:{page}", style="danger")]
            ])
        )
        return
        
    text = (
        f"⚠️ {html.bold('DIQQAT! Kanalni o‘chirishni tasdiqlang')}\n\n"
        f"Siz rostdan ham {html.bold(channel.get('title'))} ({html.code(channel_id)}) kanalini "
        f"tizimdan butunlay o‘chirib tashlamoqchimisiz?\n\n"
        f"ℹ️ {html.italic('Eslatma: Bu amalni ortga qaytarib bo‘lmaydi va keshlar butunlay tozalanadi!')}"
    )
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                # "Ha" tugmasi bosilsa, yakuniy o'chirish handleriga o'tadi
                InlineKeyboardButton(text="🟢 Ha, o‘chirilsin", callback_data=f"chandel_confirm:{channel_id}:{page}", style="success"),
                # "Yo'q" tugmasi bosilsa, hech narsa o'zgarmasdan kanal info sahifasiga qaytadi
                InlineKeyboardButton(text="🔴 Yo‘q, bekor qilish", callback_data=f"chaninfo:{channel_id}:{page}", style="danger")
            ]
        ]
    )
    
    try:
        await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest:
        pass






@router.callback_query(F.data.startswith("chandel_confirm:"))
async def execute_channel_deletion(callback: CallbackQuery, session: Any):
    _, channel_id_str, page_str = callback.data.split(":")
    channel_id = int(channel_id_str)
    page = int(page_str)
    
    service = ChannelService(session=session)
    success = await service.delete_channel(channel_id)
    
    if not success:
        await callback.answer("❌ Kanalni o‘chirishda xatolik yuz berdi!", show_alert=True)
        return
        
    await callback.answer("🗑 Kanal tizimdan butunlay o‘chirildi va kesh yangilandi!", show_alert=True)
    
    # ❌ callback.data ni o'zgartirmaymiz.
    # Buning o'rniga ro'yxatni to'g'ridan-to'g'ri shu yerda yangilaymiz:
    all_channels = await service.get_all_channels()
    active_count = sum(1 for ch in all_channels if ch.get("is_active"))
    
    text = (
        f"📊 {html.bold('Kanallar statistikasi va ro‘yxati')}\n\n"
        f"📌 {html.bold('Barcha kanallar soni:')} {len(all_channels)} ta\n"
        f"✅ {html.bold('Faol kanallar soni:')} {active_count} ta\n\n"
        f"👇 {html.underline('Batafsil ma’lumot olish uchun kanal ustiga bosing:')}"
    )
    
    # Yuqorida yozgan get_channels_keyboard helper funksiyamizni chaqiramiz
    kb = get_channels_keyboard(all_channels, page=page)
    
    try:
        await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass







@router.callback_query(F.data.startswith("chantoggle:"))
async def ask_toggle_confirmation(callback: CallbackQuery, session: Any):
    await callback.answer()
    
    # Callback ma'lumotlarini ajratib olamiz (chantoggle:channel_id:current_page)
    _, channel_id_str, page_str = callback.data.split(":")
    channel_id = int(channel_id_str)
    page = int(page_str)
    
    service = ChannelService(session=session)
    channel = await service.get_channel(channel_id)
    
    if not channel:
        await callback.message.edit_text(
            text="❌ Kanal ma'lumotlari topilmadi.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Ro‘yxatga qaytish", callback_data=f"chanpage:{page}", style="danger")]
            ])
        )
        return
        
    # Hozirgi holatiga qarab kelgusi holat matnini tayyorlaymiz
    current_status = channel.get("is_active")
    next_status_text = "🔴 O‘chirish (Tekshirmaslik)" if current_status else "🟢 Yoqish (Majburiy obunaga qo‘shish)"
    
    text = (
        f"🔄 {html.bold('Kanal holatini o‘zgartirishni tasdiqlang')}\n\n"
        f"Kanal: {html.bold(channel.get('title'))}\n"
        f"Hozirgi holat: {'🟢 Faol' if current_status else '🔴 O‘chiq'}\n\n"
        f"Siz rostdan ham ushbu kanal holatini {html.underline(next_status_text)} holatiga o‘tkazmoqchimisiz?"
    )
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                # "Ha" tugmasi bosilsa, yakuniy statusni o'zgartirish handleriga o'tadi
                InlineKeyboardButton(text="✅ Ha, o‘zgartirilsin", callback_data=f"chantoggle_confirm:{channel_id}:{page}", style="success"),
                # "Yo'q" tugmasi bosilsa, hech narsa o'zgarmasdan kanal info sahifasiga qaytadi
                InlineKeyboardButton(text="❌ Yo‘q, bekor qilish", callback_data=f"chaninfo:{channel_id}:{page}", style="danger")
            ]
        ]
    )
    
    try:
        await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest:
        pass







@router.callback_query(F.data.startswith("chantoggle_confirm:"))
async def execute_channel_toggle(callback: CallbackQuery, session: Any):
    _, channel_id_str, page_str = callback.data.split(":")
    channel_id = int(channel_id_str)
    page = int(page_str)
    
    service = ChannelService(session=session)
    success = await service.toggle_status(channel_id)
    
    if not success:
        await callback.answer("❌ Kanal holatini o‘zgartirishda xatolik yuz berdi!", show_alert=True)
        return
        
    await callback.answer("🔄 Kanal holati muvaffaqiyatli yangilandi!")
    
    # ❌ callback.data = ... qatorini olib tashladik!
    # Buning o'rniga obuna ma'lumotlarini qayta ko'rsatuvchi mantiqni shu yerning o'zida yoki 
    # show_channel_info funksiyasini helper kabi chaqirib bajaramiz.
    
    # Eng toza va xavfsiz yo'li: modelni o'zgartirmasdan, kerakli funksiyaga context uzatish
    # Buning uchun show_channel_info funksiyasini callback'ga qaram qilmasdan, parametrlarni qo'lda shakllantiramiz.
    
    # Keling, xatolik chiqmasligi uchun yangi info oynasini generatsiya qilamiz:
    channel = await service.get_channel(channel_id)
    if not channel:
        await callback.message.edit_text("❌ Kanal topilmadi.", reply_markup=None)
        return
        
    status_text = "🟢 Faol (Majburiy obuna tekshirilmoqda)" if channel.get("is_active") else "🔴 O‘chiq (Tekshirilmayapti)"
    created_val = channel.get('created_at')
    formatted_date = created_val[:19].replace("T", " ") if isinstance(created_val, str) else "Noma'lum"
    
    text = (
        f"ℹ️ {html.bold('Kanal haqida batafsil ma’lumot')}\n\n"
        f"📣 {html.bold('Kanal nomi:')} {channel.get('title')}\n"
        f"🆔 {html.bold('Kanal ID:')} {html.code(channel.get('channel_id'))}\n"
        f"🔗 {html.bold('Havola (URL):')} {channel.get('url') if channel.get('url') else 'Yo‘q'}\n"
        f"⚙️ {html.bold('Holati:')} {status_text}\n"
        f"📅 {html.bold('Qo‘shilgan vaqti:')} {formatted_date}\n"
    )
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Holatni o‘zgartirish", callback_data=f"chantoggle:{channel_id}:{page}", style="primary"),
                InlineKeyboardButton(text="🗑 O‘chirish", callback_data=f"chandel:{channel_id}:{page}", style="danger")
            ],
            [InlineKeyboardButton(text="⬅️ Ro‘yxatga qaytish", callback_data=f"chanpage:{page}", style="danger")]
        ]
    )
    
    try:
        await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass