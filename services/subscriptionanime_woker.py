import asyncio
import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramAPIError

logger = logging.getLogger(__name__)

# Global navbat (Admin yangi qism qo'shganda shu yerga tashlanadi)
notification_queue = asyncio.Queue()

def chunk_list(lst, chunk_size):
    """Ro'yxatni berilgan o'lchamda qismlarga bo'lish uchun"""
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

async def send_single_message(bot: Bot, user_id: int, text: str, reply_markup: InlineKeyboardMarkup):
    """Bitta foydalanuvchiga xavfsiz xabar yuborish"""
    try:
        await bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
        return True
    except TelegramForbiddenError:
        # Foydalanuvchi botni bloklagan
        return False
    except TelegramRetryAfter as e:
        # Telegram limitiga tushganda aytilgan vaqtcha uxlash
        await asyncio.sleep(e.retry_after)
        return False
    except TelegramAPIError:
        return False

async def process_anime_subscriptions(bot: Bot, session_maker, get_subscribers_func, deactivate_user_func=None):
    """Orqa fonda uzluksiz ishlaydigan background worker"""
    logger.info("⚙️ Background Anime Worker ishga tushdi va navbatni kutmoqda...")
    
    while True:
        try:
            # 1. Navbatdan vazifani kutib olish (bloklanib turadi, CPU'ni yeb qo'ymaydi)
            task = await notification_queue.get()
            anime_id = task["anime_id"]
            anime_title = task.get("anime_title", f"Anime #{anime_id}")
            episode_num = task["episode_num"]
            is_vip = task["is_vip"]

            # 2. Bazadan obunachilarni olish
            async with session_maker() as session:
                subscribers = await get_subscribers_func(session, anime_id, vip_only=is_vip)

            if not subscribers:
                notification_queue.task_done()
                continue
            
            # 3. Xabar matni va tugmani tayyorlash
            status_text = "🌟 VIP" if is_vip else "🆓  Bepul"
            text = (
                f"<b>💬YANGI XABAR</b> \n\n"
                f"Xurmatli obunachi!\n\n"
                f"🎉 <b>Yangi qism chiqdi!</b>\n\n"
                f"🎬 Anime: <b>{anime_title}</b>\n"
                f"📺 Qism: {episode_num}-qism ({status_text})\n\n"
                f"Ko'rish uchun pastdagi tugmani bosing 👇"
            )

            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🎬 Tomosha qilish", 
                            callback_data=f"view_anime_detals_{anime_id}",
                            style="primary" 
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="📢 Kanalga o'tish",
                            url="https://t.me/Aninovuz",
                            style="primary"
                        ),
                        InlineKeyboardButton(
                            text="💬 Guruhga o'tish",
                            url="https://t.me/aninovuz_chat",
                            style="primary"
                        )
                    ]
                ]
            )

            # 4. 🚀 Parallel va guruhlangan (Chunk) yuborish
            success_count = 0
            for chunk in chunk_list(subscribers, 25): # 25 talik guruhlar
                tasks = [
                    send_single_message(bot, user_id, text, markup) 
                    for user_id in chunk
                ]
                
                # Barchasini bir vaqtda (parallel) yuborish
                results = await asyncio.gather(*tasks, return_exceptions=True)
                success_count += sum(1 for res in results if res is True)
                
                # Telegram limitiga tushmaslik uchun 25 tadan keyin 1 soniya pauza
                await asyncio.sleep(1.0)

            logger.info(f"✅ Xabarnoma yuborildi: Anime={anime_id}, Qism={episode_num}, Yetib bordi={success_count}/{len(subscribers)}")
            
            # Vazifa bajarildi deb belgilash
            notification_queue.task_done()

        except Exception as e:
            logger.error(f"❌ Worker xatolikka uchradi: {e}", exc_info=True)
            await asyncio.sleep(5)