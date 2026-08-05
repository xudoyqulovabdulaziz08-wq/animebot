import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from config import config
from services.rating_service import RatingService 

logger = logging.getLogger("baholashlarim")
router = Router()
CREATOR_ID = config.CREATOR_ID


def get_rating_keyboard(anime_id: int, user_score: int | None = None) -> InlineKeyboardMarkup:
    """
    Dinamik rating klaviaturasi:
    - Baho berilmagan bo'lsa: 1-10 tugmalari va Orqaga
    - Baho berilgan bo'lsa: Info (noop), Bekor qilish va Orqaga
    """
    builder = []

    if user_score is None:
        # 🟢 HOLAT 1: Foydalanuvchi hali baho bermagan
        row1 = [
            InlineKeyboardButton(text=f"⭐ {i}", callback_data=f"set_rate:{anime_id}:{i}")
            for i in range(1, 6)
        ]
        row2 = [
            InlineKeyboardButton(text=f"⭐ {i}", callback_data=f"set_rate:{anime_id}:{i}")
            for i in range(6, 11)
        ]
        builder.append(row1)
        builder.append(row2)
    else:
        # 🟡 HOLAT 2: Foydalanuvchi allaqachon baho bergan
        # 1-qator: NOOP tugma (bosilganda alert beradi)
        builder.append([
            InlineKeyboardButton(
                text=f"🌟 Sizning bahoingiz: {user_score}/10", 
                callback_data=f"rate_info:{user_score}"
            )
        ])
        # 2-qator: Bekor qilish tugmasi
        builder.append([
            InlineKeyboardButton(
                text="❌ Bahoni bekor qilish", 
                callback_data=f"del_rate:{anime_id}"
            )
        ])

    # Oxirgi qator: Doimiy "Orqaga" tugmasi
    builder.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"anime_card:{anime_id}")
    ])

    return InlineKeyboardMarkup(inline_keyboard=builder)


# 1. "⭐ Baholash" tugmasi bosilganda - Klaviatura menyusini ko'rsatish
@router.callback_query(F.data.startswith("anime_rating:"))
async def anime_rating_menu_handler(callback: CallbackQuery, session):
    user_id = callback.from_user.id
    
    if user_id != CREATOR_ID:
        await callback.answer("🛑 Baholash funksiyasi tez orada ishga tushadi.", show_alert=True)
        return

    anime_id = int(callback.data.split(":")[1])
    rating_service = RatingService(session)

    # Foydalanuvchining mavjud bahosini tekshiramiz
    user_score = await rating_service.get_user_rating(user_id, anime_id)

    kb = get_rating_keyboard(anime_id, user_score=user_score)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
        await callback.answer()
    except TelegramBadRequest:
        await callback.answer()


# 2. Foydalanuvchi 1-10 ball tugmalaridan birini bosganda
@router.callback_query(F.data.startswith("set_rate:"))
async def set_rating_handler(callback: CallbackQuery, session):
    _, anime_id_str, score_str = callback.data.split(":")
    anime_id = int(anime_id_str)
    score = int(score_str)
    user_id = callback.from_user.id

    rating_service = RatingService(session)
    res = await rating_service.rate_anime(user_id=user_id, anime_id=anime_id, score=score)

    if res.get("success"):
        avg = res["average_rating"]
        cnt = res["rating_count"]
        
        # Klaviaturani darhol HOLAT 2 (baholangan) rejimlarga almashtiramiz
        new_kb = get_rating_keyboard(anime_id, user_score=score)
        await callback.message.edit_reply_markup(reply_markup=new_kb)
        
        await callback.answer(
            f"✅ Rahmat! Bahoyingiz qabul qilindi: {score}/10\n"
            f"O'rtacha reyting: ⭐ {avg} ({cnt} ta ovoz)", 
            show_alert=True
        )
    else:
        await callback.answer("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.", show_alert=True)


# 3. NOOP tugmasi (Sizning bahoingiz: X/10) bosilganda alert ko'rsatish
@router.callback_query(F.data.startswith("rate_info:"))
async def rate_info_handler(callback: CallbackQuery):
    user_score = callback.data.split(":")[1]
    await callback.answer(
        f"ℹ️ Siz ushbu animega {user_score}/10 baho bergansiz.\n\n"
        f"Bahoni o'zgartirish uchun avval bekor qiling.", 
        show_alert=True
    )


# 4. Bahoni bekor qilish tugmasi bosilganda
@router.callback_query(F.data.startswith("del_rate:"))
async def delete_rating_handler(callback: CallbackQuery, session):
    anime_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    rating_service = RatingService(session)
    res = await rating_service.remove_rating(user_id=user_id, anime_id=anime_id)

    if res.get("success"):
        # Klaviaturani qayta HOLAT 1 (1-10 tugmalari) rejimiga o'tkazamiz
        new_kb = get_rating_keyboard(anime_id, user_score=None)
        await callback.message.edit_reply_markup(reply_markup=new_kb)
        
        await callback.answer("🗑 Bahoyingiz muvaffaqiyatli bekor qilindi.", show_alert=True)
    else:
        await callback.answer("❌ Baho topilmadi yoki allaqachon o'chirilgan.", show_alert=True)