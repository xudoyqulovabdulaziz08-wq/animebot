import logging
from typing import Any, Optional
from aiogram import Router, html, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from database.models import Genre
from sqlalchemy import select
from aiogram.types import InputMediaPhoto, InputMediaVideo
from services.favorite_service import FavoriteService
from services.rating_service import RatingService
from services.user_service import UserService
from services.anime_service import AnimeService
from services.navigation import NavigationManager
from config import config

CREATOR_ID = config.CREATOR_ID

router = Router()

logger = logging.getLogger()



async def send_anime_card(
    message: Message, 
    anime: dict, 
    session: Any, 
    state: Optional[FSMContext] = None,
    edit: bool = False,               # 🔥 YANGI: Tahrirlash rejimini yoqish/o'chirish
    callback: Optional[types.CallbackQuery] = None # 🔥 YANGI: Edit qilish uchun callback
) -> bool:
    """
    Foydalanuvchiga animeni daxshat ramkali dizaynda va 
    kerakli tugmalar bilan ko'rsatuvchi yagona universal funksiya.
    """
    if not anime:
        return False
        
    anime_id = anime.get("anime_id")
    if state is not None and anime_id:
        nav = NavigationManager(state)
        await nav.push("anime_card", anime_id=anime_id)
    title = anime.get("title", "Nomsiz anime")    
    year = anime.get("year", "—")
    description = anime.get("description") or "Tavsif kiritilmagan."
    episodes_count = len(anime.get("episodes", []))
    languages = anime.get("languages", [])
    languages_str = ", ".join(languages) if languages else "Mavjud emas"

    # 🔥 KO'RILISHLAR SONINI +1 QILISH
    if anime_id and not edit: # Qayta tahrirlanganda ko'rilishni sanamaymiz
        try:
            from services.anime_service import AnimeService
            view_service = AnimeService(session=session)
            await view_service.track_anime_view(anime_id)
        except Exception as view_err:
            logger.error(f"❌ Ko'rilishlar sonini oshirishda xato: {view_err}")

    actual_user_id = message.from_user.id if message.from_user and not message.from_user.is_bot else message.chat.id

    # 🛡️ VIP/Admin Dynamic statusni tekshirish
    user_service = UserService(session=session)
    user_data = await user_service.get_user(actual_user_id)
    
    try:
        from config import config
        c_id = getattr(config, "CREATOR_ID", None)
    except:
        c_id = globals().get("CREATOR_ID", None)

    is_vip_or_admin = False
    if user_data:
        is_vip_or_admin = (
            user_data.get("is_vip", False) or 
            user_data.get("status") == "admin" or 
            actual_user_id == c_id
        )
    else:
        is_vip_or_admin = actual_user_id == c_id

    # Janrlarni yuklash
    genres_str = "Mavjud emas"
    try:
        genre_ids = anime.get("genres", [])
        if genre_ids:
            res = await session.execute(select(Genre).where(Genre.id.in_(genre_ids)))
            genre_names = [g.name for g in res.scalars().all()]
            if genre_names:
                genres_str = ", ".join(genre_names)
    except Exception as genre_err:
        logger.error(f"❌ Janrlarni yuklashda xato: {genre_err}")

    # Dubberlarni yuklash
    dubbers_str = "Mavjud emas"
    try:
        dubber_ids = anime.get("dubbers", [])
        if dubber_ids:
            from database.models import Dubber
            res = await session.execute(select(Dubber).where(Dubber.id.in_(dubber_ids)))
            dubber_names = [d.name for d in res.scalars().all()]
            if dubber_names:
                dubbers_str = ", ".join(dubber_names)
    except Exception as dubber_err:
        logger.error(f"❌ Dubberlarni yuklashda xato: {dubber_err}")

    is_favorite = False
    fav_text = "🤍 Sevimli"
    if anime_id:
        fav_service = FavoriteService(session=session)
        is_favorite = await fav_service.check_is_favorite(actual_user_id, anime_id)
        fav_text = "❤️ Sevimlida ✓" if is_favorite else "🤍 Sevimli"

    sub_text = "🔔 Obuna"
    if anime_id:
        try:
            from services.subscription_service import SubscriptionService
            sub_service = SubscriptionService(session=session)
            is_subscribed = await sub_service.is_subscribed(actual_user_id, anime_id)
            sub_text = "🔔 Obunadasiz ✓" if is_subscribed else "🔔 Obuna"
        except Exception as sub_err:
            logger.error(f"❌ Obunani tekshirishda xato: {sub_err}")

    # Baholash holati va ballini olish
    user_rating = None
    rat_text = "⭐ Baholash"
    if anime_id:
        rat_service = RatingService(session=session)
        # 1-argument: user_id, 2-argument: anime_id
        user_rating = await rat_service.get_user_rating(actual_user_id, anime_id)
        
        if user_rating:
            rat_text = f"⭐ Bahoingiz: {user_rating}/10"
        else:
            rat_text = "⭐ Baholash"
    
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
            InlineKeyboardButton(
                text="▶️ Tomosha qilish", 
                callback_data=f"show_episodes_user:{anime_id}",
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="sub_text", 
                callback_data=f"anime_subscription:{anime_id}",
                style="primary"
            ),
            InlineKeyboardButton(
                text=fav_text, 
                callback_data=f"anime_favorite:{anime_id}",
                style="primary"
            ),
        ],
        [
            InlineKeyboardButton(
                text=rat_text, 
                callback_data=f"anime_rating:{anime_id}",
                style="primary"
            ),
            InlineKeyboardButton(
                text="💬 Izoh", 
                callback_data=f"anime_comment:{anime_id}",
                style="primary"
            ),
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Orqaga", 
                callback_data="back_global",
                style="danger"
            )
        ]
    ])

    # 🔄 AGAR EDIT=TRUE BO'LSA: XABARNI SILLIQ TAHRIRLAYMIZ (O'CHIRMASDAN)
    if edit and callback and callback.message:
        poster_id = anime.get("poster_id")
        
        # Silliq transformatsiya uchun InputMedia ob'ektini tayyorlaymiz
        if poster_id:
            # Media rasm yoki video ekanligini ajratamiz (yoki standart photo deb ketamiz)
            media_obj = InputMediaPhoto(media=poster_id, caption=caption, parse_mode="HTML")
        else:
            media_obj = None

        try:
            if media_obj:
                # 💥 AYNAN SHU METOD VIDEONI RASMGA SILLIQ ALMASHTIRADI:
                await callback.message.edit_media(
                    media=media_obj,
                    reply_markup=user_anime_kb
                )
            else:
                await callback.message.edit_text(
                    text=caption,
                    reply_markup=user_anime_kb,
                    parse_mode="HTML"
                )
            return True
        except Exception as edit_err:
            err_str = str(edit_err).lower()
            if "message is not modified" in err_str:
                return True
            logger.warning(f"⚠️ Edit_media qilishda xatolik: {edit_err}")
            # Edit o'xshamasa, pastdagi standart yangi xabar jo'natish mantig'iga o'tib ketadi

    # 🧹 ESKI MENYULARNI TOZALASH (Faqat yangi karta yuborilganda)
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

    # Silliq o'chirish
    try:
        await message.delete()
    except:
        pass

    # Yangi xabar yuborish (Media turiga qarab)
    poster_id = anime.get("poster_id")
    if poster_id:
        try:
            await message.answer_photo(
                photo=poster_id, 
                caption=caption, 
                reply_markup=user_anime_kb, 
                parse_mode="HTML",
                protect_content=not is_vip_or_admin
            )
            return True
        except Exception:
            try:
                await message.answer_video(
                    video=poster_id, 
                    caption=caption, 
                    reply_markup=user_anime_kb, 
                    parse_mode="HTML",
                    protect_content=not is_vip_or_admin
                )
                return True
            except Exception:
                pass

    await message.answer(
        text=caption, 
        reply_markup=user_anime_kb, 
        parse_mode="HTML",
        protect_content=not is_vip_or_admin
    )
    return True







