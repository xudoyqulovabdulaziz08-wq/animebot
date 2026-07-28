import html
import logging
import aiohttp
import json
from typing import Any
from aiogram import Router, Bot, types
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChosenInlineResult,
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
        async with session.get(
            API_SEARCH_URL,
            params={"q": query},
        ) as response:

            if response.status == 200:
                data = await response.json()

                if data.get("success", True):
                    anime_list = data.get("data", [])
                else:
                    logger.warning(f"API success=false. Query: '{query}'")
            else:
                logger.error(f"API Error: Status {response.status}")

    except aiohttp.ClientError as e:
        logger.error(f"Inline search network error: {e}")

    except Exception as e:
        logger.exception(f"Inline search unexpected error: {e}")

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
        if isinstance(genres_raw, list):
            genres = " • ".join(str(g) for g in genres_raw if g)
        else:
            genres = str(genres_raw or "")
        genres = html.escape(genres) if genres else "Janr ko'rsatilmagan"

        poster_url = anime.get("poster") or DEFAULT_POSTER
        if not (
            isinstance(poster_url, str)
            and (poster_url.startswith("http://") or poster_url.startswith("https://"))
        ):
            poster_url = DEFAULT_POSTER

        description = f"📅 {year} \n 🎭 {genres}"

        message_content = InputTextMessageContent(
            message_text=(
                f"🎬 <b>{title}</b>\n\n"
                f"📅 <b>Yili:</b> {year}\n"
                f"🎭 <b>Janrlar:</b> {genres}\n\n"
                f"🍿 Tomosha qilish uchun quyidagi tugmani bosing."
            ),
            parse_mode="HTML",
        )

        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🍿 Boshlash / Epizodlar",
                        url=f"https://t.me/{BOT_USERNAME}?start=anime_{anime_id}",
                    )
                ]
            ]
        )

        results.append(
            InlineQueryResultArticle(
                id=str(anime_id),
                title=title,
                description=description,
                thumbnail_url=poster_url,
                input_message_content=message_content,
                reply_markup=reply_markup,
            )
        )

    await inline_query.answer(results=results, cache_time=10, is_personal=True)


# 🧪 1. CHOSEN INLINE RESULT DEBUG
@router.chosen_inline_result()
async def test_chosen_result(chosen: ChosenInlineResult):
    logger.info(
        "\n%s\n%s\n%s\n%s",
        "=" * 60,
        "🔥 CHOSEN INLINE RESULT KELDI:",
        json.dumps(chosen.model_dump(), indent=2, ensure_ascii=False),
        "=" * 60,
    )


# 🧪 2. MESSAGE UPDATE DEBUG (ChatGPT taklif qilgan oxirgi sinov)
@router.message()
async def debug_message(message: Message):
    logger.info(
        "\n%s\n%s\nMESSAGE UPDATE: chat_id=%s | msg_id=%s | via_bot=%s | text=%s\n%s",
        "=" * 60,
        "📩 YANGI MESSAGE UPDATE KELDI:",
        message.chat.id,
        message.message_id,
        message.via_bot.username if message.via_bot else None,
        message.text,
        "=" * 60,
    )