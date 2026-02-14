from telegram import Update
from telegram.ext import ContextTypes
from database.db import async_session
from services.user_service import register_user, get_user_status
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from keyboard.default import get_main_kb # Menyuni import qilamiz
from config import MAIN_ADMIN_ID # Adminni tekshirish uchun


# ===================================================================================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    tg_user = update.effective_user
    
    async with async_session() as session:
        try:
            # 1. Foydalanuvchini ro'yxatdan o'tkazish yoki ma'lumotni yangilash
            user, is_new = await register_user(session, tg_user)
            
            # 2. Statusni aniqlash (Menyu tugmalari uchun)
            status = await get_user_status(session, tg_user.id, MAIN_ADMIN_ID)
            
            # 3. Statusga mos menyuni olish
            reply_markup = get_main_kb(status)

            if is_new:
                text = (
                    f"👋 Xush kelibsiz, {tg_user.full_name}!\n"
                    f"Siz muvaffaqiyatli ro'yxatdan o'tdingiz.\n\n"
                    f"🆔 ID: `{user.user_id}`\n"
                    f"🏆 Ballar: {user.points}\n"
                    f"✨ Status: {status.upper()}"
                )
            else:
                text = (
                    f"Sizni yana ko'rib turganimizdan xursandmiz, {tg_user.full_name}! ✨\n\n"
                    f"📊 **Status:** {status.upper()}\n"
                    f"💰 **Ballar:** {user.points}\n"
                    f"📅 **A'zo bo'lgan sana:** {user.joined_at.strftime('%d.%m.%Y')}"
                )
            
            # 4. Xabarni menyu bilan birga yuborish
            await update.message.reply_text(
                text, 
                reply_markup=reply_markup, 
                parse_mode="Markdown"
            )
            
        except Exception as e:
            print(f"❌ Xatolik: {e}")
            await update.message.reply_text("Tizimda texnik xatolik yuz berdi.")



# ===================================================================================



async def cabinet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    async with async_session() as session:
        # Foydalanuvchi ma'lumotlarini bazadan olamiz
        user, _ = await register_user(session, update.effective_user)
        status = await get_user_status(session, user_id, MAIN_ADMIN_ID)
        
        text = (
            f"👤 **Sizning Kabinetingiz**\n\n"
            f"🆔 ID: `{user.user_id}`\n"
            f"🎭 Status: **{status.upper()}**\n"
            f"💰 Ballar: `{user.points}`\n"
            f"👥 Takliflar: `{user.referral_count}` ta\n"
            f"📅 Ro'yxatdan o'tdingiz: {user.joined_at.strftime('%d.%m.%Y')}\n"
        )
        
        if user.status == 'vip' and user.vip_expire_date:
            text += f"💎 VIP muddati: {user.vip_expire_date.strftime('%d.%m.%Y')}"

        await update.message.reply_text(text, parse_mode='Markdown')


async def search_anime_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qidiruv tugmasi bosilganda Inline tugmalarni chiqaradi"""
    
    search_btns = [
        [
            InlineKeyboardButton("🔎 Nomi orqali", callback_data="search_type_name"),
            InlineKeyboardButton("🆔 ID raqami", callback_data="search_type_id")
        ],
        [
            InlineKeyboardButton("🖼 Rasm orqali (AI)", callback_data="search_type_photo"),
            InlineKeyboardButton("👤 Personaj (AI)", callback_data="search_type_character")
        ],
        [
            InlineKeyboardButton("🎭 Janrlar", callback_data="search_type_genre"),
            InlineKeyboardButton("🎙 Fandublar", callback_data="search_type_fandub")
        ],
        [InlineKeyboardButton("🎲 Tasodifiy anime", callback_data="search_type_random")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_search")]
    ]
    
    reply_markup = InlineKeyboardMarkup(search_btns)
    
    await update.message.reply_text(
        "<b>🔍 Qidiruv usulini tanlang:</b>  \n\n"
        "<i>Qidirsh usulini tanglang va kerakli ma'limotlarni kiriting.</i>",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )


# ===================================================================================

async def search_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    
    if data == "search_type_name":
        context.user_data["search_mode"] = "name"
        await query.edit_message_text(
            "📝 <b>Anime nomini yuboring:</b>\n\n"
            "<i>Iltimos, nomni aniq yozing. Biz bazamizdan barcha mos keluvchi natijalarni qidirib topamiz.</i>", 
            parse_mode="HTML"
        )
        
    elif data == "search_type_id":
        context.user_data["search_mode"] = "id"
        await query.edit_message_text(
            "🔢 <b>Anime ID raqamini kiriting:</b>\n\n"
            "<i>Har bir animening o'z xos raqami (kod) mavjud. IDni to'g'ri yuborsangiz, srazu o'sha animeni chiqarib beraman.</i>", 
            parse_mode="HTML"
        )

    elif data == "search_type_photo":
        context.user_data["search_mode"] = "photo"
        await query.edit_message_text(
            "🖼 <b>Anime skrinshotini yuboring:</b>\n\n"
            "<i>Rasm tahlil qilinib, qaysi anime ekanligi aniqlanadi.</i>\n\n"
            "⚠️ <b>DIQQAT:</b> 🔞 <i>Behayolikni targ'ib qiluvchi rasmlar yuborish qat'iyan man etiladi! Qoidani buzganlar tizimdan umrbod <b>BAN</b> qilinadi!</i>", 
            parse_mode="HTML"
        )

    elif data == "search_type_character":
        context.user_data["search_mode"] = "character"
        await query.edit_message_text(
            "👤 <b>Personaj nomini yuboring:</b>\n\n"
            "<i>Sevimli qahramoningiz ismini yozing, u ishtirok etgan barcha animelarni ko'rsataman.</i>", 
            parse_mode="HTML"
        )

    elif data == "search_type_genre":
        context.user_data["search_mode"] = "genre"
        await query.edit_message_text(
            "🎭 <b>Janr nomini kiriting:</b>\n\n"
            "<i>Masalan: Komediya, Drama, Triller... Janrni aniq yozishingiz qidiruv sifatini oshiradi.</i>", 
            parse_mode="HTML"
        )

    elif data == "search_type_random":
        await query.edit_message_text("🎲 <b>Siz uchun qiziqarli anime tanlanmoqda...</b>", parse_mode="HTML")
        # Bu yerda bazadan tasodifiy bitta animeni olib beruvchi funksiyani ulaymiz
        await process_random_search(update, context)
        
    elif data == "cancel_search":
        context.user_data.clear() 
        await query.delete_message()
        

# ===================================================================================

async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Foydalanuvchi qaysi rejimda ekanligini tekshiramiz
    mode = context.user_data.get("search_mode")
    text = update.message.text

    if not mode:
        return # Agar rejim tanlanmagan bo'lsa, hech narsa qilmaymiz

    if mode == "name":
        # Shu yerda bazadan 'text' bo'yicha qidiramiz
        await update.message.reply_text(f"🔍 Nom bo'yicha qidirilmoqda: <b>{text}</b>", parse_mode="HTML")
        
    elif mode == "id":
        if text.isdigit():
             await update.message.reply_text(f"🔢 ID bo'yicha qidirilmoqda: <b>{text}</b>", parse_mode="HTML")
        else:
             await update.message.reply_text("❌ Xato! ID faqat raqamlardan iborat bo'lishi kerak.")

    elif mode == "genre":
        if text.isalpha():
             await update.message.reply_text(f"🎭 Janr bo'yicha qidirilmoqda: <b>{text}</b>", parse_mode="HTML")
        else:
            await update.message.reply_text("❌ Xato! Janr nomi faqat harflardan iborat bo'lishi kerak.")

    elif mode == "character":
        if text.isalpha():
             await update.message.reply_text(f"👤 Personaj bo'yicha qidirilmoqda: <b>{text}</b>", parse_mode="HTML")
        else:
            await update.message.reply_text("❌ Xato! Personaj nomi faqat harflardan iborat bo'lishi kerak.")





