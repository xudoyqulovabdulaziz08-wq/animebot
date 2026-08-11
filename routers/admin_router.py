from aiogram import Router
from handlers.menu import admin_menu
from handlers.admin_panel import admin_stastika
from handlers.admin_panel.admin_anime import (
    anime_menu, add_anime, list_anime, janr, dubber, 
    add_episode, del_episode, channel_anime, edit_anime
)
from handlers.admin_panel.admin_channel import (
    channel_menu, add_channel, list_channel, channel_advert
)
from handlers.admin_panel.admin_advert import (
    admin_advet_menu, admin_advert_send
)
from handlers.admin_panel.admin_vip import (
    admin_vip_menu, add_vip, list_vip
)

admin_router = Router()

admin_router.include_routers(
    admin_menu.router,
    anime_menu.router,
    channel_menu.router,
    admin_advet_menu.router,
    admin_vip_menu.router,
    admin_stastika.router,
    add_anime.router,
    list_anime.router,
    janr.router,
    dubber.router,
    add_episode.router,
    del_episode.router,
    channel_anime.router,
    edit_anime.router,
    add_vip.router,
    list_vip.router,
    add_channel.router,
    list_channel.router,
    channel_advert.router,
    admin_advert_send.router,
)