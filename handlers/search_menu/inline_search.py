import html
import logging
import re
import aiohttp
from typing import Any
from aiogram import Router, F, types
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message, 
    LinkPreviewOptions,
    InlineKeyboardMarkup, 
    InlineKeyboardButton
)
from services.anime_service import AnimeService
from utils.http import get_http_session
from handlers.search_menu.anime_card import send_anime_card
from config import config

logger = logging.getLogger(__name__)
router = Router()

API_HOMEPAGE_URL = "https://aninov.uz/api/anime/homepage"
API_SEARCH_URL = "https://aninov.uz/api/search"
DEFAULT_POSTER = "https://aninov.uz/static/images/default_poster.jpg"
BOT_USERNAME = getattr(config, "BOT_USERNAME", "Mazil_top_bot")


@router.inline_query()
async def inline_search(inline_query: InlineQuery):
    """
    Inline qidiruv handler.
    - Bo'sh yoki indikator matni tursa -> Homepage API
    - Matn kiritilsa -> Search API
    """
    query = inline_query.query.strip()
    session = get_http_session()
    timeout = aiohttp.ClientTimeout(total=2)

    anime_list = []
    is_homepage = False

    try:
        # 🎯 1. SHART: Bo'sh yoki avtomatik indikator matni bo'lsa -> Homepage API
        if not query or query.lower() in ["anime nomi yozing....", "anime nomi yozing", ""]:
            is_homepage = True
            async with session.get(API_HOMEPAGE_URL, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list):
                        anime_list = data
                    elif isinstance(data, dict):
                        anime_list = data.get("data") or data.get("results") or []
        # 🎯 2. SHART: So'rov kiritilgan bo'lsa -> Search API
        else:
            async with session.get(API_SEARCH_URL, params={"q": query}, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, dict):
                        anime_list = data.get("data", [])
                    elif isinstance(data, list):
                        anime_list = data

    except Exception as e:
        logger.error(f"Inline search network error (is_homepage={is_homepage}): {e}")

    # 🛡 XAVFSIZLIK TEKSHIRUVI
    if not isinstance(anime_list, list):
        anime_list = []

    results = []

    for anime in anime_list[:40]:
        if not isinstance(anime, dict):
            continue

        raw_id = anime.get("anime_id") if is_homepage else anime.get("id")
        if not raw_id:
            raw_id = anime.get("id") or anime.get("anime_id")
            
        if not raw_id:
            continue

        try:
            anime_id = int(raw_id)
        except (TypeError, ValueError):
            continue

        title = html.escape(str(anime.get("title") or "Noma'lum anime"))
        year = anime.get("year") or "Noma'lum"
        slug = anime.get("seo_slug") or str(anime_id)

        genres_raw = anime.get("genres", [])
        parsed_genres = []
        if isinstance(genres_raw, list):
            for g in genres_raw:
                if isinstance(g, dict) and "name" in g:
                    parsed_genres.append(str(g["name"]))
                elif isinstance(g, str):
                    parsed_genres.append(g)
        
        genres = " • ".join(parsed_genres) if parsed_genres else "Janr ko'rsatilmagan"
        genres = html.escape(genres)

        poster_url = anime.get("poster") or DEFAULT_POSTER
        if not (isinstance(poster_url, str) and (poster_url.startswith("http://") or poster_url.startswith("https://"))):
            poster_url = DEFAULT_POSTER

        # Xabar matni
        message_text = (
            f'<a href="{poster_url}">&#8203;</a>'
            f"📕 <b>{title}</b>\n\n"
            f"<blockquote expandable>🎭 <b>Janrlar:</b> {genres}\n</blockquote>"
            f"📅 <b>Yili:</b> {year}\n"
            f"🆔 <b>ID:</b> <code>{anime_id}</code>\n\n"
            f"<i>Aninovuzda tomosha qiling</i>"
        )

        message_content = InputTextMessageContent(
            message_text=message_text,
            parse_mode="HTML",
            link_preview_options=LinkPreviewOptions(
                url=poster_url,
                prefer_large_media=True,
                show_above_text=True
            )
        )

        deep_link_url = f"https://t.me/{BOT_USERNAME}?start=anime_{anime_id}"
        sayt_url = f"https://aninov.uz/anime/{slug}"
        kanal_url = "https://t.me/Aninovuz"

        inline_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🤖 Bot", url=deep_link_url, style="success"),
                    InlineKeyboardButton(text="🌐 Sayt", url=sayt_url, style="success")
                ],
                [
                    InlineKeyboardButton(text="📢 Kanal", url=kanal_url, style="primary")
                ]
            ]
        )

        results.append(
            InlineQueryResultArticle(
                id=str(anime_id),
                title=title,
                description=f"📅 {year} | 🎭 {genres}",
                thumbnail_url=poster_url,
                input_message_content=message_content,
                reply_markup=inline_kb
            )
        )

    cache_time = 5 if is_homepage else 1
    await inline_query.answer(results=results, cache_time=cache_time, is_personal=True)


# 🔥 KAWAII BOTIDAGI KABI ISHLAYDIGAN ASOSIY HANDLER
@router.message(F.via_bot.username == BOT_USERNAME)
async def process_inline_message_in_pm(message: Message, session: Any):
    """
    Foydalanuvchi PM'da inline qidiruv orqali natijani tanlaganida tushadi.
    Vaqtinchalik matn xabarini o'chiradi va send_anime_card funksiyasini ishga tushiradi.
    """
    try:
        anime_id = None
        
        # 1. Matndan ID'ni Regex yordamida kafolatlangan holda ajratib olamiz
        text_to_search = message.text or message.caption or ""
        match = re.search(r"🆔\s*<b>ID:</b>\s*<code>(\d+)</code>", text_to_search)
        if not match:
            # HTML parsingiz sizda o'chirilgan holatda ham topsin:
            match = re.search(r"ID:\s*(\d+)", text_to_search)

        if match:
            anime_id = int(match.group(1))

        if not anime_id:
            logger.warning("Inline xabardan Anime ID aniqlanmadi!")
            return

        # 2. Vaqtinchalik inline xabarni o'chirib tashlaymiz
        try:
            await message.delete()
        except Exception as del_err:
            logger.warning(f"Vaqtinchalik xabarni o'chirishda xatolik: {del_err}")

        # 3. AnimeService orqali anime ma'lumotlarini olib kartochkani chiqarish
        anime_service = AnimeService(session=session)
        anime_data = await anime_service.get_anime(anime_id)

        if not anime_data:
            logger.warning(f"ID={anime_id} bo'yicha anime topilmadi!")
            return

        # 4. Anime kartochkasini yuboramiz
        await send_anime_card(message=message, anime=anime_data, session=session)

    except Exception as e:
        logger.exception(f"❌ Inline kartochkani chiqarishda xato: {e}")