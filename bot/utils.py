from datetime import datetime
from random import random
from telegram import Bot, Update
import time
from telegram.ext import ContextTypes
from telegram.error import TelegramError, Forbidden, BadRequest, RetryAfter
from config import logger
from db import db_pool, execute_query, get_db, init_db_pool
from config import MAIN_ADMIN_ID, logger, BOT_TOKEN
from db import execute_query, get_db
from aiomysql import Pool
import asyncio
from states import U_FEEDBACK_MSG
db_pool: Pool = None


# ===================================================================================


async def check_sub(user_id: int, bot):
    not_joined = []
    

    # 1. Kanallarni bazadan olishni try-except ichiga olamiz
    channels = []
    try:
        # Timeout qo'shamizki, baza qotib qolsa bot o'lib qolmasin
        async with asyncio.timeout(5): 
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT username FROM channels")
                    channels = await cur.fetchall()
    except Exception as e:
        logger.error(f"⚠️ Kanal bazasida xato: {e}")
        return [] # Xato bo'lsa tekshirmasdan o'tkazib yuboramiz

    for row in channels:
        # DictCursor yoki oddiy Cursor ekanligiga qarab username ni olamiz
        ch = row['username'] if isinstance(row, dict) else row[0]
        
        try:
            target = str(ch).strip()
            if not target.startswith('@') and not target.startswith('-'):
                target = f"@{target}"
            
            # 2. Har bir kanalni tekshirishga 3 soniya vaqt beramiz
            async with asyncio.timeout(3):
                member = await bot.get_chat_member(target, user_id)
                if member.status in ['left', 'kicked']:
                    not_joined.append(ch)
                    
        except Exception as e:
            # 3. KANAL TOPILMASA YOKI BOT ADMIN BO'LMASA - TASHLAB KETAMIZ
            logger.warning(f"❗ Kanal tashlab ketildi: {ch}. Sabab: {e}")
            continue 
            
    return not_joined


# ===================================================================================


async def is_admin(user_id: int):
    # Asosiy adminni har doim tekshirish
    if user_id == MAIN_ADMIN_ID:
        return True
    
    # Bazadan adminlar ro'yxatidan qidirish
    # (Agar users jadvalida 'status' ustunini 'admin' qilib qo'ygan bo'lsangiz)
    res = await execute_query(
        "SELECT status FROM users WHERE user_id=%s", 
        (user_id,), fetch="one"
    )
    return res and res['status'] in ['admin', 'main_admin']


#====================================================================================


async def background_ads_task(bot, admin_id, users, msg_id, from_chat_id):
    """Fonda reklama yuborish va natijalarni real vaqtda yangilash"""
    sent = 0
    failed = 0
    total = len(users)
    
    # Boshlanish xabari
    progress_msg = await bot.send_message(
        admin_id, 
        f"⏳ <b>Reklama kampaniyasi boshlandi...</b>\nJami: <code>{total}</code> ta foydalanuvchi.",
        parse_mode="HTML"
    )

    for user in users:
        # User kortej yoki lug'at ko'rinishida bo'lishi mumkin (cursorga qarab)
        user_id = user['user_id'] if isinstance(user, dict) else user[0]
        
        try:
            # 28-BAND: Har qanday turdagi xabarni formatini buzmasdan nusxalash
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=from_chat_id,
                message_id=msg_id
            )
            sent += 1
            
        except FloodWait as e:
            # Telegram cheklovi bo'lsa, aytilgan vaqtcha kutamiz
            await asyncio.sleep(e.retry_after)
            # Kutishdan so'ng xabarni qayta yuborishga urinish (ixtiyoriy)
            continue 
            
        except Forbidden:
            # Foydalanuvchi botni bloklagan
            failed += 1
            # 28-BAND: Aktiv bo'lmagan foydalanuvchini bazada belgilash mumkin
            
        except TelegramError:
            failed += 1
        
        # Har 30 ta xabarda (Telegram limitiga yaqin) statusni yangilash
        if (sent + failed) % 30 == 0:
            try:
                # Progress bar hisoblash
                percent = round(((sent + failed) / total) * 100)
                await progress_msg.edit_text(
                    f"⏳ <b>Reklama yuborish jarayoni: {percent}%</b>\n\n"
                    f"📊 Jami: <code>{total}</code>\n"
                    f"✅ Yuborildi: <code>{sent}</code>\n"
                    f"❌ Bloklangan: <code>{failed}</code>",
                    parse_mode="HTML"
                )
            except Exception:
                pass # EditMessage limitiga tushmaslik uchun
        
        # Flood limitdan qochish uchun tanaffus
        await asyncio.sleep(0.04) 

    # 21-BAND: Audit log (Reklama tugaganini qayd etish)
    # Bu yerda db_pool orqali bazaga yozish mantiqini qo'shishingiz mumkin

    # Yakuniy hisobot
    await bot.send_message(
        admin_id, 
        f"🏁 <b>Reklama kampaniyasi yakunlandi!</b>\n\n"
        f"✅ Muvaffaqiyatli: <code>{sent}</code>\n"
        f"❌ Muvaffaqiyatsiz: <code>{failed}</code>\n"
        f"📊 Umumiy samaradorlik: <code>{round((sent/total)*100, 1)}%</code>",
        parse_mode="HTML"
    )


# ===================================================================================

async def feedback_subject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mavzuni eslab qolish va matnli xabarni kutish holatiga o'tish"""
    query = update.callback_query
    # Callback format: subj_taklif
    subject = query.data.split("_")[1]
    
    # Sessiyada mavzuni saqlaymiz
    context.user_data['fb_subject'] = subject
    
    # Mavzularga qarab turli emojilar
    emojis = {"shikoyat": "⚠️", "taklif": "💡", "savol": "❓"}
    current_emoji = emojis.get(subject, "📝")

    await query.answer()
    await query.edit_message_text(
        f"{current_emoji} <b>Tanlangan yo'nalish:</b> {subject.capitalize()}\n\n"
        f"Endi murojaatingiz matnini yozib yuboring. Matn 10 ta belgidan kam bo'lmasligi kerak:",
        parse_mode="HTML"
    )
    return U_FEEDBACK_MSG


#===================================================================================

async def delete_expired_ads(context: ContextTypes.DEFAULT_TYPE):
    """Muddati tugagan reklamalarni avtomatik o'chirish (JobQueue uchun)"""
    now = datetime.datetime.now()
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                # 1. Faol va muddati o'tgan reklamalarni saralash
                await cur.execute(
                    "SELECT * FROM auto_ads WHERE expire_at <= %s AND status = 'active'", 
                    (now,)
                )
                expired_ads = await cur.fetchall()

                if not expired_ads:
                    return

                for ad in expired_ads:
                    try:
                        # 2. Telegram'dan o'chirishga urinish
                        await context.bot.delete_message(
                            chat_id=ad['chat_id'], 
                            message_id=ad['post_id']
                        )
                        new_status = 'deleted'
                    
                    except BadRequest as e:
                        # Agar xabar allaqachon qo'lda o'chirilgan bo'lsa
                        logger.warning(f"Ad already gone: {e}")
                        new_status = 'manually_removed'
                    
                    except TelegramError as e:
                        logger.error(f"Telegram API error: {e}")
                        new_status = 'error'

                    # 3. Bazadagi statusni yangilash
                    await cur.execute(
                        "UPDATE auto_ads SET status = %s, deleted_at = %s WHERE id = %s",
                        (new_status, now, ad['id'])
                    )
                
                # Barcha o'zgarishlarni bitta tranzaksiyada saqlash
                await conn.commit()

    except Exception as e:
        logger.error(f"Cleanup job crash: {e}")

#===================================================================================

async def add_auto_ad_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin reklama yuboradi va u ma'lum vaqtdan so'ng avtomatik o'chadi"""
    ad_msg = update.message
    admin_id = update.effective_user.id
    
    # 1. Muddatni aniqlash (Default: 24 soat yoki admin kiritgan raqam)
    # Masalan: /add_ad 12 (12 soat uchun)
    try:
        if context.args:
            duration_hours = int(context.args[0])
        else:
            duration_hours = 24
    except ValueError:
        await ad_msg.reply_text("❌ Xato! Soatni raqamda kiriting. Masalan: <code>/add_ad 12</code>", parse_mode="HTML")
        return

    expire_time = datetime.datetime.now() + datetime.timedelta(hours=duration_hours)
    target_chat_id = "@sizning_kanalingiz" # Asosiy kanal yoki guruh ID-si

    try:
        # 2. Reklamani nusxalash (copy)
        sent_msg = await ad_msg.copy(chat_id=target_chat_id)

        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 3. Bazaga saqlash
                await cur.execute(
                    "INSERT INTO auto_ads (post_id, chat_id, expire_at) VALUES (%s, %s, %s)",
                    (sent_msg.message_id, str(target_chat_id), expire_time)
                )
                
                # 21-BAND: Audit log (Kim reklama qo'ydi?)
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (admin_id, f"Kanalga vaqtinchalik reklama qo'shdi ({duration_hours} soat)")
                )
                await conn.commit()

        await ad_msg.reply_text(
            f"✅ <b>Reklama muvaffaqiyatli joylandi!</b>\n\n"
            f"📍 <b>Joy:</b> <code>{target_chat_id}</code>\n"
            f"⏳ <b>Muddat:</b> <code>{duration_hours}</code> soat\n"
            f"🗑 <b>O'chish vaqti:</b> <code>{expire_time.strftime('%Y-%m-%d %H:%M')}</code>",
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Auto ad error: {e}")
        await ad_msg.reply_text("🛑 Reklamani joylashda xatolik yuz berdi.")



#===================================================================================


async def auto_check_notifications(context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchilarni VIP tugashi va bonuslar haqida avtomatik ogohlantirish"""
    now = datetime.datetime.now()
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                
                # --- 1. VIP MUDDATI TUGASHINI TEKSHIRISH (Ertaga tugaydiganlar) ---
                tomorrow = (now + datetime.timedelta(days=1)).date()
                await cur.execute("""
                    SELECT user_id, name FROM users 
                    WHERE status = 'vip' 
                    AND DATE(vip_expire_date) = %s
                """, (tomorrow,))
                vip_users = await cur.fetchall()
                
                for user in vip_users:
                    try:
                        user_id = user['user_id'] if isinstance(user, dict) else user[0]
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=(
                                "⚠️ <b>VIP MUDDATI TUGAMOQDA!</b>\n\n"
                                "Ertaga VIP obunangiz muddati yakunlanadi. 💎\n"
                                "Reklamasiz tomosha va eksklyuziv imkoniyatlarni saqlab qolish uchun obunani yangilashingizni tavsiya qilamiz!"
                            ),
                            parse_mode="HTML"
                        )
                    except (Forbidden, TelegramError):
                        continue # Bot bloklangan bo'lsa o'tib ketamiz

                # --- 2. BONUSLARNI ES LATISH (1000 balldan oshganlar) ---
                # Faqat har 10-chi tekshiruvda (kuniga 1 marta bo'lsa, 10 kunda bir marta)
                if random.randint(1, 10) == 5:
                    await cur.execute("SELECT user_id, bonus FROM users WHERE bonus >= 1000")
                    rich_users = await cur.fetchall()
                    
                    for user in rich_users:
                        try:
                            user_id = user['user_id'] if isinstance(user, dict) else user[0]
                            bonus = user['bonus'] if isinstance(user, dict) else user[1]
                            await context.bot.send_message(
                                chat_id=user_id,
                                text=(
                                    f"🎁 <b>BALLARINGIZNI ALMASHTIRING!</b>\n\n"
                                    f"Sizda <b>{bonus}</b> ball to'planibdi. Ulardan foydalanib "
                                    f"VIP statusini sotib olishingiz yoki boshqa imtiyozlarga ega bo'lishingiz mumkin! 🔄"
                                ),
                                parse_mode="HTML"
                            )
                        except:
                            continue

    except Exception as e:
        logger.error(f"Auto notification error: {e}")


# ----------------- CALLBACK HANDLER (MUHIM QISM) -----------------
