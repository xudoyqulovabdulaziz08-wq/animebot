import logging
import html
import asyncio
from aiogram import Router, F, types
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from handlers.anime_uchun.izoh_anime import anime_comment_handler
from services.comment_service import CommentService
from services.anime_service import AnimeService
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from config import config

logger = logging.getLogger("izohlarim_edit")
router = Router()
CREATOR_ID = config.CREATOR_ID


class EditCommentStates(StatesGroup):
    waiting_for_new_text = State()



def get_my_comments_keyboard(
    anime_id: int, 
    total_count: int, 
    current_index: int, 
    comment_id: int, 
    replies_count: int = 0  # <--- Yangi parametr
) -> InlineKeyboardMarkup:
    keyboard = []
    
    # 1. Sahifalash tugmalari (1, 2, 3...)
    page_buttons = []
    for i in range(total_count):
        is_active = i == current_index
        
        page_buttons.append(
            InlineKeyboardButton(
                text = f"• {i + 1} •" if i == current_index else str(i + 1),
                callback_data=f"my_comm:{anime_id}:{i}",
                style="success" if is_active else None
            )
        )
    if page_buttons:
        keyboard.append(page_buttons)

    # 2. Amal tugmalari (Javoblar, O'chirish va Tahrirlash)
    keyboard.append([
        InlineKeyboardButton(
            text=f"💬 {replies_count} ta javob",  # <--- Dinamik qiymat joylandi
            callback_data=f"reply_comm:{comment_id}:{anime_id}", 
            style="primary"
        )
    ])
    keyboard.append([
        InlineKeyboardButton(text="🗑️ O‘chirish", callback_data=f"del_comm:{comment_id}:{anime_id}", style="danger"),
        InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"edit_comm:{comment_id}", style="success")
    ])

    # 3. Orqaga tugmasi
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"anime_comment:{anime_id}", style="danger")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)



def get_comment_replies_keyboard(
    anime_id: int, 
    comment_id: int, 
    total_count: int, 
    current_index: int
) -> InlineKeyboardMarkup:
    keyboard = []
    
    # 1. Sahifalash tugmalari (1, 2, 3...)
    if total_count > 1:
        page_buttons = []
        for i in range(total_count):
            text = f"• {i + 1} •" if i == current_index else str(i + 1)
            page_buttons.append(
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"rep_page:{comment_id}:{anime_id}:{i}"
                )
            )
        keyboard.append(page_buttons)

    # 2. Orqaga tugmasi (Asosiy izohga qaytaradi)
    keyboard.append([
        InlineKeyboardButton(
            text="⬅️ Orqaga", 
            callback_data=f"my_comm:{anime_id}:{current_index}", 
            style="danger"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.callback_query(F.data.startswith("my_comm:") | F.data.startswith("my_comments:"))
async def handle_my_comments(callback: CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    anime_id = int(parts[1])
    current_index = int(parts[2]) if len(parts) > 2 else 0
    user_id = callback.from_user.id

    comment_service = CommentService(session)
    anime_service = AnimeService(session=session)
    
    # 1. Ma'lumotlarni olamiz
    anime = await anime_service.get_anime(anime_id)
    total_comments = await comment_service.get_user_comments_count(anime_id, user_id)

    if total_comments == 0:
        await callback.answer(
            "💬 Bu yerda hali sizning izohingiz yo‘q.\n"
            "✍️ Birinchi bo‘lib fikringizni qoldiring!",
            show_alert=True
        )
        return

    # Index chegarasini to'g'rilash
    if current_index >= total_comments:
        current_index = total_comments - 1
    elif current_index < 0:
        current_index = 0

    # Bazadan/keshdan joriy izohni olish
    comment = await comment_service.get_user_comment_by_index(anime_id, user_id, current_index)
    if not comment:
        await callback.answer("Izoh topilmadi.", show_alert=True)
        return

    replies_count = await comment_service.get_comment_replies_count(comment["id"])
    anime_title = anime.get("title", "Anime") if isinstance(anime, dict) else getattr(anime, "title", "Anime")

    # 2. HTML escaping bilan matn tayyorlash
    text_lines = [
        "💬 <b>Izohlarim</b>\n",
        f"🎬 <b>{html.escape(str(anime_title))}</b>\n"
    ]

    if comment.get("parent"):
        parent_author = html.escape(str(comment["parent"]["author_name"]))
        parent_text = html.escape(str(comment["parent"]["text"]))
        text_lines.append(f"↩️ <i>{parent_author} ning izohiga javob:</i>")
        text_lines.append(f"┗<blockquote expandable><i>\"{parent_text}\"</i></blockquote>\n")

    text_lines.append(f"💬 <b>Izoh {current_index + 1}/{total_comments}</b>\n")
    text_lines.append(f"<blockquote expandable>{html.escape(str(comment['text']))}</blockquote>")

    caption = "\n".join(text_lines)

    keyboard = get_my_comments_keyboard(
        anime_id=anime_id,
        total_count=total_comments,
        current_index=current_index,
        comment_id=comment["id"],
        replies_count=replies_count
    )

    # 3. Xabarni xavfsiz va kafolatli yangilash
    try:
        if callback.message.photo or callback.message.document:
            await callback.message.edit_caption(
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                text=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        if "message is not modified" in err_msg:
            pass
        elif "there is no caption" in err_msg or "message has no caption" in err_msg:
            # Agar xabarda caption bo'lmasa, edit_text ga o'tamiz
            await callback.message.edit_text(
                text=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            logger.error(f"❌ handle_my_comments edit xatosi: {e}")

    try:
        await callback.answer()
    except Exception:
        pass







@router.callback_query(F.data.startswith(("reply_comm:", "rep_page:")))
async def handle_comment_replies(callback: CallbackQuery, session: AsyncSession):
    # 1. callback_data xavfsiz parse qilish
    try:
        parts = callback.data.split(":")
        comment_id = int(parts[1])
        anime_id = int(parts[2])
        current_index = int(parts[3]) if len(parts) > 3 else 0
    except (IndexError, ValueError):
        await callback.answer("❌ Noto'g'ri so'rov!", show_alert=True)
        return

    comment_service = CommentService(session)

    # 2. Bazadan ketma-ket ma'lumotlarni olish (asyncio.gather o'rniga)
    try:
        parent_comment = await comment_service.get_comment_by_id(comment_id)
        replies = await comment_service.get_comment_replies(comment_id, limit=50, offset=0)
    except Exception as err:
        logger.error(f"❌ Izohlarni olishda xatolik: {err}", exc_info=True)
        await callback.answer("❌ Tizimda xatolik yuz berdi.", show_alert=True)
        return

    # 3. Javoblar yo'qligini tekshirish
    if not replies:
        await callback.answer(
            "💬 Hozircha bu izohingizga hech kim javob yozmagan.",
            show_alert=True
        )
        return

    total_replies = len(replies)

    # Index chegarasini to'g'rilash
    if current_index >= total_replies:
        current_index = total_replies - 1
    elif current_index < 0:
        current_index = 0

    # Joriy tanlangan javob
    current_reply = replies[current_index]
    
    # Foydalanuvchi ma'lumotlari va matnlarni olish
    reply_user_name = (
        current_reply.get("user", {}).get("full_name") 
        or current_reply.get("user", {}).get("username") 
        or "Foydalanuvchi"
    )
    
    reply_text = current_reply.get("text", "")
    parent_text = parent_comment.get("text", "") if parent_comment else ""

    # 4. Matn shakllantirish va HTML teglarini qochirish (html.escape)
    text_lines = [
        "↩️ <b>Sizning izohingizga javoblar</b>\n",
        f"“<i>{html.escape(parent_text)}</i>”\n",
        f"👤 <b>{html.escape(reply_user_name)}</b>\n",
        f"<blockquote expandable>{html.escape(reply_text)}</blockquote>",
        f"\n💬 <b>Javob {current_index + 1}/{total_replies}</b>"
    ]

    caption = "\n".join(text_lines)

    # Keyboard yasash
    keyboard = get_comment_replies_keyboard(
        anime_id=anime_id,
        comment_id=comment_id,
        total_count=total_replies,
        current_index=current_index
    )

    # Callback so'rovini yopamiz
    await callback.answer()

    # 5. Xabarni xavfsiz yangilash
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                text=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
    except TelegramBadRequest as e:
        error_msg = str(e).lower()
        if "message is not modified" in error_msg:
            pass  # Xabar o'zgarmagan bo'lsa e'tiborsiz qoldiramiz
        elif "message to edit not found" in error_msg or "message can't be edited" in error_msg:
            await callback.message.answer(text=caption, reply_markup=keyboard, parse_mode="HTML")
        else:
            logger.error(f"❌ TelegramBadRequest yuz berdi: {e}")
    except Exception as err:
        logger.error(f"❌ Javoblarni ko'rsatishda kutilmagan xatolik: {err}")



# 1-BOSQICH: O'chirish tugmasi bosilganda tasdiqlash oynasiga o'tkazish
@router.callback_query(F.data.startswith("del_comm:"))
async def handle_delete_comment_ask(callback: CallbackQuery):
    parts = callback.data.split(":")
    comment_id = int(parts[1])
    anime_id = int(parts[2])

    text = "⚠️ <b>Rostdan ham ushbu izohni o‘chirmoqchimisiz?</b>\n\n<i>Ushbu amalni ortga qaytarib bo‘lmaydi!</i>"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, o‘chirish", callback_data=f"del_comm_confirm:{comment_id}:{anime_id}", style="success"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"my_comm:{anime_id}:0", style="danger")
        ]
    ])

    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text(
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
    except TelegramBadRequest as e:
        if "message is not modified" not in e.message.lower():
            raise e

    await callback.answer()






@router.callback_query(F.data.startswith("del_comm_confirm:"))
async def handle_delete_comment_confirm(callback: CallbackQuery, session: AsyncSession):
    try:
        parts = callback.data.split(":")
        comment_id = int(parts[1])
        anime_id = int(parts[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Noto'g'ri so'rov!", show_alert=True)
        return

    user_id = callback.from_user.id
    comment_service = CommentService(session)

    # 1. Bazadan va keshdan o'chiramiz
    try:
        success = await comment_service.delete_comment(
            comment_id=comment_id, 
            user_id=user_id, 
            anime_id=anime_id
        )
    except Exception as err:
        logger.error(f"❌ Izohni o'chirishda xatolik: {err}", exc_info=True)
        await callback.answer("❌ Tizimda xatolik yuz berdi.", show_alert=True)
        return

    if not success:
        await callback.answer("❌ Izohni o'chirib bo'lmadi yoki u allaqachon o'chirilgan.", show_alert=True)
        return

    # 2. Alert chiqarish
    await callback.answer("🗑 Izohingiz muvaffaqiyatli o'chirildi!", show_alert=True)

    # 3. Qolgan izohlar sonini tekshirish
    total_comments = await comment_service.get_user_comments_count(anime_id, user_id)

    # 4. Agar izohlar qolmagan bo'lsa -> Izohlar bosh sahifasiga qaytamiz
    if total_comments == 0:
        new_callback = callback.model_copy(update={"data": f"anime_comments:{anime_id}"})
        try:
            await anime_comment_handler(new_callback, session)
        except Exception as e:
            logger.error(f"anime_comment_handler chaqirishda xatolik: {e}")
        return

    # 5. Boshqa izohlar bo'lsa -> Keyingi/oldingi izohni ko'rsatamiz
    new_callback = callback.model_copy(update={"data": f"my_comm:{anime_id}:0"})
    try:
        await handle_my_comments(new_callback, session)
    except Exception as e:
        logger.error(f"handle_my_comments chaqirishda xatolik: {e}")




# =======================================================
# 1. ✏️ TAHRIRLASH TUGMASI (Input holatiga o'tkazish)
# =======================================================
@router.callback_query(F.data.startswith("edit_comm:"))
async def edit_comment_start_handler(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    try:
        comment_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Noto'g'ri so'rov!", show_alert=True)
        return

    comment_service = CommentService(session)
    
    try:
        comment = await comment_service.get_comment_by_id(comment_id)
    except Exception as err:
        logger.error(f"❌ Bazadan izohni olishda xatolik: {err}")
        await callback.answer("❌ Tizimda xatolik yuz berdi.", show_alert=True)
        return

    if not comment or comment.get("user_id") != callback.from_user.id:
        await callback.answer("❌ Izoh topilmadi yoki bu sizning izohingiz emas!", show_alert=True)
        return

    await callback.answer()

    anime_id = comment["anime_id"]
    old_text = comment.get("text", "")

    await state.set_state(EditCommentStates.waiting_for_new_text)
    await state.update_data(
        edit_comment_id=comment_id,
        anime_id=anime_id,
        prompt_message_id=callback.message.message_id,
        old_text=old_text
    )

    text = (
        f"✏️ <b>Izohni tahrirlash</b>\n\n"
        f"📝 <b>Eski izoh:</b>\n"
        f"<blockquote expandable><i>{html.escape(old_text)}</i></blockquote>\n\n"
        f"✍️ Yangi izohni yuboring..."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Bekor qilish", 
                    callback_data=f"my_comm:{anime_id}:0",
                    style="danger"
                )
            ]
        ]
    )

    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await callback.message.edit_text(text=text, reply_markup=keyboard, parse_mode="HTML")
            
    except TelegramBadRequest as e:
        error_msg = str(e).lower()
        if "message is not modified" in error_msg:
            pass
        elif "message to edit not found" in error_msg or "message can't be edited" in error_msg:
            msg = await callback.message.answer(text=text, reply_markup=keyboard, parse_mode="HTML")
            await state.update_data(prompt_message_id=msg.message_id)
        else:
            logger.error(f"❌ TelegramBadRequest yuz berdi: {e}")
            
    except Exception as err:
        logger.error(f"❌ Kutilmagan xatolik: {err}")


# =======================================================
# 2. 📝 MATN QABUL QILISH VA PREVIEW (Bitta xabar rejimi)
# =======================================================
@router.message(EditCommentStates.waiting_for_new_text)
async def process_new_comment_text(message: types.Message, state: FSMContext, bot):
    user_text = message.text.strip() if message.text else ""
    data = await state.get_data()
    
    prompt_message_id = data.get("prompt_message_id")
    anime_id = data.get("anime_id")
    comment_id = data.get("edit_comment_id")

    try:
        await message.delete()
    except Exception:
        pass

    if not user_text or len(user_text) < 2:
        return

    await state.update_data(pending_new_text=user_text)

    preview_text = (
        f"📝 <b>Yangi izohingizni tasdiqlaysizmi?</b>\n\n"
        f"💬 <b>Yangi izohingiz:</b>\n"
        f"<blockquote expandable><i>{html.escape(user_text)}</i></blockquote>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Tasdiqlash", 
                    callback_data=f"confirm_edit_comm:{comment_id}",
                    style="success"
                ),
                InlineKeyboardButton(
                    text="🔄 Qayta kiritish", 
                    callback_data=f"edit_comm:{comment_id}",
                    style="primary"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Bekor qilish", 
                    callback_data=f"my_comm:{anime_id}:0",
                    style="danger"
                )
            ]
        ]
    )

    try:
        await bot.edit_message_caption(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            caption=preview_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        error_msg = str(e).lower()
        if "there is no caption in the message to edit" in error_msg or "message has no caption" in error_msg:
            try:
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=prompt_message_id,
                    text=preview_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            except Exception as err:
                logger.error(f"❌ Text edit qilishda xato: {err}")
        else:
            logger.error(f"❌ Caption edit qilishda xato: {e}")
    except Exception as err:
        logger.error(f"❌ Kutilmagan xatolik: {err}")


# =======================================================
# 3. ✅ TASDIQLASH VA BAZAGA SAQLASH
# =======================================================
@router.callback_query(F.data.startswith("confirm_edit_comm:"))
async def confirm_edit_comment_handler(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    try:
        comment_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Noto'g'ri so'rov!", show_alert=True)
        await state.clear()
        return

    data = await state.get_data()
    new_text = data.get("pending_new_text")
    anime_id = data.get("anime_id")
    user_id = callback.from_user.id

    if not new_text or not anime_id:
        await callback.answer("⚠️ Izoh matni topilmadi. Qaytadan urinib ko'ring.", show_alert=True)
        await state.clear()
        return

    try:
        comment_service = CommentService(session=session)
        success = await comment_service.update_comment(
            comment_id=comment_id,
            user_id=user_id,
            anime_id=anime_id,
            new_text=new_text
        )

        # FSM holatni tozalaymiz
        await state.clear()

        if success:
            await callback.answer("✅ Izohingiz muvaffaqiyatli yangilandi!", show_alert=True)

            # Callback data'ni almashtirib yangi nusxa uzatamiz
            new_callback = callback.model_copy(
                update={"data": f"my_comm:{anime_id}:0"}
            )
            await handle_my_comments(new_callback, session)
        else:
            await callback.answer("❌ Izohni yangilashda xatolik yuz berdi.", show_alert=True)

    except Exception as e:
        logger.error(f"❌ Izohni tahrirlashda xatolik: {e}", exc_info=True)
        await callback.answer("❌ Izohni saqlashda xatolik yuz berdi.", show_alert=True)