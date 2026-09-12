import asyncio
import logging
from typing import Any, Optional

from aiogram import Router, html, types, F
from aiogram.types import (
    CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto, InputMediaVideo, Message
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from database.models import Genre
from sqlalchemy import select

from services.favorite_service import FavoriteService
from services.rating_service import RatingService
from services.user_service import UserService
from services.anime_service import AnimeService
from services.navigation import NavigationManager
from config import config

CREATOR_ID = config.CREATOR_ID

router = Router()
logger = logging.getLogger(__name__)

# =======================================================
# 🧰 YORDAMCHI FUNKSIYALAR (Telegram xatolaridan himoya)
# =======================================================

async def safe_answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False) -> None:
    """CallbackQuery'ga xavfsiz javob berish (kutilgan xatoliklarni yutish va flood'dan himoya)."""
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "query is too old" not in msg and "query id is invalid" not in msg and "response timeout" not in msg:
            logger.warning(f"safe_answer xatosi (BadRequest): {e}")
    except TelegramForbiddenError:
        pass
    except TelegramRetryAfter as e:
        logger.warning(f"safe_answer Flood control: retry_after={e.retry_after}")
    except Exception as e:
        logger.warning(f"safe_answer kutilmagan xato: {e}")


async def safe_send(message: Message, **kwargs) -> Optional[Message]:
    """Xabarni xavfsiz yuborish (Flood va Network xatolarni ushlash)."""
    try:
        return await message.answer(**kwargs)
    except TelegramRetryAfter as e:
        logger.warning(f"Flood control: {e.retry_after} soniya kutish kerak.")
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError) as e:
        logger.warning(f"Xabar yuborishda kutilgan xato: {e}")
    except Exception as e:
        logger.error(f"Xabar yuborishda kutilmagan xato: {e}", exc_info=True)
    return None


# =======================================================
# 🎬 ASOSIY ANIME KARTASINI YUBORISH FUNKSIYASI
# =======================================================

async def send_anime_card(
    message: Message,
    anime: dict,
    session: Any,
    state: Optional[FSMContext] = None,
    edit: bool = False,                              # Tahrirlash rejimini yoqish/o'chirish
    callback: Optional[types.CallbackQuery] = None    # Edit qilish uchun callback
) -> bool:
    """
    Foydalanuvchiga animeni daxshat ramkali dizaynda va
    kerakli tugmalar bilan ko'rsatuvchi yagona universal funksiya.
    """
    if not anime:
        return False

    anime_id = anime.get("anime_id")

    # 🟢 TUZATILDI: navigatsiya tarixiga FAQAT yangi ko'rsatishda qo'shiladi.
    # Avval edit=True bo'lganda ham qo'shilardi — natijada "Orqaga" tugmasi
    # bir xil kartaga ikki marta qaytarardi.
    if state is not None and anime_id and not edit:
        try:
            nav = NavigationManager(state)
            await nav.push("anime_card", anime_id=anime_id)
        except Exception as nav_err:
            logger.error(f"❌ Navigatsiya tarixiga qo'shishda xato: {nav_err}")

    # 🟢 TUZATILDI: `.get(key, default)` — kalit mavjud-u qiymati None bo'lsa,
    # default ISHLAMAYDI ("Yil: None" ko'rinishi mumkin edi). Endi `or` bilan.
    # Shu bilan birga barcha matnlar html.quote() bilan HTML-xavfsiz qilindi —
    # aks holda nomda/tavsifda '<' yoki '&' bo'lsa, Telegram butun xabarni
    # "can't parse entities" deb rad etardi.
    title = html.quote(str(anime.get("title") or "Nomsiz anime"))
    year = html.quote(str(anime.get("year") or "—"))
    description = html.quote(str(anime.get("description") or "Tavsif kiritilmagan."))
    episodes_count = anime.get("episodes_count", len(anime.get("episodes", [])))
    languages = anime.get("languages", [])
    languages_str = html.quote(", ".join(languages)) if languages else "Mavjud emas"

    # Ko'rilishlar sonini +1 qilish (faqat yangi ko'rsatishda, qayta tahrirlashda emas)
    if anime_id and not edit:
        try:
            view_service = AnimeService(session=session)
            await view_service.track_anime_view(anime_id)
        except Exception as view_err:
            logger.error(f"❌ Ko'rilishlar sonini oshirishda xato: {view_err}")

    actual_user_id = (
        message.from_user.id
        if message.from_user and not message.from_user.is_bot
        else message.chat.id
    )

    # 🟢 TUZATILDI: CREATOR_ID allaqachon modul darajasida muvaffaqiyatli import
    # qilingan (aks holda modul umuman yuklanmas edi) — bare `except:` bilan
    # uni qayta "tiklashga" urinishning hojati yo'q edi.
    c_id = CREATOR_ID

    # 🟢 TUZATILDI: avval user/sevimli/baho so'rovlari try/except'siz edi —
    # bittasi DB xatosi bersa BUTUN karta ko'rinmay qolardi. Endi har biri
    # o'zi alohida xavfsiz va PARALLEL (asyncio.gather) bajariladi.
    async def _get_user():
        try:
            return await UserService(session=session).get_user(actual_user_id)
        except Exception as e:
            logger.error(f"❌ Userni yuklashda xato: {e}")
            return None

    async def _get_favorite():
        if not anime_id:
            return False
        try:
            return await FavoriteService(session=session).check_is_favorite(actual_user_id, anime_id)
        except Exception as e:
            logger.error(f"❌ Sevimlini tekshirishda xato: {e}")
            return False

    async def _get_subscribed():
        if not anime_id:
            return False
        try:
            from services.subscription_service import SubscriptionService
            return await SubscriptionService(session=session).is_subscribed(actual_user_id, anime_id)
        except Exception as e:
            logger.error(f"❌ Obunani tekshirishda xato: {e}")
            return False

    async def _get_rating():
        if not anime_id:
            return None
        try:
            return await RatingService(session=session).get_user_rating(actual_user_id, anime_id)
        except Exception as e:
            logger.error(f"❌ Bahoni yuklashda xato: {e}")
            return None

    async def _get_genres():
        genre_ids = anime.get("genres", [])
        if not genre_ids:
            return "Mavjud emas"
        try:
            res = await session.execute(select(Genre).where(Genre.id.in_(genre_ids)))
            names = [g.name for g in res.scalars().all()]
            return html.quote(", ".join(names)) if names else "Mavjud emas"
        except Exception as e:
            logger.error(f"❌ Janrlarni yuklashda xato: {e}")
            return "Mavjud emas"

    async def _get_dubbers():
        dubber_ids = anime.get("dubbers", [])
        if not dubber_ids:
            return "Mavjud emas"
        try:
            from database.models import Dubber
            res = await session.execute(select(Dubber).where(Dubber.id.in_(dubber_ids)))
            names = [d.name for d in res.scalars().all()]
            return html.quote(", ".join(names)) if names else "Mavjud emas"
        except Exception as e:
            logger.error(f"❌ Dubberlarni yuklashda xato: {e}")
            return "Mavjud emas"

    user_data, is_favorite, is_subscribed, user_rating, genres_str, dubbers_str = await asyncio.gather(
        _get_user(), _get_favorite(), _get_subscribed(), _get_rating(), _get_genres(), _get_dubbers()
    )

    is_vip_or_admin = False
    if user_data:
        is_vip_or_admin = (
            user_data.get("is_vip", False)
            or user_data.get("status") == "admin"
            or (c_id is not None and actual_user_id == c_id)
        )
    else:
        is_vip_or_admin = c_id is not None and actual_user_id == c_id

    fav_text = "❤️ Sevimlida ✓" if is_favorite else "🤍 Sevimli"
    sub_text = "🔔 Obunadasiz ✓" if is_subscribed else "🔔 Obuna"
    # 🟢 TUZATILDI: `if user_rating:` o'rniga `is not None` — nazariy jihatdan
    # 0 ball ham "baholanmagan" bilan aralashib ketmasligi uchun.
    rat_text = f"⭐ Bahoingiz: {user_rating}/10" if user_rating is not None else "⭐ Baholash"

    # Caption dizayni
    caption = (
        f"    🎬 <b>{title}</b>\n\n"
        f"📌 <b>Anime haqida ma'lumot:</b>\n"
        f"╔═══════════════╗\n"
        f"├ 🆔 Kod: <code>#{anime_id}</code>\n"
        f"├ 📅 Yil: <b>{year}</b>\n"
        f"├ ▶️ Qism: <b>{episodes_count}</b> \n"
        f"├ 🌐 Til: <b>{languages_str}</b>\n"
        f"├ 🎙 Dubber: <b>{dubbers_str}</b>\n"
        f"╚═══════════════╝\n"
        f"╔═══════════════╗\n"
        f" 🔮 Janrlar: <i>{genres_str}</i>\n"
        f"╚═══════════════╝\n\n"
        f"📝 <b>Tavsif:</b>\n"
        f"<blockquote expandable>{description}</blockquote>"
    )

    user_anime_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="▶️ Tomosha qilish", callback_data=f"show_episodes_user:{anime_id}", style="primary"),
        ],
        [
            InlineKeyboardButton(text="💎 Elite qismlar", callback_data=f"show_episodes_vip:{anime_id}", style="primary"),
        ],
        [
            InlineKeyboardButton(text=sub_text, callback_data=f"anime_subscription:{anime_id}", style="primary"),
            InlineKeyboardButton(text=fav_text, callback_data=f"anime_favorite:{anime_id}", style="primary"),
        ],
        [
            InlineKeyboardButton(text=rat_text, callback_data=f"anime_rating:{anime_id}", style="primary"),
            InlineKeyboardButton(text="💬 Izoh", callback_data=f"anime_comment:{anime_id}", style="primary"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_global", style="danger")
        ]
    ])

    trailer_id = anime.get("trailer_id")
    poster_id = anime.get("poster_id")
    protect = not is_vip_or_admin

    # ================= EDIT REJIMI (silliq tahrirlash) =================
    if edit and callback and callback.message:
        target = callback.message
        media_obj = None
        if trailer_id:
            media_obj = InputMediaVideo(media=trailer_id, caption=caption, parse_mode="HTML")
        elif poster_id:
            media_obj = InputMediaPhoto(media=poster_id, caption=caption, parse_mode="HTML")

        try:
            if media_obj:
                await target.edit_media(media=media_obj, reply_markup=user_anime_kb)
            else:
                await target.edit_text(text=caption, reply_markup=user_anime_kb, parse_mode="HTML")
            return True
        except TelegramForbiddenError:
            return False
        except Exception as edit_err:
            err_str = str(edit_err).lower()
            if "message is not modified" in err_str:
                return True
            logger.warning(f"⚠️ Edit muvaffaqiyatsiz bo'ldi, yangi xabar jo'natiladi: {edit_err}")
            try:
                await target.delete()
            except Exception:
                pass
            # Pastga tushib, yangi xabar yuborish bilan davom etamiz

    # ================= ESKI MENYULARNI TOZALASH =================
    if state is not None:
        try:
            state_data = await state.get_data()
            stale_menu_id = state_data.get("last_menu_id")
            if stale_menu_id and stale_menu_id != message.message_id:
                try:
                    await message.bot.delete_message(chat_id=message.chat.id, message_id=stale_menu_id)
                except Exception:
                    pass
                await state.update_data(last_menu_id=None)
        except Exception as state_err:
            logger.error(f"❌ last_menu_id tozalashda xato: {state_err}")

    # Silliq o'chirish (eski xabarni tozalash) — edit muvaffaqiyatsiz bo'lib
    # target allaqachon o'chirilgan bo'lsa, bu urinish xavfsiz jimgina o'tadi.
    try:
        await message.delete()
    except Exception:
        pass

    # ================= YANGI XABAR: video -> poster -> matn zanjiri =================
    # 🟢 TUZATILDI: avval trailer_id yaroqsiz bo'lsa (Telegram rad etsa),
    # funksiya darhol False qaytarib, foydalanuvchi HECH NARSA ko'rmasdi.
    # Endi admin panelidagi kabi to'liq zaxira zanjiri qo'llaniladi.
    try:
        if trailer_id:
            try:
                await message.answer_video(
                    video=trailer_id, caption=caption, reply_markup=user_anime_kb,
                    parse_mode="HTML", protect_content=protect
                )
                return True
            except TelegramBadRequest as e:
                logger.warning(f"⚠️ Tizer video yuborilmadi ({e}), boshqa usul bilan urinib ko'ramiz")

        if poster_id:
            try:
                await message.answer_photo(
                    photo=poster_id, caption=caption, reply_markup=user_anime_kb,
                    parse_mode="HTML", protect_content=protect
                )
                return True
            except TelegramBadRequest as e:
                logger.warning(f"⚠️ Poster yuborilmadi ({e}), matn bilan urinib ko'ramiz")

        await message.answer(
            text=caption, reply_markup=user_anime_kb, parse_mode="HTML", protect_content=protect
        )
        return True

    except TelegramRetryAfter as e:
        logger.warning(f"Flood control (Retry After): {e.retry_after}")
    except (TelegramForbiddenError, TelegramNetworkError) as e:
        logger.warning(f"Xabar yuborishda kutilgan xato: {e}")
    except Exception as e:
        logger.error(f"Yangi xabar yuborishda xato: {e}", exc_info=True)

    return False