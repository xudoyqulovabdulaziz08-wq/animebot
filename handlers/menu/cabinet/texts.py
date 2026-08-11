def get_cabinet_text(user_id: int, password: str, is_vip: bool) -> str:
    status = "💎 VIP" if is_vip else "👤 Oddiy"
    
    return (
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

CABINET_ERROR_TEXT = (
    "❌ Kechirasiz, ayni vaqtda shaxsiy kabinet tizimi vaqtincha ishlamayapti.\n"
    "Tizimda texnik ishlar olib borilayotgan bo'lishi mumkin. Birozdan so'ng qayta urinib ko'ring."
)