from typing import Dict, Any
from aiogram.types import CallbackQuery, Message

async def open_page(
    event: CallbackQuery | Message, 
    page: str, 
    params: Dict[str, Any], 
    session: Any = None,
    user_service: Any = None,
    state: Any = None,
    user: dict = None
):
    from handlers.start import send_or_edit_start_menu
    from handlers.search import search_menu
    from handlers.qollanma import guide_menu
    from handlers.help import support_menu
    from handlers.reklama import advertise_menu, advertise_submit
    from handlers.kabinet import open_cabinet_handler
    from handlers.buy_vip import buy_vip_menu, vip_payed, process_vip_checkout
    from handlers.admin_menu import admin_menu
    from handlers.creator_menu import creator_menu
    from handlers.search_menu.search_genr import search_by_genre
    from handlers.search_menu.anime_card import send_anime_card
    from handlers.search_menu.wiev_episode import process_anime_streaming_player
    from handlers.animelarim.sevimlilarim import animelarim_menu as show_favorites_menu  # Aliasing
    from handlers.animelarim.baholaganlarim import animelarim_menu as show_rating_menu
    from services.anime_service import AnimeService

    """
    Butun bot bo'yicha sahifalarni tarix asosida qayta tiklovchi universal markaz.
    """
    if page == "main_menu":
        user_id = event.from_user.id
        username = event.from_user.username or "do'stim"
        await send_or_edit_start_menu(event, user_id=user_id, username=username, session=session)

    elif page == "search_menu":
        await search_menu(event, state=state)

    elif page == "guide":
        await guide_menu(event, state=state)

    elif page == "support":
        await support_menu(event, state=state)

    elif page == "advertise":
        await advertise_menu(event)

    elif page == "advertise_submit":
        await advertise_submit(event)
        
    elif page == "search_genre":
        await search_by_genre(event, state=state)

    elif page == "cabinet":
        await open_cabinet_handler(event, user_service=user_service)

    # 📌 1. YANGI: Animelarim sub-menyusi uchun shart
    elif page == "animelarim_cabinet":
        from handlers.kabinet import animelarim_menu
        if isinstance(event, CallbackQuery):
            await animelarim_menu(callback=event, session=session, state=state)

    elif page == "buy_vip":
        await buy_vip_menu(event, user_service=user_service)

    elif page == "purchase_vip":
        await vip_payed(event, user_service=user_service)

    # 📌 2. TUZATILDI: event.data mutation olib tashlandi
    elif page == "purchases_vip":
        months = params.get("months", "1")
        await process_vip_checkout(event, months_override=months)

    elif page == "admin_menu":
        await admin_menu(event, user=user or {})

    elif page == "creator_menu":
        await creator_menu(event, user=user or {})

    elif page == "anime_card":
        anime_id = params.get("anime_id")
        if anime_id:
            anime_service = AnimeService(session=session)
            anime = await anime_service.get_anime(anime_id)
            if anime:
                msg = event.message if isinstance(event, CallbackQuery) else event
                cb = event if isinstance(event, CallbackQuery) else None
                await send_anime_card(
                    message=msg,
                    anime=anime,
                    session=session,
                    state=state,
                    edit=bool(cb),
                    callback=cb
                )

    # 📌 3. TUZATILDI: event.data mutation olib tashlandi
    elif page == "video_player":
        if isinstance(event, CallbackQuery):
            anime_id = params.get("anime_id")
            ep_num = params.get("ep_num", 1)
            page_num = params.get("page_num", 1)
            await process_anime_streaming_player(
                event, 
                session=session,
                anime_id_override=anime_id,
                ep_num_override=ep_num,
                page_num_override=page_num
            )

    # 📌 4. TO'G'RILANGAN SEVIMLILAR BO'LIMI
    elif page == "favorites":
        page_num = params.get("page", 1)
        if isinstance(event, CallbackQuery):
            await show_favorites_menu(
                callback=event, 
                session=session, 
                state=state, 
                page_override=page_num
            )

    elif page == "rating":
        page_num = params.get("page", 1)
        if isinstance(event, CallbackQuery):
            await show_rating_menu(
                callback=event, 
                session=session, 
                state=state, 
                page_override=page_num
            )