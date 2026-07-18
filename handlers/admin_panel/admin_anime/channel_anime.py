from typing import Any
from aiogram import Router, F, html, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
import logging

logger = logging.getLogger("PublishAnime")
router = Router()

# =========================================================================
# 📢 E'LONLAR CHIQADIGAN KANALLAR RO'YXATI (Shu yerga xohlagancha kanal qo'shing)
# =========================================================================
PUBLISH_ANIME_CHANNELS = [
    "@Aninovuz",      # Username orqali (kanal ommaviy bo'lsa)
    # -1002154878546,             # Yoki ID raqami orqali (eng xavfsiz yo'li)
]

@router.callback_query(F.data.startswith("publish_episodes_chan:"))
async def publish_anime_to_channels_handler(callback: CallbackQuery, session: Any, bot: Bot):
    # Admin paneli qotib qolmasligi uchun darhol javob beramiz
    await callback.answer("📢 Kanalga e'lon qilinmoqda...", show_alert=False)
    
    _, anime_id_str = callback.data.split(":")
    anime_id = int(anime_id_str)

    from services.anime_service import AnimeService
    service = AnimeService(session=session)
    
    # 1. Animeni kesh yoki bazadan yuklash
    try:
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ Anime yuklashda xato: {e}")
        anime = None
        
    if not anime:
        await callback.answer("❌ Anime topilmadi!", show_alert=True)
        return

    # 2. Ma'lumotlarni xavfsiz o'qish
    title = anime.get("title", "Nomsiz anime")
    anime_id_val = anime.get("anime_id", anime_id)
    year = anime.get("year", "—")
    description = anime.get("description") or "Tavsif kiritilmagan."
    episodes_count = len(anime.get("episodes", []))
    languages = anime.get("languages", [])
    languages_str = ", ".join(languages) if languages else "Mavjud emas"
    
    # 3. Janrlarni avtomatik bazadan tortib chizish
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

    # 4. Daxshat ramkali professional UX dizayn (Kanal uchun)
    channel_caption = (
        
        f"     🎬 <b>{title}</b>\n\n"
        f"📌 <b>Anime haqida ma'lumot:</b>\n"
        f"╔══════════════════╗\n"
        f"├ 🆔 Kod: <code>#{anime_id_val}</code>\n"  
        f"├ 📅 Yil: <b>{year}</b>\n"
        f"├ ▶️ Qism: <b>{episodes_count}-qism yuklandi</b> \n"
        f"├ 🌐 Til: <b>{languages_str}</b>\n"
        f"├ 🎙 Dubber: <b>{dubbers_str}</b>\n"
        f"╚══════════════════╝\n"
        f"  🔮 Janrlar: <i>{genres_str}</i>\n\n"
        
        f"📝 <b>Tavsif:</b>\n"
        f"<blockquote expandable>{description}</blockquote>\n\n"
        f"🔥 <i>Barcha qismlarni tomosha qilish uchun quyidagi tugmani bosing:</i>"
    )

    # 5. Kanal postining tagida turadigan "🎬 Animeni ko'rish" inline tugmasi
    bot_properties = await bot.get_me()
    bot_username = bot_properties.username
    
    channel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🎬 Animeni ko‘rish", 
                # TO'G'RILANDI: Oxiridagi ortiqcha vergul olib tashlandi
                url=f"https://t.me/{bot_username}?start=anime_{anime_id_val}", style="primary"
            )
        ]
    ])

    # 6. Kod ichida ko'rsatilgan statik kanallarga xabarni tarqatamiz
    poster_id = anime.get("poster_id")
    success_count = 0

    for channel_chat_id in PUBLISH_ANIME_CHANNELS:
        try:
            if poster_id:
                try:
                    # Rasm sifatida kanalga jo'natish
                    await bot.send_photo(chat_id=channel_chat_id, photo=poster_id, caption=channel_caption, reply_markup=channel_kb, parse_mode="HTML")
                except TelegramBadRequest:
                    try:
                        # Video sifatida kanalga jo'natish
                        await bot.send_video(chat_id=channel_chat_id, video=poster_id, caption=channel_caption, reply_markup=channel_kb, parse_mode="HTML")
                    except TelegramBadRequest:
                        # Matn sifatida kanalga jo'natish
                        await bot.send_message(chat_id=channel_chat_id, text=f"⚠️ (Media xatoligi)\n\n{channel_caption}", reply_markup=channel_kb, parse_mode="HTML")
            else:
                await bot.send_message(chat_id=channel_chat_id, text=channel_caption, reply_markup=channel_kb, parse_mode="HTML")
            
            success_count += 1
        except Exception as channel_error:
            logger.error(f"❌ {channel_chat_id} kanaliga e'lon joylashda xatolik: {channel_error}")

    # 7. Yakuniy natija haqida adminga bildirishnoma berish
    if success_count > 0:
        await callback.answer(f"🚀 Anime muvaffaqiyatli {success_count} ta kanalga e‘lon qilindi!", show_alert=True)
    else:
        await callback.answer("❌ E‘lon qilishda xatolik! Bot kanalda admin ekanligini va username to'g'riligini tekshiring.", show_alert=True)