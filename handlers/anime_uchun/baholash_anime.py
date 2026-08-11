import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from config import config
from services.rating_service import RatingService 
from services.anime_service import AnimeService

logger = logging.getLogger("baholashlarim")
router = Router()
CREATOR_ID = config.CREATOR_ID


def get_rating_keyboard(anime_id: int, user_score: int | None = None) -> InlineKeyboardMarkup:
    """Dinamik baholash klaviaturasi"""
    builder = []

    if user_score is None:
        # 🟢 HOLAT 1: Hali baho berilmagan (1-10 tugmalari)
        row1 = [
            InlineKeyboardButton(text=f"⭐ {i}", callback_data=f"set_rate:{anime_id}:{i}", style="primary")
            for i in range(1, 6)
        ]
        row2 = [
            InlineKeyboardButton(text=f"⭐ {i}", callback_data=f"set_rate:{anime_id}:{i}", style="primary")
            for i in range(6, 11)
        ]
        builder.append(row1)
        builder.append(row2)
    else:
        # 🟡 HOLAT 2: Allaqachon baho berilgan
        builder.append([
            InlineKeyboardButton(
                text=f"🌟 Sizning bahoyingiz: {user_score}/10", 
                callback_data=f"rate_info:{user_score}",
                style="primary"
            )
        ])
        builder.append([
            InlineKeyboardButton(
                text="❌ Bahoni bekor qilish", 
                callback_data=f"del_rate:{anime_id}",
                style="danger"
            )
        ])

    # Doimiy "Orqaga" tugmasi
    builder.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"anime_card_back:{anime_id}", style="danger")
    ])

    return InlineKeyboardMarkup(inline_keyboard=builder)













def build_rating_caption(
    anime_title: str,
    avg_rating: float | None,
    rating_count: int,
    user_score: int | None = None
) -> str:
    """Baholash oynasi uchun dinamik caption yaratadi."""

    if avg_rating is not None:
        avg_text = f"{avg_rating:.1f}/10"
    else:
        avg_text = "Hali baholanmagan"

    score_status = (
        f"🌟 Sizning bahoyingiz: <b>{user_score}/10</b>"
        if user_score is not None
        else "⭐ Siz hali baho bermagansiz."
    )

    return (
        f"⭐ <b>Baholash</b>\n\n"
        f"🎬 <b>{anime_title}</b>\n\n"
        f"⭐ Umumiy reyting: <b>{avg_text}</b>\n"
        f"👥 <b>{rating_count} ta baho</b>\n\n"
        f"{score_status}"
    )













@router.callback_query(F.data.startswith("anime_rating:"))
async def anime_rating_menu_handler(callback: CallbackQuery, session):
    user_id = callback.from_user.id

    if user_id != CREATOR_ID:
        await callback.answer(
            "🛑 Baholash funksiyasi tez orada ishga tushadi.",
            show_alert=True
        )
        return

    anime_id = int(callback.data.split(":")[1])

    rating_service = RatingService(session)
    anime_service = AnimeService(session)

    anime = await anime_service.get_anime(anime_id)

    if not anime:
        await callback.answer(
            "❌ Anime topilmadi.",
            show_alert=True
        )
        return

    user_score = await rating_service.get_user_rating(
        user_id,
        anime_id
    )

    r_sum = anime.get("rating_sum", 0)
    r_cnt = anime.get("rating_count", 0)

    avg = round(r_sum / r_cnt, 1) if r_cnt > 0 else None

    caption = build_rating_caption(
        anime.get("title", "Nomsiz anime"),
        avg,
        r_cnt,
        user_score
    )

    kb = get_rating_keyboard(
        anime_id,
        user_score
    )

    try:
        await callback.message.edit_caption(
            caption=caption,
            reply_markup=kb,
            parse_mode="HTML"
        )
        await callback.answer()

    except TelegramBadRequest as e:
        logger.warning(f"Rating menu update failed: {e}")
        await callback.answer()








@router.callback_query(F.data.startswith("set_rate:"))
async def set_rating_handler(callback: CallbackQuery, session):
    _, anime_id_str, score_str = callback.data.split(":")

    anime_id = int(anime_id_str)
    score = int(score_str)
    user_id = callback.from_user.id

    rating_service = RatingService(session)
    anime_service = AnimeService(session)

    res = await rating_service.rate_anime(
        user_id=user_id,
        anime_id=anime_id,
        score=score
    )

    if not res.get("success"):
        await callback.answer(
            "❌ Baholashda xatolik yuz berdi.",
            show_alert=True
        )
        return

    avg = res["average_rating"]
    cnt = res["rating_count"]

    anime = await anime_service.get_anime(anime_id)
    title = anime.get("title", "Nomsiz anime") if anime else "Anime"

    new_caption = build_rating_caption(
        title,
        avg,
        cnt,
        user_score=score
    )

    new_kb = get_rating_keyboard(
        anime_id,
        user_score=score
    )

    await callback.message.edit_caption(
        caption=new_caption,
        reply_markup=new_kb,
        parse_mode="HTML"
    )

    await callback.answer(
        f"⭐ Bahoyingiz: {score}/10\n"
        f"📊 O‘rtacha: {avg:.1f}/10 ({cnt} ta baho)",
        show_alert=True
    )





@router.callback_query(F.data.startswith("rate_info:"))
async def rate_info_handler(callback: CallbackQuery):
    user_score = callback.data.split(":")[1]

    await callback.answer(
        f"⭐ Sizning bahoyingiz: {user_score}/10\n\n"
        f"🔄 Bahoni o‘zgartirish uchun avval uni bekor qiling.",
        show_alert=True
    )







@router.callback_query(F.data.startswith("del_rate:"))
async def delete_rating_handler(callback: CallbackQuery, session):
    anime_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    rating_service = RatingService(session)
    anime_service = AnimeService(session)

    res = await rating_service.remove_rating(
        user_id=user_id,
        anime_id=anime_id
    )

    if not res.get("success"):
        await callback.answer(
            "❌ Sizda ushbu anime uchun baho mavjud emas.",
            show_alert=True
        )
        return

    avg = res["average_rating"]
    cnt = res["rating_count"]

    anime = await anime_service.get_anime(anime_id)
    title = anime.get("title", "Nomsiz anime") if anime else "Anime"

    new_caption = build_rating_caption(
        title,
        avg,
        cnt,
        user_score=None
    )

    new_kb = get_rating_keyboard(
        anime_id,
        user_score=None
    )

    await callback.message.edit_caption(
        caption=new_caption,
        reply_markup=new_kb,
        parse_mode="HTML"
    )

    await callback.answer(
        "✅ Bahoyingiz bekor qilindi.",
        show_alert=True
    )






@router.callback_query(F.data.startswith("anime_card_back:"))
async def back_to_anime_card_handler(callback: CallbackQuery, session):
    anime_id = int(callback.data.split(":")[1])
    anime_service = AnimeService(session)
    
    anime = await anime_service.get_anime(anime_id)
    if anime:
        # Mavjud send_anime_card funksiyangiz orqali silliq tahrirlaymiz
        from handlers.search.anime_card import send_anime_card  # Import yo'lini to'g'rilang
        await send_anime_card(
            message=callback.message,
            anime=anime,
            session=session,
            edit=True,
            callback=callback
        )
    await callback.answer()