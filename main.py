import os
import sys
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler
from config import TOKEN

from telegram.ext import MessageHandler, filters
from handlers.user import  start, cabinet_handler

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
    
    # Application yaratish
    application = ApplicationBuilder().token(TOKEN).build()

    # Handlerlarni qo'shish
    application.add_handler(CommandHandler("start", start))

    application.add_handler(MessageHandler(filters.Text("👤 Shaxsiy Kabinet"), cabinet_handler))

    print("🤖 Bot polling rejimida ishlamoqda...")
    
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

