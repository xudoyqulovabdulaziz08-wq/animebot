from aiogram import Router

from handlers.admin_panel.admin_anime.episode import( 
    add_episode, 
    del_episode,
    swap_episode,
    episode_menu,
    main_episode,
    filler_episode,
    add_vip_episode,
    main_vip_episode,
    filler_vip_episode,
    swap_vip_episode,
    del_vip_episode
)
from handlers.menu import admin_menu
from handlers.admin_panel import admin_stastika
from handlers.admin_panel.admin_anime import (
    anime_menu,  janr, dubber, 
    edit_anime, list_anime1
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
from handlers.admin_panel.admin_anime.list_anime import (
    list_all_anime, list_end_anime, list_contine_anime
)
from handlers.admin_panel.admin_anime.anime import (
    add_anime,
    channel_anime
)
admin_router = Router()

admin_router.include_routers(
    admin_menu.router,
    anime_menu.router,
    channel_menu.router,
    admin_advet_menu.router,
    admin_vip_menu.router,
    admin_stastika.router,
    
    
    list_all_anime.router,
    list_end_anime.router,
    list_contine_anime.router,
    list_anime1.router,
    

    janr.router,
    dubber.router,

    add_anime.router,
    add_episode.router,
    del_episode.router,
    swap_episode.router,
    episode_menu.router,
    main_episode.router,
    filler_episode.router,
    add_vip_episode.router,
    main_vip_episode.router,
    filler_vip_episode.router,
    swap_vip_episode.router,
    del_vip_episode.router,

    channel_anime.router,
    edit_anime.router,
    add_vip.router,
    list_vip.router,
    add_channel.router,
    list_channel.router,
    channel_advert.router,
    admin_advert_send.router,
)