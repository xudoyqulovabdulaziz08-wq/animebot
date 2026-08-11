import urllib.parse
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.exceptions import TelegramBadRequest
import logging

from services.user_service import UserService
router = Router()
logger = logging.getLogger("UserVipMenu")


ADMIN_USERNAME = "Khudoyqulov_pg" 

@router.callback_query(F.data == "buy_vip")
async def buy_vip_menu(callback: CallbackQuery, user_service: UserService):
    await callback.answer()
    
    
    
    # 💎 1. Kesh-first orqali foydalanuvchi ma'lumotlarini olamiz va VIP muddatini tekshiramiz
    user_data = await user_service.get_user(callback.from_user.id)
    user_data = user_service._ensure_fresh_vip_status(user_data)
    
    is_vip = user_data.get("is_vip", False)
    vip_expire = user_data.get("vip_expire_date") # ISO string formatda keladi
    # 🎰 3. Statusga qarab dinamik matn va klaviaturani shakllantiramiz
    inline_keyboard = []
    # 📝 2. Umumiy imtiyozlar matni (Har ikkala status uchun ham ko'rinadi)
    benefits_text = (
        "👑 <b>VIP IMTIYOZLAR:</b>\n\n"
        "<blockquote expandable> 🎬 Premyeralarni hammadan birinchi ko'rish</blockquote>\n"
        "<blockquote expandable> 🚀 Animelarni  cheklovsiz yuklab olish va ulashish </blockquote>\n"
        "<blockquote expandable> 🚫 Mutlaqo reklamasiz botdan foydalanish </blockquote>\n"
        "<blockquote expandable> 🛑 Animelarni cheklovsiz boshqalar yubora olish </blockquote>\n"
        "<blockquote expandable>🎧 Eksklyuziv funksiyalardan foydalanish va botni qulay ishlatish</blockquote>\n\n"
    )
    
    if is_vip:
        # Sanani chiroyli formatga keltiramiz
        expire_str = "Noma'lum"
        if vip_expire:
            try:
                expire_dt = datetime.fromisoformat(vip_expire)
                expire_str = expire_dt.strftime("%d.%m.%Y %H:%M")
            except Exception:
                expire_str = str(vip_expire)
                
        text = (
            "💎 <b>VIP OBUNA</b>\n\n"
            "✅ <b>Status:</b> <code>VIP Faol</code>\n"
            f"📅 <b>Tugash sanasi:</b> <code>{expire_str}</code>\n\n"
            
            f"{benefits_text}"
            "✨ <i>Obunangizni muddatidan oldin uzaytirishingiz ham mumkin:</i>"
        )
        # VIP foydalanuvchilar uchun uzaytirish tugmasi
        inline_keyboard.append([InlineKeyboardButton(text="🔄 VIP uzaytirish", callback_data="purchase_vip", style="primary")])
    else:
        text = (
            "💎 <b>VIP OBUNA</b>\n\n"
            "👤 <b>Status:</b> Oddiy foydalanuvchi\n\n"
            

            f"{benefits_text}"
            
            "💳 <b>VIP obuna olib barcha imkoniyatlarni oching.</b>"
        )
        # Oddiy foydalanuvchilar uchun sotib olish tugmasi
        inline_keyboard.append([InlineKeyboardButton(text="💳 VIP olish", callback_data="purchase_vip", style="primary")])
        
    # ⬅️ Har doim eng tagida turadigan ORQAGA tugmasi
    inline_keyboard.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="cabinet", style="danger")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
    
    # 📸 4. Mediani va matnni bitta oynada silliq edit qilamiz
    try:
        await callback.message.edit_caption(
            caption=text,
            parse_mode="HTML",
            reply_markup=kb
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            pass
        else:
            logger.error(f"❌ Kutilmagan BadRequest xatoligi: {e}")
    except Exception as e:
        logger.error(f"❌ Umumiy xatolik: {e}")
 
    
   

@router.callback_query(F.data == "purchase_vip")
async def vip_payed(callback: CallbackQuery, user_service: UserService):
    await callback.answer()
    
    
    
    # 💎 1. Kesh-first orqali foydalanuvchi ma'lumotlarini olamiz
    user_data = await user_service.get_user(callback.from_user.id)
    user_data = user_service._ensure_fresh_vip_status(user_data)
    is_vip = user_data.get("is_vip", False)

    # 📊 2. Tariflar ro'yxati (Chiroyli UI formatda va HTML xatolarsiz)
    rates_text = (
        "💳 <b>VIP  TARIFLARI:</b>\n\n"
        "📅 <b>1 Oylik VIP</b>\n"
        "<blockquote expandable>💰 Narxi: 9,000 so'm (asl narx 💵)</blockquote>\n"
        "📅 <b>2 Oylik VIP</b>\n"
        "<blockquote expandable>💰 Narxi: 16,000 so'm (Chegirma! 🔥)</blockquote>\n"
        "📅 <b>3 Oylik VIP</b>\n"
        "<blockquote expandable>💰 Narxi: 22,000 so'm (Tavsiya etiladi! ✨)</blockquote>\n"
        "📅 <b>6 Oylik VIP</b>\n"
        "<blockquote expandable>💰 Narxi: 43,000 so'm (Tejamkor! 🚀)</blockquote>\n"
        "📅 <b>1 Yillik VIP</b>\n"
        "<blockquote expandable>💰 Narxi: 83,000 so'm (Eng katta chegirma! 👑)</blockquote>\n\n"
    )
    
    # 🎰 3. Statusga qarab sarlavha matnini dinamik moslaymiz
    if is_vip:
        title_text = "🔄 <b>VIP obunangizni uzaytirish uchun o'zingizga qulay tarifni tanlang:</b>\n\n"
    else:
        title_text = "🛒 <b>VIP status sotib olish uchun o'zingizga qulay tarifni tanlang:</b>\n\n"
        
    full_caption = f"{title_text}{rates_text}<i>👇 Kerakli muddat tugmasini bosing:</i>"

    # 🎛 4. To'g'ri va vizual jihatdan chiroyli inline klaviatura (List strukturasi)
    inline_keyboard = [
        [
            InlineKeyboardButton(text="📅 1 oylik", callback_data="purchases_vip:1", style="primary"),
            InlineKeyboardButton(text="📅 2 oylik", callback_data="purchases_vip:2", style="primary")
        ],
        [
            InlineKeyboardButton(text="📅 3 oylik", callback_data="purchases_vip:3", style="primary"),
            InlineKeyboardButton(text="📅 6 oylik", callback_data="purchases_vip:6", style="primary")
        ],
        [
            InlineKeyboardButton(text="👑 1 yillik (Eng zo'ri)", callback_data="purchases_vip:12", style="primary")
        ],
        [
            # Boyagi buy_vip menyusiga (ortga) qaytarish tugmasi
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data="buy_vip", style="danger")
        ]
    ]
    
    kb = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
    
    # 📸 5. Mediani va matnni bitta oynada silliq edit qilamiz
    try:
        await callback.message.edit_caption(
            caption=full_caption,
            parse_mode="HTML",
            reply_markup=kb
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            pass
        else:
            logger.error(f"❌ Kutilmagan BadRequest xatoligi: {e}")
    except Exception as e:
        logger.error(f"❌ Umumiy xatolik: {e}")




@router.callback_query(F.data.startswith("purchases_vip:"))
async def process_vip_checkout(callback: CallbackQuery):
    await callback.answer()
    
    
    
    # 💎 1. Callback datadan muddatni (oyni) ajratib olamiz
    months = callback.data.split(":")[1]
    
    # 📊 2. Muddatga qarab narx va matnni dinamik belgilaymiz
    rates = {
        "1": {"duration": "1 oylik", "price": "9 000 so'm"},
        "2": {"duration": "2 oylik", "price": "16 000 so'm"},
        "3": {"duration": "3 oylik", "price": "22 000 so'm"},
        "6": {"duration": "6 oylik", "price": "43 000 so'm"},
        "12": {"duration": "1 yillik", "price": "83 000 so'm"}
    }
    
    selected_rate = rates.get(months, {"duration": f"{months} oylik", "price": "Kelishilgan"})
    duration = selected_rate["duration"]
    price = selected_rate["price"]
    
    # 📝 3. Adminga yuboriladigan tayyor matn shabloni
    start_text = (
        f"Assalomu alaykum! Men {duration} VIP obuna sotib olmoqchi edim.\n"
        f"💰 Narxi: {price}\n"
        f"🆔 Mening ID: {callback.from_user.id}"
    )
    
    # URL xavfsiz bo'lishi uchun matnni url-encode qilamiz (probel va belgilarni %20 formatga o'tkazadi)
    encoded_text = urllib.parse.quote(start_text)
    admin_url = f"https://t.me/{ADMIN_USERNAME}?text={encoded_text}"
    
    # ⚠️ 4. Foydalanuvchiga chiroyli ogohlantirish matni
    checkout_caption = (
        f"🛒 <b>VIP BUYURTMANI RASMIYLASHTIRISH</b>\n\n"
        f"📅 Tanlangan tarif: <b>{duration} VIP</b>\n"
        f"💵 To'lov summasi: <code>{price}</code>\n\n"
        f"🚨 <b>MUHIM OGOHLANTIRISH:</b>\n\n"
        f"<i>Tizim xavfsizligi va firgarlikka qarshi kurashish maqsadida, botga har xil soxta (feyk) cheklarni tashlash mutlaqo taqiqlanadi! Soxta chek yuborgan foydalanuvchilar ogohlantirishsiz botdan abadiy <b>BAN</b> qilinadi.</i>\n\n"
        f"👇 Quyidagi tugmani bossangiz, siz uchun barcha ma'lumotlar tayyorlangan holda adminga xabar yuborish oynasi ochiladi. Admindan to'lov rekvizitlarini olib to'lovni amalga oshirasiz:"
    )
    
    # 🎛 5. Adminga o'tish va Orqaga qaytish inline klaviaturasi
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            # Bu tugma bosilganda telegram avtomatik admin bilan chatni ochadi va pastdagi yozuv tayyor turadi
            InlineKeyboardButton(text="💬 Bog'lanish", url=admin_url, style="success")
        ],
        [
            # Tariflar bo'limiga qaytarish
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data="purchase_vip", style="danger")
        ]
    ])
    
    # 📸 6. Mediani va matnni bitta oynada silliq edit qilamiz
    try:
        await callback.message.edit_caption(
            caption=checkout_caption,
            parse_mode="HTML",
            reply_markup=kb
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            pass
        else:
            logger.error(f"❌ Kutilmagan BadRequest xatoligi: {e}")
    except Exception as e:
        logger.error(f"❌ Umumiy xatolik: {e}")