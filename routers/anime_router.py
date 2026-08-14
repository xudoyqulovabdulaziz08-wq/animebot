from aiogram import Router
from handlers.search import (
    search, inline_search, search_id, search_name, search_genr, anime_card, wiev_episode
)
from handlers.anime_uchun import (
    baholash_anime, izoh_anime, obuna_anime, sevimli_anime
)

from handlers.anime_uchun.izohlar.add_izohlar import (
    add_izoh,
    add_edit
)
from handlers.anime_uchun.izohlar.izohlarim import (
    edit_izohlarim,
    del_izohlarim
)
from handlers.anime_uchun.izohlar.view_izohlar import (
    izohlar_all,
    izoh_reply,
    add_reply
)
anime_router = Router()

anime_router.include_routers(
    search.router,
    inline_search.router,
    search_id.router,
    search_name.router,
    search_genr.router,
    anime_card.router,
    wiev_episode.router,
    baholash_anime.router,
    izoh_anime.router,
    obuna_anime.router,
    sevimli_anime.router,
    izohlar_all.router,
    izoh_reply.router,
    add_reply.router,

    add_izoh.router,
    add_edit.router,
    edit_izohlarim.router,
    del_izohlarim.router
)