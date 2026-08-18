import math
import logging
from typing import Any, Optional
from aiogram import Router, F, html
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from services.anime_service import AnimeService

router = Router()
logger = logging.getLogger(__name__)

async def safe_answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False) -> None:
    """Telegramda 'query is too old' kabi xatolarni ushlab qoluvchi funksiya."""
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "query is too old" not in msg and "query id is invalid" not in msg and "response timeout expired" not in msg:
            logger.warning(f"safe_answer xatosi: {e}")
    except TelegramForbiddenError:
        pass
    except Exception as e:
        logger.warning(f"safe_answer kutilmagan xato: {e}")

async def get_episode_list_markup(anime_id: int, episodes: list, page: int = 1, per_page: int = 12) -> InlineKeyboardMarkup:
    """Qismlar ro'yxatini sahifalash va klaviaturani yasash."""
    total_episodes = len(episodes)
    
    # Agar qismlar hali yuklanmagan bo'lsa
    if total_episodes == 0:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⛔️ Qismlar mavjud emas", callback_data="void")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"manage_episodes:{anime_id}")]
        ])

    total_pages = math.ceil(total_episodes / per_page)
    page = max(1, min(page, total_pages))

    # Joriy sahifaga mos qismlarni kesib olish
    start_idx = (page - 1) * per_page
    current_page_episodes = episodes[start_idx : start_idx + per_page]

    inline_keyboard = []
    row = []

    # Qismlarni chiroyli to'r (grid) ko'rinishida 3 tadan qilib joylaymiz
    for ep in current_page_episodes:
        ep_num = ep.get("episode")
        
        # 📌 O'ZGARISH SHU YERDA: Filler holatini tekshiramiz
        is_filler = ep.get("is_filler", False)
        
        # Filler bo'lsa 🌀 stikerini, canon bo'lsa 📹 stikerini qo'yamiz
        icon = "🌀" if is_filler else "📹"
        
        row.append(InlineKeyboardButton(
            text=f"{icon} {ep_num} ▶️", 
            callback_data=f"show_ep:{anime_id}:{ep_num}:{page}"
        ))
        
        if len(row) == 3:  # Har 3 ta tugmadan keyin yangi qatorga o'tadi
            inline_keyboard.append(row)
            row = []
            
    if row:  # Qolib ketgan tugmalar bo'lsa qo'shib qo'yamiz
        inline_keyboard.append(row)

    # Paginatsiya (Navigatsiya) satri
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"view_episodes_page:{anime_id}:{page-1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="⛔️", callback_data="void", style="primary"))

    nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="void", style="primary"))

    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"view_episodes_page:{anime_id}:{page+1}", style="primary"))
    else:
        nav_row.append(InlineKeyboardButton(text="⛔️", callback_data="void", style="primary"))

    inline_keyboard.append(nav_row)

    # Ortga qaytish satri
    inline_keyboard.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"manage_episodes:{anime_id}", style="danger")
    ])

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


@router.callback_query(F.data.startswith("view_episodes_list:") | F.data.startswith("view_episodes_page:"))
async def view_episodes_list_handler(callback: CallbackQuery, session: Any):
    await safe_answer(callback, "Qismlar yuklanmoqda...")
    
    try:
        parts = callback.data.split(":")
        anime_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 1
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov formati!", show_alert=True)
        return

    service = AnimeService(session=session)
    try:
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"Anime bazadan olinishida xato yuz berdi: {e}")
        anime = None
    
    if not anime:
        try:
            await callback.message.answer("❌ Anime topilmadi!")
        except Exception:
            pass
        return

    raw_title = anime.get("title", "Nomsiz anime")
    title = html.quote(str(raw_title))  # HTML injeksiyadan himoya
    episodes = anime.get("episodes", [])

    # 📌 O'ZGARISH SHU YERDA: Caption matniga Eslatma qo'shildi
    caption = (
        f"╔══════════════════╗\n"
        f"  🎬 <b>{title}</b>\n"
        f"╚══════════════════╝\n\n"
        f"📹 Ro‘yxatdan kerakli qismni tanlang.\n"
        f"💡 {html.italic('Tanlangan qism videosi va uni boshqarish tugmalari shu yerning o‘zida ochiladi.')}\n\n"
        f"📌 <b>Eslatma:</b> 🌀 <i>belgisi turgan qismlar filler hisoblanadi.</i>"
    )

    markup = await get_episode_list_markup(anime_id=anime_id, episodes=episodes, page=page)

    try:
        await callback.message.edit_caption(caption=caption, reply_markup=markup, parse_mode="HTML")
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "message is not modified" in msg:
            return  # Hech narsa o'zgarmasa jim turadi
        try:
            await callback.message.edit_text(text=caption, reply_markup=markup, parse_mode="HTML")
        except TelegramBadRequest as err:
            if "message is not modified" not in str(err).lower():
                logger.warning(f"edit_text orqali yangilash amalga oshmadi: {err}")
        except Exception as err:
            logger.error(f"❌ Qismlar ro'yxatini tahrirlashda xato: {err}")
    except Exception as e:
        logger.error(f"Kutilmagan xato: {e}")




@router.callback_query(F.data.startswith("show_ep:"))
async def show_specific_episode_handler(callback: CallbackQuery, session: Any):
    await safe_answer(callback, "Video yuklanmoqda...")
    
    try:
        _, anime_id_str, ep_num_str, back_page_str = callback.data.split(":")
        anime_id = int(anime_id_str)
        ep_num = int(ep_num_str)
        back_page = int(back_page_str)  # Orqaga qaytganda o'sha sahifani eslab qolish uchun
    except (IndexError, ValueError):
        await safe_answer(callback, "❌ Noto'g'ri so'rov formati!", show_alert=True)
        return

    service = AnimeService(session=session)
    try:
        anime = await service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"Anime yuklanmadi: {e}")
        anime = None
    
    if not anime:
        await safe_answer(callback, "❌ Anime topilmadi!", show_alert=True)
        return

    # Kerakli epizod ma'lumotlarini file_id si bilan ajratib olamiz
    episodes = anime.get("episodes", [])
    target_ep = next((ep for ep in episodes if ep.get("episode") == ep_num), None)

    if not target_ep:
        await safe_answer(callback, "❌ Ushbu qism videosi topilmadi!", show_alert=True)
        return

    file_id = target_ep.get("file_id")
    is_filler = target_ep.get("is_filler", False)  # Filler holatini aniqlaymiz
    
    raw_title = anime.get("title", "Nomsiz anime")
    title = html.quote(str(raw_title))  # HTML xatoligini oldini olamiz
    
    # Filler holatiga mos ravishda status matni
    filler_status_text = "🌀 <b>Filler qism</b>" if is_filler else "✅ <b>Canon qism</b>"
    
    caption = (
        f"🎬 <b>{title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📹 Joriy qism: <b>{ep_num}-qism</b> ({filler_status_text})\n\n"
        f"🛠 <b>Admin amallari:</b>\n"
        f"⚠️ {html.italic('Ushbu qismni o‘chirish, almashish yoki filler holatini o‘zgartirish uchun quyidagi tugmalardan foydalaning.')}"
    )

    # Filler tugmasining matni va callback malumoti holatga qarab o'zgaradi
    filler_btn_text = "🌀 Filler" if is_filler else "✅ Canon "
    filler_btn_style = "success" if is_filler else "primary"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑   O‘chirish", callback_data=f"burn_ep:{anime_id}:{ep_num}:{back_page}", style="danger"),
            InlineKeyboardButton(text="🔄  Almashtirish", callback_data=f"swap_ep:{anime_id}:{ep_num}:{back_page}", style="primary")
        ],
        [
            InlineKeyboardButton(text=filler_btn_text, callback_data=f"toggle_filler:{anime_id}:{ep_num}:{back_page}", style=filler_btn_style)
        ],
        [
            # Ro'yxatga qaytishda aynan qaysi sahifadan kelgan bo'lsa, o'shanga qaytadi
            InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"view_episodes_page:{anime_id}:{back_page}", style="danger")
        ]
    ])

    # 🔥 MEDIA EDIT va XAVFSIZLIK FALLBACK
    try:
        new_media = InputMediaVideo(media=file_id, caption=caption, parse_mode="HTML")
        await callback.message.edit_media(media=new_media, reply_markup=kb)
    except TelegramBadRequest as e:
        msg = str(e).lower()
        if "message is not modified" in msg:
            pass # Eski media va xabar turi bir xil bo'lsa, o'zgarishsiz qoldiradi
        elif "there is no media in the message" in msg:
            # Muhim xavfsizlik: Matnli xabarni mediaga 'edit_media' qilib bo'lmaydi. 
            # Shuning uchun uni o'chirib, o'rniga yangi video yuboramiz!
            try:
                await callback.message.delete()
                await callback.message.answer_video(video=file_id, caption=caption, reply_markup=kb, parse_mode="HTML")
            except Exception as err:
                logger.error(f"Xabarni o'chirib yangi video yuborishda xato: {err}")
        else:
            logger.error(f"❌ Media almashtirishda xatolik yuz berdi: {e}")
            await safe_answer(callback, "❌ Videoni yuklashda xatolik! Fayl ID buzilgan bo'lishi mumkin.", show_alert=True)
    except Exception as e:
        logger.error(f"Kutilmagan xato: {e}")