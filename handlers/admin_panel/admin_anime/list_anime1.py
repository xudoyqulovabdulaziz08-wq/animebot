
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












@router.callback_query(F.data.startswith("v_anime:"))
async def view_anime_details(callback: CallbackQuery, session: Any):
    data_parts = callback.data.split(":")
    anime_id = int(data_parts[1])
    
    # Agar 3-qism (page) kelmasa, avtomatik 1 deb qabul qiladi
    page = int(data_parts[2]) if len(data_parts) > 2 else 1 
    
    from services.anime_service import AnimeService
    service = AnimeService(session=session)
    
    # 1. DB/Cache dan xavfsiz yuklash
    try:
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ Anime yuklashda xato: {e}")
        anime = None
        
    if not anime:
        await callback.answer("❌ Anime topilmadi yoki o‘chirilgan!", show_alert=True)
        return

    # 2. KeyError oldini olish uchun lug'atdan xavfsiz o'qish
    title = anime.get("title", "Nomsiz anime")
    anime_id_val = anime.get("anime_id", anime_id)
    year = anime.get("year", "—")
    description = anime.get("description") or "Tavsif kiritilmagan."
    episodes_count = len(anime.get("episodes", []))
    
    languages = anime.get("languages", [])
    languages_str = ", ".join(languages) if languages else "Mavjud emas"
    
    # 3. Janr nomlarini xavfsiz shakllantirish
    genres_str = "Mavjud emas"
    try:
        genre_ids = anime.get("genres", [])
        if genre_ids:
            from database.models import Genre
            from sqlalchemy import select
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
            from sqlalchemy import select
            res = await session.execute(select(Dubber).where(Dubber.id.in_(dubber_ids)))
            dubber_names = [d.name for d in res.scalars().all()]
            if dubber_names:
                dubbers_str = ", ".join(dubber_names)
    except Exception as e:
        logger.error(f"❌ Dubberlarni yuklashda xato: {e}")


    # 4. Siz aytgan daxshat ramkali UX dizayn
    caption = (
        f"╔══════════════════╗\n"
        f"     🎬 <b>{title}</b>\n"
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
            InlineKeyboardButton(text="🗑 Animeni o‘chirish", callback_data=f"del_anime:{anime_id}", style="danger")
        ],
        [
            InlineKeyboardButton(text="🟢 Tugalandi", callback_data=f"end:{anime_id}", style="primary"),
            InlineKeyboardButton(text="🎯 Anime turi", callback_data=f"anime_type:{anime_id}", style="primary"),
        ],
        [
            InlineKeyboardButton(text="🎬 Tizer edit", callback_data=f"tizer_edit:{anime_id}", style="primary"),
            InlineKeyboardButton(text="🧩 Anime edit", callback_data=f"edit_anime:{anime_id}", style="primary" )
        ],

        [
            InlineKeyboardButton(text="🆔 MAL ID", callback_data=f"mal_id:{anime_id}", style="primary" ),
            InlineKeyboardButton(text="📢 E‘lon qilish", callback_data=f"publish_episodes_chan:{anime_id}", style="primary")
        ],
        [
            InlineKeyboardButton(text="⬅️ Ro‘yxatga qaytish", callback_data=f"list_anime_page:{page}", style="danger")
        ]
    ])

    # 5. Interfeys qotib qolmasligi uchun answer shu yerda beriladi
    await callback.answer("Yuklanmoqda...") 
    
    try:
        await callback.message.delete()
    except Exception:
        pass

    # 6. Fallback mexanizmi (Posterni xavfsiz yuborish)
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
    else:
        # Agar poster_id bazada umuman saqlanmagan bo'lsa
        await callback.message.answer(text=caption, reply_markup=kb, parse_mode="HTML")










@router.callback_query(F.data.startswith("del_anime:"))
async def confirm_delete_anime_handler(callback: CallbackQuery, session: Any):
    await callback.answer("Yuklanmoqda...")
    anime_id = int(callback.data.split(":")[1])
    
    confirm_text = (
        f"⚠️ {html.bold('DIQQAT! O‘chirishni tasdiqlang')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Ushbu animeni ro‘yxatdan butunlay o‘chirib tashlamoqchimisiz?\n\n"
        f"🛑 {html.italic('Bu amalni ortga qaytarib bo‘lmaydi! Animega tegishli barcha qismlar (seriyalar) ham bazadan o‘chib ketadi.')}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha,  o‘chirish", callback_data=f"burn_anime:{anime_id}", style="success"),
            InlineKeyboardButton(text="❌ bekor qilish", callback_data=f"v_anime:{anime_id}:1", style="danger")
        ]
    ])
    
    # Agar xabarda rasm yoki video bo'lsa, posterni saqlab faqat matnni o'zgartiramiz
    if callback.message.photo or callback.message.video:
        try:
            await callback.message.edit_caption(caption=confirm_text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass
    else:
        try:
            await callback.message.edit_text(text=confirm_text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass








@router.callback_query(F.data.startswith("burn_anime:"))
async def execute_delete_anime_handler(callback: CallbackQuery, session: Any):
    await callback.answer("O'chirilmoqda")
    anime_id = int(callback.data.split(":")[1])
    
    # 🎯 MUAMMONI ILDIZI BILAN YUQOTISH:
    # SafeSession proxy hali bazaga ulanmagan bo'lsa, uni majburan uyg'otamiz.
    # Bu orqali ichki _session obyekti None bo'lishdan to'xtaydi va SQLAlchemy sessiyasiga aylanadi.
    try:
        if hasattr(session, "_ensure_session"):
            await session._ensure_session()
    except Exception as e:
        logger.error(f"❌ Lazy sessionni faollashtirishda xato: {e}")

    from services.anime_service import AnimeService
    # Endi session ichidagi _session mutlaqo tayyor va None emas!
    service = AnimeService(session=session)
    
    ok = False
    try:
        # Tranzaksiya bilan bazadan o'chirish va keshni butunlay tozalash
        ok = await service.delete_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ Anime o'chirishda jiddiy xatolik: {e}")

    # Eski posterli/mediali tasdiqlash xabarini barqaror o'chirib tashlaymiz
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Adminga yakuniy natija matnini tayyorlaymiz
    if ok:
        success_text = (
            f"🗑 {html.bold('Muvaffaqiyatli o‘chirildi!')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ Tanlangan anime, uning barcha qismlari ma’lumotlar bazasidan hamda kesh xotirasidan butunlay yo‘q qilindi."
        )
    else:
        success_text = (
            f"❌ {html.bold('Xatolik yuz berdi!')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ Ushbu animeni o‘chirishda xatolik yuz berdi. U allaqachon o‘chirilgan yoki tizimda ulanish uzilgan bo‘lishi mumkin."
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Animelar ro‘yxatiga", callback_data="list_anime_page:1", style="danger")]
    ])
    
    # Toza matn ko'rinishida yakuniy javobni yuboramiz
    try:
        await callback.message.answer(text=success_text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ Yakuniy xabarni yuborishda xato: {e}")
















