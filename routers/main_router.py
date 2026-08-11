from aiogram import Router
from middlewares.subscription import CheckSubscriptionMiddleware

from routers.start_router import start_router
from routers.user_router import user_router
from routers.anime_router import anime_router
from routers.admin_router import admin_router
from routers.creator_router import creator_router

main_router = Router()

# 1. Xavfsizlik va obuna tekshiruvini ASOSIY routerga ulaymiz
main_router.message.middleware(CheckSubscriptionMiddleware())
main_router.callback_query.middleware(CheckSubscriptionMiddleware())

# 2. Keyin barcha sub-routerlarni qo'shamiz
main_router.include_routers(
    start_router,
    user_router,
    anime_router,
    admin_router,
    creator_router,
)