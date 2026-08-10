import logging
import html
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from handlers.anime_uchun.izoh_anime import anime_comment_handler
from services.comment_service import CommentService
from services.anime_service import AnimeService
from aiogram.fsm.state import State, StatesGroup

from config import config

logger = logging.getLogger("izohlarim")
router = Router()
CREATOR_ID = config.CREATOR_ID

class CommentStates(StatesGroup):
    waiting_for_comment = State()  # Text kiritish kutilmoqda

# =======================================================
# 1. "IZOH YOZISH" TUGMASI BOSILGANDA (State set va Prompt)
# =======================================================
@router.callback_query(F.data.startswith("add_comment:"))
async def start_add_comment_handler(callback: CallbackQuery, state: FSMContext, session):
    # 1. Ruxsat tekshiruvi (callback.answer'dan oldin bajariladi)
    if callback.from_user.id != CREATOR_ID:
        await callback.answer(text="🛑 Izohlar funksiyasi tez orada ishga tushadi.", show_alert=True)
        return

    # 2. Double-click va tugma "qotib qolishi" oldini olish uchun darhol answer beramiz
    await callback.answer()

    # 3. FSM race-condition: Agar foydalanuvchi allaqachon shu holatda bo'lsa, qayta ishlatmaymiz
    current_state = await state.get_state()
    if current_state == CommentStates.waiting_for_comment.state:
        return

    try:
        anime_id = int(callback.data.split(":")[1])
        anime_service = AnimeService(session=session)
        anime = await anime_service.get_anime(anime_id)
        
        if not anime:
            await callback.answer(text="❌ Anime topilmadi.", show_alert=True)
            return

        anime_title = anime.get("title", "Anime") if isinstance(anime, dict) else getattr(anime, "title", "Anime")

        text = (
            f"💬 <b>Izoh yozish</b>\n\n"
            f"🎬 <b>{anime_title}</b>\n\n"
            f"✍️ Fikringizni yuboring..."
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Orqaga", 
                        callback_data=f"cancel_comment_input:{anime_id}",
                        style="danger"
                    )
                ]
            ]
        )

        message = callback.message
        if not message:
            return

        # 4. FSM holatini EDIT'dan oldin o'rnatamiz (DB/Telegram sekinlashganda input yo'qolmasligi uchun)
        await state.set_state(CommentStates.waiting_for_comment)

        # 5. Xabarni yangilash (Media/Text xavfsiz tahriri)
        if message.photo or message.video or message.animation or message.document:
            prompt_msg = await message.edit_caption(caption=text, reply_markup=keyboard, parse_mode="HTML")
        else:
            prompt_msg = await message.edit_text(text=text, reply_markup=keyboard, parse_mode="HTML")

        # Context ma'lumotlarini saqlaymiz
        await state.update_data(
            anime_id=anime_id,
            anime_title=anime_title,
            prompt_message_id=prompt_msg.message_id
        )

    except TelegramBadRequest as e:
        # Tahrirlanayotgan xabar o'zgarmagan bo'lsa yoki topilmasa xatoni shunchaki yutib yuboramiz
        if "message is not modified" in str(e) or "message to edit not found" in str(e):
            pass
        else:
            logger.warning(f"Add comment TelegramBadRequest: {e}")
            await state.clear()
    except Exception as e:
        logger.error(f"Add comment handler error: {e}", exc_info=True)
        await state.clear()
        await callback.answer(text="❌ Xatolik yuz berdi, qayta urinib ko'ring.", show_alert=True)

# =======================================================
# 2. USER MATN YUBORGANDA (Kutish va User xabarini o'chirish)
# =======================================================
import html

@router.message(CommentStates.waiting_for_comment, F.text)
async def process_comment_input(message: Message, state: FSMContext, session):
    data = await state.get_data()
    anime_id = data.get("anime_id")
    anime_title = data.get("anime_title")
    prompt_message_id = data.get("prompt_message_id")
    
    # 1. State va session tekshiruvi
    if not anime_id or not prompt_message_id:
        await state.clear()
        try:
            await message.delete()
        except Exception:
            pass
        return

    raw_text = message.text.strip()
    
    # Text uzunligini tekshirish
    if len(raw_text) > 1000:
        try:
            await message.delete()
        except Exception:
            pass
        await message.answer("⚠️ Izoh juda uzun! Maksimal 1000 ta belgi yuborishingiz mumkin.")
        return

    # Foydalanuvchi yuborgan xabarni o'chirib, chatni toza tutamiz
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"User message delete error: {e}")

    safe_comment_text = html.escape(raw_text)
    safe_anime_title = html.escape(str(anime_title))

    # FSM ga izoh matnini saqlaymiz
    await state.update_data(comment_text=raw_text)

    preview_text = (
        f"💬 <b>Izohingiz</b>\n\n"
        f"<blockquote>{safe_comment_text}</blockquote>\n\n"
        f"🎬 <b>{safe_anime_title}</b>\n\n"
        f"Izohni yuborishni tasdiqlaysizmi?"
    )

    confirm_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yuborish", callback_data=f"confirm_send_comment:{anime_id}", style="success"),
                InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"edit_comment_input:{anime_id}", style="success")
            ],
            [
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_comment_input:{anime_id}" ,style="danger")
            ]
        ]
    )

    # 🎯 MUHIM QISM: Yangi xabar yubormaymiz!
    # Dastlabki POSTERLI xabar caption'ini tahrirlaymiz
    try:
        await message.bot.edit_message_caption(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            caption=preview_text,
            reply_markup=confirm_keyboard,
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        # Agar qandaydir sabab bilan xabar media bo'lmay chiqsa (fallback)
        if "message is not modified" in str(e):
            pass
        else:
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=prompt_message_id,
                    text=preview_text,
                    reply_markup=confirm_keyboard,
                    parse_mode="HTML"
                )
            except Exception as ex:
                logger.error(f"Fallback edit text error: {ex}")


# =======================================================
# 3. ✅ YUBORISH TUGMASI (DB ga yozish va keshni tozalash)
# =======================================================
@router.callback_query(F.data.startswith("confirm_send_comment:"))
async def confirm_send_comment_handler(callback: CallbackQuery, state: FSMContext, session):
    anime_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    comment_text = data.get("comment_text")

    # 1. State va text validatsiyasi
    if not comment_text:
        await callback.answer("⚠️ Izoh topilmadi!", show_alert=True)
        await state.clear()
        return

    try:
        comment_service = CommentService(session=session)
        await comment_service.add_comment(
            anime_id=anime_id,
            user_id=callback.from_user.id,
            text=comment_text
        )

        # 2. FSM state'ni tozalaymiz
        await state.clear()

        # 3. Yagona va muvaffaqiyatli alert chiqarish
        await callback.answer("✅ Izohingiz muvaffaqiyatli yuborildi!", show_alert=True)

        # 4. Izohlar bo'limiga qaytamiz
        # Eslatma: anime_comment_handler ichida ham await callback.answer() bor bo'lsa, 
        # uni try-except ichiga olish yoki u yerdagisini bosib ketishini e'tiborga olish kerak.
        await anime_comment_handler(callback, session)

    except Exception as e:
        logger.error(f"Izohni saqlashda xatolik: {e}", exc_info=True)
        await callback.answer("❌ Izohni saqlashda xatolik yuz berdi.", show_alert=True)
# =======================================================
# 4. ✏️ TAHRIRLASH TUGMASI (Qaytadan kiritish holatiga o'tkazish)
# =======================================================
@router.callback_query(F.data.startswith("edit_comment_input:"))
async def edit_comment_input_handler(callback: CallbackQuery, state: FSMContext, session):
    await callback.answer()
    anime_id = int(callback.data.split(":")[1])
    
    # Eskisini o'chiramiz
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Qayta prompt yaratamiz
    anime_service = AnimeService(session=session)
    anime = await anime_service.get_anime(anime_id)
    anime_title = anime.get("title", "Anime") if isinstance(anime, dict) else getattr(anime, "title", "Anime")

    text = (
        f"💬 <b>Izoh yozish</b>\n\n"
        f"🎬 <b>{anime_title}</b>\n\n"
        f"✍️ Fikringizni yuboring..."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Orqaga", 
                    callback_data=f"cancel_comment_input:{anime_id}"
                )
            ]
        ]
    )

    prompt_msg = await callback.message.answer(text=text, reply_markup=keyboard, parse_mode="HTML")

    await state.set_state(CommentStates.waiting_for_comment)
    await state.update_data(
        anime_id=anime_id,
        anime_title=anime_title,
        prompt_message_id=prompt_msg.message_id
    )


# =======================================================
# 5. ❌ BEKOR QILISH / ORQAGA TUGMASI (FSM tozalash va ortga)
# =======================================================
@router.callback_query(F.data.startswith("cancel_comment_input:"))
async def cancel_comment_input_handler(callback: CallbackQuery, state: FSMContext, session):
    # 1. Callback answer beramiz
    await callback.answer("Jarayon bekor qilindi.")

    try:
        # FSM ma'lumotlarini olamiz
        data = await state.get_data()
        prompt_message_id = data.get("prompt_message_id")
        
        # 2. State'ni zudlik bilan tozalaymiz
        await state.clear()

        # 3. Agar alohida preview xabari (Text Message) bo'lsa va bu callback shunga tegishli bo'lsa:
        # Eski prompt xabarini xavfsiz o'chirishga urinib ko'ramiz
        if prompt_message_id and prompt_message_id != callback.message.message_id:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id, 
                    message_id=prompt_message_id
                )
            except Exception:
                pass

        # 4. Izohlar bo'limiga xavfsiz qaytamiz
        await anime_comment_handler(callback, session)

    except TelegramBadRequest as e:
        if "message is not modified" in str(e) or "message to delete not found" in str(e):
            pass
        else:
            logger.warning(f"Cancel comment input TelegramBadRequest: {e}")
            await state.clear()
    except Exception as e:
        logger.error(f"Cancel comment input handler error: {e}", exc_info=True)
        await state.clear()