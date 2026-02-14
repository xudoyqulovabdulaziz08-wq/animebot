import os
import sys
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler
from config import TOKEN
from telegram.ext import CallbackQueryHandler
from handlers.user import search_callback_handler

from telegram.ext import MessageHandler, filters
from handlers.user import  start, cabinet_handler, search_anime_handler, handle_user_input, handle_photo_input
from handlers.anime import show_episodes, video_handler, show_anime_details_callback

# Importni xavfsiz qilish
try:
    from database.db import engine
except ImportError:
    try:
        from db import engine
    except:
        engine = None

async def start_bot():
    """Botni sozlash va ishga tushirish funksiyasi"""
    
    application = ApplicationBuilder().token(TOKEN).build()

    # 1. Buyruqlar (Commands)
    application.add_handler(CommandHandler("start", start))

    # 2. Shaxsiy kabinet (Text filters)
    application.add_handler(MessageHandler(filters.Text("👤 Shaxsiy Kabinet"), cabinet_handler))
    application.add_handler(MessageHandler(filters.Text("🔍 Anime qidirish 🎬"), search_anime_handler))

    # 3. Callbacklar (Tugmalar bosilganda)
    # Diqqat: pattern orqali har xil turdagi tugmalarni ajratib olamiz
    application.add_handler(CallbackQueryHandler(search_callback_handler, pattern=r"^search_type_|^cancel_search"))
    application.add_handler(CallbackQueryHandler(show_episodes, pattern=r"^show_episodes_|^episodes_"))
    application.add_handler(CallbackQueryHandler(video_handler, pattern=r"^video_"))
    application.add_handler(CallbackQueryHandler(show_anime_details_callback, pattern=r"^info_"))
    application.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.message.delete(), pattern="delete_msg"))

    # 4. Matnli kirishlar (Qidiruv so'zini yuborganda)
    # Bu eng pastda bo'lishi kerak, aks holda buyruqlarni ham "text" deb o'ylashi mumkin
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_input))

    print("🤖 Bot polling rejimida ishlamoqda...")
    await application.run_polling()
    
    # Render va boshqa serverlarda botni to'xtovsiz ushlab turish uchun
    # run_polling() eng xavfsiz usul hisoblanadi
    async with application:
        await application.initialize()
        await application.start()
        # stop_signals=None Render'da signal xatolarini oldini olish uchun
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
        # Bu qator botni o'chmaguncha kutib turadi (while True o'rniga)
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(start_bot())


