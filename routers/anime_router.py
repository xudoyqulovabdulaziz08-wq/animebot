from aiogram import Router
from handlers.search import (
    search, inline_search, search_id, search_name, search_genr, anime_card, wiev_episode
)
from handlers.anime_uchun import (
    baholash_anime, izoh_anime, obuna_anime, sevimli_anime
)
from handlers.anime_uchun.izohlar import (
    add_izoh, edit_izohlar
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
    add_izoh.router,
    edit_izohlar.router,
)