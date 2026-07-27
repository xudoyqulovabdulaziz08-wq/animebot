import html
import logging
import aiohttp
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

# 🤖 Botning username'i (@ belgisisiz). Agar config.py da BOT_USERNAME bo'lsa,
# undan olamiz; bo'lmasa quyidagi qatorga qo'lda yozing.
BOT_USERNAME = getattr(config, "BOT_USERNAME", "aninovuz_bot")


@router.inline_query()
async def inline_search(inline_query: InlineQuery):
    """
    Inline qidiruv handler.
    Natijadagi tugma - callback emas, balki bevosita botga olib boruvchi
    deep-link (url) tugmasi. Shuning uchun boshqa chatda faqat statik
    kartochka ko'rinadi, tomosha qilish esa har doim bot ichida bo'ladi.
    """
    query = inline_query.query.strip()

    # 1. 1 tadan kam belgi bo'lsa darhol bo'sh javob qaytaramiz
    if len(query) < 1:
        await inline_query.answer(results=[], cache_time=10, is_personal=True)
        return

    anime_list = []

    # 2. Qidiruv so'rovi (Timeout: 2s)
    
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

    # 3. Top 40 natijalarni Article ko'rinishida shakllantiramiz
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

        # Janrlar ishlovi
        genres_raw = anime.get("genres", [])
        if isinstance(genres_raw, list):
            genres = " • ".join(str(g) for g in genres_raw if g)
        else:
            genres = str(genres_raw or "")
        genres = html.escape(genres) if genres else "Janr ko'rsatilmagan"

        # Poster rasmi (Thumbnail uchun)
        poster_url = anime.get("poster") or DEFAULT_POSTER
        if not (
            isinstance(poster_url, str)
            and (poster_url.startswith("http://") or poster_url.startswith("https://"))
        ):
            poster_url = DEFAULT_POSTER

        # Telegram natijalar oynasidagi qisqa tavsif
        description = f"📅 {year} \n 🎭 {genres}"

        # Boshqa chatga yuborilganda ko'rinadigan statik matn.
        # Tomosha qilish faqat bot ichida bo'lgani uchun bu yerda
        # hech qanday "yuklanmoqda" kabi vaqtinchalik holat yo'q.
        message_content = InputTextMessageContent(
            message_text=(
                f"🎬 <b>{title}</b>\n\n"
                f"📅 <b>Yili:</b> {year}\n"
                f"🎭 <b>Janrlar:</b> {genres}\n\n"
                f"🍿 Tomosha qilish uchun quyidagi tugmani bosing."
            ),
            parse_mode="HTML",
        )

        # 🔗 Deep-link tugma: bosilganda foydalanuvchi to'g'ridan-to'g'ri
        # botning shaxsiy chatiga o'tadi va /start anime_{id} ishga tushadi
        # (cmd_start ichidagi mavjud deep-link parsing shu formatni kutadi).
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

    # 4. Javobni tezkorlik bilan qaytaramiz (cache_time=1)
    await inline_query.answer(results=results, cache_time=10, is_personal=True)





@router.chosen_inline_result()
async def process_chosen_inline_result(
    chosen_result: ChosenInlineResult, 
    bot: Bot, 
    session: Any,
    data_service: AnimeService
):
    """
    Foydalanuvchi inline qidiruv ro'yxatidan biror animeni tanlab bosganda ishlaydi.
    """
    # 1. Agar foydalanuvchi botning SHAXSIY CHATIDA inline qidiruv ishlatgan bo'lsa
    # (PM da inline_message_id bo'lmaydi)
    if not chosen_result.inline_message_id:
        user_id = chosen_result.from_user.id
        anime_id = chosen_result.result_id

        try:
            # A) Bazadan yoki API'dan anime ma'lumotlarini (dict ko'rinishida) olamiz
            anime = await data_service.get_anime_by_id(anime_id)
            if not anime:
                return

            # B) send_anime_card ga berish uchun soxta (dummy) Message obyektini yasaymiz
            # Bu send_anime_card ichidagi message.delete() va message.answer_photo()
            # to'g'ri ishlashi uchun kerak.
            dummy_message = Message(
                message_id=0,
                date=chosen_result.from_user.id,  # Muhim emas
                chat=types.Chat(id=user_id, type="private"),
                from_user=chosen_result.from_user,
                bot=bot
            )

            # C) Tayyor send_anime_card funksiyangizni chaqiramiz!
            # U barcha ko'rilishlarni hisoblaydi, VIP/Admin holatiga qarab protect_content
            # qo'yadi va rasmli kartochkani chiqaradi.
            await send_anime_card(message=dummy_message, anime=anime, session=session)

        except Exception as e:
            logger.error(f"❌ Inline chosen result ishlovida xato: {e}")