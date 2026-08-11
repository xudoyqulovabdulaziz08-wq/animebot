from aiogram import Router
from handlers.start import (
    start_cmd,
    start_callbacks
)
from middlewares.subscription import CheckSubscriptionMiddleware

start_router = Router()


start_router.include_routers(
    start_cmd.router,
    start_callbacks.router
)