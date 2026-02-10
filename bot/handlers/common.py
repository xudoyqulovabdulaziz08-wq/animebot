import datetime
import io
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from db import db_pool, execute_query
from config import MAIN_ADMIN_ID, logger, ADMIN_GROUP_ID
from keyboards import get_main_kb
from states import A_MAIN, U_FEEDBACK_SUBJ
from utils import check_sub, get_user_status, show_specific_anime_by_id, get_pagination_keyboard, get_db, execute_query, get_db_pool, show_anime_details


# ===================================================================================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    user_obj = update.effective_user
    username = (user_obj.username or user_obj.first_name or "User")[:50]
    
    # 1. Deep Link
    ref_id = None
    if context.args:
        arg = context.args[0]
        if arg.startswith("ani_"):
            context.user_data['pending_anime'] = arg.replace("ani_", "")
        elif arg.isdigit():
            ref_id = int(arg)

    # 2. Baza bilan ishlash
    try:
        # DB pool ulanishini olish
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Avval foydalanuvchini tekshiramiz
                await cur.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
                user_exists = await cur.fetchone()
                
                new_user_bonus = False
                if not user_exists:
                    # Yangi foydalanuvchini qo'shish
                    await cur.execute(
                        "INSERT INTO users (user_id, username, joined_at, points) VALUES (%s, %s, %s, %s)",
                        (user_id, username, datetime.datetime.now(), 10)
                    )
                    new_user_bonus = True
                    
                    # Referral mantiqi
                    if ref_id and ref_id != user_id:
                        await cur.execute("UPDATE users SET points = points + 20 WHERE user_id = %s", (ref_id,))
                        try:
                            await context.bot.send_message(
                                chat_id=ref_id, 
                                text=f"🎉 Tabriklaymiz! Do'stingiz (@{username}) qo'shildi va sizga 20 ball berildi."
                            )
                        except: pass
                
                # O'zgarishlarni saqlash
                await conn.commit()
    except Exception as e:
        logger.error(f"DATABASE ERROR (Start): {e}")
        # Xato bo'lsa ham foydalanuvchini to'xtatmaymiz!
        # Faqat foydalanuvchi obuna bo'lganligini qo'lda tekshirishga o'tamiz


    # 3. Obunani tekshirish
    try:
        not_joined = await check_sub(user_id, context.bot)
        if not_joined:
            btn = [[InlineKeyboardButton("Obuna bo'lish ➕", url=f"https://t.me/{c.replace('@','')}") ] for c in not_joined]
            btn.append([InlineKeyboardButton("Tekshirish ✅", callback_data="recheck")])
            
            msg = "👋 Botdan foydalanish uchun kanallarga a'zo bo'ling:"
            if 'pending_anime' in context.user_data:
                msg = "🎬 <b>Siz tanlagan animeni ko'rish uchun</b> avval a'zo bo'ling:"

            return await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(btn), parse_mode="HTML")
    except Exception as e:
        logger.error(f"SUB CHECK ERROR: {e}")

    # 4. Asosiy Menyu
    try:
        status = await get_user_status(user_id)
        welcome_msg = f"✨ Xush kelibsiz, {user_obj.first_name}!\n"
        welcome_msg += "💰 10 ball bonus berildi!" if new_user_bonus else "Xush kelibsiz! 😊"

        await update.message.reply_text(welcome_msg, reply_markup=get_main_kb(status))
    except Exception as e:
        logger.error(f"MENU ERROR: {e}")
    
    return ConversationHandler.END
        

# ===================================================================================       
        

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha jarayonlarni to'xtatadi, ma'lumotlarni tozalaydi va menyuga qaytaradi"""
    user_id = update.effective_user.id
    
    # 1. Foydalanuvchining ushbu sessiyadagi vaqtinchalik ma'lumotlarini o'chirish
    # Bu juda muhim: anime_id yoki reklama targeti kabi ma'lumotlar saqlanib qolmasligi kerak
    context.user_data.clear()

    # 2. Foydalanuvchi statusini aniqlash
    status = await get_user_status(user_id)

    # 3. Javob xabari
    text = "🔙 <b>Jarayon bekor qilindi.</b>\n\nSiz asosiy menyuga qaytdingiz. Davom etish uchun kerakli bo'limni tanlang."
    
    # Agar xabar callback orqali kelsa (tugma bosilsa)
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text, reply_markup=get_main_kb(status), parse_mode="HTML")
    else:
        # Agar foydalanuvchi /cancel komandasini yozsa
        await update.message.reply_text(text, reply_markup=get_main_kb(status), parse_mode="HTML")

    # 4. ConversationHandler'dan butunlay chiqish
    return ConversationHandler.END


# ===================================================================================


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha jarayonlarni to'xtatadi, ma'lumotlarni tozalaydi va menyuga qaytaradi"""
    user_id = update.effective_user.id
    
    # 1. Foydalanuvchining ushbu sessiyadagi vaqtinchalik ma'lumotlarini o'chirish
    # Bu juda muhim: anime_id yoki reklama targeti kabi ma'lumotlar saqlanib qolmasligi kerak
    context.user_data.clear()

    # 2. Foydalanuvchi statusini aniqlash
    status = await get_user_status(user_id)

    # 3. Javob xabari
    text = "🔙 <b>Jarayon bekor qilindi.</b>\n\nSiz asosiy menyuga qaytdingiz. Davom etish uchun kerakli bo'limni tanlang."
    
    # Agar xabar callback orqali kelsa (tugma bosilsa)
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text, reply_markup=get_main_kb(status), parse_mode="HTML")
    else:
        # Agar foydalanuvchi /cancel komandasini yozsa
        await update.message.reply_text(text, reply_markup=get_main_kb(status), parse_mode="HTML")

    # 4. ConversationHandler'dan butunlay chiqish
    return ConversationHandler.END


# ===================================================================================


async def get_user_status(user_id: int):
    """
    Foydalanuvchi statusini asinxron aniqlash.
    28-band: VIP muddatini avtomatik tekshirish va statusni yangilash qo'shildi.
    """
    # 1. Asosiy egasini tekshirish
    if user_id == MAIN_ADMIN_ID: 
        return "main_admin"
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 2. Adminlar jadvalini tekshirish
                # Eslatma: init_db da 'admins' jadvali qolib ketgan bo'lsa, uni yaratishni unutmang
                await cur.execute("SELECT user_id FROM admins WHERE user_id=%s", (user_id,))
                if await cur.fetchone():
                    return "admin"
                
                # 3. Foydalanuvchi ma'lumotlarini olish
                await cur.execute("SELECT status, vip_expire_date FROM users WHERE user_id=%s", (user_id,))
                res = await cur.fetchone()
                
                if not res:
                    return "user"
                
                status = res['status']
                vip_date = res['vip_expire_date']
                
                # 4. 28-BAND: VIP muddati o'tganini tekshirish (Avtomatlashtirish)
                if status == 'vip' and vip_date:
                    if datetime.datetime.now() > vip_date:
                        # Muddat tugagan bo'lsa statusni tushiramiz
                        await cur.execute("UPDATE users SET status='user', vip_expire_date=NULL WHERE user_id=%s", (user_id,))
                        return "user"
                
                return status
                
    except Exception as e:
        logger.error(f"⚠️ Status aniqlashda (aiomysql) xato: {e}")
        return "user"

# ===================================================================================   


async def recheck_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Obunani tekshirish va har bir kanal uchun o'sish statistikasini hisoblash.
    """
    query = update.callback_query
    user_id = query.from_user.id
    
    # 1. Hozirgi holatni tekshiramiz
    not_joined = await check_sub(user_id, context.bot)
    
    if not not_joined:
        # Foydalanuvchi hamma kanalga a'zo bo'ldi.
        # 2. Xotiradan avval a'zo bo'lmagan kanallar ro'yxatini olamiz
        old_not_joined = context.user_data.get('last_not_joined', [])
        
        if old_not_joined:
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # 3. 28-BAND (8-band): Har bir yangi a'zo bo'lingan kanal uchun +1
                    for ch_username in old_not_joined:
                        await cur.execute(
                            "UPDATE channels SET subscribers_added = subscribers_added + 1 WHERE username = %s",
                            (ch_username,)
                        )
            # Hisoblagandan keyin xotirani tozalaymiz
            context.user_data.pop('last_not_joined', None)

        try:
            await query.message.delete()
        except:
            pass
        
        # 4. Kutilayotgan anime bo'lsa ko'rsatish
        if 'pending_anime' in context.user_data:
            ani_id = context.user_data.pop('pending_anime')
            return await show_specific_anime_by_id(query, context, ani_id)
        
        # 5. Aks holda asosiy menyu
        status = await get_user_status(user_id)
        await query.message.reply_text(
            "✅ Rahmat! Obuna tasdiqlandi. Marhamat, botdan foydalanishingiz mumkin.", 
            reply_markup=get_main_kb(status)
        )
    else:
        # Foydalanuvchi hali ham a'zo emas. 
        # Keyingi safar solishtirish uchun hozirgi a'zo bo'lmagan kanallarini saqlab qo'yamiz.
        context.user_data['last_not_joined'] = not_joined
        await query.answer("❌ Hali hamma kanallarga a'zo emassiz!", show_alert=True)


# ===================================================================================

async def show_specific_anime_by_id(update_or_query, context, ani_id):
    """
    ID bo'yicha bazadan animeni topib, tafsilotlarini chiqaradi.
    28-band: Haftalik ko'rishlar sonini avtomatik oshirish qo'shildi.
    """
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Animeni bazadan qidirish
                await cur.execute("SELECT * FROM anime_list WHERE anime_id=%s", (ani_id,))
                anime = await cur.fetchone()
                
                if anime:
                    # 2. 28-BAND (11-band): Ko'rishlar sonini 1 taga oshirish
                    await cur.execute(
                        "UPDATE anime_list SET views_week = views_week + 1 WHERE anime_id=%s", 
                        (ani_id,)
                    )
                    # O'zgarishlarni saqlash shart emas (autocommit=True bo'lgani uchun)
                    
                    # Tafsilotlarni chiqarish funksiyasiga yuboramiz
                    return await show_anime_details(update_or_query, anime, context)
                
                else:
                    # Anime topilmasa xabar berish
                    error_text = "❌ Kechirasiz, bu anime bazadan o'chirilgan yoki topilmadi."
                    if hasattr(update_or_query, 'message') and update_or_query.message:
                        await update_or_query.message.reply_text(error_text)
                    else:
                        await update_or_query.edit_message_text(error_text)
                        
    except Exception as e:
        logger.error(f"⚠️ show_specific_anime_by_id xatosi: {e}")
        # Foydalanuvchiga texnik xato haqida bildirish
        msg = "⚠️ Ma'lumotlarni yuklashda xatolik yuz berdi."
        if hasattr(update_or_query, 'message') and update_or_query.message:
            await update_or_query.message.reply_text(msg)
        else:
            await update_or_query.edit_message_text(msg)


# ===================================================================================


async def export_all_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha animelar ro'yxatini JSON fayl qilib yuborish (Xotirada shakllantirish)"""
    query = update.callback_query
    msg = update.effective_message
    user_id = update.effective_user.id

    if query:
        await query.answer("📊 Fayl tayyorlanmoqda, kuting...")

    try:
        # 1. Asinxron bazadan ma'lumotlarni olish
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                await cur.execute("SELECT * FROM anime_list")
                animes = await cur.fetchall()

        if not animes:
            await msg.reply_text("📭 Bazada eksport qilish uchun ma'lumot topilmadi.")
            return

        # 21-BAND: Audit (Eksport amalini qayd etish)
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO admin_logs (admin_id, action) VALUES (%s, %s)",
                    (user_id, f"Baza eksport qilindi ({len(animes)} ta anime)")
                )

        # 2. JSON ma'lumotlarini matn ko'rinishida tayyorlash
        json_data = json.dumps(animes, indent=4, default=str, ensure_ascii=False)
        
        # 3. Faylni diskka yozmasdan, RAM (BytesIO) orqali yuborish
        # Bu server xotirasini tejaydi va diskdagi qoldiq fayllarni kamaytiradi
        file_stream = io.BytesIO(json_data.encode('utf-8'))
        file_stream.name = f"anime_database_backup.json"

        await msg.reply_document(
            document=file_stream,
            caption=(
                f"📂 <b>BAZA EKSPORTI</b>\n\n"
                f"📊 <b>Jami animelar:</b> <code>{len(animes)}</code> ta\n"
                f"📅 <b>Sana:</b> <code>{context.args[0] if context.args else 'Bugun'}</code>\n"
                f"👤 <b>Eksport qildi:</b> Admin (ID: {user_id})"
            ),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Export error: {e}")
        await msg.reply_text(f"❌ Eksport jarayonida texnik xatolik: <code>{e}</code>", parse_mode="HTML")



# ----------------- CALLBACK HANDLER (MUHIM QISM) -----------------

async def recheck_subscription_logic(update, context, status):
    query = update.callback_query
    user_id = update.effective_user.id
    not_joined = await check_sub(user_id, context.bot)
    
    if not not_joined:
        try:
            await query.message.delete()
        except:
            pass
        
        await context.bot.send_message(
            chat_id=user_id, 
            text="<b>Tabriklaymiz! ✅ Obuna tasdiqlandi.</b>", 
            reply_markup=get_main_kb(status),
            parse_mode="HTML"
        )
    else:
        await query.answer("❌ Hali hamma kanallarga a'zo emassiz!", show_alert=True)
    return None