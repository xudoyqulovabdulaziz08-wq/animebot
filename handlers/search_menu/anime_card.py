import logging
from typing import Any, Optional
from aiogram import Router, html, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from database.models import Genre
from sqlalchemy import select
from services.favorite_service import FavoriteService
from services.user_service import UserService
from config import config

CREATOR_ID = config.CREATOR_ID

router = Router()

logger = logging.getLogger()



async def send_anime_card(message: Message, anime: dict, session: Any, state: Optional[FSMContext] = None) -> bool:
    """
    Foydalanuvchiga animeni daxshat ramkali dizaynda va 
    kerakli tugmalar bilan ko'rsatuvchi yagona universal funksiya.
    """
    if not anime:
        return False
        
    anime_id = anime.get("anime_id")
    title = anime.get("title", "Nomsiz anime")    
    year = anime.get("year", "—")
    description = anime.get("description") or "Tavsif kiritilmagan."
    episodes_count = len(anime.get("episodes", []))
    languages = anime.get("languages", [])
    languages_str = ", ".join(languages) if languages else "Mavjud emas"

    # 🔥 YANGI: KARTA OCHILGANDA KO'RILIShLAR SONINI +1 QILISh MANTIQLARI
    if anime_id:
        try:
            from services.anime_service import AnimeService
            view_service = AnimeService(session=session)
            # Orqa fonda hisoblagichni oshiramiz va keshni yangilaymiz
            await view_service.track_anime_view(anime_id)
        except Exception as view_err:
            logger.error(f"❌ Ko'rilishlar sonini oshirishda xato yuz berdi: {view_err}")

    # 🔥 CALLBACK VA ODDIY MESSAGE ID'SINI SUG'URTALASH
    actual_user_id = message.from_user.id if message.from_user and not message.from_user.is_bot else message.chat.id

    # 🛡️ VIP/Admin Dynamic statusni tekshirish qatlami
    user_service = UserService(session=session)
    user_data = await user_service.get_user(actual_user_id)
    
    
    # 👑 Global Creator ID tekshiruvini aniq va xavfsiz holatga keltiramiz
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
        # Agar foydalanuvchi bazada hali yo'q bo'lsa ham Creator bo'lsa ruxsat berish
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

    # Siz taqdim etgan UX dizayn qolipi (UMUMAN O'ZGARTIRILMADI)
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
    is_favorite = False
    if anime_id:
        is_favorite = await FavoriteService.check_is_favorite(session, actual_user_id, anime_id)
        
    fav_text = "❤️ Sevimli" if is_favorite else "🤍 Sevimli"
    fav_style = "success" if is_favorite else "primary"
    # Inline tugmalar (style parametrlariga tegilmadi)
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
                text="🔔 Obuna", 
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
                text="⭐ Baholash", 
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
                text="🏠 Bosh menyu", 
                callback_data="back_to_start",
                style="danger"
            )
        ]
    ])

    # 🧹 ESKI "QIDIRISH MENYUSI" XABARINI TOZALASH
    # Agar foydalanuvchi avval search_menu orqali ochgan "ANIME QIDIRISH"
    # rasmli xabari hali chatda tursa (FSM'da last_menu_id sifatida saqlangan),
    # kartochka chiqishidan oldin uni ham o'chirib tashlaymiz — aks holda
    # ikkita xabar bir-birining ustiga to'planib qoladi.
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

    # Media turiga qarab jo'natish mantig'i + 🛡️ protect_content integratsiyasi
    poster_id = anime.get("poster_id")
    if poster_id:
        try:
            await message.answer_photo(
                photo=poster_id, 
                caption=caption, 
                reply_markup=user_anime_kb, 
                parse_mode="HTML",
                protect_content=not is_vip_or_admin  # 🔥 Creator va VIP'larda blokirovka bo'lmaydi!
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

    # Agar rasmsiz/videosiz bo'lsa oddiy text xabarni himoyalash
    await message.answer(
        text=caption, 
        reply_markup=user_anime_kb, 
        parse_mode="HTML",
        protect_content=not is_vip_or_admin
    )
    return True