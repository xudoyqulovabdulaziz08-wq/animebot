from aiogram import Router


# ============================================================
# ADMIN MENU
# ============================================================

from handlers.menu import admin_menu
from handlers.admin_panel import admin_stastika


# ============================================================
# ADMIN ANIME — ASOSIY
# ============================================================

from handlers.admin_panel.admin_anime import (
    anime_menu,
    anime_type_menu,
    janr,
    dubber,
    edit_anime,
    list_anime1,
)

from handlers.admin_panel.admin_anime.anime import (
    add_anime,
    channel_anime,
    tugalandi,
)

from handlers.admin_panel.admin_anime.list_anime import (
    list_all_anime,
    list_end_anime,
    list_contine_anime,
)


# ============================================================
# ADMIN ANIME — EPISODE
# ============================================================

from handlers.admin_panel.admin_anime.episode import (
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
    del_vip_episode,
)


# ============================================================
# ADMIN ANIME — TIZER
# ============================================================

from handlers.admin_panel.admin_anime.tizer_edit import (
    tizer_menu,
    tizzer_edit_add,
    tizer_view,
)


# ============================================================
# ADMIN CHANNEL
# ============================================================

from handlers.admin_panel.admin_channel import (
    channel_menu,
    add_channel,
    list_channel,
    channel_advert,
)


# ============================================================
# ADMIN ADVERT
# ============================================================

from handlers.admin_panel.admin_advert import (
    admin_advet_menu,
    admin_advert_send,
)


# ============================================================
# ADMIN VIP
# ============================================================

from handlers.admin_panel.admin_vip import (
    admin_vip_menu,
    add_vip,
    list_vip,
)


# ============================================================
# MAIN ADMIN ROUTER
# ============================================================

admin_router = Router()


# ============================================================
# 1. MAIN MENU
# ============================================================

admin_router.include_routers(
    admin_menu.router,
    admin_stastika.router,
)


# ============================================================
# 2. ANIME MENU
# ============================================================

admin_router.include_routers(
    anime_menu.router,
    anime_type_menu.router,
    janr.router,
    dubber.router,
    edit_anime.router,
)


# ============================================================
# 3. ANIME MANAGEMENT
# ============================================================

admin_router.include_routers(
    add_anime.router,
    channel_anime.router,
    tugalandi.router,
)


# ============================================================
# 4. ANIME LIST
# ============================================================

admin_router.include_routers(
    list_anime1.router,
    list_all_anime.router,
    list_end_anime.router,
    list_contine_anime.router,
)


# ============================================================
# 5. EPISODE MANAGEMENT
# ============================================================

admin_router.include_routers(
    episode_menu.router,
    add_episode.router,
    del_episode.router,
    swap_episode.router,
    main_episode.router,
    filler_episode.router,
)


# ============================================================
# 6. VIP EPISODE MANAGEMENT
# ============================================================

admin_router.include_routers(
    add_vip_episode.router,
    main_vip_episode.router,
    filler_vip_episode.router,
    swap_vip_episode.router,
    del_vip_episode.router,
)


# ============================================================
# 7. TIZER
# ============================================================

admin_router.include_routers(
    tizer_menu.router,
    tizzer_edit_add.router,
    tizer_view.router,
)


# ============================================================
# 8. CHANNEL
# ============================================================

admin_router.include_routers(
    channel_menu.router,
    add_channel.router,
    list_channel.router,
    channel_advert.router,
)


# ============================================================
# 9. ADVERT
# ============================================================

admin_router.include_routers(
    admin_advet_menu.router,
    admin_advert_send.router,
)


# ============================================================
# 10. VIP
# ============================================================

admin_router.include_routers(
    admin_vip_menu.router,
    add_vip.router,
    list_vip.router,
)