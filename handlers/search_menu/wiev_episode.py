import logging
import asyncio
from typing import Any
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo, BufferedInputFile
from aiogram.exceptions import TelegramBadRequest

from services.anime_service import AnimeService
from services.user_service import UserService
from config import config
CREATOR_ID = config.CREATOR_ID
logger = logging.getLogger("PlayerHandler")
router = Router()

# Bir sahifada nechta qism tugmasi chiqishi (4 tadan 3 qator = 12 ta)
EPISODES_PER_PAGE = 12



@router.callback_query(F.data.startswith("show_episodes_user:") | F.data.startswith("play_ep_page:"))
async def process_anime_streaming_player(callback: CallbackQuery, session: Any):
    await callback.answer()
    
    # 1. Kelgan callback ma'lumotlarini ajratib olamiz
    data_parts = callback.data.split(":")
    
    if data_parts[0] == "show_episodes_user":
        anime_id = int(data_parts[1])
        current_ep_num = 1  # Birinchi marta kirganda 1-qism
        current_page = 1
    else:
        anime_id = int(data_parts[1])
        current_ep_num = int(data_parts[2])
        current_page = int(data_parts[3])

    # 2. Xizmat qatlamlarini chaqiramiz
    anime_service = AnimeService(session=session)
    user_service = UserService(session=session)
    
    episodes = await anime_service.get_anime_episodes_cache(anime_id)
    anime = await anime_service.get_anime(anime_id)
    
    user_id = callback.from_user.id
    user = await user_service.get_user(user_id)
    
    if not episodes or not anime:
        await callback.message.answer("⚠️ Kechirasiz, ushbu animening qismlari yuklanmagan yoki topilmadi.")
        return

    # 🛡️ VIP/Admin/Creator statusini tekshirish
    c_id = getattr(config, "CREATOR_ID", None)
    
    is_vip_or_admin = False
    if user:
        is_vip_or_admin = (
            user.get("is_vip", False) or 
            user.get("status") == "admin" or 
            user_id == c_id
        )
    else:
        is_vip_or_admin = user_id == c_id

    # 3. Joriy ko'rilayotgan epizod
    current_episode = next((e for e in episodes if e["episode"] == current_ep_num), episodes[0])
    current_ep_num = current_episode["episode"]
    
    video_file_id = current_episode.get("file_id") or current_episode.get("video_file_id")

    if not video_file_id:
        await callback.answer("⚠️ Ushbu qismning video fayli topilmadi!", show_alert=True)
        return

    # 4. Caption
    caption = (
        f"╔══════════════════════╗\n"
        f"   🎬 <b>{anime['title']}</b>\n"
        f"╚══════════════════════╝\n\n"
        f"📌 <b>Joriy tomosha:</b>\n"
        f"╔══════════════════════╗\n"
        f"├ 📹 Qism: <b>{current_ep_num}-qism</b>\n"
        f"├ 🌐 Platforma: <a href='https://t.me/Aninovuz_Bot'>Aninovuz</a>\n"
        f"╚══════════════════════╝\n\n"
        f"📢 Kanal @Aninovuz"
    )

    # 5. Pult (Tugmalar UX Premium)
    buttons = []
    start_idx = (current_page - 1) * EPISODES_PER_PAGE
    end_idx = start_idx + EPISODES_PER_PAGE
    page_episodes = episodes[start_idx:end_idx]
    
    # Qismlar tugmalari (4 tadan)
    row = []
    for ep in page_episodes:
        ep_num = ep["episode"]
        if ep_num == current_ep_num:
            # ✨ UX yaxshilandi: [ 1 ] o'rniga ▶️ 1 qo'yildi
            row.append(InlineKeyboardButton(text=f"▶️ {ep_num}", callback_data="noop", style="success"))
        else:
            row.append(InlineKeyboardButton(
                text=str(ep_num), 
                callback_data=f"play_ep_page:{anime_id}:{ep_num}:{current_page}"
            ))
            
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # 🌟 PROFESSIONAL PAGINATION (Har doim o'zgarmas tartibda)
    total_pages = (len(episodes) + EPISODES_PER_PAGE - 1) // EPISODES_PER_PAGE
    
    # Agar sahifalar 1 tadan ko'p bo'lsa, navigatsiyani chiroyli 1 qator qilib joylaymiz
    if total_pages > 1:
        nav_row = []
        
        # ⬅️ Chap tugma (Oldingi sahifa bo'lsa ishlaydi, bo'lmasa ko'rinmas bo'sh tugma)
        if current_page > 1:
            nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"play_ep_page:{anime_id}:{current_ep_num}:{current_page - 1}", style="primary"))
        else:
            nav_row.append(InlineKeyboardButton(text="⏹️", callback_data="noopa", style="primary"))

        # 📄 O'rta tugma (Har doim turadi va nechanchi sahifaligini ko'rsatadi: masalan 1/5)
        nav_row.append(InlineKeyboardButton(text=f"📄 {current_page}/{total_pages}", callback_data="noopg", style="primary"))

        # ➡️ O'ng tugma (Keyingi sahifa bo'lsa ishlaydi)
        if current_page < total_pages:
            nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"play_ep_page:{anime_id}:{current_ep_num}:{current_page + 1}", style="primary"))
        else:
            nav_row.append(InlineKeyboardButton(text="⏹️", callback_data="noopa",style="primary"))

        buttons.append(nav_row)

    # VIP funksiya
    if is_vip_or_admin:
        buttons.append([InlineKeyboardButton(text="📥 Barcha yuklash", callback_data=f"download_all_vip:{anime_id},", style="success"  )])
    
    # Orqaga qaytish
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"back_to_card:{anime_id}", style="danger")])
    
    player_kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    # 6. EDIT YOKI O'CHIRIB YUBORISH
    media_player = InputMediaVideo(
        media=video_file_id,
        caption=caption,
        parse_mode="HTML"
    )

    try:
        await callback.message.edit_media(
            media=media_player,
            reply_markup=player_kb
        )
    except TelegramBadRequest as e:
        error_msg = str(e).lower()
        if "message is not modified" in error_msg:
            pass
        else:
            try:
                await callback.message.delete()
            except Exception:
                pass
                
            await callback.message.answer_video(
                video=video_file_id,
                caption=caption,
                reply_markup=player_kb,
                parse_mode="HTML",
                protect_content=not is_vip_or_admin
            )
    except Exception as e:
        logger.error(f"❌ Pleyer tahrirlanishida kutilmagan xato: {e}")





@router.callback_query(F.data.startswith("download_all_vip:"))
async def process_download_all_vip(callback: CallbackQuery, session: Any):
    try:
        anime_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("🚨 Noto'g'ri so'rov!", show_alert=True)
        return

    # 1. 🗑 Eski pleer xabarini darhol o'chiramiz
    try:
        await callback.message.delete()
    except Exception as e:
        logger.debug(f"Xabarni o'chirishda xato: {e}")

    await callback.answer("📥 Qismlar bazadan qidirilmoqda...")

    # 2. Qismlarni keshdan yoki DB dan yuklaymiz
    try:
        anime_service = AnimeService(session=session)
        episodes = await anime_service.get_anime_episodes_cache(anime_id=anime_id)
    except Exception as e:
        logger.error(f"VIP yuklashda qismlarni olishda xato: {e}")
        await callback.message.answer("❌ Qismlarni yuklashda texnik xatolik yuz berdi.")
        return

    if not episodes:
        await callback.message.answer("📭 Ushbu animening yuklangan qismlari topilmadi.")
        return

    # 3. Qismlarni tartiblaymiz (ustun nomi 'episode_number' yoki 'number' bo'lishi mumkin)
    sorted_episodes = sorted(
        episodes, 
        key=lambda x: x.get("episode_number") or x.get("number") or 0
    )

    # 4. Foydalanuvchiga yuklash boshlanganini xabar qilamiz
    status_msg = await callback.message.answer(
        f"📦 <b>Jami {len(sorted_episodes)} ta qism tayyorlanmoqda, ketma-ket yuboriladi...</b>", 
        parse_mode="HTML"
    )

    sent_count = 0

    # 5. 🚀 KETMA-KET YUBORISH SIKLI
    for ep in sorted_episodes:
        # 🔥 DIQQAT: Har xil nomlanish formatlarini tekshiramiz (Baza yoki Kesh mosligi uchun)
        video_file_id = ep.get("video_file_id") or ep.get("video_id") or ep.get("file_id")
        ep_num = ep.get("episode") or ep.get("episode_number") or ep.get("number") or "?"
        
        # Agar dict ichida video ID umuman topilmasa, log yozamiz va tekshiramiz
        if not video_file_id:
            logger.warning(f"⚠️ Epizod dict ichida video kaliti topilmadi! Bor kalitlar: {list(ep.keys())}")
            continue
            
        try:
            # Telegram API orqali videoni uzatamiz
            await callback.bot.send_video(
                chat_id=callback.from_user.id,
                video=str(video_file_id),
                caption=f"🎬 <b>{ep_num}-Qism</b>\n\n🍿 @AniNovuz loyihasi taqdim etadi.",
                parse_mode="HTML"
            )
            sent_count += 1
            # Telegram FloodWait olmaslik uchun har bir videodan keyin qisqa 0.3 soniya kutish qo'shamiz
            await asyncio.sleep(0.3)
            
        except Exception as send_err:
            logger.error(f"❌ Qism yuborishda xato (Epizod: {ep_num}): {send_err}")
            continue

    # 6. Yakuniy tekshiruv va xabar
    if sent_count > 0:
        await callback.message.answer(
            f"✅ <b>Barcha {sent_count} ta qism muvaffaqiyatli yuborildi! Yoqimli tomosha!</b> 🍿", 
            parse_mode="HTML"
        )
    else:
        await callback.message.answer(
            "⚠️ Qismlar topildi, biroq ularning video fayllari (`file_id`) botga mos kelmadi.\n"
            "Iltimos, admin panel orqali epizodlar to'g'ri yuklanganini tekshiring."
        )

        


@router.callback_query(F.data == "noopa")
async def process_noop_callback(callback: CallbackQuery):
    """
    Faol bo'lmagan tugmalar (masalan, joriy sahifa yoki ⏹️ tugmasi) 
    bosilganda foydalanuvchiga alert chiqarish handleri.
    """
    await callback.answer(
        text="⚠️ Boshqa sahifa afsuski topilmadi",
        show_alert=True
    )

@router.callback_query(F.data == "noopg")
async def process_noop_callback(callback: CallbackQuery):
    """
    Faol bo'lmagan tugmalar (masalan, joriy sahifa yoki ⏹️ tugmasi) 
    bosilganda foydalanuvchiga alert chiqarish handleri.
    """
    await callback.answer(
        text="🛑 Bu tugma sahifa korsatish uchun",
        show_alert=True
    )

