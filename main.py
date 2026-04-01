import os

from telegram import Update # Update alohida telegram modulidan olinadi
from telegram.ext import ApplicationBuilder, CommandHandler, AIORateLimiter, Defaults, TypeHandler
from telegram.constants import ParseMode

from handlers import start, health_check, error_handler, pre_handler
from core import on_startup, on_shutdown

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
SECRET_TOKEN = os.getenv("SECRET_TOKEN")
PORT = int(os.environ.get("PORT", 10000))


def run():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN topilmadi!")

    if not WEBHOOK_URL:
        raise ValueError("WEBHOOK_URL topilmadi!")

    defaults = Defaults(
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .defaults(defaults)
        .rate_limiter(AIORateLimiter())  # optional lekin tavsiya qilaman
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )

    app.add_handler(TypeHandler(Update, pre_handler), group=-1)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("health", health_check))
    app.add_error_handler(error_handler)

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
        secret_token=SECRET_TOKEN
    )


if __name__ == "__main__":
    run()
