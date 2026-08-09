import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from services.comment_service import CommentService
from services.anime_service import AnimeService
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from config import config

logger = logging.getLogger("izohlarim")
router = Router()
CREATOR_ID = config.CREATOR_ID


@router.callback_query(F.data.startswith("anime_comment:"))
async def anime_comment_handler(callback: CallbackQuery, session):
    # 1. Double-click va tugma "qotib qolishi"ni oldini olish uchun darhol answer beramiz
    await callback.answer()

    # 🔒 Ruxsat tekshiruvi
    if callback.from_user.id != CREATOR_ID:
        await callback.answer(
            text="🛑 Izohlar funksiyasi tez orada ishga tushadi.",
            show_alert=True
        )
        return

    try:
        anime_id = int(callback.data.split(":")[1])

        comment_service = CommentService(session=session)
        anime_service = AnimeService(session=session)

        # Async o'qish (DB/Cache)
        anime = await anime_service.get_anime(anime_id)
        comment_count = await comment_service.get_comments_count(anime_id)

        anime_title = anime.get("title", "Anime") if isinstance(anime, dict) else getattr(anime, "title", "Anime")

        text = (
            f"💬 <b>Izohlar bo'limi</b>\n\n"
            f"🎬 <b>{anime_title}</b>\n"
            f"💬 Jami izohlar: <b>{comment_count} ta</b>"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="➕ Izoh yozish", callback_data=f"add_comment:{anime_id}"),
                    InlineKeyboardButton(text="💬 Izohlar", callback_data=f"view_comments:{anime_id}:1")
                ],
                [
                    InlineKeyboardButton(text="🗨️ Izohlarim", callback_data=f"my_comments:{anime_id}")
                ],
                [
                    InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"anime_card_com_back:{anime_id}")
                ]
            ]
        )

        # 2. Xabar turi va Telegram API xatolarini xavfsiz boshqarish
        message = callback.message
        if not message:
            return

        # Agar xabar Media (photo/video/animation) bo'lsa -> Caption'ni tahrirlaymiz
        if message.photo or message.video or message.animation or message.document:
            await message.edit_caption(
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            # Oddiy matnli xabar bo'lsa -> Text'ni tahrirlaymiz
            await message.edit_text(
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )

    except TelegramBadRequest as e:
        # "Message is not modified" xatosini inkor qilamiz (foydalanuvchi bir xil tugmani ko'p bossa chiqadi)
        if "message is not modified" in str(e):
            pass
        else:
            logger.warning(f"Anime comment handler TelegramBadRequest: {e}")
    except Exception as e:
        logger.error(f"Anime comment handler error: {e}", exc_info=True)


@router.callback_query(F.data.startswith("anime_card_com_back:"))
async def back_to_anime_card_handler(callback: CallbackQuery, session):
    anime_id = int(callback.data.split(":")[1])
    anime_service = AnimeService(session)
    
    anime = await anime_service.get_anime(anime_id)
    if anime:
        # Mavjud send_anime_card funksiyangiz orqali silliq tahrirlaymiz
        from handlers.search_menu.anime_card import send_anime_card  # Import yo'lini to'g'rilang
        await send_anime_card(
            message=callback.message,
            anime=anime,
            session=session,
            edit=True,
            callback=callback
        )
    await callback.answer()