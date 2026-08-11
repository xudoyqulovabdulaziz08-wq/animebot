from aiogram import Router
from handlers.menu import creator_menu
from handlers.creator_panel.cretor_admin_panel import (
    creator_admin, add_admin, list_admin
)
from handlers.creator_panel.Baza_control import creator_db

creator_router = Router()

creator_router.include_routers(
    creator_menu.router,
    creator_admin.router,
    add_admin.router,
    list_admin.router,
    creator_db.router,
)