import asyncio
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
)
from utils import keep_alive, init_db_pool, db_pool
from handlers import (
    start, search_menu_cmd, admin_panel_text_handler, start_profile_creation, add_comment_callback,
    admin_channels_menu, admin_ch_callback_handler, anime_control_panel, admin_stats_logic,
    check_ads_pass, export_all_anime, admin_control, search_anime_logic, handle_callback,
    list_animes_view, add_anime_panel, remove_menu_handler, select_ani_for_new_ep, get_poster_handler, save_ani_handler, handle_ep_uploads,
    exec_add_channel, exec_rem_channel, ads_send_finish, save_comment_handler, feedback_subject_callback, feedback_message_handler, show_selected_anime, view_comments_handler, add_favorite_handler, process_redeem, search_anime_by_photo, admin_reply_handler, show_user_cabinet, feedback_start, show_bonus, show_guide, vip_pass_info, auto_check_notifications, delete_expired_ads, recheck_callback, handle_pagination, pagination_handler, get_episode_handler  
)
from config import BOT_TOKEN, ADMIN_GROUP_ID
from logger import logger, s
from flask_app import app
from states import A_MAIN, A_ANI_CONTROL, A_GET_POSTER, A_GET_DATA, A_ADD_EP_FILES, A_ADD_CH, A_REM_CH, A_SEND_ADS_PASS, A_SEND_ADS_MSG, U_ADD_COMMENT, U_FEEDBACK_SUBJ, U_FEEDBACK_MSG, A_SEARCH_BY_ID, A_SEARCH_BY_NAME


async def main():
    # 1. Serverni uyg'oq saqlash (Keep-alive mantiqi)
    keep_alive() 

    # 2. Ma'lumotlar bazasini ishga tushirish
    try:
        await init_db_pool() 
        if db_pool is None:
            logger.error("🛑 Baza ulanmadi (pool is None)!")
            return
        logger.info("✅ Ma'lumotlar bazasi asinxron ulandi.")
    except Exception as e:
        logger.error(f"🛑 Baza ulanishida xato: {e}")
        return

    # 3. Applicationni qurish
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # 4. Menyu filtri (Regex) - Klaviaturadagi tugmalar uchun
    menu_filter = filters.Regex(
        "Anime qidirish|VIP PASS|Bonus ballarim|Qo'llanma|Barcha anime ro'yxati|ADMIN PANEL|Bekor qilish|"
        "🎙 Fandablar|❤️ Sevimlilar|🤝 Do'st orttirish|Rasm orqali qidirish"
    )
    
    # 5. Conversation Handler (Botning asosiy mantiqiy zanjiri)
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex(r"Anime qidirish"), search_menu_cmd),
            MessageHandler(filters.Regex(r"ADMIN PANEL"), admin_panel_text_handler),
            MessageHandler(filters.Regex(r"🤝 Do'st orttirish"), start_profile_creation),
            CallbackQueryHandler(add_comment_callback, pattern="^comment_"),
        ],
        states={
            # ADMIN PANEL ASOSIY HOLATI
            A_MAIN: [
                CallbackQueryHandler(admin_channels_menu, pattern="^adm_ch$"),
                CallbackQueryHandler(admin_ch_callback_handler, pattern="^(add_ch_start|rem_ch_start)$"),
                CallbackQueryHandler(anime_control_panel, pattern="^adm_ani_ctrl$"),
                CallbackQueryHandler(admin_stats_logic, pattern="^adm_stats$"),
                CallbackQueryHandler(check_ads_pass, pattern="^adm_ads_start$"),
                CallbackQueryHandler(export_all_anime, pattern="^adm_export$"),
                CallbackQueryHandler(admin_control, pattern="^manage_admins$"),
                MessageHandler(filters.Regex("Anime boshqaruvi"), anime_control_panel),
                CallbackQueryHandler(search_anime_logic, pattern="^search_type_"),
                CallbackQueryHandler(handle_callback),
            ],
            
            # ANIME BOSHQARUVI ICHKI MENYUSI
            A_ANI_CONTROL: [
                MessageHandler(filters.Regex("Anime List"), list_animes_view),
                MessageHandler(filters.Regex("Yangi anime"), add_anime_panel),
                MessageHandler(filters.Regex("Anime o'chirish"), remove_menu_handler),
                MessageHandler(filters.Regex("Yangi qism qo'shish"), select_ani_for_new_ep),
                MessageHandler(filters.Regex("Orqaga"), admin_panel_text_handler),
                CallbackQueryHandler(handle_callback),
            ],

            # MA'LUMOTLARNI QABUL QILISH HOLATLARI
            A_GET_POSTER: [
                MessageHandler(filters.PHOTO, get_poster_handler), 
                CallbackQueryHandler(handle_callback)
            ],
            A_GET_DATA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_filter, save_ani_handler), 
                CallbackQueryHandler(handle_callback)
            ],
            A_ADD_EP_FILES: [
                MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_ep_uploads),
                CallbackQueryHandler(handle_callback)
            ],
            A_ADD_CH: [MessageHandler(filters.TEXT & ~filters.COMMAND, exec_add_channel)],
            A_REM_CH: [MessageHandler(filters.TEXT & ~filters.COMMAND, exec_rem_channel)],
            A_SEND_ADS_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_ads_pass)],
            A_SEND_ADS_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, ads_send_finish)],
            
            # FOYDALANUVCHI INTERFEYSI
            U_ADD_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_comment_handler)],
            U_FEEDBACK_SUBJ: [CallbackQueryHandler(feedback_subject_callback, pattern="^subj_")],
            U_FEEDBACK_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_message_handler)],
            
            # QIDIRUV VA RO'YXATLAR
            A_SEARCH_BY_ID: [
                CallbackQueryHandler(show_selected_anime, pattern="^show_anime_"), 
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_filter, search_anime_logic),
                CallbackQueryHandler(handle_callback)
            ],
            A_SEARCH_BY_NAME: [
                CallbackQueryHandler(show_selected_anime, pattern="^show_anime_"), 
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~menu_filter, search_anime_logic),
                CallbackQueryHandler(handle_callback)
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^Bekor qilish$"), start),
            CallbackQueryHandler(start, pattern="^cancel_search$")
        ],
        allow_reentry=True,
        name="aninow_v103_persistent"
    )

    # 6. TAYMERNI (SCHEDULER) SOZLASH
    scheduler = AsyncIOScheduler()
    scheduler.add_job(auto_check_notifications, 'cron', hour=10, minute=0, args=[application])
    scheduler.add_job(delete_expired_ads, 'interval', minutes=15, args=[application])
    scheduler.start()

    # 7. HANDLERLARNI RO'YXATGA OLISH (TARTIB MUHIM!)
    
    # 7.1. Maxsus Callbacklar (Birinchi bo'lib mustaqil tugmalar)
    application.add_handler(CallbackQueryHandler(recheck_callback, pattern="^recheck$"))
    application.add_handler(CallbackQueryHandler(handle_pagination, pattern="^page_"))
    application.add_handler(CallbackQueryHandler(pagination_handler, pattern="^pg_"))
    application.add_handler(CallbackQueryHandler(get_episode_handler, pattern="^get_ep_"))
    application.add_handler(CallbackQueryHandler(show_selected_anime, pattern="^show_anime_"))
    application.add_handler(CallbackQueryHandler(view_comments_handler, pattern="^view_comm_"))
    application.add_handler(CallbackQueryHandler(add_favorite_handler, pattern="^fav_"))
    application.add_handler(CallbackQueryHandler(process_redeem, pattern="^redeem_"))

    # 7.2. CONVERSATION HANDLERNI QO'SHISH
    application.add_handler(conv_handler)

    # 7.3. MATNLI TUGMALAR (Keyboard)
    application.add_handler(MessageHandler(filters.Regex(r"Shaxsiy Kabinet"), show_user_cabinet))
    application.add_handler(MessageHandler(filters.Regex(r"Muxlislar Klubi"), start_profile_creation))
    application.add_handler(MessageHandler(filters.Regex(r"Murojaat & Shikoyat"), feedback_start))
    application.add_handler(MessageHandler(filters.Regex(r"Ballar & VIP"), show_bonus))
    application.add_handler(MessageHandler(filters.Regex(r"Barcha animelar"), export_all_anime))
    application.add_handler(MessageHandler(filters.Regex(r"Qo'llanma"), show_guide))
    application.add_handler(MessageHandler(filters.Regex(r"VIP PASS"), vip_pass_info))

    # 7.4. MEDIA VA ADMIN JAVOBI
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, search_anime_by_photo))
    application.add_handler(MessageHandler(filters.Chat(ADMIN_GROUP_ID) & filters.REPLY, admin_reply_handler))

    # 7.5. OXIRGI FALLBACK
    application.add_handler(CommandHandler("start", start))

    # 8. BOTNI ISHGA TUSHIRISH
    logger.info("🚀 Bot polling rejimida ishga tushdi...")
    
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__ == '__main__':
    # Flaskni alohida oqimda ishga tushirish (Render/Uptime uchun)
    from threading import Thread
    port = int(os.environ.get("PORT", 10000))
    
    def run_flask():
        try:
            app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
        except Exception as e:
            logger.error(f"Flask xatosi: {e}")

    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Botni ishga tushirish
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Bot to'xtatildi.")
    except Exception as e:
        logger.error(f"Kutilmagan xato: {e}")
