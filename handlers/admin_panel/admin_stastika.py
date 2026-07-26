import logging
from typing import Any
from aiogram import Router, F, html
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from services.user_service import UserService
logger = logging.getLogger(__name__)



router = Router()

@router.callback_query(F.data == "admin_statistics")
async def show_admin_stats_handler(callback: CallbackQuery, session: Any):
    await callback.answer()

    # Servisni yuklaymiz
    service = UserService(session=session)
    
    try:
        stats = await service.get_admin_statistics()
    except Exception as e:
        logger.error(f"❌ Statistika olishda xato: {e}")
        await callback.message.answer("❌ Statistika ma'lumotlarini yuklashda xatolik yuz berdi.")
        return

    # Chiroyli admin panel dizaynidagi matn
    text = (
        f"📊 <b>BOTNING REAL VAQTDAGI STATISTIKASI</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 <b>Foydalanuvchilar:</b>\n"
        f" ├ 👤 Jami a'zolar: <code>{stats['total_users']} ta</code>\n"
        f" └ 💎 VIP obunachilar: <code>{stats['vip_users']} ta</code>\n\n"
        f"🔥 <b>Faollik (Active Users):</b>\n"
        f" ├ 📅 Kunlik faol: <code>{stats['daily_active']} ta</code>\n"
        f" ├ 🗓 Haftalik faol: <code>{stats['weekly_active']} ta</code>\n"
        f" └ 📆 Oylik faol: <code>{stats['monthly_active']} ta</code>\n\n"
        f"🎬 <b>Kontentlar muvozanati:</b>\n"
        f" ├ 📚 Jami Animelar: <code>{stats['total_anime']} ta</code>\n"
        f" └ 📹 Yuklangan jami qismlar: <code>{stats['total_episodes']} ta</code>\n\n"
        f"📢 <b>Tizim xavfsizligi:</b>\n"
        f" └ 🔗 Faol homiy kanallar: <code>{stats['active_channels']} ta</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Ma'lumotlar har 5 daqiqada yangilanadi.</i>"
    )

    # Orqaga (Asosiy admin panel menyusiga) qaytish tugmasi
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga qaytish", callback_data="admin_panel", style="danger")]
    ])

    try:
        await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        # Agar xabar tahrirlanmasa (mabodo rasm ustida bo'lsa), yangi xabar qilib yuboradi
        await callback.message.answer(text=text, reply_markup=kb, parse_mode="HTML")