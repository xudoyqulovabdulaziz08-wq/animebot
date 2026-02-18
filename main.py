import os
import sys
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ConversationHandler
from config import TOKEN
from database.db import init_databases
from handlers.user import (
    start,
    cabinet_handler,
    search_anime_handler,
    search_callback_handler,
    handle_user_input,
    handle_photo_input
    
)
from handlers.anime import (
    DATA,
    POSTER,
    VIDEO,
    finish_handler,
    get_anime_data,
    get_episodes,
    get_poster,
    publish_handler,
    show_episodes,
    start_add_anime,
    video_handler,
    show_anime_details_callback,
    admin_list_anime,
    admin_view_anime
)
from handlers.admin import (
    admin_panel_handler

)

from keyboard.anime_kb import(
    anime_control_menu
)



async def start_bot():
    """Botni sozlash va ishga tushirish funksiyasi"""
    
    print("⏳ Bazalar tekshirilmoqda...")
    # 1. 7 ta bazada jadvallarni avtomatik yaratish
    await init_databases()
    print("✅ Bazalar tayyor!")


    # Application yaratish
    application = ApplicationBuilder().token(TOKEN).build()

    # 1. Buyruqlar (Har doim birinchi)
    application.add_handler(CommandHandler("start", start))

    # 2. Maxsus matnli tugmalar (Exact Match)
    application.add_handler(MessageHandler(filters.Text("👤 Shaxsiy Kabinet"), cabinet_handler))
    application.add_handler(MessageHandler(filters.Text("🔍 Anime qidirish 🎬"), search_anime_handler))
    application.add_handler(MessageHandler(filters.Text(["👨‍💼 Admin Panel", "🛠 ADMIN PANEL"]), admin_panel_handler))

    # 3. CONVERSATION HANDLER (Buni barcha umumiy Callback'lardan TEPAGA qo'yamiz)
    anime_add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_anime, pattern="^admin_add_anime$")],
        states={
            POSTER: [MessageHandler(filters.PHOTO | filters.Document.IMAGE, get_poster)],
            DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_anime_data)],
            VIDEO: [
                MessageHandler(filters.VIDEO | filters.Document.VIDEO, get_episodes), # <-- Bu yerda video va hujjat formatidagi videolarni qabul qilish uchun filter qo'shildi
                CallbackQueryHandler(finish_handler, pattern="^finish_add$"),   # <-- Bu yerda "finish_add" patterni qo'shildi, bu tugma bosilganda anime qo'shish jarayoni tugaydi
                CallbackQueryHandler(publish_handler, pattern="^publish_to_channel$") # <-- Bu yerda "publish_to_channel" patterni qo'shildi, bu tugma bosilganda anime kanallarga joylanadi
            ],
        },
        fallbacks=[CallbackQueryHandler(finish_handler, pattern="^adm_ani_ctrl$")], # <-- Bu yerda "adm_ani_ctrl" patterni qo'shildi, bu tugma bosilganda konversatsiya tugaydi va anime boshqaruv menyusiga qaytadi
        allow_reentry=True
    )
    # MUHIM: Bu barcha adm_ bilan boshlanuvchi callbacklardan oldin qo'shilishi kerak
    application.add_handler(anime_add_conv)

    # 4. Aniq patternli Callbacklar
    application.add_handler(CallbackQueryHandler(search_callback_handler, pattern=r"^search_type_|^cancel_search|^back_to_search_main")) # <-- Bu yerda "back_to_search_main" patterni qo'shildi, bu tugma bosilganda qidiruv bosh menyusiga qaytadi
    application.add_handler(CallbackQueryHandler(anime_control_menu, pattern=r"^adm_ani_ctrl|^back_to_admin_main")) # <-- Bu yerda "back_to_admin_main" patterni qo'shildi, bu tugma bosilganda admin boshqaruv menyusiga qaytadi
    application.add_handler(CallbackQueryHandler(admin_list_anime, pattern=r"^admin_list_anime")) # <-- Bu yerda "admin_list_anime" patterni qo'shildi, bu tugma bosilganda barcha animelarni ko'rsatadi
    application.add_handler(CallbackQueryHandler(admin_view_anime, pattern=r"^adm_v_")) # <-- Bu yerda "adm_v_" patterni qo'shildi, bu tugma bosilganda tanlangan animeni ko'rsatadi
    application.add_handler(CallbackQueryHandler(show_episodes, pattern=r"^show_episodes_|^episodes_")) # <-- Bu yerda "episodes_" patterni qo'shildi, bu tugma bosilganda epizodlarni ko'rsatadi
    application.add_handler(CallbackQueryHandler(video_handler, pattern=r"^video_")) # <-- Bu yerda "video_" patterni qo'shildi, bu tugma bosilganda epizod videosini ko'rsatadi
    application.add_handler(CallbackQueryHandler(show_anime_details_callback, pattern=r"^info_")) # <-- Bu yerda "info_" patterni qo'shildi, bu tugma bosilganda anime tafsilotlarini ko'rsatadi
    
    # 5. Umumiy Callbacklar (Eng oxirida bo'lishi shart)
    application.add_handler(CallbackQueryHandler(admin_panel_handler, pattern=r"^adm_|admin_menu")) # <-- Bu yerda "admin_menu" patterni qo'shildi
    application.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.message.delete(), pattern="delete_msg")) # Oddiy "delete_msg" patterni qo'shildi, bu tugma bosilganda xabarni o'chiradi

    # 6. Umumiy Message handlerlar
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input)) # <-- Bu yerda umumiy matnli xabarlar uchun handler qo'shildi, bu handler barcha matnli xabarlarni qabul qiladi va handle_user_input funksiyasiga yuboradi
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_input)) # <-- Bu yerda umumiy rasmli xabarlar uchun handler qo'shildi, bu handler barcha rasmli xabarlarni qabul qiladi va handle_photo_input funksiyasiga yuboradi

    # --- Render va Polling qismi ---
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
        print("🤖 Bot muvaffaqiyatli ishga tushdi...")
        
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











