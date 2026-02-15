import select
from telegram import Update
from telegram.ext import ContextTypes
from database.db import async_session
from services.user_service import register_user, get_user_status
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from keyboard.default import get_main_kb # Menyuni import qilamiz
from config import MAIN_ADMIN_ID # Adminni tekshirish uchun
from handlers.anime import show_anime_details # Anime detallarini ko'rsatish funksiyasi
from database.models import Anime
from sqlalchemy import select

# ===================================================================================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    tg_user = update.effective_user
    
    async with async_session() as session:
        try:
            # register_user funksiyasida user_id = tg_user.id ekanligini tekshiring
            user, is_new = await register_user(session, tg_user)
            
            # Statusni aniqlash
            status = await get_user_status(session, tg_user.id, MAIN_ADMIN_ID)
            reply_markup = get_main_kb(status)

            # joined_at DateTime obyektini formatlash
            joined_date = user.joined_at.strftime('%d.%m.%Y') if user.joined_at else "Noma'lum"

            if is_new:
                text = (
                    f"👋 Xush kelibsiz, <b>{tg_user.full_name}</b>!\n"
                    f"Siz muvaffaqiyatli ro'yxatdan o'tdingiz.\n\n"
                    f"🆔 <b>Sizning ID:</b> <code>{user.user_id}</code>\n"
                    f"🏆 <b>Ballar:</b> {user.points}\n"
                    f"✨ <b>Status:</b> {status.upper()}"
                )
            else:
                text = (
                    f"Sizni yana ko'rib turganimizdan xursandmiz, <b>{tg_user.full_name}</b>! ✨\n\n"
                    f"📊 <b>Status:</b> {status.upper()}\n"
                    f"💰 <b>Ballar:</b> {user.points}\n"
                    f"📅 <b>A'zo bo'lgan sana:</b> {joined_date}"
                )
            
            await update.message.reply_text(
                text, 
                reply_markup=reply_markup, 
                parse_mode="HTML"
            )
            
        except Exception as e:
            print(f"❌ Xatolik (Start): {e}")
            await update.message.reply_text("⚠️ Bazaga ulanishda texnik xatolik yuz berdi.")
            



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
    mode = context.user_data.get("search_mode")
    text = update.message.text
    tg_user = update.effective_user

    if not mode:
        return 

    # 1. Bazadan qidirishni boshlaymiz (Rejimga qarab)
    result = None
    
    async with async_session() as session:
        if mode == "name":
            # Nomi bo'yicha qidirish (ILIKE - o'xshashlarini topadi)
            stmt = select(Anime).where(Anime.name.ilike(f"%{text}%")).limit(10)
            res = await session.execute(stmt)
            result = res.scalars().all()
            
        elif mode == "id":
            if text.isdigit():
                stmt = select(Anime).where(Anime.anime_id == int(text))
                res = await session.execute(stmt)
                result = res.scalar_one_or_none()
            
        elif mode == "genre":
            stmt = select(Anime).where(Anime.genre.ilike(f"%{text}%")).limit(10)
            res = await session.execute(stmt)
            result = res.scalars().all()

        elif mode == "fandub":
            stmt = select(Anime).where(Anime.fandub.ilike(f"%{text}%")).limit(10)
            res = await session.execute(stmt)
            result = res.scalars().all()


    # 2. AGAR NATIJA TOPILMASA (Barcha rejimlar uchun umumiy to'xtatuvchi)
    if not result:
        context.user_data.clear() 

        retry_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Qayta urinish", callback_data=f"search_type_{mode}"),
                InlineKeyboardButton("⬅️ Orqaga", callback_data="cancel_search")
            ]
        ])

        await update.message.reply_text(
            f"😔 Kechirasiz {tg_user.full_name} siz bergan , <b>'{text}'</b> bo'yicha hech qanday natija topilmadi.\n\n"
            f"<i>Qidiruv tugadi. Qayta uranasizmi yoki boshqa ylni tanlaysizmi</i>",
            reply_markup=retry_kb,
            parse_mode="HTML"
        )
        return

    # 3. NATIJA TOPILGANDA
    context.user_data.clear() 

    # Agar qidiruv ID bo'yicha bo'lsa (Natija bitta obyekt bo'ladi)
    if mode == "id":
        await show_anime_details(update, context, result.anime_id)

    # Agar boshqa usullar bilan qidirilsa (Natija ro'yxat/list bo'ladi)
    else:
        # Agar ro'yxatda faqat bitta anime bo'lsa, srazu o'shani ko'rsatamiz
        if isinstance(result, list) and len(result) == 1:
            await show_anime_details(update, context, result[0].anime_id)
            return

        # Agar natijalar ko'p bo'lsa, tugmalar chiqaramiz
        buttons = []
        for anime in result:
            # Boss, tugma bosilganda info_ID callback-ini yuboradi
            buttons.append([InlineKeyboardButton(f"🎬 {anime.name}", callback_data=f"info_{anime.anime_id}")])
        
        reply_markup = InlineKeyboardMarkup(buttons)
        count = len(result)
        
        response = (
            f"🔍 <b>'{text}'</b> bo'yicha <b>{count}</b> ta natija topildi.\n\n"
            f"<i>Kerakli animeni tanlang <b>{tg_user.full_name}</b>:</i>"
        )
        
        await update.message.reply_text(response, reply_markup=reply_markup, parse_mode="HTML")

# ===================================================================================

async def handle_photo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rasm yuborilganda ishlovchi funksiya"""
    mode = context.user_data.get("search_mode")
    
    if mode == "photo":
        await update.message.reply_text(
            "🖼 <b>Rasmingiz qabul qilindi!</b>\n"
            "AI tahlil qilmoqda, biroz kuting...", 
            parse_mode="HTML"
        )
        # Kelajakda bu yerga AI qidiruv mantiqi qo'shiladi
    else:
        # Agar foydalanuvchi qidiruv rejimida bo'lmasa, shunchaki e'tibor bermaymiz
        return




