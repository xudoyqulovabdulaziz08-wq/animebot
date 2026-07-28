import html
import logging
import aiohttp
from typing import Any
from aiogram import Router, F, types
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message
)
from services.anime_service import AnimeService
from utils.http import get_http_session
from handlers.search_menu.anime_card import send_anime_card
from config import config

logger = logging.getLogger(__name__)
router = Router()

API_SEARCH_URL = "https://aninov.uz/api/search"
DEFAULT_POSTER = "https://aninov.uz/static/images/default_poster.jpg"
BOT_USERNAME = getattr(config, "BOT_USERNAME", "Mazil_top_bot")


@router.inline_query()
async def inline_search(inline_query: InlineQuery):
    """
    Inline qidiruv handler.
    """
    query = inline_query.query.strip()

    if len(query) < 1:
        await inline_query.answer(results=[], cache_time=10, is_personal=True)
        return

    anime_list = []

    try:
        timeout = aiohttp.ClientTimeout(total=2)
        session = get_http_session()
        async with session.get(API_SEARCH_URL, params={"q": query}, timeout=timeout) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("success", True):
                    anime_list = data.get("data", [])
            else:
                logger.error(f"API Error: Status {response.status}")
    except Exception as e:
        logger.error(f"Inline search network error: {e}")

    results = []

    for anime in anime_list[:40]:
        anime_id = anime.get("id")
        if not anime_id:
            continue

        try:
            anime_id = int(anime_id)
        except (TypeError, ValueError):
            continue

        title = html.escape(str(anime.get("title") or "Noma'lum anime"))
        year = anime.get("year") or "Noma'lum"

        genres_raw = anime.get("genres", [])
        genres = " • ".join(str(g) for g in genres_raw if g) if isinstance(genres_raw, list) else str(genres_raw or "")
        genres = html.escape(genres) if genres else "Janr ko'rsatilmagan"

        poster_url = anime.get("poster") or DEFAULT_POSTER
        if not (isinstance(poster_url, str) and (poster_url.startswith("http://") or poster_url.startswith("https://"))):
            poster_url = DEFAULT_POSTER

        # 📌 Vaqtinchalik inline xabar matni (Orqasidan ID bilan beramiz)
        message_content = InputTextMessageContent(
            message_text=(
                f"🎬 <b>{title}</b>\n\n"
                f"📅 <b>Yili:</b> {year}\n"
                f"🎭 <b>Janrlar:</b> {genres}\n\n"
                f"🔄 <i>Yuklanmoqda... (ID: {anime_id})</i>"
            ),
            parse_mode="HTML",
        )

        results.append(
            InlineQueryResultArticle(
                id=str(anime_id),
                title=title,
                description=f"📅 {year} | 🎭 {genres}",
                thumbnail_url=poster_url,
                input_message_content=message_content,
            )
        )

    await inline_query.answer(results=results, cache_time=1, is_personal=True)


# 🔥 KAWAII BOTIDAGI KABI ISHLAYDIGAN ASOSIY HANDLER
@router.message(F.via_bot.username == BOT_USERNAME)
async def process_inline_message_in_pm(message: Message, session: Any):
    """
    Foydalanuvchi PM'da inline qidiruv orqali natijani tanlaganida tushadi.
    Vaqtinchalik matn xabarini o'chiradi va o'zingizning tayyor
    send_anime_card funksiyangizni ishga tushiradi.
    """
    try:
        # 1. Inline natijadan (chosen result) tanlangan Anime ID'sini aniqlaymiz
        # Matn ichidagi ID: {anime_id} qismidan ajratib olamiz
        anime_id = None
        if message.text and "ID: " in message.text:
            try:
                anime_id = int(message.text.split("ID: ")[1].replace(")", "").strip())
            except (IndexError, ValueError):
                pass

        if not anime_id:
            logger.warning("Inline xabardan Anime ID aniqlanmadi!")
            return

        # 2. AnimeService orqali anime ma'lumotlarini (dict) olamiz
        anime_service = AnimeService(session=session)
        anime_data = await anime_service.get_anime_by_id(anime_id)

        if not anime_data:
            logger.warning(f"ID={anime_id} bo'yicha anime topilmadi!")
            return

        # 3. SIZNING TAYYOR FUNKSIYANGIZNI CHAQRMIZ!
        # U eski vaqtinchalik xabarni o'chiradi (message.delete) 
        # va protect_content=True bilan tayyor kartochkani chiqaradi.
        await send_anime_card(message=message, anime=anime_data, session=session)

    except Exception as e:
        logger.exception(f"❌ Inline kartochkani chiqarishda xato: {e}")