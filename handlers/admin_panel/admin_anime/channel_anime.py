from typing import Any
from aiogram import Router, F, html, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
import logging

from services.orchestrator import state

logger = logging.getLogger("PublishAnime")
router = Router()

# =========================================================================
# 📌 CALLBACK DATA FORMATLARI (o'zgartirilganda barchasini yangilang!)
# publish_episodes_chan:{anime_id}:{page}
# pub_toggle:{anime_id}:{page}:{channel_pk}
# pub_confirm:{anime_id}:{page}
# v_anime:{anime_id}:{page}
# =========================================================================

if not hasattr(state, "pending_publish_selections"):
    state.pending_publish_selections = {}  # {(user_id, anime_id): set(channel_pk_ids)}


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


async def _safe_edit(message, text: str, reply_markup: InlineKeyboardMarkup):
    """
    Xabar matn ko'rinishida bo'lsa edit_text, rasm/video (caption) bo'lsa
    edit_caption, ikkalasi ham ishlamasa delete+answer bilan yangi xabar yuboradi.
    """
    try:
        await message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
        return
    except TelegramBadRequest:
        pass

    try:
        await message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
        return
    except TelegramBadRequest:
        pass

    try:
        await message.delete()
    except Exception:
        pass
    await message.answer(text=text, reply_markup=reply_markup, parse_mode="HTML")


# =========================================================================
# 1️⃣ KANAL TANLASH MENYUSINI OCHISH
# =========================================================================
@router.callback_query(F.data.startswith("publish_episodes_chan:"))
async def show_channel_selection_handler(callback: CallbackQuery, session: Any):
    await callback.answer()
    parts = callback.data.split(":")
    anime_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 1

    from services.channel_service import ChannelService
    channel_service = ChannelService(session=session)
    channels = await channel_service.get_active_channels()

    if not channels:
        await callback.answer("❌ Bazada faol kanal topilmadi!", show_alert=True)
        return

    key = (callback.from_user.id, anime_id)
    state.pending_publish_selections[key] = set()  # har safar yangidan boshlaymiz

    await _safe_edit(
        callback.message,
        "📢 <b>Qaysi kanal(lar)ga e'lon qilmoqchisiz?</b>\n\nKerakli kanallarni belgilang:",
        _build_channel_selection_kb(anime_id, page, channels, set())
    )


# =========================================================================
# 2️⃣ KANALNI BELGILASH / OLIB TASHLASH (TOGGLE)
# =========================================================================
@router.callback_query(F.data.startswith("pub_toggle:"))
async def toggle_channel_selection_handler(callback: CallbackQuery, session: Any):
    await callback.answer()
    _, anime_id_str, page_str, channel_pk_str = callback.data.split(":")
    anime_id, page, channel_pk = int(anime_id_str), int(page_str), int(channel_pk_str)

    key = (callback.from_user.id, anime_id)
    selected = state.pending_publish_selections.setdefault(key, set())

    if channel_pk in selected:
        selected.discard(channel_pk)
    else:
        selected.add(channel_pk)

    from services.channel_service import ChannelService
    channel_service = ChannelService(session=session)
    channels = await channel_service.get_active_channels()

    try:
        await callback.message.edit_reply_markup(
            reply_markup=_build_channel_selection_kb(anime_id, page, channels, selected)
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.error(f"❌ Toggle reply_markup yangilashda xato: {e}")


# =========================================================================
# 3️⃣ TANLANGAN KANALLARGA TASDIQLASH VA YUBORISH
# =========================================================================
@router.callback_query(F.data.startswith("pub_confirm:"))
async def publish_anime_to_channels_handler(callback: CallbackQuery, session: Any, bot: Bot):
    _, anime_id_str, page_str = callback.data.split(":")
    anime_id, page = int(anime_id_str), int(page_str)

    key = (callback.from_user.id, anime_id)
    selected_ids = state.pending_publish_selections.get(key, set())

    if not selected_ids:
        await callback.answer("⚠️ Kamida bitta kanal tanlang!", show_alert=True)
        return

    await callback.answer("📢 Kanallarga e'lon qilinmoqda...", show_alert=False)

    from services.channel_service import ChannelService
    channel_service = ChannelService(session=session)
    all_channels = await channel_service.get_active_channels()
    target_channels = [ch for ch in all_channels if ch["id"] in selected_ids]

    from services.anime_service import AnimeService
    service = AnimeService(session=session)

    try:
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ Anime yuklashda xato: {e}")
        anime = None

    if not anime:
        await callback.answer("❌ Anime topilmadi!", show_alert=True)
        return

    title = anime.get("title", "Nomsiz anime")
    anime_id_val = anime.get("anime_id", anime_id)
    year = anime.get("year", "—")
    description = anime.get("description") or "Tavsif kiritilmagan."
    episodes_count = len(anime.get("episodes", []))
    languages = anime.get("languages", [])
    languages_str = ", ".join(languages) if languages else "Mavjud emas"

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

    bot_properties = await bot.get_me()
    bot_username = bot_properties.username

    channel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎬 Animeni ko'rish",
            url=f"https://t.me/{bot_username}?start=anime_{anime_id_val}",
            style="primary"
        )],
        [
            InlineKeyboardButton(text="🌐 Sayt", url="https://aninov.uz", style="primary")
        ]
    ])

    poster_id = anime.get("poster_id")
    success_count = 0

    for ch in target_channels:
        channel_chat_id = ch["channel_id"]  # 👈 haqiqiy Telegram chat_id, ch["id"] emas!
        try:
            if poster_id:
                try:
                    await bot.send_photo(chat_id=channel_chat_id, photo=poster_id, caption=channel_caption, reply_markup=channel_kb, parse_mode="HTML")
                except TelegramBadRequest:
                    try:
                        await bot.send_video(chat_id=channel_chat_id, video=poster_id, caption=channel_caption, reply_markup=channel_kb, parse_mode="HTML")
                    except TelegramBadRequest:
                        await bot.send_message(chat_id=channel_chat_id, text=f"⚠️ (Media xatoligi)\n\n{channel_caption}", reply_markup=channel_kb, parse_mode="HTML")
            else:
                await bot.send_message(chat_id=channel_chat_id, text=channel_caption, reply_markup=channel_kb, parse_mode="HTML")

            success_count += 1
        except Exception as channel_error:
            logger.error(f"❌ {channel_chat_id} kanaliga e'lon joylashda xatolik: {channel_error}")

    state.pending_publish_selections.pop(key, None)  # tozalash

    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⬅️ Anime sahifasiga qaytish",
            callback_data=f"v_anime:{anime_id}:{page}",
            style="danger"
        )]
    ])

    if success_count > 0:
        await _safe_edit(
            callback.message,
            f"🚀 Anime muvaffaqiyatli {success_count} ta kanalga e'lon qilindi!",
            back_kb
        )
    else:
        await _safe_edit(
            callback.message,
            "❌ E'lon qilishda xatolik! Bot kanalda admin ekanligini tekshiring.",
            back_kb
        )