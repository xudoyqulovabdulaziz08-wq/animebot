from aiogram import Router
from handlers.menu import (
    qollanma, help
)
from handlers.menu.vip import(
    vip_handler
)
from handlers.menu.reklama import (
    reklama_handlers
)
from handlers.animelarim import (
    animelarim_menu, sevimlilarim, baholaganlarim, shahrlaganim
)
from handlers.menu.cabinet import (
    cabinet_handlers
)

user_router = Router()

user_router.include_routers(
    cabinet_handlers.router,
    qollanma.router,
    reklama_handlers.router,
    vip_handler.router,
    help.router,
    animelarim_menu.router,
    sevimlilarim.router,
    baholaganlarim.router,
    shahrlaganim.router
)