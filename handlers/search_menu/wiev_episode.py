import logging
import asyncio
from typing import Any
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo, BufferedInputFile
from aiogram.exceptions import TelegramBadRequest
from handlers.search_menu.anime_card import send_anime_card
from aiogram.fsm.context import FSMContext
from services.anime_service import AnimeService
from services.user_service import UserService
from aiogram.exceptions import TelegramRetryAfter
from config import config
CREATOR_ID = config.CREATOR_ID
logger = logging.getLogger("PlayerHandler")
router = Router()

# Bir sahifada nechta qism tugmasi chiqishi (4 tadan 3 qator = 12 ta)
EPISODES_PER_PAGE = 12
BATCH_SIZE = 12


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
    # 1. Callback datani xavfsiz parsing qilish
    try:
        data_parts = callback.data.rstrip(",").split(":")
        anime_id = int(data_parts[1])
        batch_page = int(data_parts[2]) if len(data_parts) > 2 else 1
    except (IndexError, ValueError):
        await callback.answer("🚨 Noto'g'ri so'rov formati!", show_alert=True)
        return

    await callback.answer("📥 Qismlar tayyorlanmoqda...")

    # 🔥 TEPADAGI ESKI PLEYERNI YOKI OLDINGI BATCH XABARINI O'CHIRISH
    try:
        await callback.message.delete()
    except Exception as del_err:
        logger.warning(f"⚠️ Eski pleyer xabarini o'chirishda xatolik (allaqachon o'chirilgan bo'lishi mumkin): {del_err}")

    # 2. Epizodlarni kesh / DB dan yuklash
    try:
        anime_service = AnimeService(session=session)
        episodes = await anime_service.get_anime_episodes_cache(anime_id=anime_id)
        anime = await anime_service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"VIP yuklashda qismlarni olishda xato: {e}")
        await callback.bot.send_message(
            chat_id=callback.from_user.id, 
            text="❌ Qismlarni yuklashda texnik xatolik yuz berdi."
        )
        return

    if not episodes:
        await callback.bot.send_message(
            chat_id=callback.from_user.id, 
            text="📭 Ushbu animening yuklangan qismlari topilmadi."
        )
        return

    # 3. Qismlarni tartiblash
    sorted_episodes = sorted(
        episodes, 
        key=lambda x: x.get("episode") or x.get("episode_number") or x.get("number") or 0
    )

    total_episodes = len(sorted_episodes)
    
    # Paginatsiya hisob-kitoblari
    start_idx = (batch_page - 1) * BATCH_SIZE
    end_idx = start_idx + BATCH_SIZE
    current_batch = sorted_episodes[start_idx:end_idx]

    if not current_batch:
        await callback.bot.send_message(
            chat_id=callback.from_user.id, 
            text="⚠️ Ushbu sahifada qismlar topilmadi."
        )
        return

    total_batches = (total_episodes + BATCH_SIZE - 1) // BATCH_SIZE
    anime_title = anime.get("title", "Anime") if anime else "Anime"

    # 4. Status xabarini yuborish (Endi bot.send_message orqali, chunki callback.message o'chirildi)
    status_msg = await callback.bot.send_message(
        chat_id=callback.from_user.id,
        text=(
            f"📦 <b>{anime_title}</b>\n"
            f"🚀 <b>{start_idx + 1}-{min(end_idx, total_episodes)}</b> qismlar yuborilmoqda... (Paket: {batch_page}/{total_batches})"
        ), 
        parse_mode="HTML"
    )

    sent_count = 0

    # 5. 🚀 12 TA QISMNI XAVFSIZ KETMA-KET YUBORISH
    for ep in current_batch:
        video_file_id = ep.get("video_file_id") or ep.get("file_id") or ep.get("video_id")
        ep_num = ep.get("episode") or ep.get("episode_number") or ep.get("number") or "?"
        
        if not video_file_id:
            logger.warning(f"⚠️ Epizod dict ichida video kaliti topilmadi! Epizod: {ep_num}")
            continue
            
        try:
            await callback.bot.send_video(
                chat_id=callback.from_user.id,
                video=str(video_file_id),
                caption=f"🎬 <b>{anime_title} — {ep_num}-Qism</b>\n\n🍿 @AniNovuz loyihasi taqdim etadi.",
                parse_mode="HTML"
            )
            sent_count += 1
            await asyncio.sleep(0.4)
            
        except TelegramRetryAfter as e:
            logger.warning(f"FloodWait: {e.retry_after} soniya kutilmoqda...")
            await asyncio.sleep(e.retry_after + 1)
            try:
                await callback.bot.send_video(
                    chat_id=callback.from_user.id,
                    video=str(video_file_id),
                    caption=f"🎬 <b>{anime_title} — {ep_num}-Qism</b>\n\n🍿 @AniNovuz loyihasi taqdim etadi.",
                    parse_mode="HTML"
                )
                sent_count += 1
            except Exception as retry_err:
                logger.error(f"Retry xatosi: {retry_err}")

        except Exception as send_err:
            logger.error(f"❌ Qism yuborishda xato (Epizod: {ep_num}): {send_err}")
            continue

    # Status xabarini o'chiramiz
    try:
        await status_msg.delete()
    except Exception:
        pass

    # 6. 🔘 UX TUGMALARINI SHAKLLANTIRISH
    nav_buttons = []
    
    # 1. Paginatsiya tugmalari
    batch_nav_row = []
    if batch_page > 1:
        batch_nav_row.append(
            InlineKeyboardButton(
                text="⬅️ Oldingi 12 ta", 
                callback_data=f"download_all_vip:{anime_id}:{batch_page - 1}",
                style="primary"
            )
        )
    if end_idx < total_episodes:
        batch_nav_row.append(
            InlineKeyboardButton(
                text="➡️ Keyingi 12 ta", 
                callback_data=f"download_all_vip:{anime_id}:{batch_page + 1}",
                style="primary"
            )
        )
    if batch_nav_row:
        nav_buttons.append(batch_nav_row)

    # 2. Yangi Pleyer va Anime Kartasini pastda ochish tugmalari
    nav_buttons.append([
        InlineKeyboardButton(
            text="🎬 Pleyerni ochish", 
            callback_data=f"show_episodes_user:{anime_id}",
            style="primary"
        ),
        InlineKeyboardButton(
            text="🎴 Anime kartasi", 
            callback_data=f"back_to_card:{anime_id}:1",
            style="primary"
        )
    ])

    batch_kb = InlineKeyboardMarkup(inline_keyboard=nav_buttons)

    # 7. Yakuniy natija xabari (Eng ostida yangi tugmalar bilan chiqadi)
    if sent_count > 0:
        if end_idx < total_episodes:
            finish_text = (
                f"✅ <b>{sent_count} ta qism muvaffaqiyatli yuborildi!</b>\n\n"
                f"📊 <i>Progress: {min(end_idx, total_episodes)} / {total_episodes} qism</i>\n"
                f"👇 Keyingi qismlarni yuklab olish yoki pleyerga qaytish uchun tugmani bosing:"
            )
        else:
            finish_text = (
                f"🎉 <b>Barcha {total_episodes} ta qism to'liq yuklab berildi!</b>\n\n"
                f"🍿 Yoqimli tomosha!"
            )
            
        await callback.bot.send_message(
            chat_id=callback.from_user.id,
            text=finish_text,
            reply_markup=batch_kb,
            parse_mode="HTML"
        )
    else:
        await callback.bot.send_message(
            chat_id=callback.from_user.id,
            text=(
                "⚠️ Qismlar topildi, biroq ularning video fayllari (`file_id`) botga mos kelmadi.\n"
                "Iltimos, admin panel orqali epizodlar to'g'ri yuklanganini tekshiring."
            )
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




@router.callback_query(F.data.startswith("back_to_card:"))
async def process_back_to_anime_card(callback: CallbackQuery, session: Any, state: FSMContext):
    await callback.answer()

    # 1. Anime ID ni ajratib olamiz
    try:
        anime_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError) as e:
        logger.error(f"❌ Callback ma'lumotini o'qishda xato: {e}")
        return

    # 2. Bazadan anime ma'lumotlarini olamiz
    anime_service = AnimeService(session=session)
    anime = await anime_service.get_anime(anime_id)

    if not anime:
        await callback.answer("❌ Kechirasiz, anime ma'lumotlari topilmadi.", show_alert=True)
        return

    # 3. Xabar video yoki rasm bo'lishidan qat'i nazar har doim edit=True beramiz!
    # Telegram edit_media orqali Video -> Photo transformatsiyasini silliq bajaradi.
    await send_anime_card(
        message=callback.message, 
        anime=anime, 
        session=session,
        state=state,
        edit=True,
        callback=callback
    )