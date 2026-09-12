import logging
from typing import Any, Optional
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaVideo
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from services.anime_service import AnimeService
from services.user_service import UserService
from config import config

logger = logging.getLogger("VipPlayerHandler")
router = Router()

EPISODES_PER_PAGE = 12

# (safe_answer yordamchi funksiyasi o'z o'rnida qoladi, uni qayta yozish shart emas agar faylda bor bo'lsa)
# =======================================================
# 🧰 YORDAMCHI FUNKSIYALAR
# =======================================================
async def safe_answer(callback: CallbackQuery, text: Optional[str] = None, show_alert: bool = False) -> None:
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

# =======================================================
# 💎 VIP (ELITE) PLEYER HANDLER
# =======================================================
@router.callback_query(F.data.startswith("show_episodes_vip:") | F.data.startswith("play_vip_ep_page:"))
async def process_vip_anime_streaming_player(callback: CallbackQuery, session: Any):
    # 1. 🛡️ QAT'IY RUXSAT TEKSHIRUVI (Eng birinchi bajariladi)
    user_id = callback.from_user.id
    user_service = UserService(session=session)
    user = await user_service.get_user(user_id)
    
    c_id = getattr(config, "CREATOR_ID", None)
    
    is_vip_or_admin = False
    if user:
        is_vip_or_admin = (
            user.get("is_vip", False) or 
            user.get("status") == "admin" or 
            user_id == c_id
        )
    else:
        is_vip_or_admin = (user_id == c_id)

    # Agar foydalanuvchi oddiy (VIP/Admin emas) bo'lsa, qat'iy rad etamiz!
    if not is_vip_or_admin:
        await safe_answer(
            callback, 
            "💎 Kechirasiz, ushbu Elite qismlar faqat VIP obunachilar uchun ochiq!\n\nVIP xarid qilish uchun adminlarga murojaat qiling.", 
            show_alert=True
        )
        return

    # 2. Callback ma'lumotlarini xavfsiz ajratib olamiz
    try:
        data_parts = callback.data.split(":")
        if data_parts[0] == "show_episodes_vip":
            anime_id = int(data_parts[1])
            current_ep_num = 1  
            current_page = 1
        else:
            anime_id = int(data_parts[1])
            current_ep_num = int(data_parts[2])
            current_page = int(data_parts[3])
    except (IndexError, ValueError) as e:
        logger.error(f"❌ VIP Pleyer callback xatosi: {callback.data} | Xato: {e}")
        await safe_answer(callback, "⚠️ Ma'lumotlarni o'qishda xatolik yuz berdi.", show_alert=True)
        return

    # 3. Xizmat qatlamlarini chaqiramiz
    anime_service = AnimeService(session=session)
    
    # DIQQAT: Bu yerda VIP qismlarni bazadan ajratib oladigan funksiya bo'lishi kerak. 
    # Agar alohida funksiya bo'lmasa, oddiy episodes ichidan filter qilib oling.
    # Masalan: episodes = await anime_service.get_anime_vip_episodes_cache(anime_id)
    episodes = await anime_service.get_anime_vip_episodes_cache(anime_id) 
    anime = await anime_service.get_anime(anime_id)
    
    if not episodes or not anime:
        await safe_answer(callback, "⚠️ Kechirasiz, ushbu anime uchun VIP qismlar topilmadi.", show_alert=True)
        return

    # 4. Joriy ko'rilayotgan epizodni xavfsiz topish
    current_episode = next((e for e in episodes if e["episode"] == current_ep_num), episodes[0])
    current_ep_num = current_episode["episode"]
    video_file_id = current_episode.get("file_id") or current_episode.get("video_file_id")

    if not video_file_id:
        await safe_answer(callback, "⚠️ Ushbu VIP qismning video fayli topilmadi!", show_alert=True)
        return
    else:
        await safe_answer(callback)

    # 5. VIP Caption (Dizaynga moslashtirildi)
    caption = (
        f"╔══════════════════════╗\n"
        f"   💎 <b>{anime['title']} (Elite)</b>\n"
        f"╚══════════════════════╝\n\n"
        f"📌 <b>VIP Tomosha:</b>\n"
        f"╔══════════════════════╗\n"
        f"├ 📹 Qism: <b>{current_ep_num}-qism</b>\n"
        f"├ 🔒 <i>Tarqatish qat'iyan taqiqlanadi!</i>\n"
        f"╚══════════════════════╝\n\n"
        f"📢 Premium @Aninovuz"
    )

    # 6. Pagination va Pult
    total_pages = max(1, (len(episodes) + EPISODES_PER_PAGE - 1) // EPISODES_PER_PAGE)
    current_page = max(1, min(current_page, total_pages))

    buttons = []
    start_idx = (current_page - 1) * EPISODES_PER_PAGE
    end_idx = start_idx + EPISODES_PER_PAGE
    page_episodes = episodes[start_idx:end_idx]
    
    row = []
    for ep in page_episodes:
        ep_num = ep["episode"]
        is_filler = ep.get("is_filler", False)
        
        if ep_num == current_ep_num:
            # Hozir ko'rilayotgan qism
            btn_text = f"▶️ 🌀 {ep_num}" if is_filler else f"▶️ {ep_num}"
            row.append(InlineKeyboardButton(text=btn_text, callback_data="noop", style="success"))
        else:
            # Boshqa VIP qismlar - callback_data VIP ga o'zgartirildi
            btn_text = f"🌀 {ep_num}" if is_filler else str(ep_num)
            cb_data = f"play_vip_ep_page:{anime_id}:{ep_num}:{current_page}"
            
            if is_filler:
                row.append(InlineKeyboardButton(text=btn_text, callback_data=cb_data, style="danger"))
            else:
                row.append(InlineKeyboardButton(text=btn_text, callback_data=cb_data))
                
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # VIP navigatsiya tugmalari
    if total_pages > 1:
        nav_row = []
        if current_page > 1:
            nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"play_vip_ep_page:{anime_id}:{current_ep_num}:{current_page - 1}", style="primary"))
        else:
            nav_row.append(InlineKeyboardButton(text="⏹️", callback_data="noopa", style="primary"))

        nav_row.append(InlineKeyboardButton(text=f"📄 {current_page}/{total_pages}", callback_data="noopg", style="primary"))

        if current_page < total_pages:
            nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"play_vip_ep_page:{anime_id}:{current_ep_num}:{current_page + 1}", style="primary"))
        else:
            nav_row.append(InlineKeyboardButton(text="⏹️", callback_data="noopa", style="primary"))
        buttons.append(nav_row)

    # ❌ YUKLAB OLISH TUGMASI QO'SHILMAYDI! ❌
    
    # Orqaga qaytish tugmasi
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"back_to_card:{anime_id}", style="danger")])
    
    player_kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    # 7. Media yangilash (Xavfsiz yuborish)
    media_player = InputMediaVideo(
        media=video_file_id,
        caption=caption,
        parse_mode="HTML"
    )

    try:
        # Eski xabarni o'zgartirishga harakat qilamiz
        await callback.message.edit_media(
            media=media_player,
            reply_markup=player_kb
        )
    except TelegramBadRequest as e:
        error_msg = str(e).lower()
        if "message is not modified" in error_msg:
            pass
        else:
            # Agar tahrirlash iloji bo'lmasa, xabarni o'chirib yangidan yuboramiz
            try:
                await callback.message.delete()
            except Exception:
                pass
            try:    
                # 🔒 QAT'IY HIMOYA: protect_content=True qilib yuboriladi
                await callback.message.answer_video(
                    video=video_file_id,
                    caption=caption,
                    reply_markup=player_kb,
                    parse_mode="HTML",
                    protect_content=True  # Vidoni saqlash va ulashish taqiqlanadi
                )
            except Exception as inner_e:
                logger.error(f"❌ VIP videoni yangidan yuborishda xato: {inner_e}")
    except Exception as e:
        logger.error(f"❌ VIP Pleyer tahrirlanishida kutilmagan xato: {e}")