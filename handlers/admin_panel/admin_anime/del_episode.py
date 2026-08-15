from aiogram.types import InputMediaPhoto
import math
import logging

from typing import Any
from aiogram import Router, F, html
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from services.anime_service import AnimeService
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InputMediaVideo
from handlers.admin_panel.admin_anime.list_anime1 import get_episode_list_markup

from handlers.admin_panel.admin_anime.list_anime1 import show_specific_episode_handler
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
router = Router()


class SwapEpisodeStates(StatesGroup):
    waiting_for_new_video = State()  # Yangi videoni kutish holati

logger = logging.getLogger(__name__)



@router.callback_query(F.data.startswith("burn_ep:"))
async def confirm_delete_episode_handler(callback: CallbackQuery, session: Any):
    await callback.answer()
    
    _, anime_id_str, ep_num_str, back_page_str = callback.data.split(":")
    anime_id = int(anime_id_str)
    ep_num = int(ep_num_str)
    back_page = int(back_page_str)

    service = AnimeService(session=session)
    anime = await service.get_anime(anime_id)
    
    if not anime:
        await callback.message.answer("❌ Anime topilmadi!")
        return

    title = anime.get("title", "Nomsiz anime")
    poster_id = anime.get("poster_id")

    # Qizil ogohlantirish matni
    caption = (
        f"⚠️ {html.bold('DIQQAT! QISMNI O‘CHIRISH')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎬 Anime: <b>{title}</b>\n"
        f"🔢 O‘chirilayotgan qism: {html.bold(f'{ep_num}-qism')}\n\n"
        f"🛑 {html.italic('Ushbu amalni ortga qaytarib bo‘lmaydi! Ushbu qism ma’lumotlar bazasidan hamda kesh xotirasidan butunlay o‘chib ketadi.')}\n\n"
        f"Haqiqatdan ham ushbu qismni o‘chirmoqchimisiz?"
    )

    # Tasdiqlash tugmalari
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            # Tasdiqlash tugmasi: maxsus 'real_burn_ep' callbackiga yo'naltiriladi
            InlineKeyboardButton(text="✅ Ha, o‘chirilsin", callback_data=f"real_burn_ep:{anime_id}:{ep_num}:{back_page}"),
            # Bekor qilish: qaytadan boyagi videoli ko'rish sahifasiga qaytaradi
            InlineKeyboardButton(text="❌ Yo‘q, bekor qilish", callback_data=f"show_ep:{anime_id}:{ep_num}:{back_page}")
        ]
    ])

    # Videoni pleeridan rasmli (posterli) ogohlantirish holatiga o'tkazamiz
    try:
        if poster_id:
            new_media = InputMediaPhoto(media=poster_id, caption=caption, parse_mode="HTML")
            await callback.message.edit_media(media=new_media, reply_markup=kb)
        else:
            await callback.message.edit_text(text=caption, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ Ogohlantirish panelini ko'rsatishda xato: {e}")






@router.callback_query(F.data.startswith("real_burn_ep:"))
async def execute_delete_episode_handler(callback: CallbackQuery, session: Any):
    _, anime_id_str, ep_num_str, back_page_str = callback.data.split(":")
    anime_id = int(anime_id_str)
    ep_num = int(ep_num_str)
    back_page = int(back_page_str)

    service = AnimeService(session=session)
    
    # 1. Metodni chaqirib bazadan va keshdan o'chiramiz
    try:
        ok = await service.delete_episode(anime_id=anime_id, episode_num=ep_num)
    except Exception as e:
        logger.error(f"❌ Epizod o'chirish handlerida xato: {e}")
        ok = False

    if ok:
        await callback.answer(f"🗑 {ep_num}-qism muvaffaqiyatli o‘chirildi!", show_alert=True)
    else:
        await callback.answer("❌ Xatolik: Qism allaqachon o‘chirilgan bo‘lishi mumkin!", show_alert=True)

    # 2. O'chgandan keyin adminni chalg'itmasdan o'zi turgan qismlar ro'yxatiga qaytaramiz
    # Yangilangan kesh tufayli o'chgan qism ro'yxatdan g'oyib bo'ladi
    anime = await service.get_anime(anime_id)
    episodes = anime.get("episodes", []) if anime else []
    title = anime.get("title", "Nomsiz anime") if anime else ""

    caption = (
        f"╔══════════════════╗\n"
        f"  🎬 <b>{title}</b>\n"
        f"╚══════════════════╝\n\n"
        f"📹 Ro‘yxatdan kerakli qismni tanlang.\n"
        f"💡 {html.italic('Tanlangan qism videosi va uni boshqarish tugmalari shu yerning o‘zida ochiladi.')}"
    )

    # Boyagi paginatsiyali markup funksiyangizni chaqiramiz
    markup = await get_episode_list_markup(anime_id=anime_id, episodes=episodes, page=back_page)

    try:
        poster_id = anime.get("poster_id") if anime else None
        if poster_id:
            new_media = InputMediaPhoto(media=poster_id, caption=caption, parse_mode="HTML")
            await callback.message.edit_media(media=new_media, reply_markup=markup)
        else:
            await callback.message.edit_text(text=caption, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ Ro'yxatga qaytarishda xatolik: {e}")



















@router.callback_query(F.data.startswith("swap_ep:"))
async def start_swap_episode_handler(callback: CallbackQuery, state: FSMContext, session: Any):
    await callback.answer()
    
    _, anime_id_str, ep_num_str, back_page_str = callback.data.split(":")
    anime_id = int(anime_id_str)
    ep_num = int(ep_num_str)
    back_page = int(back_page_str)

    service = AnimeService(session=session)
    anime = await service.get_anime(anime_id)
    
    if not anime:
        await callback.message.answer("❌ Anime topilmadi!")
        return

    # FSM holatiga o'tamiz va kerakli o'zgaruvchilarni saqlaymiz
    await state.set_state(SwapEpisodeStates.waiting_for_new_video)
    await state.update_data(anime_id=anime_id, ep_num=ep_num, back_page=back_page)

    poster_id = anime.get("poster_id")
    title = anime.get("title", "Nomsiz anime")

    caption = (
        f"🔄 <b>{title} — {ep_num}-qismni almashtirish</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📹 Iltimos, ushbu qism uchun **yangi videoni** yuboring (tashlang).\n\n"
        f"📥 {html.italic('Yangi video qabul qilingandan so‘ng, tizim sizdan yakuniy ruxsatni so‘raydi.')}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        # Bekor qilsa, yana boyagi videoni ko'rish sahifasiga FSMni yopib qaytaradi
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"show_ep:{anime_id}:{ep_num}:{back_page}")]
    ])

    # Videoni pleeridan rasmli holatga o'tkazib, video so'raymiz
    try:
        if poster_id:
            new_media = InputMediaPhoto(media=poster_id, caption=caption, parse_mode="HTML")
            await callback.message.edit_media(media=new_media, reply_markup=kb)
        else:
            await callback.message.edit_text(text=caption, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ Almashtirish panelini ochishda xato: {e}")







@router.message(SwapEpisodeStates.waiting_for_new_video, F.video)
async def receive_new_swap_video_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    anime_id = data.get("anime_id")
    ep_num = data.get("ep_num")
    back_page = data.get("back_page")
    
    new_file_id = message.video.file_id
    # Yangi kelgan file_id ni ham FSM ichiga saqlab qo'yamiz
    await state.update_data(new_file_id=new_file_id)

    caption = (
        f"⚠️ <b>ALMASHTIRISHNI TASDIQLASH</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔢 Qism raqami: <b>{ep_num}-qism</b>\n"
        f"📹 Yangi video fayli muvaffaqiyatli qabul qilindi.\n\n"
        f"🛑 {html.bold('DIQQAT!')} {html.italic('Ushbu qismning eski videosi butunlay o‘chib ketadi va yangisiga almashadi. Ushbu amalni ortga qaytarib bo‘lmaydi.')}\n\n"
        f"Haqiqatdan ham ushbu qism videosini yangilashni tasdiqlaysizmi?"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            # Tasdiqlash: Maxsus callback orqali ijro etiladi
            InlineKeyboardButton(text="✅ Ha, almashtirilsin", callback_data="confirm_real_swap"),
            # Rad etish: FSMni yopib, eski videoni o'ziga qaytaradi
            InlineKeyboardButton(text="❌ Yo‘q, bekor qilish", callback_data=f"cancel_swap_process")
        ]
    ])

    await message.answer(text=caption, reply_markup=kb, parse_mode="HTML")





@router.callback_query(F.data == "cancel_swap_process", SwapEpisodeStates.waiting_for_new_video)
async def cancel_swap_handler(callback: CallbackQuery, state: FSMContext, session: Any):
    data = await state.get_data()
    await state.clear()  # FSM holatidan chiqamiz
    
    await callback.answer("Jarayon bekor qilindi.")
    
    # ❌ callback.message.delete() bu yerda ham bo'lmasligi shart!
    
    cloned_callback = callback.model_copy(
        update={"data": f"show_ep:{data['anime_id']}:{data['ep_num']}:{data['back_page']}"}
    )
    await show_specific_episode_handler(cloned_callback, session=session)



@router.callback_query(F.data == "confirm_real_swap", SwapEpisodeStates.waiting_for_new_video)
async def execute_swap_handler(callback: CallbackQuery, state: FSMContext, session: Any):
    data = await state.get_data()
    anime_id = data.get("anime_id")
    ep_num = data.get("ep_num")
    back_page = data.get("back_page")
    new_file_id = data.get("new_file_id")

    service = AnimeService(session=session)
    
    try:
        ok = await service.update_episode_file(
            anime_id=anime_id,
            episode_num=ep_num,
            new_file_id=new_file_id
        )
    except Exception as e:
        logger.error(f"❌ Almashtirishda xato yuz berdi: {e}")
        ok = False

    await state.clear()  # FSM tozalash

    # ❌ BU YERDAGI callback.message.delete() NI OLIB TASHLADIK!
    # Chunki u o'chib ketsa, pastdagi funksiya tahrirlashga xabar topolmay qoladi.

    if ok:
        await callback.answer(f"✅ {ep_num}-qism videosi muvaffaqiyatli almashtirildi!", show_alert=True)
    else:
        await callback.answer("❌ Tizimda xatolik yuz berdi, almashtirilmadi.", show_alert=True)

    # Callback ob'ektidan xavfsiz nusxa olamiz
    cloned_callback = callback.model_copy(
        update={"data": f"show_ep:{anime_id}:{ep_num}:{back_page}"}
    )
    
    # Endi show_specific_episode_handler aynan shu mavjud xabarni video pleerga aylantiradi
    await show_specific_episode_handler(cloned_callback, session=session)