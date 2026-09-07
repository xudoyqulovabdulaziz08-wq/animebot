import math
import logging
from typing import Any
from aiogram import Router, F, html
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from services.anime_service import AnimeService

from aiogram.types import InputMediaVideo



from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
logger = logging.getLogger(__name__)
router = Router()












async def build_anime_card(session: Any, anime: dict, anime_id: int, page: int = 1):
    """
    🎬 Anime kartasi uchun caption va klaviaturani yasaydi.
    Bir nechta joydan (ro'yxatdan ko'rish, tizer o'chirilgach qaytish va h.k.)
    qayta ishlatiladi — shu bilan karta dizayni FAQAT bitta joyda saqlanadi.
    """
    title = anime.get("title") or "Nomsiz anime"
    anime_id_val = anime.get("anime_id", anime_id)
    year = anime.get("year") or "—"
    description = anime.get("description") or "Tavsif kiritilmagan."
    episodes_count = len(anime.get("episodes", []))

    languages = anime.get("languages", [])
    languages_str = ", ".join(languages) if languages else "Mavjud emas"

    genres_str = "Mavjud emas"
    try:
        genre_ids = anime.get("genres", [])
        if genre_ids:
            from database.models import Genre
            res = await session.execute(select(Genre).where(Genre.id.in_(genre_ids)))
            genre_names = [g.name for g in res.scalars().all()]
            if genre_names:
                genres_str = ", ".join(genre_names)
    except Exception as e:
        logger.error(f"❌ Janrlarni yuklashda xato: {e}")

    dubbers_str = "Mavjud emas"
    try:
        dubber_ids = anime.get("dubbers", [])
        if dubber_ids:
            from database.models import Dubber
            res = await session.execute(select(Dubber).where(Dubber.id.in_(dubber_ids)))
            dubber_names = [d.name for d in res.scalars().all()]
            if dubber_names:
                dubbers_str = ", ".join(dubber_names)
    except Exception as e:
        logger.error(f"❌ Dubberlarni yuklashda xato: {e}")

    is_finished = anime.get("is_finished", False)
    if is_finished:
        finished_btn_text = "🟢 Tugallandi"
        finished_btn_style = "success"
    else:
        finished_btn_text = "🟡 Davom etmoqda"
        finished_btn_style = "primary"

    caption = (
        f"╔══════════════════╗\n"
        f"    🎬 <b>{title}</b>\n"
        f"╚══════════════════╝\n\n"
        f"📌 <b>Anime haqida ma'lumot:</b>\n"
        f"╔══════════════════╗\n"
        f"├ 🆔 Kod: <code>#{anime_id_val}</code>\n"
        f"├ 📅 Yil: <b>{year}</b>\n"
        f"├ ▶️ Qism: <b>{episodes_count}</b> \n"
        f"├ 🌐 Til: <b>{languages_str}</b>\n"
        f"├ 🎙 Dubber: <b>{dubbers_str}</b>\n"
        f"╚══════════════════╝\n"
        f"╔══════════════════╗\n"
        f"  🔮 Janrlar: <i>{genres_str}</i>\n"
        f"╚══════════════════╝\n\n"
        f"📝 <b>Tavsif:</b>\n"
        f"<blockquote expandable>{description}</blockquote>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📹 Qism tahrirlash", callback_data=f"manage_episodes:{anime_id}", style="primary"),
            InlineKeyboardButton(text="🗑 O‘chirish", callback_data=f"del_anime:{anime_id}", style="danger")
        ],
        [
            InlineKeyboardButton(text=finished_btn_text, callback_data=f"anime_end:{anime_id}", style=finished_btn_style),
            InlineKeyboardButton(text="🎯 Anime turi", callback_data=f"anime_type:{anime_id}", style="primary"),
        ],
        [
            InlineKeyboardButton(text="🎬 Tizer edit", callback_data=f"tizer_edit:{anime_id}", style="primary"),
            InlineKeyboardButton(text="🧩 Anime edit", callback_data=f"edit_anime:{anime_id}", style="primary")
        ],
        [
            InlineKeyboardButton(text="🆔 MAL ID", callback_data=f"mal_id:{anime_id}", style="primary"),
            InlineKeyboardButton(text="📢 E‘lon qilish", callback_data=f"publish_episodes_chan:{anime_id}", style="primary")
        ],
        [
            InlineKeyboardButton(text="⬅️ Ro‘yxatga qaytish", callback_data=f"list_anime_page:{page}", style="danger")
        ]
    ])

    return caption, kb


@router.callback_query(F.data.startswith("v_anime:"))
async def view_anime_details(callback: CallbackQuery, session: Any):
    data_parts = callback.data.split(":")
    
    # 1. Xavfsiz ID o'qish (IndexError yoki ValueError oldini olamiz)
    if len(data_parts) < 2 or not data_parts[1].isdigit():
        await callback.answer("❌ Noto'g'ri anime ID!", show_alert=True)
        return
        
    anime_id = int(data_parts[1])
    
    # Xavfsiz sahifa (page) o'qish
    page = 1
    if len(data_parts) > 2 and data_parts[2].isdigit():
        page = int(data_parts[2])
        
    from services.anime_service import AnimeService
    service = AnimeService(session=session)
    
    # 2. DB/Cache dan xavfsiz yuklash
    try:
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ Anime yuklashda xato: {e}")
        anime = None
        
    if not anime:
        await callback.answer("❌ Anime topilmadi yoki o‘chirilgan!", show_alert=True)
        return

    # 3. Karta caption va klaviaturasini umumiy funksiyadan olamiz
    caption, kb = await build_anime_card(session, anime, anime_id, page)

    # 4. Interfeys qotib qolmasligi uchun answer shu yerda beriladi
    await callback.answer("Yuklanmoqda...") 
    
    try:
        await callback.message.delete()
    except Exception:
        pass

    # 5. Fallback mexanizmi (Posterni xavfsiz yuborish)
    poster_id = anime.get("poster_id")
    
    if poster_id:
        try:
            # Avval rasm sifatida jo'natishga urinamiz
            await callback.message.answer_photo(photo=poster_id, caption=caption, reply_markup=kb, parse_mode="HTML")
        except TelegramBadRequest:
            try:
                # Agar rasm bo'lmasa, video sifatida urinamiz
                await callback.message.answer_video(video=poster_id, caption=caption, reply_markup=kb, parse_mode="HTML")
            except TelegramBadRequest:
                # Agar Telegram media ID ni umuman tanimasa, matn yuboramiz (bot qotmasligi uchun)
                await callback.message.answer(text=f"⚠️ (Media topilmadi)\n\n{caption}", reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            # Har qanday boshqa kutilmagan tarmoq yoki server xatosida bot qotmasligi uchun
            logger.error(f"Media yuborishda xato: {e}")
            await callback.message.answer(text=caption, reply_markup=kb, parse_mode="HTML")
    else:
        # Agar poster_id bazada umuman saqlanmagan bo'lsa
        await callback.message.answer(text=caption, reply_markup=kb, parse_mode="HTML")









