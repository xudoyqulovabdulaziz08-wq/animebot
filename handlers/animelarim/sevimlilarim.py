import math
import logging
from typing import Any, Optional
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message, InputMediaPhoto, InputMediaVideo
from sqlalchemy.ext.asyncio import AsyncSession
from services.favorite_service import FavoriteService
from services.anime_service import AnimeService
from sqlalchemy import select
from aiogram.fsm.context import FSMContext
from database.models import Genre
from aiogram.exceptions import TelegramBadRequest
from services.user_service import UserService

logger = logging.getLogger("favorite_markup")


logger = logging.getLogger("sevimlilarim")
router = Router()


async def get_user_favorites_markup(
    session, 
    user_id: int, 
    page: int = 1, 
    per_page: int = 10
) -> tuple[InlineKeyboardMarkup, int]:
    fav_service = FavoriteService(session=session)

    # 1. Jami animelar sonini KESH/DB dan olamiz (Cache-First)
    try:
        total_anime = await fav_service.get_user_favorites_count(user_id)
    except Exception as e:
        logger.error(f"❌ Sevimlilar sonini olishda xatolik: {e}")
        total_anime = 0

    # 2. Agar sevimlilar bo'sh bo'lsa
    if total_anime == 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="animelarim_cabinet", style="danger")]
        ])
        return kb, 0

    total_pages = math.ceil(total_anime / per_page)
    page = max(1, min(page, total_pages))

    # 3. 🔥 Keshdan/DBdan 1 ta so'rov bilan joriy sahifadagi animelarni olamiz
    try:
        current_page_anime = await fav_service.get_user_favorite_anime_list(
            user_id=user_id, 
            page=page, 
            per_page=per_page
        )
    except Exception as e:
        logger.error(f"❌ Sevimlilar ro'yxatini olishda xatolik: {e}")
        current_page_anime = []

    inline_keyboard = []

    # 4. Tugmalarni shakllantiramiz
    for anime in current_page_anime:
        anime_id = anime.get("anime_id")
        title = anime.get("title", "Nomsiz anime")
        year = anime.get("year", "—")
        
        inline_keyboard.append([
            InlineKeyboardButton(
                text=f"🎬 {title} ({year})", 
                callback_data=f"cards_anime:{anime_id}:{page}"
            )
        ])

    # 5. Paginatsiya satri
    nav_row = []
    
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"fav_page:{page-1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="⏹️", callback_data="voider", style="primary"))

    # O'rtadagi sahifa tugmasi (Bosilganda tezkor sahifani tanlash setkasiga o'tadi)
    page_callback = f"fav_select_page:{total_pages}:{page}" if total_pages > 1 else "fav_single_page"
    nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data=page_callback, style="primary"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"fav_page:{page+1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="⏹️", callback_data="voider", style="primary"))

    inline_keyboard.append(nav_row)

    # 6. Pastki ortga qaytish menyusi
    inline_keyboard.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data="animelarim_cabinet", style="danger")
    ])

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard), total_anime


def get_pages_grid_markup(total_pages: int, current_page: int) -> InlineKeyboardMarkup:
    """
    Sahifalarni tezkor tanlash uchun raqamli tugmalar setkasini (Grid) hosil qiladi.
    """
    inline_keyboard = []
    row = []
    
    for p in range(1, total_pages + 1):
        # Joriy sahifaga ajratib ko'rsatish uchun belgi qo'shamiz
        text = f"• {p} •" if p == current_page else f"{p}"
        
        row.append(InlineKeyboardButton(
            text=text, 
            callback_data=f"fav_page:{p}", 
            style="primary" if p != current_page else "success"
        ))
        
        # Har 4 ta tugmada yangi qator ochamiz
        if len(row) == 4:
            inline_keyboard.append(row)
            row = []
            
    if row:
        inline_keyboard.append(row)

    # Bekor qilish / Orqaga qaytish tugmasi
    inline_keyboard.append([
        InlineKeyboardButton(
            text="⬅️ Bekor qilish", 
            callback_data=f"fav_page:{current_page}", 
            style="danger"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


@router.callback_query(F.data == "voider")
async def process_noop_callback(callback: CallbackQuery):
    """
    Faol bo'lmagan tugmalar (masalan, joriy sahifa yoki ⏹️ tugmasi) 
    bosilganda foydalanuvchiga alert chiqarish handleri.
    """
    await callback.answer(
        text="⚠️ Boshqa sahifa afsuski topilmadi",
        show_alert=True
    )




@router.callback_query(F.data == "fav_single_page")
async def process_single_page_callback(callback: CallbackQuery):
    """Faqat 1 ta sahifa borligida alert chiqarish."""
    await callback.answer(
        text="ℹ️ Sahifalar soni faqat 1 ta. Boshqa sahifalar mavjud emas!",
        show_alert=True
    )



@router.callback_query(F.data.startswith("fav_select_page:"))
async def process_select_page_menu(callback: CallbackQuery):
    """
    '📄 1/5' bosilganda sahifalar grid menyusini ochish.
    """
    try:
        _, total_pages, current_page = callback.data.split(":")
        total_pages = int(total_pages)
        current_page = int(current_page)

        grid_markup = get_pages_grid_markup(total_pages, current_page)

        text = (
            f"🔢 <b>Tezkor sahifaga o'tish</b>\n\n"
            f"O'tmoqchi bo'lgan sahifa raqamini tanlang (Jami: <b>{total_pages}</b> ta sahifa):"
        )

        if callback.message.photo or callback.message.video:
            await callback.message.edit_caption(caption=text, reply_markup=grid_markup, parse_mode="HTML")
        else:
            await callback.message.edit_text(text=text, reply_markup=grid_markup, parse_mode="HTML")

        await callback.answer()
    except Exception as e:
        logger.error(f"Sahifalar grid menyusida xatolik: {e}")
        await callback.answer("❌ Xatolik yuz berdi", show_alert=True)




@router.callback_query(F.data == "cabinet_favorite")
@router.callback_query(F.data.startswith("fav_page:"))
async def animelarim_menu(callback: CallbackQuery, session: AsyncSession):
    """
    Sevimlilar ro'yxati bosilganda rasmni (FAVORITES_POSTER) joyida edit_media
    orqali yangilab, ostiga tugmalarni chiqaradi.
    """
    user_id = callback.from_user.id
    
    # Paginatsiya sahifasini aniqlash
    page = 1
    if callback.data.startswith("fav_page:"):
        try:
            page = int(callback.data.split(":")[1])
        except ValueError:
            page = 1

    # Markup va umumiy sonini olamiz
    reply_markup, total_count = await get_user_favorites_markup(
        session=session, 
        user_id=user_id, 
        page=page
    )

    # Chiroyli matn shakllantiramiz
    if total_count > 0:
        text = (
            f"❤️ <b>Sizning sevimli animelaringiz</b>\n\n"
            f"<blockquote expandable>📌 Jami saqlangan animelar: <b>{total_count} ta</b></blockquote>\n\n"
            f"👇 Tomosha qilish uchun kerakli animeni tanlang:"
        )
    else:
        text = (
            f"💔 <b>Sevimlilar ro'yxatingiz bo'sh!</b>\n\n"
            f"<blockquote expandable>Siz hali birorta ham animeni sevimlilarga qo'shmadingiz.</blockquote>\n\n"
            f"<i>Animelar sahifasidagi ❤️ tugmasi orqali bu yerga qo'shishingiz mumkin.</i>"
        )

    favorites_poster = "AgACAgIAAxkBAAFQCZRqZCQF0c5psFnoAiOw5BrIOWe2-wACTRZrG9sKKEvA-QJNWCdkVAEAAwIAA20AAz0E"

    try:
        if favorites_poster:
            # Agar Sevimlilar uchun maxsus rasm/poster o'rnatilgan bo'lsa
            media_obj = InputMediaPhoto(
                media=favorites_poster,
                caption=text,
                parse_mode="HTML"
            )
            await callback.message.edit_media(
                media=media_obj,
                reply_markup=reply_markup
            )
        else:
            # Agar maxsus rasm o'rnatilmagan bo'lsa va mavjud xabar allaqachon media bo'lsa:
            if callback.message.photo or callback.message.video:
                await callback.message.edit_caption(
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )

    except TelegramBadRequest as e:
        err_str = str(e).lower()
        if "message is not modified" in err_str:
            pass  # Xabar o'zgarmagan bo'lsa e'tiborsiz qoldiramiz
        else:
            logger.warning(f"Message edit_media qilishda ogohlantirish: {e}")
            
            # Har qanday kutilmagan holatda oddiy edit_caption/edit_text fallback
            try:
                if callback.message.photo or callback.message.video:
                    await callback.message.edit_caption(
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode="HTML"
                    )
                else:
                    await callback.message.edit_text(
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode="HTML"
                    )
            except Exception as ex:
                logger.error(f"Fallback edit xatosi: {ex}")

    except Exception as e:
        logger.error(f"Sevimlilar menyusini ko'rsatishda kutilmagan xato: {e}")

    await callback.answer()





@router.callback_query(F.data.startswith("cards_anime:"))
async def process_favorite_anime_card(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Sevimlilar ro'yxatidan anime tanlanganda maxsus kartochkani ochadi.
    callback.data pattern: cards_anime:{anime_id}:{from_page}
    """
    try:
        parts = callback.data.split(":")
        anime_id = int(parts[1])
        from_page = int(parts[2]) if len(parts) > 2 else 1

        anime_service = AnimeService(session=session)
        anime_data = await anime_service.get_anime(anime_id)

        if not anime_data:
            await callback.answer("❌ Anime topilmadi!", show_alert=True)
            return

        # Maxsus favorite funksiyamizni chaqiramiz:
        await send_favorite_anime_card(
            message=callback.message,
            anime=anime_data,
            session=session,
            from_page=from_page,
            state=state
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Sevimlilar kartasini ochishda xatolik: {e}")
        await callback.answer("❌ Xatolik yuz berdi", show_alert=True)


async def send_favorite_anime_card(
    message: Message, 
    anime: dict, 
    session: Any, 
    from_page: int = 1,
    state: Optional[FSMContext] = None
) -> bool:
    """
    🚀 Sevimlilar ro'yxatidan tanlangan anime uchun maxsus kartochka funksiyasi.
    - O'chirish va qayta yuborish o'rniga silliq EDIT qilinadi.
    - 'Orqaga' tugmasi bosilganda (fav_page:{from_page}) ham bitta xabarda edit bo'ladi.
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

    # 📊 KO'RILISHLAR SONINI +1 QILISH
    if anime_id:
        try:
            from services.anime_service import AnimeService
            view_service = AnimeService(session=session)
            await view_service.track_anime_view(anime_id)
        except Exception as view_err:
            logger.error(f"❌ Sevimlilar kartasida ko'rilishlar sonini oshirishda xato: {view_err}")

    actual_user_id = message.from_user.id if message.from_user and not message.from_user.is_bot else message.chat.id

    # 🛡️ VIP/Admin statusini tekshirish
    user_service = UserService(session=session)
    user_data = await user_service.get_user(actual_user_id)
    
    try:
        from config import config
        c_id = getattr(config, "CREATOR_ID", None)
    except Exception:
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
    if anime_id:
        fav_service = FavoriteService(session=session)
        is_favorite = await fav_service.check_is_favorite(actual_user_id, anime_id)
        fav_text = "❤️ Sevimlida ✓" if is_favorite else "🤍 Sevimli "

    # 🎨 Caption
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
    
    # 🔘 Tugmalar to'plami
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
                text="⬅️ Sevimlilarga qaytish", 
                callback_data=f"fav_page:{from_page}",
                style="danger"
            )
        ]
    ])

    poster_id = anime.get("poster_id")

    # 🔄 SILIK EDIT AMALGA OSHIRISH (O'chirish va answer qilinmaydi)
    try:
        if poster_id:
            # Agar muqovasi bo'lsa, edit_media qilamiz
            media_obj = InputMediaPhoto(
                media=poster_id,
                caption=caption,
                parse_mode="HTML"
            )
            await message.edit_media(
                media=media_obj,
                reply_markup=user_anime_kb
            )
        else:
            # Rasm bo'lmasa shunchaki text edit qilinadi
            await message.edit_text(
                text=caption,
                reply_markup=user_anime_kb,
                parse_mode="HTML"
            )
        return True

    except TelegramBadRequest as e:
        err_str = str(e).lower()
        if "message is not modified" in err_str:
            return True
        
        # Fallback: Agar Telegram edit_media bajarishda turli format xatosi bersa (masalan media tipi Video bo'lsa)
        try:
            if poster_id:
                media_obj = InputMediaVideo(
                    media=poster_id,
                    caption=caption,
                    parse_mode="HTML"
                )
                await message.edit_media(
                    media=media_obj,
                    reply_markup=user_anime_kb
                )
                return True
        except Exception:
            pass

        # Juda kam hollarda (masalan xabar o'chib ketgan bo'lsa) yangi xabar yuboriladi:
        try:
            await message.delete()
        except Exception:
            pass

        if poster_id:
            await message.answer_photo(
                photo=poster_id,
                caption=caption,
                reply_markup=user_anime_kb,
                parse_mode="HTML",
                protect_content=not is_vip_or_admin
            )
        else:
            await message.answer(
                text=caption,
                reply_markup=user_anime_kb,
                parse_mode="HTML",
                protect_content=not is_vip_or_admin
            )
        return True