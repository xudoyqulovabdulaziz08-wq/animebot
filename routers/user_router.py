from aiogram import Router
from handlers.menu import (
     kabinet, qollanma, help
)
from handlers.menu.vip import(
    vip_handler
)
from handlers.menu.reklama import (
    reklama_handlers
)
from handlers.animelarim import (
    animelarim_menu, sevimlilarim, baholaganlarim
)

user_router = Router()

user_router.include_routers(
    kabinet.router,
    qollanma.router,
    reklama_handlers.router,
    vip_handler.router,
    help.router,
    animelarim_menu.router,
    sevimlilarim.router,
    baholaganlarim.router,
)