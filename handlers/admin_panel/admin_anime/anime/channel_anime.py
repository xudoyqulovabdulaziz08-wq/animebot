import asyncio
import logging
from typing import Any, Optional

from aiogram import Router, F, html, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramNetworkError,
)

from services.orchestrator import state

logger = logging.getLogger("PublishAnime")
router = Router()


SEND_CONCURRENCY = 5


if not hasattr(state, "pending_publish_selections"):
    state.pending_publish_selections = {}  # {(user_id, anime_id): set(channel_pk_ids)}

_bot_username_cache: Optional[str] = None


# =======================================================
# 🧰 YORDAMCHI FUNKSIYALAR (Telegramning turli xatolaridan himoya)
# =======================================================
async def safe_answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False) -> None:
    """
    callback.answer()ni xavfsiz chaqiradi. Har bir callback_query FAQAT BIR MARTA
    javob olishi mumkin — shu sabab bu funksiya har bir handlerda faqat BIR marta
    chaqiriladi, qolgan barcha xabarlar _safe_edit orqali beriladi.
    """
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "query is too old" in msg or "query id is invalid" in msg or "response timeout expired" in msg:
            pass
        else:
            logger.warning(f"callback.answer xatosi: {e}")
    except TelegramForbiddenError:
        pass
    except Exception as e:
        logger.warning(f"callback.answer kutilmagan xato: {e}")


async def _safe_edit(message, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> None:
    """
    Xabar matn ko'rinishida bo'lsa edit_text, rasm/video (caption) bo'lsa
    edit_caption, ikkalasi ham ishlamasa delete+answer bilan yangi xabar yuboradi.
    Barcha bosqichlarda Telegramning kutilgan xatolari (bloklangan, o'zgarmagan
    xabar, topilmagan xabar) xavfsiz yutiladi.
    """
    try:
        await message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
        return
    except TelegramForbiddenError:
        return
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
    except Exception as e:
        logger.warning(f"_safe_edit: edit_text kutilmagan xato: {e}")

    try:
        await message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
        return
    except TelegramForbiddenError:
        return
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
    except Exception as e:
        logger.warning(f"_safe_edit: edit_caption kutilmagan xato: {e}")

    try:
        await message.delete()
    except Exception:
        pass

    try:
        await message.answer(text=text, reply_markup=reply_markup, parse_mode="HTML")
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError) as e:
        logger.warning(f"_safe_edit: yangi xabar yuborib bo'lmadi: {e}")
    except Exception as e:
        logger.error(f"_safe_edit: yangi xabar yuborishda kutilmagan xato: {e}", exc_info=True)


async def _get_bot_username(bot: Bot) -> Optional[str]:
    """Bot usernameni keshlab qo'yamiz — har chaqiriqda get_me() so'ramaslik uchun."""
    global _bot_username_cache
    if _bot_username_cache is None:
        me = await bot.get_me()
        _bot_username_cache = me.username
    return _bot_username_cache


def _build_channel_selection_kb(anime_id: int, page: int, channels: list, selected_ids: set) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        mark = "✅" if ch["id"] in selected_ids else "▫️"
        rows.append([InlineKeyboardButton(
            text=f"{mark} {ch['title']}",
            callback_data=f"pub_toggle:{anime_id}:{page}:{ch['id']}"
        )])

    rows.append([
        InlineKeyboardButton(text=f"🚀 Yuborish ({len(selected_ids)})", callback_data=f"pub_confirm:{anime_id}:{page}", style="success"),
        InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data=f"v_anime:{anime_id}:{page}", style="danger"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# =======================================================
# 1️⃣ KANAL TANLASH MENYUSINI OCHISH
# =======================================================
@router.callback_query(F.data.startswith("publish_episodes_chan:"))
async def show_channel_selection_handler(callback: CallbackQuery, session: Any):
    try:
        parts = callback.data.split(":")
        anime_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 1
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    await safe_answer(callback)

    try:
        from services.channel_service import ChannelService
        channel_service = ChannelService(session=session)
        channels = await channel_service.get_active_channels()
    except Exception as e:
        logger.error(f"❌ Kanallar ro'yxatini olishda xato: {e}", exc_info=True)
        await _safe_edit(callback.message, "❌ Kanallar ro'yxatini yuklashda xatolik yuz berdi.")
        return

    if not channels:

        await _safe_edit(callback.message, "❌ Bazada faol kanal topilmadi!")
        return

    key = (callback.from_user.id, anime_id)
    state.pending_publish_selections[key] = set()  # har safar yangidan boshlaymiz

    await _safe_edit(
        callback.message,
        "📢 <b>Qaysi kanal(lar)ga e'lon qilmoqchisiz?</b>\n\nKerakli kanallarni belgilang:",
        _build_channel_selection_kb(anime_id, page, channels, set())
    )


# =======================================================
# 2️⃣ KANALNI BELGILASH / OLIB TASHLASH (TOGGLE)
# =======================================================
@router.callback_query(F.data.startswith("pub_toggle:"))
async def toggle_channel_selection_handler(callback: CallbackQuery, session: Any):
    await safe_answer(callback)

    try:
        _, anime_id_str, page_str, channel_pk_str = callback.data.split(":")
        anime_id, page, channel_pk = int(anime_id_str), int(page_str), int(channel_pk_str)
    except (ValueError, IndexError):
        return

    key = (callback.from_user.id, anime_id)
    selected = state.pending_publish_selections.setdefault(key, set())

    if channel_pk in selected:
        selected.discard(channel_pk)
    else:
        selected.add(channel_pk)

    try:
        from services.channel_service import ChannelService
        channel_service = ChannelService(session=session)
        channels = await channel_service.get_active_channels()
    except Exception as e:
        logger.error(f"❌ toggle: kanallarni olishda xato: {e}", exc_info=True)
        return

    try:
        await callback.message.edit_reply_markup(
            reply_markup=_build_channel_selection_kb(anime_id, page, channels, selected)
        )
    except TelegramForbiddenError:
        pass
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            logger.warning(f"Toggle reply_markup yangilashda xato: {e}")
    except Exception as e:
        logger.error(f"❌ Toggle reply_markup kutilmagan xato: {e}", exc_info=True)


# =======================================================
# 3️⃣ BITTA KANALGA YUBORISH (RetryAfter uchun 1 marta qayta urinish bilan)
# =======================================================
async def _do_send(bot: Bot, chat_id: int, poster_id: Optional[str], caption: str, keyboard: InlineKeyboardMarkup) -> None:
    if poster_id:
        try:
            await bot.send_photo(chat_id=chat_id, photo=poster_id, caption=caption, reply_markup=keyboard, parse_mode="HTML")
            return
        except TelegramBadRequest:
            pass
        try:
            await bot.send_video(chat_id=chat_id, video=poster_id, caption=caption, reply_markup=keyboard, parse_mode="HTML")
            return
        except TelegramBadRequest:
            pass
        await bot.send_message(chat_id=chat_id, text=f"⚠️ (Media xatoligi)\n\n{caption}", reply_markup=keyboard, parse_mode="HTML")
    else:
        await bot.send_message(chat_id=chat_id, text=caption, reply_markup=keyboard, parse_mode="HTML")


async def _send_one(
    bot: Bot,
    channel_chat_id: int,
    poster_id: Optional[str],
    caption: str,
    keyboard: InlineKeyboardMarkup,
    semaphore: asyncio.Semaphore,
) -> tuple:
    """Bitta kanalga yuborish — xatolik boshqa kanallarga ta'sir qilmaydi (izolyatsiya)."""
    async with semaphore:
        try:
            await _do_send(bot, channel_chat_id, poster_id, caption, keyboard)
            return (channel_chat_id, True, "")
        except TelegramRetryAfter as e:
            wait_s = e.retry_after + 0.5
            logger.warning(f"⏳ {channel_chat_id}: flood control, {wait_s:.1f}s kutib qayta urinilyapti...")
            await asyncio.sleep(wait_s)
            try:
                await _do_send(bot, channel_chat_id, poster_id, caption, keyboard)
                return (channel_chat_id, True, "")
            except Exception as e2:
                logger.error(f"❌ {channel_chat_id}: qayta urinishda ham xato: {e2}")
                return (channel_chat_id, False, str(e2))
        except TelegramForbiddenError as e:
            logger.error(f"❌ {channel_chat_id}: bot kanalda admin emas / chiqarib yuborilgan: {e}")
            return (channel_chat_id, False, "bot kanalda admin emas")
        except TelegramNetworkError as e:
            logger.error(f"❌ {channel_chat_id}: tarmoq xatosi: {e}")
            return (channel_chat_id, False, "tarmoq xatosi")
        except Exception as e:
            logger.error(f"❌ {channel_chat_id} kanaliga e'lon joylashda xatolik: {e}", exc_info=True)
            return (channel_chat_id, False, str(e))


# =======================================================
# 4️⃣ TANLANGAN KANALLARGA TASDIQLASH VA PARALLEL YUBORISH
# =======================================================
@router.callback_query(F.data.startswith("pub_confirm:"))
async def publish_anime_to_channels_handler(callback: CallbackQuery, session: Any, bot: Bot):
    try:
        _, anime_id_str, page_str = callback.data.split(":")
        anime_id, page = int(anime_id_str), int(page_str)
    except (ValueError, IndexError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov!", show_alert=True)
        return

    key = (callback.from_user.id, anime_id)
    selected_ids = state.pending_publish_selections.get(key, set())

    if not selected_ids:
        await safe_answer(callback, "⚠️ Kamida bitta kanal tanlang!", show_alert=True)
        return

    # ✅ callback shu yerda FAQAT BIR MARTA javob oladi. Bundan keyingi barcha
    # xabar/xatolar _safe_edit orqali beriladi — ikkinchi callback.answer()
    # chaqiruvi "query is too old" xatosini berardi (avvalgi versiyadagi bug).
    await safe_answer(callback, "📢 Kanallarga e'lon qilinmoqda...")

    try:
        from services.channel_service import ChannelService
        channel_service = ChannelService(session=session)
        all_channels = await channel_service.get_active_channels()
    except Exception as e:
        logger.error(f"❌ Kanallarni yuklashda xato: {e}", exc_info=True)
        await _safe_edit(callback.message, "❌ Kanallar ro'yxatini yuklashda xatolik yuz berdi.")
        return

    target_channels = [ch for ch in all_channels if ch["id"] in selected_ids]
    if not target_channels:
        await _safe_edit(callback.message, "❌ Tanlangan kanallar endi mavjud emas.")
        return

    try:
        from services.anime_service import AnimeService
        service = AnimeService(session=session)
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ Anime yuklashda xato: {e}", exc_info=True)
        await _safe_edit(callback.message, "❌ Anime ma'lumotlarini yuklashda xatolik yuz berdi.")
        return

    if not anime:
        await _safe_edit(callback.message, "❌ Anime topilmadi!")
        return

    # 🟢 TUZATILDI: title/description/genres/dubbers/languages endi html.quote()
    # bilan escape qilinadi — aks holda ichida '<', '&', '>' bo'lsa Telegram
    # "can't parse entities" xatosi berib, e'lon UMUMAN yuborilmay qolardi.
    title = html.quote(str(anime.get("title") or "Nomsiz anime"))
    anime_id_val = anime.get("anime_id", anime_id)
    year = html.quote(str(anime.get("year") or "—"))
    description = html.quote(str(anime.get("description") or "Tavsif kiritilmagan."))
    episodes_count = len(anime.get("episodes", []))
    languages = anime.get("languages", [])
    languages_str = html.quote(", ".join(languages)) if languages else "Mavjud emas"

    genres_str = "Mavjud emas"
    try:
        genre_ids = anime.get("genres", [])
        if genre_ids:
            from database.models import Genre
            from sqlalchemy import select
            res = await session.execute(select(Genre).where(Genre.id.in_(genre_ids)))
            genre_names = [g.name for g in res.scalars().all()]
            if genre_names:
                genres_str = html.quote(", ".join(genre_names))
    except Exception as e:
        logger.error(f"❌ Janrlarni yuklashda xato: {e}", exc_info=True)

    dubbers_str = "Mavjud emas"
    try:
        dubber_ids = anime.get("dubbers", [])
        if dubber_ids:
            from database.models import Dubber
            from sqlalchemy import select
            res = await session.execute(select(Dubber).where(Dubber.id.in_(dubber_ids)))
            dubber_names = [d.name for d in res.scalars().all()]
            if dubber_names:
                dubbers_str = html.quote(", ".join(dubber_names))
    except Exception as e:
        logger.error(f"❌ Dubberlarni yuklashda xato: {e}", exc_info=True)

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

    try:
        bot_username = await _get_bot_username(bot)
    except Exception as e:
        logger.error(f"❌ Bot username olishda xato: {e}", exc_info=True)
        bot_username = None

    buttons = []
    if bot_username:
        buttons.append([InlineKeyboardButton(
            text="🎬 Animeni ko'rish",
            url=f"https://t.me/{bot_username}?start=anime_{anime_id_val}",
            style="primary"
        )])
    buttons.append([InlineKeyboardButton(text="🌐 Sayt", url="https://aninov.uz", style="primary")])
    channel_kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    poster_id = anime.get("poster_id")


    semaphore = asyncio.Semaphore(SEND_CONCURRENCY)
    tasks = [
        _send_one(bot, ch["channel_id"], poster_id, channel_caption, channel_kb, semaphore)
        for ch in target_channels
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    title_by_chat_id = {ch["channel_id"]: ch["title"] for ch in target_channels}
    success_count = 0
    failed_names = []

    for res in results:
        if isinstance(res, Exception):
            logger.error(f"❌ Kutilmagan gather xatosi: {res}", exc_info=True)
            continue
        channel_chat_id, ok, _err = res
        if ok:
            success_count += 1
        else:
            failed_names.append(title_by_chat_id.get(channel_chat_id, str(channel_chat_id)))

    state.pending_publish_selections.pop(key, None)  # tozalash

    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⬅️ Anime sahifasiga qaytish",
            callback_data=f"v_anime:{anime_id}:{page}",
            style="danger"
        )]
    ])

    if success_count > 0 and not failed_names:
        final_text = f"🚀 Anime muvaffaqiyatli {success_count} ta kanalga e'lon qilindi!"
    elif success_count > 0 and failed_names:
        failed_str = html.quote(", ".join(failed_names))
        final_text = (
            f"⚠️ Qisman yuborildi: {success_count} ta kanalga muvaffaqiyatli,\n"
            f"{len(failed_names)} tasiga xato berdi.\n\n"
            f"❌ Xato bergan kanallar: {failed_str}\n"
            f"Bot shu kanal(lar)da admin ekanligini tekshiring."
        )
    else:
        final_text = "❌ E'lon qilishda xatolik! Bot kanal(lar)da admin ekanligini tekshiring."

    await _safe_edit(callback.message, final_text, back_kb)