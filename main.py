import os
import sys
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler
from config import TOKEN
from telegram.ext import CallbackQueryHandler


from telegram.ext import MessageHandler, filters
from handlers.user import (
    start,
    cabinet_handler,
    search_anime_handler,
    search_callback_handler,
    handle_user_input,
    handle_photo_input
    
)
from handlers.anime import (
    show_episodes,
    video_handler,
    show_anime_details_callback
)

# Importni xavfsiz qilish
try:
    from database.db import engine
except ImportError:
    try:
        from db import engine
    except:
        engine = None

import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram import Update

async def start_bot():
    """Botni sozlash va ishga tushirish funksiyasi"""
    
    # Application yaratish
    application = ApplicationBuilder().token(TOKEN).build()

    # 1. Buyruqlar (Har doim birinchi)
    application.add_handler(CommandHandler("start", start))

    # 2. Maxsus matnli tugmalar (Exact Match)
    # Bular handle_user_input dan TEPADA bo'lishi shart!
    application.add_handler(MessageHandler(filters.Text("👤 Shaxsiy Kabinet"), cabinet_handler))
    application.add_handler(MessageHandler(filters.Text("🔍 Anime qidirish 🎬"), search_anime_handler))

    # 3. Callbacklar (Tugmalar)
    application.add_handler(CallbackQueryHandler(search_callback_handler, pattern=r"^search_type_|^cancel_search|^back_to_search_main"))
    application.add_handler(CallbackQueryHandler(show_episodes, pattern=r"^show_episodes_|^episodes_"))
    application.add_handler(CallbackQueryHandler(video_handler, pattern=r"^video_"))
    application.add_handler(CallbackQueryHandler(show_anime_details_callback, pattern=r"^info_"))
    application.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.message.delete(), pattern="delete_msg"))

    # 4. Umumiy matn ushlagich (Catch-all text)
    # Bu eng PASTDA bo'lishi kerak. Shunda u menyu tugmalarini "yeb qo'ymaydi".
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_input))

    # --- Render uchun MUHIM qism ---
    async with application:
        await application.initialize()
        await application.start()
        
        # start_polling() ishlatilganda, stop_signals=None Render'dagi signal xatolarini oldini oladi
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
        print("🤖 Bot muvaffaqiyatli ishga tushdi (Polling)...")
        
        # Botni to'xtovsiz ushlab turish (Event wait - eng xavfsiz usul)
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            print("🛑 Bot to'xtatilmoqda...")
        finally:
            await application.stop()
            await application.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(start_bot())
    except Exception as e:
        print(f"❌ Xatolik yuz berdi: {e}")









