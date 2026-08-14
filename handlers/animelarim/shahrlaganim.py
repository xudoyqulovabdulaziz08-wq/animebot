import math
import logging
from typing import Any, Optional, Tuple

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

from services.comment_service import CommentService
from services.anime_service import AnimeService
from handlers.search.anime_card import send_anime_card
from services.navigation import NavigationManager
from config import config

POSTER_ID = config.RASM_ID
router = Router()
logger = logging.getLogger("mening_izohlarim")
EPISODES_PER_PAGE = 12
BATCH_SIZE = 12


async def get_user_comments_markup(
    session: Any, 
    user_id: int, 
    page: int = 1, 
    per_page: int = 5
) -> Tuple[InlineKeyboardMarkup, int]:
    comment_service = CommentService(session=session)

    # 1. Jami izoh qoldirilgan animelar sonini olamiz (DISTINCT anime_id)
    try:
        total_anime = await comment_service.get_user_commented_anime_count(user_id)
    except Exception as e:
        logger.error(f"❌ Izoh qoldirilgan animelar sonini olishda xatolik: {e}")
        total_anime = 0

    # 2. Agar foydalanuvchi hali hech qaysi animega izoh yozmagan bo'lsa
    if total_anime == 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="animelarim_cabinet", style="danger")]
        ])
        return kb, 0

    total_pages = math.ceil(total_anime / per_page)
    page = max(1, min(page, total_pages))

    # 3. Keshdan/DBdan sahifalangan animelarni olamiz
    try:
        current_page_anime = await comment_service.get_user_commented_anime_list(
            user_id=user_id, 
            page=page, 
            per_page=per_page
        )
    except Exception as e:
        logger.error(f"❌ Izoh qoldirilgan animelar ro'yxatini olishda xatolik: {e}")
        current_page_anime = []

    inline_keyboard = []

    # 4. Tugmalarni shakllantiramiz
    for anime in current_page_anime:
        anime_id = anime.get("anime_id")
        title = anime.get("title", "Nomsiz anime")
        year = anime.get("year", "—")

        inline_keyboard.append([
            InlineKeyboardButton(
                text=f"💬 {title} ({year})", 
                callback_data=f"mycomm_cards_anime:{anime_id}:{page}"
            )
        ])

    # 5. Paginatsiya satri
    nav_row = []

    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"mycomm_page:{page-1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="⏹️", callback_data="mycomm_voider", style="primary"))

    # O'rtadagi sahifa tugmasi
    page_callback = f"mycomm_select_page:{total_pages}:{page}" if total_pages > 1 else "mycomm_single_page"
    nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data=page_callback, style="primary"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"mycomm_page:{page+1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="⏹️", callback_data="mycomm_voider", style="primary"))

    inline_keyboard.append(nav_row)

    # 6. Pastki ortga qaytish menyusi
    inline_keyboard.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data="animelarim_cabinet", style="danger")
    ])

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard), total_anime


def get_mycomm_pages_grid_markup(total_pages: int, current_page: int) -> InlineKeyboardMarkup:
    """Sahifalarni tezkor tanlash uchun raqamli tugmalar setkasini (Grid) hosil qiladi."""
    inline_keyboard = []
    row = []

    for p in range(1, total_pages + 1):
        text = f"• {p} •" if p == current_page else f"{p}"

        row.append(InlineKeyboardButton(
            text=text, 
            callback_data=f"mycomm_page:{p}", 
            style="primary" if p != current_page else "success"
        ))

        if len(row) == 4:
            inline_keyboard.append(row)
            row = []

    if row:
        inline_keyboard.append(row)

    inline_keyboard.append([
        InlineKeyboardButton(
            text="⬅️ Bekor qilish", 
            callback_data=f"mycomm_page:{current_page}", 
            style="danger"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


@router.callback_query(F.data == "mycomm_voider")
async def process_noop_callback(callback: CallbackQuery):
    await callback.answer(text="ℹ️ Boshqa sahifa afsuski topilmadi", show_alert=True)


@router.callback_query(F.data == "mycomm_single_page")
async def process_single_page_callback(callback: CallbackQuery):
    await callback.answer(text="ℹ️ Sahifalar soni faqat 1 ta. Boshqa sahifalar mavjud emas!", show_alert=True)


@router.callback_query(F.data.startswith("mycomm_select_page:"))
async def process_select_page_menu(callback: CallbackQuery):
    try:
        _, total_pages, current_page = callback.data.split(":")
        total_pages = int(total_pages)
        current_page = int(current_page)

        grid_markup = get_mycomm_pages_grid_markup(total_pages, current_page)

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
        logger.error(f"Izohlar grid menyusida xatolik: {e}")
        await callback.answer("❌ Xatolik yuz berdi", show_alert=True)


@router.callback_query(F.data == "cabinet_comments")
@router.callback_query(F.data.startswith("mycomm_page:"))
async def my_comments_menu(
    callback: CallbackQuery, 
    session: AsyncSession, 
    state: Optional[FSMContext] = None,
    page_override: Optional[int] = None
):
    user_id = callback.from_user.id

    if page_override is not None:
        page = page_override
    elif callback.data and callback.data.startswith("mycomm_page:"):
        try:
            page = int(callback.data.split(":")[1])
        except ValueError:
            page = 1
    else:
        page = 1

    reply_markup, total_count = await get_user_comments_markup(
        session=session, 
        user_id=user_id, 
        page=page
    )

    if total_count > 0:
        text = (
            f"<b>💬 Mening izohlarim</b>\n\n"
            f"📚 <b>Siz izoh qoldirgan animelar</b>\n"
            f"<blockquote expandable>📌 Jami animelar: <b>{total_count} ta</b></blockquote>\n\n"
            f"👇 Tomosha qilish yoki izohlarni ko'rish uchun kerakli animeni tanlang:"
        )
    else:
        text = (
            f"<b>💬 Mening izohlarim</b>\n\n"
            f"📚 <b>Izohlar ro'yxatingiz bo'sh!</b>\n\n"
            f"<blockquote expandable>Siz hali birorta ham animega izoh qoldirmagansiz.</blockquote>\n\n"
            f"<i>Animelar sahifasidagi 💬 Izohlar tugmasi orqali fikringizni yozishingiz mumkin.</i>"
        )

    rating_poster = POSTER_ID

    try:
        if rating_poster:
            media_obj = InputMediaPhoto(
                media=rating_poster,
                caption=text,
                parse_mode="HTML"
            )
            await callback.message.edit_media(
                media=media_obj,
                reply_markup=reply_markup
            )
        else:
            if callback.message.photo or callback.message.video:
                await callback.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
            else:
                await callback.message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")

    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            try:
                if callback.message.photo or callback.message.video:
                    await callback.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
                else:
                    await callback.message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
            except Exception as ex:
                logger.error(f"Fallback edit xatosi: {ex}")
    except Exception as e:
        logger.error(f"Izohlar menyusini ko'rsatishda kutilmagan xato: {e}")

    await callback.answer()


@router.callback_query(F.data.startswith("mycomm_cards_anime:"))
async def process_comment_anime_card_click(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    data_parts = callback.data.split(":")
    anime_id = int(data_parts[1])
    page_num = int(data_parts[2]) if len(data_parts) > 2 else 1

    nav = NavigationManager(state)
    # Ushbu bo'limdan anime ichiga kirganda "my_comments" tarixiga yozamiz:
    await nav.push("my_comments", page=page_num)

    anime_service = AnimeService(session)
    anime = await anime_service.get_anime(anime_id)

    if anime:
        await send_anime_card(
            message=callback.message,
            anime=anime,
            session=session,
            state=state,
            edit=True,
            callback=callback
        )