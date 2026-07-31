# utils/page_renderer.py
from typing import Dict, Any
from aiogram.types import CallbackQuery, Message

# Handler funksiyalaringizdan importlar:

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
    from handlers.search import search_menu  # fayl nomingizga qarab moslang
    from handlers.qollanma import guide_menu, 
    from handlers.help import support_menu
    from handlers.reklama import advertise_menu, advertise_submit
    from handlers.kabinet import open_cabinet_handler
    from handlers.buy_vip import buy_vip_menu, vip_payed, process_vip_checkout
    from handlers.admin_menu import admin_menu
    from handlers.creator_menu import creator_menu

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
        await guide_menu(event)

    elif page == "support":
        await support_menu(event)

    elif page == "advertise":
        await advertise_menu(event)

    elif page == "advertise_submit":
        await advertise_submit(event)

    elif page == "cabinet":
        await open_cabinet_handler(event, user_service=user_service)

    elif page == "buy_vip":
        await buy_vip_menu(event, user_service=user_service)

    elif page == "purchase_vip":
        await vip_payed(event, user_service=user_service)

    elif page == "purchases_vip":
        # Dynamic callback soxtalashtiriladi
        months = params.get("months", "1")
        event.data = f"purchases_vip:{months}"
        await process_vip_checkout(event)

    elif page == "admin_menu":
        await admin_menu(event, user=user or {})

    elif page == "creator_menu":
        await creator_menu(event, user=user or {})