import logging
import asyncio
from typing import Any, Optional
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaVideo, Message
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from handlers.search.anime_card import send_anime_card
from services.anime_service import AnimeService
from services.user_service import UserService
from config import config

logger = logging.getLogger("PlayerHandler")
router = Router()

EPISODES_PER_PAGE = 12
BATCH_SIZE = 12

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
# 🎬 ASOSIY PLEYER HANDLER
# =======================================================
@router.callback_query(F.data.startswith("show_episodes_user:") | F.data.startswith("play_ep_page:"))
async def process_anime_streaming_player(callback: CallbackQuery, session: Any):
    # 1. Kelgan callback ma'lumotlarini xavfsiz ajratib olamiz
    try:
        data_parts = callback.data.split(":")
        if data_parts[0] == "show_episodes_user":
            anime_id = int(data_parts[1])
            current_ep_num = 1  
            current_page = 1
        else:
            anime_id = int(data_parts[1])
            current_ep_num = int(data_parts[2])
            current_page = int(data_parts[3])
    except (IndexError, ValueError) as e:
        logger.error(f"❌ Pleyer callback ma'lumotlarida xato: {callback.data} | Xato: {e}")
        await safe_answer(callback, "⚠️ Ma'lumotlarni o'qishda xatolik yuz berdi.", show_alert=True)
        return

    # 2. Xizmat qatlamlarini chaqiramiz
    anime_service = AnimeService(session=session)
    user_service = UserService(session=session)
    
    episodes = await anime_service.get_anime_episodes_cache(anime_id)
    anime = await anime_service.get_anime(anime_id)
    
    user_id = callback.from_user.id
    user = await user_service.get_user(user_id)
    
    if not episodes or not anime:
        await safe_answer(callback, "⚠️ Kechirasiz, ushbu animening qismlari yuklanmagan yoki topilmadi.", show_alert=True)
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
        is_vip_or_admin = (user_id == c_id)

    # 3. Joriy ko'rilayotgan epizodni xavfsiz topish
    current_episode = next((e for e in episodes if e["episode"] == current_ep_num), episodes[0])
    current_ep_num = current_episode["episode"]
    video_file_id = current_episode.get("file_id") or current_episode.get("video_file_id")

    if not video_file_id:
        await safe_answer(callback, "⚠️ Ushbu qismning video fayli topilmadi!", show_alert=True)
        return
    else:
        await safe_answer(callback)

    # 4. Caption (Dizaynga tegilmadi)
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

    # 🌟 PROFESSIONAL PAGINATION (Chegaralarni nazorat qilish)
    total_pages = max(1, (len(episodes) + EPISODES_PER_PAGE - 1) // EPISODES_PER_PAGE)
    current_page = max(1, min(current_page, total_pages)) # Sahifa raqamini to'g'irlash himoyasi

    # 5. Pult (Tugmalar UX Premium va Filler Ajratuvchi)
    buttons = []
    start_idx = (current_page - 1) * EPISODES_PER_PAGE
    end_idx = start_idx + EPISODES_PER_PAGE
    page_episodes = episodes[start_idx:end_idx]
    
    row = []
    for ep in page_episodes:
        ep_num = ep["episode"]
        is_filler = ep.get("is_filler", False)  # Filler maqomini tekshirish
        
        if ep_num == current_ep_num:
            # Hozir ko'rilayotgan qism (Yashil bo'lib turadi, agar filler bo'lsa belgi qo'shiladi)
            btn_text = f"▶️ 🌀 {ep_num}" if is_filler else f"▶️ {ep_num}"
            row.append(InlineKeyboardButton(text=btn_text, callback_data="noop", style="success"))
        else:
            # Boshqa qismlar
            btn_text = f"🌀 {ep_num}" if is_filler else str(ep_num)
            cb_data = f"play_ep_page:{anime_id}:{ep_num}:{current_page}"
            
            # Agar filler bo'lsa style danger beramiz, yo'qsa oddiy
            if is_filler:
                row.append(InlineKeyboardButton(text=btn_text, callback_data=cb_data, style="danger"))
            else:
                row.append(InlineKeyboardButton(text=btn_text, callback_data=cb_data))
                
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Navigatsiya tugmalari (O'zgarmas qoldirildi)
    if total_pages > 1:
        nav_row = []
        if current_page > 1:
            nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"play_ep_page:{anime_id}:{current_ep_num}:{current_page - 1}", style="primary"))
        else:
            nav_row.append(InlineKeyboardButton(text="⏹️", callback_data="noopa", style="primary"))

        nav_row.append(InlineKeyboardButton(text=f"📄 {current_page}/{total_pages}", callback_data="noopg", style="primary"))

        if current_page < total_pages:
            nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"play_ep_page:{anime_id}:{current_ep_num}:{current_page + 1}", style="primary"))
        else:
            nav_row.append(InlineKeyboardButton(text="⏹️", callback_data="noopa", style="primary"))
        buttons.append(nav_row)

    # VIP funksiya
    if is_vip_or_admin:
        buttons.append([InlineKeyboardButton(text="📥 Barcha yuklash", callback_data=f"download_all_vip:{anime_id},", style="success")])
    
    # Orqaga qaytish
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"back_to_card:{anime_id}", style="danger")])
    
    player_kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    # 6. EDIT YOKI O'CHIRIB YUBORISH (Xavfsizroq blok)
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
            # Agar foydalanuvchi aynan o'zi turgan qismni qayta bossa xato bermasligi uchun indamaymiz
            pass
        else:
            try:
                await callback.message.delete()
            except Exception:
                pass
            try:    
                await callback.message.answer_video(
                    video=video_file_id,
                    caption=caption,
                    reply_markup=player_kb,
                    parse_mode="HTML",
                    protect_content=not is_vip_or_admin
                )
            except Exception as inner_e:
                logger.error(f"❌ Videoni yangidan yuborishda xato: {inner_e}")
    except Exception as e:
        logger.error(f"❌ Pleyer tahrirlanishida kutilmagan xato: {e}")


#📥 VIP BARCHA QISMLARNI YUKLASH (FILLERSIZ)
# =======================================================
@router.callback_query(F.data.startswith("download_all_vip:"))
async def process_download_all_vip(callback: CallbackQuery, session: Any):
    # 1. Callback datani xavfsiz parsing qilish
    try:
        data_parts = callback.data.rstrip(",").split(":")
        anime_id = int(data_parts[1])
        batch_page = int(data_parts[2]) if len(data_parts) > 2 and data_parts[2].isdigit() else 1
    except (IndexError, ValueError) as e:
        logger.error(f"❌ VIP callback parsing xatosi: {e}")
        await safe_answer(callback, "🚨 Noto'g'ri so'rov formati!", show_alert=True)
        return

    await safe_answer(callback, "📥 Qismlar tayyorlanmoqda...")

    # 旧 Pleyer xabarini xavfsiz o'chirish
    try:
        await callback.message.delete()
    except Exception as del_err:
        logger.warning(f"⚠️ Eski pleyer xabarini o'chirishda xatolik: {del_err}")

    # 2. Epizodlarni DB / Keshdan olish
    try:
        anime_service = AnimeService(session=session)
        episodes = await anime_service.get_anime_episodes_cache(anime_id=anime_id)
        anime = await anime_service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ VIP yuklashda ma'lumotlarni olishda xato: {e}")
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

    # 3. Tartiblash va Fillellarni filtrlab tashlash
    sorted_episodes = sorted(
        episodes, 
        key=lambda x: x.get("episode") or x.get("episode_number") or x.get("number") or 0
    )

    # 🌀 Filler bo'lmagan asosiy qismlarni ajratib olamiz
    main_episodes = [ep for ep in sorted_episodes if not ep.get("is_filler", False)]
    total_fillers_count = len(sorted_episodes) - len(main_episodes)

    if not main_episodes:
        await callback.bot.send_message(
            chat_id=callback.from_user.id, 
            text="🌀 Ushbu animening barcha qismlari filler bo'lganligi sababli yuboriladigan qism topilmadi."
        )
        return

    total_episodes = len(main_episodes)
    total_batches = max(1, (total_episodes + BATCH_SIZE - 1) // BATCH_SIZE)
    batch_page = max(1, min(batch_page, total_batches)) # Sahifadan chiqib ketish himoyasi

    start_idx = (batch_page - 1) * BATCH_SIZE
    end_idx = start_idx + BATCH_SIZE
    current_batch = main_episodes[start_idx:end_idx]

    anime_title = anime.get("title", "Anime") if anime else "Anime"

    # 4. Status xabarini yuborish
    status_msg = await callback.bot.send_message(
        chat_id=callback.from_user.id,
        text=(
            f"📦 <b>{anime_title}</b>\n"
            f"🚀 <b>{start_idx + 1}-{min(end_idx, total_episodes)}</b> qismlar yuborilmoqda... (Paket: {batch_page}/{total_batches})\n"
            f"<i>🌀 Filler (asosiy syujetga aloqasiz) qismlar avtomatik o'tkazib yuboriladi.</i>"
        ), 
        parse_mode="HTML"
    )

    sent_count = 0

    # 5. 🚀 QISMLARNI KETMA-KET YUBORISH
    for ep in current_batch:
        video_file_id = ep.get("video_file_id") or ep.get("file_id") or ep.get("video_id")
        ep_num = ep.get("episode") or ep.get("episode_number") or ep.get("number") or "?"
        
        if not video_file_id:
            logger.warning(f"⚠️ Video fayl ID topilmadi, Epizod: {ep_num}")
            continue

        caption_text = f"🎬 <b>{anime_title} — {ep_num}-Qism</b>\n\n🍿 @AniNovuz loyihasi taqdim etadi."

        try:
            await callback.bot.send_video(
                chat_id=callback.from_user.id,
                video=str(video_file_id),
                caption=caption_text,
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
                    caption=caption_text,
                    parse_mode="HTML"
                )
                sent_count += 1
            except Exception as retry_err:
                logger.error(f"Retry xatosi (Qism: {ep_num}): {retry_err}")

        except Exception as send_err:
            logger.error(f"❌ Qism yuborishda xato (Epizod: {ep_num}): {send_err}")
            continue

    # Status xabarini o'chirish
    try:
        await status_msg.delete()
    except Exception:
        pass

    # 6. 🔘 NAVIGATSIYA TUGMALARI
    nav_buttons = []
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

    # 7. Yakuniy natija xabari (Fillerlar soni bilan)
    filler_status_str = f"\n🌀 <b>O'tkazib yuborilgan filler qismlar:</b> {total_fillers_count} ta" if total_fillers_count > 0 else ""

    if sent_count > 0:
        if end_idx < total_episodes:
            finish_text = (
                f"✅ <b>{sent_count} ta asosiy qism yuborildi!</b>\n"
                f"📊 <i>Progress: {min(end_idx, total_episodes)} / {total_episodes} (Asosiy qismlar)</i>"
                f"{filler_status_str}\n\n"
                f"👇 Keyingi qismlarni yuklab olish yoki pleyerga qaytish uchun tugmani bosing:"
            )
        else:
            finish_text = (
                f"🎉 <b>Barcha {total_episodes} ta asosiy qism to'liq yuklab berildi!</b>"
                f"{filler_status_str}\n\n"
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

# =======================================================
# 🔘 NOOP HANDLERLAR
# =======================================================
@router.callback_query(F.data == "noopa")
async def process_noop_no_more_pages(callback: CallbackQuery):
    await safe_answer(callback, "⚠️ Boshqa sahifa afsuski topilmadi", show_alert=True)

@router.callback_query(F.data == "noopg")
async def process_noop_page_indicator(callback: CallbackQuery):
    await safe_answer(callback, "🛑 Bu tugma sahifani ko'rsatish uchun mo'ljallangan", show_alert=True)

# =======================================================
# 🎴 ANIME KARTASIGA QAYTISH HANDLERI
# =======================================================
@router.callback_query(F.data.startswith("back_to_card:"))
async def process_back_to_anime_card(callback: CallbackQuery, session: Any, state: FSMContext):
    await safe_answer(callback)

    # 1. Anime ID ni ajratib olish
    try:
        data_parts = callback.data.split(":")
        anime_id = int(data_parts[1])
    except (IndexError, ValueError) as e:
        logger.error(f"❌ back_to_card callback parsing xatosi: {e}")
        await safe_answer(callback, "🚨 Xatolik yuz berdi!", show_alert=True)
        return

    # 2. Bazadan anime ma'lumotlarini olish
    try:
        anime_service = AnimeService(session=session)
        anime = await anime_service.get_anime(anime_id)
    except Exception as e:
        logger.error(f"❌ Anime ma'lumotini olishda xato: {e}")
        await safe_answer(callback, "❌ Texnik xatolik yuz berdi.", show_alert=True)
        return

    if not anime:
        await safe_answer(callback, "❌ Kechirasiz, anime ma'lumotlari topilmadi.", show_alert=True)
        return

    # 3. Anime kartasini xavfsiz tahrirlab yuborish
    try:
        await send_anime_card(
            message=callback.message, 
            anime=anime, 
            session=session,
            state=state,
            edit=True,
            callback=callback
        )
    except Exception as e:
        logger.error(f"❌ send_anime_card chaqirishda xatolik: {e}")