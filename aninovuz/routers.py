from aiogram import Router
from middlewares.subscription import CheckSubscriptionMiddleware
from handlers import(
    start,
    search,
    qollanma,
    reklama,
    buy_vip,
    help,
    admin_menu,
    creator_menu,
    kabinet
)
from  handlers.creator_panel.Baza_control import (
    creator_db
)
from handlers.creator_panel.cretor_admin_panel import (
    add_admin,
    creator_admin,
    list_admin
)
from handlers.admin_panel import(
    admin_stastika
    
)

from handlers.admin_panel.admin_anime import(
    anime_menu,
    add_anime,
    list_anime,
    janr,
    add_episode,
    del_episode,
    channel_anime,
    edit_anime,
    dubber
)
from handlers.admin_panel.admin_channel import(
    channel_menu,
    add_channel,
    list_channel
)
from handlers.admin_panel.admin_advert import(
    admin_advet_menu,
    admin_advert_send
)
from handlers.admin_panel.admin_vip import(
    admin_vip_menu,
    add_vip,
    list_vip
)

from handlers.search_menu import(
    search_id,
    search_name,
    anime_card,
    search_genr,
    wiev_episode
)


main_router = Router()

main_router.message.middleware(CheckSubscriptionMiddleware())
main_router.callback_query.middleware(CheckSubscriptionMiddleware())

main_router.include_routers(

    start.router,
    creator_menu.router,

    creator_admin.router,
    add_admin.router,
    list_admin.router,
    creator_db.router,
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
    anime_card.router,
    admin_advert_send.router,

    kabinet.router,
    qollanma.router,
    reklama.router,
    buy_vip.router,
    help.router,
    wiev_episode.router,


    search.router,
    search_id.router,
    search_name.router,
    search_genr.router

)