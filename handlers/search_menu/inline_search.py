import html
import logging
import aiohttp
from typing import Any
from aiogram import Router, F, types
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    LinkPreviewOptions
)
from utils.http import get_http_session
from config import config

logger = logging.getLogger(__name__)
router = Router()

API_SEARCH_URL = "https://aninov.uz/api/search"
API_HOMEPAGE_URL = "https://aninov.uz/api/anime/homepage"
DEFAULT_POSTER = "https://aninov.uz/static/images/default_poster.jpg"
BOT_USERNAME = getattr(config, "BOT_USERNAME", "Mazil_top_bot")


@router.inline_query()
async def inline_search(inline_query: InlineQuery):
    """
    Inline qidiruv handler:
    - Agar query bo'sh bo'lsa -> Homepage (so'nggi) animelarni ko'rsatadi.
    - Agar query bo'lsa -> Qidiruv bo'yicha animelarni ko'rsatadi.
    """
    query = inline_query.query.strip()
    session = get_http_session()
    timeout = aiohttp.ClientTimeout(total=2)

    anime_list = []
    is_homepage = False

    try:
        # 🎯 1. SHART: Agar so'rov bo'sh bo'lsa -> Homepage API ga so'rov yuboramiz
        if len(query) == 0:
            is_homepage = True
            async with session.get(API_HOMEPAGE_URL, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    # Agar javob ro'yxat bo'lsa yoki dict bo'lsa moslashtiramiz
                    if isinstance(data, list):
                        anime_list = data
                    elif isinstance(data, dict):
                        anime_list = data.get("data", []) or data.get("results", [])
        # 🎯 2. SHART: Matn kiritilgan bo'lsa -> Search API ga so'rov yuboramiz
        else:
            async with session.get(API_SEARCH_URL, params={"q": query}, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("success", True):
                        anime_list = data.get("data", [])
    except Exception as e:
        logger.error(f"Inline search network error (is_homepage={is_homepage}): {e}")

    results = []

    for anime in anime_list[:40]:
        # Homepage va Search API o'rtasidagi ID farqini tekshiramiz
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

        # Janrlarni to'g'ri formatlash (Homepage'da dict, Search'da str keladi)
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

        # 🖼 Katta rasm bilan chiqadigan xabar matni
        message_text = (
            f'<a href="{poster_url}">&#8203;</a>'
            f"📕 <b>{title}</b>\n\n"
            f"<blockquote expandable>"
            f"🎭 <b>Janrlar:</b> {genres}\n"
            f"📅 <b>Yili:</b> {year}\n"
            f"🆔 <b>ID:</b> <code>{anime_id}</code>"
            f"</blockquote>"
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

        # 🔗 Inline Klaviaturasidagi tugmalar
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

    # Cache vaqtini homepage uchun kamroq, shunda yangi animelar tez aks etadi
    cache_time = 5 if is_homepage else 1
    await inline_query.answer(results=results, cache_time=cache_time, is_personal=True)