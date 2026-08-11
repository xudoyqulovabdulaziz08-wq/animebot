from aiogram import Router
from handlers.menu import (
    kabinet, qollanma, reklama, buy_vip, help
)
from handlers.animelarim import (
    animelarim_menu, sevimlilarim, baholaganlarim
)

user_router = Router()

user_router.include_routers(
    kabinet.router,
    qollanma.router,
    reklama.router,
    buy_vip.router,
    help.router,
    animelarim_menu.router,
    sevimlilarim.router,
    baholaganlarim.router,
)