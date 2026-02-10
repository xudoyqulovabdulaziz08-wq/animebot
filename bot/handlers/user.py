import os
import datetime
from telegram import LabeledPrice, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from db import db_pool, execute_query
from config import logger
from handlers.common import get_user_status, show_user_cabinet, add_vip_logic, get_main_kb
from keyboards import get_admin_kb
from states import U_FEEDBACK_SUBJ, U_FEEDBACK_MSG, A_MAIN, U_CHAT_MESSAGE, A_MAIN, U_CREATE_PROFILE, U_ADD_COMMENT
from utils import check_sub

# ===================================================================================


async def show_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        # aiomysql pool orqali ulanish
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT bonus, status FROM users WHERE user_id=%s", (user_id,))
                res = await cur.fetchone()
        
        # Ma'lumotlarni olish (DictCursor ishlatilgan deb hisoblaymiz)
        val = res['bonus'] if res else 0
        st = res['status'] if res else "user"
        
        # Statusga qarab chiroyli emoji tanlash
        st_emoji = "💎 VIP" if st == "vip" else "👤 Foydalanuvchi"
        if st in ["admin", "main_admin"]:
            st_emoji = "👮 Admin"

        text = (
            "🏦 <b>SHAXSIY HISOB</b>\n\n"
            f"👤 <b>Foydalanuvchi:</b> {update.effective_user.mention_html()}\n"
            f"💰 <b>To'plangan ballar:</b> <code>{val}</code>\n"
            f"⭐ <b>Maqomingiz:</b> {st_emoji}\n\n"
            "<i>💡 Ballar yordamida VIP statusini sotib olishingiz yoki maxsus imkoniyatlardan foydalanishingiz mumkin.</i>"
        )

        # Agar foydalanuvchi xabar yuborgan bo'lsa (command), aks holda callback bo'lsa
        if update.message:
            await update.message.reply_text(text, parse_mode="HTML")
        elif update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Bonus ko'rsatishda xato: {e}")
        error_msg = "⚠️ Ma'lumotlarni yuklashda xatolik yuz berdi."
        if update.message:
            await update.message.reply_text(error_msg)
        elif update.callback_query:
            await update.callback_query.answer(error_msg, show_alert=True)

        
# ===================================================================================


async def vip_pass_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchiga VIP PASS haqida batafsil ma'lumot beradi"""
    
    text = (
        "💎 <b>VIP PASS — CHEKSIZ IMKONIYATLAR!</b>\n\n"
        "Obuna bo'lish orqali siz quyidagi afzalliklarga ega bo'lasiz:\n\n"
        "🚫 <b>Reklamasiz tomosha:</b> Bot va kanallardagi ortiqcha reklamalarsiz kontentdan bahra oling.\n"
        "⚡️ <b>Eksklyuzivlik:</b> Yangi anime qismlarini barchadan oldin tomosha qiling.\n"
        "👥 <b>Yopiq hamjamiyat:</b> Maxsus VIP guruh va muhokamalarda qatnashing.\n"
        "🌟 <b>Yuqori sifat:</b> Videolarni eng yaxshi sifatda yuklab olish imkoniyati.\n\n"
        "💳 <b>VIP PASS sotib olish yoki savollar bo'lsa:</b>\n"
        "👉 @Khudoyqulov_pg — <i>Admin bilan bog'lanish</i>"
    )

    keyboard = [
        [InlineKeyboardButton("✅ Adminga yozish", url="https://t.me/Khudoyqulov_pg")],
        [InlineKeyboardButton("🔙 Bosh menyu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Callback bo'lsa xabarni tahrirlaymiz, aks holda yangi xabar yuboramiz
    if update.callback_query:
        # Eski xabarni tahrirlash (foydalanuvchi chatida joy tejash uchun)
        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    else:
        # /vip komandasi uchun yangi xabar
        await update.message.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )


# ===================================================================================

async def toggle_health_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sog'liq rejimini yoqish yoki o'chirish (Asinxron)"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Atomar yangilash: 1 - 0 = 1 yoki 1 - 1 = 0
                # Bu usul SELECT so'rovini tejaydi va bazaga yuklamani kamaytiradi
                await cur.execute(
                    "UPDATE users SET health_mode = 1 - health_mode WHERE user_id = %s", 
                    (user_id,)
                )
                await conn.commit()

        # 2. Foydalanuvchiga bildirishnoma (Toast) yuborish
        await query.answer("✅ Sozlama muvaffaqiyatli yangilandi!")
        
        # 3. Kabinetni qayta yangilab ko'rsatish
        # Bu foydalanuvchiga o'zgarishni darhol ko'rish imkonini beradi
        return await show_user_cabinet(update, context)

    except Exception as e:
        logger.error(f"Health toggle error: {e}")
        await query.answer("🛑 Sozlamani o'zgartirishda xatolik yuz berdi.", show_alert=True)


# ===================================================================================

async def show_user_cabinet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi shaxsiy kabinetini ko'rsatish"""
    user_id = update.effective_user.id
    query = update.callback_query
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                # 1. Foydalanuvchi asosiy ma'lumotlari
                await cur.execute("""
                    SELECT points, status, health_mode, joined_at 
                    FROM users WHERE user_id = %s
                """, (user_id,))
                user = await cur.fetchone()
                
                if not user:
                    await (query.answer("❌ Profil topilmadi", show_alert=True) if query else update.message.reply_text("❌ Profil topilmadi."))
                    return

                # 2. Tarixiy ma'lumotlarni hisoblash
                await cur.execute("SELECT COUNT(*) as total FROM history WHERE user_id = %s", (user_id,))
                hist_res = await cur.fetchone()
                history_count = hist_res['total']

        # 3. Vizual formatlash
        status_icon = "💎 <b>VIP</b>" if user['status'] == 'vip' else "👤 <b>Oddiy foydalanuvchi</b>"
        health_status = "✅ <b>Yoqilgan</b>" if user['health_mode'] == 1 else "❌ <b>O'chirilgan</b>"
        
        text = (
            f"<b>🏠 SHAXSIY KABINET</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🆔 <b>Sizning ID:</b> <code>{user_id}</code>\n"
            f"🌟 <b>Status:</b> {status_icon}\n"
            f"💰 <b>Ballaringiz:</b> <code>{user['points']}</code> ball\n"
            f"🎬 <b>Ko'rilgan animelar:</b> <b>{history_count}</b> ta\n"
            f"🌙 <b>Sog'liq rejimi:</b> {health_status}\n"
            f"📅 <b>Ro'yxatdan o'tgan:</b> <code>{user['joined_at'].strftime('%d.%m.%Y')}</code>\n\n"
            f"────────────────────\n"
            f"💡 <i>Sog'liq rejimi tunda botdan ko'p foydalansangiz, dam olishni eslatib turish uchun kerak.</i>"
        )

        # 4. Klaviatura
        kb = [
            [InlineKeyboardButton("🔄 Sog'liq rejimini o'zgartirish", callback_data="toggle_health")],
            [InlineKeyboardButton("🎁 Ballarni almashtirish", callback_data="redeem_menu")],
            [InlineKeyboardButton("🔙 Asosiy menyu", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(kb)

        # 5. Xabarni yuborish yoki tahrirlash
        if query:
            await query.answer()
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Cabinet error: {e}")
        error_msg = "🛑 Kabinetni yuklashda xatolik yuz berdi."
        if query: await query.answer(error_msg, show_alert=True)
        else: await update.message.reply_text(error_msg)


# ===================================================================================

async def feedback_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Murojaatni qabul qilish, bazaga yozish va adminga tugma bilan yuborish"""
    user = update.effective_user
    text = update.message.text.strip()
    subject = context.user_data.get('fb_subject', 'Umumiy')
    admin_chat_id = os.getenv("ADMIN_ID") # Admin yoki Maxsus Gruppa ID si

    # 1. Validatsiya: Juda qisqa xabarlarni rad etamiz
    if len(text) < 10:
        await update.message.reply_text(
            "❌ <b>Xabar juda qisqa!</b>\n"
            "Murojaatingiz tushunarli bo'lishi uchun kamida 10 ta belgi yozing.",
            parse_mode="HTML"
        )
        return U_FEEDBACK_MSG

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 2. Bazaga saqlash
                await cur.execute(
                    "INSERT INTO feedback (user_id, subject, message, created_at) VALUES (%s, %s, %s, %s)",
                    (user.id, subject, text, datetime.datetime.now())
                )
                await conn.commit()

        # 3. Admin uchun chiroyli formatlangan xabar
        admin_text = (
            f"📩 <b>YANGI MUROJAAT</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Kimdan:</b> {user.mention_html()}\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
            f"📌 <b>Mavzu:</b> #{subject.upper()}\n"
            f"📝 <b>Xabar:</b> <code>{text}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <i>Vaqti: {datetime.datetime.now().strftime('%H:%M | %d.%m')}</i>"
        )
        
        # 4. Adminga javob berish tugmasini qo'shish
        # Bu tugma admin bosganida foydalanuvchi ID sini avtomatik reply sifatida oladi
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✍️ Javob berish", callback_data=f"reply_to_{user.id}")]
        ])

        await context.bot.send_message(
            chat_id=admin_chat_id, 
            text=admin_text, 
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        # 5. Foydalanuvchiga tasdiqlash
        await update.message.reply_text(
            "✅ <b>Xabaringiz muvaffaqiyatli yuborildi!</b>\n\n"
            "Adminlarimiz tez orada siz bilan bog'lanishadi yoki "
            "bot orqali javob yuborishadi. Rahmat!",
            parse_mode="HTML"
        )
        
        # Sessiyani tozalash
        context.user_data.pop('fb_subject', None)
        return A_MAIN

    except Exception as e:
        logger.error(f"Feedback send error: {e}")
        await update.message.reply_text("⚠️ Xatolik yuz berdi. Keyinroq urinib ko'ring.")
        return ConversationHandler.END
    

# ===================================================================================

async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Murojaat turini tanlash (Conversation boshlanishi)"""
    # 7-BAND: Obunani tekshirish (faqat a'zolar murojaat qila olishi uchun)
    user_id = update.effective_user.id
    
    keyboard = [
        [
            InlineKeyboardButton("⚠️ Shikoyat", callback_data="subj_shikoyat"),
            InlineKeyboardButton("💡 Taklif", callback_data="subj_taklif")
        ],
        [InlineKeyboardButton("❓ Savol", callback_data="subj_savol")],
        [InlineKeyboardButton("🔙 Bekor qilish", callback_data="cancel_feedback")]
    ]
    
    await update.message.reply_text(
        "<b>Murojaat turini tanlang:</b>\n\n"
        "Adminlarimiz sizning fikringizni diqqat bilan o'rganib chiqishadi. "
        "Iltimos, xabaringizni bitta xabarda batafsil yozing.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    return U_FEEDBACK_SUBJ


# ===================================================================================

async def send_donation_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchiga Telegram Stars orqali to'lov hisobini yuborish"""
    query = update.callback_query
    user_id = query.from_user.id
    
    # Callback'dan miqdorni olamiz (masalan: don_5000 -> 5000)
    try:
        amount_uzs = int(query.data.split("_")[1])
    except (IndexError, ValueError):
        await query.answer("❌ Miqdorni aniqlashda xatolik!")
        return

    # Telegram Stars (XTR) kursini belgilash 
    # Eslatma: 1 Star taxminan 250-300 so'm atrofida (Telegram belgilagan kurs bo'yicha)
    star_count = amount_uzs // 300 
    
    # Agar hisob-kitob 1 dan kam bo'lsa, kamida 1 Star qilamiz
    star_count = max(star_count, 1)

    await query.answer() # Tugma yuklanishini to'xtatish

    try:
        # Invoys yuborish
        await context.bot.send_invoice(
            chat_id=user_id,
            title="💎 Botni qo'llab-quvvatlash",
            description=(
                f"Siz tanlagan paket: {amount_uzs} so'm.\n"
                f"Bu taxminan {star_count} Telegram Stars bo'ladi.\n\n"
                "Rahmat! Sizning yordamingiz biz uchun juda muhim."
            ),
            payload=f"donate_{amount_uzs}_{user_id}", # To'lovni tekshirish uchun ma'lumot
            provider_token="", # Stars uchun har doim bo'sh qoladi
            currency="XTR",
            prices=[LabeledPrice(label="Donat (XTR)", amount=star_count)],
            photo_url="https://telegram.org/img/t_logo.png", # Ixtiyoriy rasm
            need_name=False,
            need_phone_number=False,
            need_email=False,
            is_flexible=False
        )
    except Exception as e:
        logger.error(f"Invoice send error: {e}")
        await query.message.reply_text("🛑 To'lov tizimini ishga tushirishda xatolik. Keyinroq urinib ko'ring.")



# ===================================================================================


async def process_donation_reward(user_id: int, amount: int, context: ContextTypes.DEFAULT_TYPE):
    """Donat miqdoriga qarab sovg'alarni asinxron va xavfsiz taqdim etish"""
    
    msg = "🎉 <b>Rahmat! Sizning donatingiz muvaffaqiyatli qabul qilindi.</b>\n\n🎁 <b>Sizning sovg'alaringiz:</b>\n"
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Tranzaksiya ichida har bir amalni bajarish
                if amount == 5000:
                    await cur.execute("UPDATE users SET bonus = bonus + 500 WHERE user_id = %s", (user_id,))
                    msg += "✅ 500 bonus ball hisobingizga qo'shildi!"
                
                elif amount == 20000:
                    # VIP muddatini 1 oyga uzaytirish (asinxron logic)
                    await add_vip_logic(user_id, 1) 
                    await cur.execute("UPDATE users SET bonus = bonus + 1000 WHERE user_id = %s", (user_id,))
                    msg += "💎 1 oylik VIP maqomi faollashdi!\n✅ 1000 bonus ball qo'shildi!"
                    
                elif amount >= 100000:
                    # Lifetime VIP va Maxsus 'Homiy' statusi
                    await cur.execute(
                        "UPDATE users SET status = 'homiy', bonus = bonus + 10000 WHERE user_id = %s", 
                        (user_id,)
                    )
                    msg += "👑 Sizga <b>'Homiy'</b> maqomi berildi!\n💎 Cheksiz VIP imkoniyati yaratildi!\n✅ 10 000 bonus ball qo'shildi!"

                # 2. To'lov tarixini yozish (Audit)
                await cur.execute(
                    "INSERT INTO donation_logs (user_id, amount, date) VALUES (%s, %s, %s)",
                    (user_id, amount, datetime.datetime.now())
                )
                
                # 3. Hamma amallar muvaffaqiyatli bo'lsa, bazani saqlash
                await conn.commit()

        # Foydalanuvchini tabriklash
        await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="HTML")
        
        # 4. Adminni xabardor qilish
        await context.bot.send_message(
            chat_id=os.getenv("ADMIN_ID"),
            text=f"💰 <b>Yangi Donat!</b>\n👤 Foydalanuvchi: <code>{user_id}</code>\n💵 Miqdor: <code>{amount}</code> so'm",
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Donation reward error: {e}")
        # Xato bo'lsa, xabar yuborish (bazada commit bo'lmagani uchun ballar qo'shilmaydi)
        await context.bot.send_message(
            chat_id=user_id, 
            text="⚠️ Sovg'alarni taqdim etishda xatolik yuz berdi. Iltimos, adminga murojaat qiling."
        )


# ===================================================================================


async def process_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ballarni xizmatlarga haqiqiy ayirboshlash jarayoni"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data.split("_")
    
    # Ma'lumotlarni olish: redeem_vip_1 -> type='vip', value=1
    item_type = data[1]
    value = int(data[2])
    
    # Narxlar jadvali (Buni global o'zgaruvchi qilish ham mumkin)
    prices = {
        'ad_1': 250, 'ad_3': 500,
        'vip_1': 1000, 'vip_3': 2500
    }
    key = f"{item_type}_{value}"
    cost = prices.get(key, 999999)

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                # 1. Joriy ballarni tekshirish (SELECT)
                await cur.execute("SELECT bonus, name FROM users WHERE user_id = %s", (user_id,))
                user = await cur.fetchone()

                if not user or user['bonus'] < cost:
                    needed = cost - (user['bonus'] if user else 0)
                    await query.answer(f"❌ Ballar yetarli emas! Yana {needed} ball to'plashingiz kerak.", show_alert=True)
                    return

                # --- TRANZAKSIYA BOSHLANDI ---
                # 2. Ballarni ayirish
                await cur.execute("UPDATE users SET bonus = bonus - %s WHERE user_id = %s", (cost, user_id))
                
                if item_type == 'vip':
                    # VIP muddatini hisoblash va yangilash
                    # Avvalgi darslarda yozgan add_vip_logic funksiyamizni chaqiramiz
                    new_expire = await add_vip_logic(user_id, value) 
                    
                    msg_text = (
                        f"🎉 <b>Tabriklaymiz!</b>\n\n"
                        f"💎 <code>{value}</code> oylik VIP maqomi faollashtirildi.\n"
                        f"📅 Tugash muddati: <b>{new_expire.strftime('%d.%m.%Y')}</b>\n\n"
                        f"<i>Imkoniyatlardan bahramand bo'ling!</i>"
                    )
                
                elif item_type == 'ad':
                    # Reklama uchun adminni ogohlantirish (21-band: Audit)
                    admin_id = os.getenv("ADMIN_ID")
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=(
                            f"🔔 <b>YANGI REKLAMA BUYURTMASI (BALLI)</b>\n\n"
                            f"👤 <b>Foydalanuvchi:</b> {user['name']} (ID: {user_id})\n"
                            f"📊 <b>Tur:</b> {value} kunlik reklama\n"
                            f"💰 <b>Sarflangan:</b> {cost} ball"
                        ),
                        parse_mode="HTML"
                    )
                    msg_text = (
                        f"✅ <b>Ballar muvaffaqiyatli yechildi!</b>\n\n"
                        f"📢 <code>{value}</code> kunlik reklama buyurtmangiz qabul qilindi.\n"
                        f"Aloqa uchun: @admin_username"
                    )

                # 3. Tranzaksiyani yakunlash
                await conn.commit()
                # --- TRANZAKSIYA YAKUNLANDI ---

        await query.message.reply_text(msg_text, parse_mode="HTML")
        await query.answer("Muvaffaqiyatli bajarildi!")

    except Exception as e:
        logger.error(f"Redeem process error: {e}")
        await query.answer("🛑 Tranzaksiyada xatolik yuz berdi. Ballaringiz qaytarildi.", show_alert=True)


# ===================================================================================

async def send_message_to_friend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Boshqa muxlisga bot orqali xabar yuborish"""
    query = update.callback_query
    target_id = query.data.split("_")[2]
    
    context.user_data['msg_target_id'] = target_id
    await query.message.reply_text("Xabaringizni yozing, men uni egasiga yetkazaman:")
    return U_CHAT_MESSAGE

async def deliver_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xabarni manzilga yetkazish"""
    sender_id = update.effective_user.id
    target_id = context.user_data.get('msg_target_id')
    text = update.message.text

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"📩 **Yangi xabar!**\n\nMuxlisdan sizga xabar keldi:\n\n\"{text}\"\n\n"
                 f"Javob berish uchun profiliga o'ting.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("👤 Profilini ko'rish", callback_data=f"view_prof_{sender_id}")
            ]])
        )
        await update.message.reply_text("✅ Xabar yetkazildi!")
    except:
        await update.message.reply_text("❌ Xabarni yetkazib bo'lmadi (foydalanuvchi botni bloklagan bo'lishi mumkin).")
    
    return A_MAIN


# ===================================================================================

async def find_random_friend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bazada mavjud ochiq profillar orasidan tasodifiy birini ko'rsatish"""
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor(dictionary=True) as cur:
                # 1. Tasodifiy profilni tanlash
                # JOIN yordamida status va profil ma'lumotlarini birlashtiramiz
                # 28-BAND: Faqat is_public=1 bo'lgan ochiq profillar chiqadi
                await cur.execute("""
                    SELECT p.nickname, p.favorite_anime, p.about, p.user_id, u.status 
                    FROM user_profiles p 
                    JOIN users u ON p.user_id = u.user_id 
                    WHERE p.user_id != %s AND p.is_public = 1 
                    ORDER BY RAND() LIMIT 1
                """, (user_id,))
                friend = await cur.fetchone()

        if not friend:
            await query.answer("🧐 Hozircha ochiq profillar topilmadi. Keyinroq urinib ko'ring!", show_alert=True)
            return

        # 2. Ma'lumotlarni chiroyli formatlash
        # Statusga qarab maxsus emojilar qo'shamiz
        status_emoji = "💎" if friend['status'] == 'vip' else "👤"
        
        # 1. Oldindan tayyorlab olamiz
        fav_anime = friend['favorite_anime'] or 'Sirligicha qolgan'
        about_text = friend['about'] or "Ma'lumot berilmagan"
        status_cap = friend['status'].capitalize()

        # 2. Keyin f-string ichiga qo'yamiz
        text = (
            f"🌟 <b>ANIME MUXLISI PROFILI</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🏷 <b>Nik:</b> {friend['nickname']}\n"
            f"{status_emoji} <b>Maqomi:</b> {status_cap}\n"
            f"❤️ <b>Sevimli animesi:</b> <i>{fav_anime}</i>\n"
            f"📝 <b>Fikri:</b> <code>{about_text}</code>\n"
        )

        # 3. Tugmalar
        keyboard = [
            [InlineKeyboardButton("💌 Xabar yuborish", callback_data=f"send_msg_{friend['user_id']}")],
            [InlineKeyboardButton("🎲 Boshqasini ko'rish", callback_data="find_friend_rand")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_main")]
        ]
        
        # 4. Xabarni yangilash yoki yangi yuborish
        # reply_text orqali yuborish yaxshiroq, chunki har gal tasodifiy rasm yoki boshqa format bo'lishi mumkin
        await query.message.reply_text(
            text=text, 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        await query.answer()

    except Exception as e:
        logger.error(f"Find friend error: {e}")
        await query.answer("🛑 Ma'lumot topishda xatolik yuz berdi.", show_alert=True)


#===================================================================================


async def start_profile_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi profilini yaratish jarayonini boshlash"""
    user_id = update.effective_user.id
    
    # 1. Obunani tekshirish (Funksiya nomi va mantiq tuzatildi)
    not_joined = await check_sub(user_id, context.bot)
    if not_joined:
        # Obuna bo'lmagan bo'lsa, start() funksiyasidagi obuna xabarini qaytaramiz
        await update.message.reply_text("❌ Profil yaratish uchun avval kanallarga a'zo bo'ling!")
        return ConversationHandler.END

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur: # dictionary=True db.py da sozlangan bo'lishi kerak
                # 2. Profil allaqachon mavjudligini tekshirish
                # (Sizda 'users' jadvalida 'name' yoki 'username' ustuni borligini tekshiring)
                await cur.execute("SELECT username FROM users WHERE user_id = %s", (user_id,))
                user = await cur.fetchone()
                
                # Agar user topilsa va uning ismi bo'sh bo'lmasa (masalan, oldin ro'yxatdan o'tgan bo'lsa)
                if user and user[0]: 
                    await update.message.reply_text(
                        f"✨ <b>Sizning profilingiz allaqachon mavjud!</b>\n\n"
                        f"Nikingiz: <code>{user[0]}</code>\n"
                        f"Uni o'zgartirish uchun sozlamalar bo'limiga o'ting.",
                        parse_mode="HTML"
                    )
                    return ConversationHandler.END

        # 3. Sessiyani tozalash va jarayonni boshlash
        context.user_data.clear()
        await update.message.reply_text(
            "🌟 <b>Anime Muxlislari Hamjamiyatiga xush kelibsiz!</b>\n\n"
            "✍️ <b>Profilingiz uchun yangi nik (taxallus) kiriting:</b>",
            parse_mode="HTML"
        )
        return U_CREATE_PROFILE

    except Exception as e:
        logger.error(f"Profile creation start error: {e}")
        await update.message.reply_text("⚠️ Tizimda xatolik yuz berdi.")
        return ConversationHandler.END
    

#===================================================================================

async def save_rating_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ovozni bazaga yozish va umumiy reytingni hisoblash"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data.split("_")
    # Format: rate_set_123_5
    anime_id = data[2]
    stars = int(data[3])

    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Anti-spam: Foydalanuvchi oldin ovoz berganmi?
                # Buning uchun 'user_ratings' degan kichik jadval kerak bo'ladi
                await cur.execute(
                    "SELECT id FROM user_ratings WHERE user_id = %s AND anime_id = %s", 
                    (user_id, anime_id)
                )
                if await cur.fetchone():
                    await query.answer("⚠️ Siz ushbu animega allaqachon ovoz bergansiz!", show_alert=True)
                    return

                # 2. Ovozni hisobga olish
                # user_ratings ga yozamiz
                await cur.execute(
                    "INSERT INTO user_ratings (user_id, anime_id, rating) VALUES (%s, %s, %s)",
                    (user_id, anime_id, stars)
                )
                
                # anime_list jadvalini yangilaymiz
                await cur.execute("""
                    UPDATE anime_list 
                    SET rating_sum = rating_sum + %s, rating_count = rating_count + 1 
                    WHERE anime_id = %s
                """, (stars, anime_id))
                
                await conn.commit()

        await query.answer(f"✅ Rahmat! Siz {stars} ball berdingiz.", show_alert=True)
        # 3. UI yangilash
        await query.edit_message_caption(
            caption="✅ <b>Bahoingiz qabul qilindi!</b>\n\nFikringiz uchun rahmat. Endi boshqa animelarni ham ko'rishingiz mumkin.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Asosiy menyu", callback_data="back_to_main")
            ]]),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Rating save error: {e}")
        await query.answer("🛑 Xatolik: Ovozni saqlash imkoni bo'lmadi.")


#=====================================================================================================

async def add_comment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchidan izoh so'rash (Callback orqali)"""
    query = update.callback_query
    # Format: addcomm_123
    try:
        anime_id = query.data.split("_")[1]
    except IndexError:
        await query.answer("❌ Xatolik!")
        return ConversationHandler.END

    # Sessiyada anime_id ni saqlaymiz
    context.user_data['commenting_anime_id'] = anime_id
    
    await query.answer()
    await query.message.reply_text(
        "📝 <b>Ushbu anime haqida fikringizni yozib qoldiring:</b>\n\n"
        "<i>⚠️ Eslatma: Haqoratli izohlar uchun botdan chetlatilishingiz mumkin.</i>",
        parse_mode="HTML"
    )
    return U_ADD_COMMENT


#=====================================================================================================

async def save_comment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Izohni bazaga saqlash va foydalanuvchini rag'batlantirish"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    anime_id = context.user_data.get('commenting_anime_id')

    # 1. Validatsiya (Izoh uzunligi va anime_id mavjudligi)
    if not anime_id or len(text) < 5:
        await update.message.reply_text("❌ <b>Xato:</b> Izoh juda qisqa (kamida 5 ta belgi) yoki vaqt tugagan.")
        return A_MAIN

    # 2. Spam filtr (ixtiyoriy: bir xil izohni takrorlashni oldini olish)
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 3. Izohni saqlash
                await cur.execute(
                    "INSERT INTO comments (user_id, anime_id, comment_text) VALUES (%s, %s, %s)",
                    (user_id, anime_id, text)
                )
                
                # 4. Bonus berish (28-band: Motivatsiya tizimi)
                # Foydalanuvchi statusiga qarab bonusni o'zgartirish ham mumkin
                await cur.execute(
                    "UPDATE users SET bonus = bonus + 2 WHERE user_id = %s", 
                    (user_id,)
                )
                
                await conn.commit()

        # 5. Muvaffaqiyatli xabar
        status = await get_user_status(user_id)
        await update.message.reply_text(
            f"✅ <b>Rahmat!</b> Izohingiz qabul qilindi.\n"
            f"🎁 Faollik uchun sizga <b>2 bonus ball</b> berildi!",
            reply_markup=get_main_kb(status),
            parse_mode="HTML"
        )
        
        # User_data ni tozalaymiz
        context.user_data.pop('commenting_anime_id', None)

    except Exception as e:
        logger.error(f"Comment save error: {e}")
        await update.message.reply_text("⚠️ Texnik xatolik tufayli izoh saqlanmadi.")

    return A_MAIN

#=====================================================================================================



#=====================================================================================================


# ----------------- CALLBACK HANDLER (MUHIM QISM) -----------------

