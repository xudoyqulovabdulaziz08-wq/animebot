from aiogram import Router, html, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from dotenv.main import logger
from aiogram.fsm.context import FSMContext
from config import config
POSTER_ID = config.RASM_ID
router = Router()

# ✅ F.data orqali yaxshilandi
@router.callback_query(F.data == "search_menu")
async def search_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    # 1. Oldingi state'larni tozalaymiz, lekin saqlangan xabar ID'larini saqlab qolamiz
    data = await state.get_data()
    last_menu_id = data.get("last_menu_id")
    await state.clear()  # State toza bo'lishi uchun

    SEARCH_COVER = POSTER_ID

    text = (
        "🔍 <b>ANIME QIDIRISH</b>\n\n"
        "Qidiruv menyusiga xush kelibsiz! 🌟\n\n"
        "<blockquote expandable>📝 Anime nomi bo'yicha qidirish tezkor</blockquote>\n"
        "<blockquote expandable>🔢 Anime ID raqami bo'yicha qidirish</blockquote>\n"
        "<blockquote expandable>🎭 Janr  bo'yicha animeni saralash </blockquote>\n\n"
        "👇 Qidiruv usulini tanlang."
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔍 Anime qidirish", switch_inline_query_current_chat="", style="primary")
            ],
            [
                InlineKeyboardButton(text="🔢 ID ", callback_data="search_by_id", style="primary"),
                InlineKeyboardButton(text="🎭 Janr", callback_data="search_by_genre", style="primary")
            ],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_start", style="danger")]
        ]
    )

    current_msg_id = callback.message.message_id

    # -------------------------------------------------------------
    # 🔥 SINGLE WINDOW / MANTIQLIY TEKSHIRUV
    # -------------------------------------------------------------
    # Agar foydalanuvchi eski xabardagi tugmani bosgan bo'lsa (kunlar o'tib)
    # yoki callback.message ni edit qilib bo'lmasa:
    if last_menu_id and last_menu_id != current_msg_id:
        try:
            # 1. Eski eskirgan menyuni o'chiramiz
            await callback.message.delete()
        except Exception:
            pass

        # 2. Yangi menyuni chatning ENG PASTIGA yuboramiz
        new_msg = await callback.message.answer_photo(
            photo=SEARCH_COVER,
            caption=text,
            reply_markup=kb,
            parse_mode="HTML"
        )
        # Yangi xabar ID'sini FSM keshga saqlaymiz
        await state.update_data(last_menu_id=new_msg.message_id)
        return

    # ✅ Agar bu joriy (oxirgi) xabar bo'lsa — shunchaki EDIT qilamiz
    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=SEARCH_COVER,
                caption=text,
                parse_mode="HTML"
            ),
            reply_markup=kb
        )
        # Menyu ID'sini keshda saqlaymiz / yangilaymiz
        await state.update_data(last_menu_id=current_msg_id)

    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            pass
        elif "message to edit not found" in str(e).lower() or "message can't be edited" in str(e).lower():
            # Agar xabarni tahrirlab bo'lmasa (masalan o'chirilgan bo'lsa), yangisini yuboramiz
            new_msg = await callback.message.answer_photo(
                photo=SEARCH_COVER,
                caption=text,
                reply_markup=kb,
                parse_mode="HTML"
            )
            await state.update_data(last_menu_id=new_msg.message_id)
        else:
            logger.error(f"❌ Kutilmagan xatolik: {e}")
    except Exception as e:
        logger.error(f"❌ Tizimda xatolik yuz berdi: {e}")