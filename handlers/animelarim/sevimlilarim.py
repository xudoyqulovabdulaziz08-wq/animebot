import math
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from services.favorite_service import FavoriteService
from services.anime_service import AnimeService

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
    Sevimlilar ro'yxati bosilganda caption/text va tugmalarni yangilaydi.
    Paginatsiyani ham bir xil handlerda ushlaydi.
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
            f"❤️ <b>Sizning Sevimlilaringiz</b>\n\n"
            f"📌 Jami saqlangan animelar: <b>{total_count} ta</b>\n"
            f"👇 Tomosha qilish uchun kerakli animeni tanlang:"
        )
    else:
        text = (
            f"💔 <b>Sevimlilar ro'yxatingiz bo'sh!</b>\n\n"
            f"Siz hali birorta ham animeni sevimlilarga qo'shmadingiz.\n"
            f"<i>Animelar sahifasidagi ❤️ tugmasi orqali bu yerga qo'shishingiz mumkin.</i>"
        )

    try:
        # Agar rasm/video caption bo'lsa `edit_caption`, aks holda `edit_text` qilamiz
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
    except Exception as e:
        # Xabar o'zgarmagan bo'lsa Telegram error berishini oldini olamiz
        logger.warning(f"Message edit qilishda kichik ogohlantirish: {e}")

    await callback.answer()