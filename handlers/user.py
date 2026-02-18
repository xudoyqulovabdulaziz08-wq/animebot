import select
from flask import sessions
from telegram import Update
from telegram.ext import ContextTypes
from database.db import get_user_session, get_anime_session
from services.user_service import register_user, get_user_status
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from keyboard.default import get_main_kb # Menyuni import qilamiz
from config import MAIN_ADMIN_ID # Adminni tekshirish uchun
from handlers.anime import show_anime_details # Anime detallarini ko'rsatish funksiyasi
from database.models import Anime
from sqlalchemy import select

# ===================================================================================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Update va foydalanuvchini tekshirish
    if not update.message or not update.effective_user:
        return

    tg_user = update.effective_user
    
    # 2. Router orqali ID bo'yicha kerakli bazaga ulanish (0-3: U1, 4-6: U2, 7-9: U3)
    async with get_user_session(tg_user.id) as session:
        try:
            # Foydalanuvchini aynan unga tegishli bazada ro'yxatdan o'tkazish
            user, is_new = await register_user(session, tg_user)
            
            # Statusni o'sha bazadan tekshirish
            status = await get_user_status(session, tg_user.id, MAIN_ADMIN_ID)
            
            # O'zgarishlarni bazaga yozish
            await session.commit()
            
            # Klaviatura menyusini olish
            reply_markup = get_main_kb(status)

            # joined_at formatlash
            joined_date = user.joined_at.strftime('%d.%m.%Y') if (user and user.joined_at) else "Noma'lum"

            # 3. HTML formatidagi matn
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
            
            # 4. Javob yuborish
            await update.message.reply_text(
                text, 
                reply_markup=reply_markup, 
                parse_mode="HTML"
            )
            
        except Exception as e:
            # Xatolik bo'lsa sessiyani orqaga qaytarish
            await session.rollback()
            print(f"❌ Xatolik (Start Router): {e}")
            await update.message.reply_text("⚠️ Tizimda bazaga ulanish bilan bog'liq xatolik yuz berdi.")
            
            



# ===================================================================================



from database.db import get_user_session  # Routerni chaqiramiz
from config import MAIN_ADMIN_ID

async def cabinet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Update va foydalanuvchini tekshirish
    if not update.effective_user:
        return
        
    user_id = update.effective_user.id
    
    # 2. Router orqali ID oxiriga qarab (0-3, 4-6, 7-9) kerakli bazani ochamiz
    async with get_user_session(user_id) as session:
        try:
            # 1. Foydalanuvchi ma'lumotlarini o'sha bazadan olish
            # Register_user status o'zgargan bo'lsa yangilab beradi
            user, _ = await register_user(session, update.effective_user)
            status = await get_user_status(session, user_id, MAIN_ADMIN_ID)
            
            # O'zgarishlarni (masalan, VIP muddati tugab status o'zgargan bo'lsa) saqlash
            await session.commit()

            # 2. Ma'lumotlarni tayyorlash
            joined_date = user.joined_at.strftime('%d.%m.%Y') if user.joined_at else "Noma'lum"
            
            text = (
                f"👤 <b>Sizning Kabinetingiz</b>\n\n"
                f"🆔 <b>ID:</b> <code>{user.user_id}</code>\n"
                f"🎭 <b>Status:</b> <b>{status.upper()}</b>\n"
                f"💰 <b>Ballar:</b> <code>{user.points}</code>\n"
                f"👥 <b>Takliflar:</b> <code>{user.referral_count}</code> ta\n"
                f"📅 <b>Ro'yxatdan o'tdingiz:</b> {joined_date}\n"
            )
            
            # 3. VIP muddatini tekshirish
            if status.lower() == 'vip' and user.vip_expire_date:
                vip_date = user.vip_expire_date.strftime('%d.%m.%Y')
                text += f"💎 <b>VIP muddati:</b> {vip_date}"

            # 4. Javob yuborish
            await update.message.reply_text(
                text, 
                parse_mode='HTML'
            )
            
        except Exception as e:
            # Xatolik bo'lsa faqat shu bazadagi sessiyani rollback qilamiz
            await session.rollback()
            print(f"❌ Kabinet xatosi (Router): {e}")
            await update.message.reply_text("⚠️ Kabinet ma'lumotlarini yuklashda xatolik yuz berdi.")
            


# ===================================================================================


async def search_anime_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asosiy qidiruv menyusi (Nomi, ID, Janr va h.k.)"""
    
    # 1. Tugmalarni yaratish
    search_btns = [
        [
            InlineKeyboardButton("🔎 Nomi orqali", callback_data="search_type_name"),
            InlineKeyboardButton("🆔 ID orqali", callback_data="search_type_id")
        ],
        [
            InlineKeyboardButton("🖼 Rasm orqali (AI)", callback_data="search_type_photo"),
            InlineKeyboardButton("👤 Personaj orqali (AI)", callback_data="search_type_character")
        ],
        [
            InlineKeyboardButton("🎭 Janrlar orqali", callback_data="search_type_genre"),
            InlineKeyboardButton("🎙 Fandublar", callback_data="search_type_fandub")
        ],
        [InlineKeyboardButton("🎲 Tasodifiy anime", callback_data="search_type_random")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_search")]
    ]
    reply_markup = InlineKeyboardMarkup(search_btns)
    
    text = (
        "<b>🔍 Qidiruv usulini tanlang:</b>\n\n"
        "<i>Kerakli usulni tanlang va ma'lumotni yuboring.</i>"
    )

    # 2. ENG MUHIM JOYI: Qanday javob berishni aniqlash
    # Agar 'Orqaga' tugmasi orqali kelgan bo'lsa (CallbackQuery)
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    # Agar menyudagi tugma orqali kelgan bo'lsa (Message)
    elif update.message:
        await update.message.reply_text(
            text=text,
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
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_search_main")]
        ])
        await query.edit_message_text(
            "📝 <b>Anime nomini yuboring:</b>\n\n"
            "<i>Iltimos, nomni aniq yozing. Biz bazamizdan barcha mos keluvchi natijalarni qidirib topamiz.</i>",
            reply_markup=keyboard, 
            parse_mode="HTML"
        )
        
    elif data == "search_type_id":
        context.user_data["search_mode"] = "id"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_search_main")]
        ])
        await query.edit_message_text(
            "🔢 <b>Anime ID raqamini kiriting:</b>\n\n"
            "<i>Har bir animening o'z xos raqami (kod) mavjud. IDni to'g'ri yuborsangiz, srazu o'sha animeni chiqarib beraman.</i>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    elif data == "search_type_photo":
        context.user_data["search_mode"] = "photo"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_search_main")]
        ])
        await query.edit_message_text(
            "🖼 <b>Anime skrinshotini yuboring:</b>\n\n"
            "<i>Rasm tahlil qilinib, qaysi anime ekanligi aniqlanadi.</i>\n\n"
            "⚠️ <b>DIQQAT:</b> 🔞 <i>Behayolikni targ'ib qiluvchi rasmlar yuborish qat'iyan man etiladi! Qoidani buzganlar tizimdan umrbod <b>BAN</b> qilinadi!</i>", 
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    elif data == "search_type_character":
        context.user_data["search_mode"] = "character"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_search_main")]
        ])
        await query.edit_message_text(
            "👤 <b>Personaj nomini yuboring:</b>\n\n"
            "<i>Sevimli qahramoningiz ismini yozing, u ishtirok etgan barcha animelarni ko'rsataman.</i>", 
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    elif data == "search_type_genre":
        context.user_data["search_mode"] = "genre"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_search_main")]
        ])
        await query.edit_message_text(
            "🎭 <b>Janr nomini kiriting:</b>\n\n"
            "<i>Masalan: Komediya, Drama, Triller... Janrni aniq yozishingiz qidiruv sifatini oshiradi.</i>", 
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    elif data == "back_to_search_main":
        # 1. Rejimni tozalash (Matn yozsa bot qidirib ketmasligi uchun)
        context.user_data["search_mode"] = None
        
        # 2. Tugma bosilganiga javob berish (soat belgisi yo'qolishi uchun)
        await query.answer("Asosiy menyuga qaytildi")
        
        # 3. Yuqoridagi funksiyani chaqiramiz
        await search_anime_handler(update, context)

    elif data == "cancel_search":
        context.user_data.clear()
        try:
            # Xabarni o'chirishdan oldin javob berish xavfsizroq
            await query.answer("Qidiruv bekor qilindi ❌")
            await query.delete_message()
        except Exception:
            pass
        

# ===================================================================================

from telegram.constants import ChatAction # Typing status uchun

async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("search_mode")
    if not mode or not update.message.text:
        return 

    text = update.message.text
    tg_user = update.effective_user
    results = []

    # 1️⃣ "Yozmoqda..." statusini ko'rsatish
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    # 2️⃣ Vaqtinchalik "Qidirilmoqda..." xabarini yuborish
    waiting_msg = await update.message.reply_text("🔎 <i>Bazadan qidirilmoqda...</i>", parse_mode="HTML")

    try:
        if mode == "name":
            async with get_anime_session(text) as session:
                stmt = select(Anime).where(Anime.name.ilike(f"%{text}%")).limit(10)
                res = await session.execute(stmt)
                results = res.scalars().all()
        
        elif mode == "id":
            if text.isdigit():
                anime_id = int(text)
                for key in ["a1", "a2", "a3"]:
                    async with sessions[key]() as session:
                        res = await session.execute(select(Anime).where(Anime.anime_id == anime_id))
                        anime = res.scalar_one_or_none()
                        if anime:
                            results = [anime]
                            break

        elif mode in ["genre", "fandub"]:
            for key in ["a1", "a2", "a3"]:
                async with sessions[key]() as session:
                    column = Anime.genre if mode == "genre" else Anime.fandub
                    stmt = select(Anime).where(column.ilike(f"%{text}%")).limit(5)
                    res = await session.execute(stmt)
                    results.extend(res.scalars().all())

    except Exception as e:
        print(f"🔍 Qidiruv xatosi: {e}")
        await waiting_msg.delete() # Xato bo'lsa kutish xabarini o'chirish
        await update.message.reply_text("⚠️ Qidiruvda xatolik yuz berdi.")
        return

    # 3️⃣ Qidiruv tugagach, kutish xabarini o'chiramiz
    await waiting_msg.delete()

    # --- NATIJANI CHIQARISH ---
    if not results:
        retry_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Qayta urinish", callback_data=f"search_type_{mode}"),
             InlineKeyboardButton("⬅️ Asosiy menyu", callback_data="back_to_search_main")],
            [InlineKeyboardButton("❌ Qidiruvni yopish", callback_data="cancel_search")]
        ])
        await update.message.reply_text(
            f"😔 Kechirasiz <b>{tg_user.full_name}</b>, topilmadi.",
            reply_markup=retry_kb, parse_mode="HTML"
        )
        return

    context.user_data["search_mode"] = None 

    buttons = []
    for anime in results[:15]:
        buttons.append([InlineKeyboardButton(f"🎬 {anime.name}", callback_data=f"info_{anime.anime_id}")])
    
    buttons.append([InlineKeyboardButton("⬅️ Qidiruvga qaytish", callback_data="back_to_search_main")])
    
    await update.message.reply_text(
        f"✅ <b>{len(results)}</b> ta natija topildi:",
        reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML"
    )

# ===================================================================================

async def handle_photo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rasm yuborilganda vaqtinchalik javob"""
    await update.message.reply_text(
        "🖼 <b>Rasm qidiruvi funksiyasi tez kunda qo'shiladi!</b>\n\n"
        "Hozircha animelarni nomi yoki janri bo'yicha qidirib turing. 🎬",
        parse_mode="HTML"
    )


# ===================================================================================

async def process_random_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tasodifiy anime qidirish (Hozircha vaqtinchalik javob)"""
    query = update.callback_query
    await query.answer("🎲 Tasodifiy anime qidirish tez kunda qo'shiladi...")












