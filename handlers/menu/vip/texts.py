import urllib.parse
from datetime import datetime

ADMIN_USERNAME = "Khudoyqulov_pg"

VIP_BENEFITS = (
    "👑 <b>VIP IMTIYOZLAR:</b>\n\n"
    "<blockquote expandable> 🎬 Premyeralarni hammadan birinchi ko'rish</blockquote>\n"
    "<blockquote expandable> 🚀 Animelarni cheklovsiz yuklab olish va ulashish </blockquote>\n"
    "<blockquote expandable> 🚫 Mutlaqo reklamasiz botdan foydalanish </blockquote>\n"
    "<blockquote expandable> 🛑 Animelarni cheklovsiz boshqalar yubora olish </blockquote>\n"
    "<blockquote expandable>🎧 Eksklyuziv funksiyalardan foydalanish va botni qulay ishlatish</blockquote>\n\n"
)

RATES_TEXT = (
    "💳 <b>VIP TARIFLARI:</b>\n\n"
    "📅 <b>1 Oylik VIP</b>\n<blockquote expandable>💰 Narxi: 9,000 so'm (asl narx 💵)</blockquote>\n"
    "📅 <b>2 Oylik VIP</b>\n<blockquote expandable>💰 Narxi: 16,000 so'm (Chegirma! 🔥)</blockquote>\n"
    "📅 <b>3 Oylik VIP</b>\n<blockquote expandable>💰 Narxi: 22,000 so'm (Tavsiya etiladi! ✨)</blockquote>\n"
    "📅 <b>6 Oylik VIP</b>\n<blockquote expandable>💰 Narxi: 43,000 so'm (Tejamkor! 🚀)</blockquote>\n"
    "📅 <b>1 Yillik VIP</b>\n<blockquote expandable>💰 Narxi: 83,000 so'm (Eng katta chegirma! 👑)</blockquote>\n\n"
)

RATES_DATA = {
    "1": {"duration": "1 oylik", "price": "9 000 so'm"},
    "2": {"duration": "2 oylik", "price": "16 000 so'm"},
    "3": {"duration": "3 oylik", "price": "22 000 so'm"},
    "6": {"duration": "6 oylik", "price": "43 000 so'm"},
    "12": {"duration": "1 yillik", "price": "83 000 so'm"}
}

def get_vip_info_text(is_vip: bool, vip_expire: str | None = None) -> str:
    if is_vip:
        expire_str = "Noma'lum"
        if vip_expire:
            try:
                expire_str = datetime.fromisoformat(vip_expire).strftime("%d.%m.%Y %H:%M")
            except Exception:
                expire_str = str(vip_expire)
        return (
            "💎 <b>VIP OBUNA</b>\n\n"
            "✅ <b>Status:</b> <code>VIP Faol</code>\n"
            f"📅 <b>Tugash sanasi:</b> <code>{expire_str}</code>\n\n"
            f"{VIP_BENEFITS}"
            "✨ <i>Obunangizni muddatidan oldin uzaytirishingiz ham mumkin:</i>"
        )
    return (
        "💎 <b>VIP OBUNA</b>\n\n"
        "👤 <b>Status:</b> Oddiy foydalanuvchi\n\n"
        f"{VIP_BENEFITS}"
        "💳 <b>VIP obuna olib barcha imkoniyatlarni oching.</b>"
    )

def get_checkout_data(months: str, user_id: int):
    selected = RATES_DATA.get(months, {"duration": f"{months} oylik", "price": "Kelishilgan"})
    duration, price = selected["duration"], selected["price"]
    
    start_text = (
        f"Assalomu alaykum! Men {duration} VIP obuna sotib olmoqchi edim.\n"
        f"💰 Narxi: {price}\n"
        f"🆔 Mening ID: {user_id}"
    )
    admin_url = f"https://t.me/{ADMIN_USERNAME}?text={urllib.parse.quote(start_text)}"
    
    caption = (
        f"🛒 <b>VIP BUYURTMANI RASMIYLASHTIRISH</b>\n\n"
        f"📅 Tanlangan tarif: <b>{duration} VIP</b>\n"
        f"💵 To'lov summasi: <code>{price}</code>\n\n"
        f"🚨 <b>MUHIM OGOHLANTIRISH:</b>\n\n"
        f"<i>Tizim xavfsizligi va firgarlikka qarshi kurashish maqsadida, botga har xil soxta (feyk) cheklarni tashlash mutlaqo taqiqlanadi! Soxta chek yuborgan foydalanuvchilar ogohlantirishsiz botdan abadiy <b>BAN</b> qilinadi.</i>\n\n"
        f"👇 Quyidagi tugmani bossangiz, siz uchun barcha ma'lumotlar tayyorlangan holda adminga xabar yuborish oynasi ochiladi. Admindan to'lov rekvizitlarini olib to'lovni amalga oshirasiz:"
    )
    return caption, admin_url