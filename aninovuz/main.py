import os
import asyncio
import logging
import orjson
from contextlib import suppress
from aiohttp import web

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ================= YANGI ARXITEKTURA IMPORTLARI =================
from config import config
from database.connection import AsyncSessionLocal, engine, check_db
from database.events import attach_cache_listeners
from database.cache import cache_manager

# Workerlarni o'zingiz joylagan fayldan import qiling (masalan: workers.py)
from services.cache_worker import CacheInvalidationWorker
from services.outbox.worker import OutboxWorker 

# Middleware'lar (Oldingi qadamlarda to'g'irlangan fayllardan)
from middlewares.middlewere import DbSessionMiddleware
from middlewares.subscription import CheckSubscriptionMiddleware
from repositories.channel_repository import ChannelRepository # kerak bo'lsa

from routers import main_router

logger = logging.getLogger("Main")
logging.basicConfig(level=logging.INFO)

# ================= GLOBAL STATE =================
background_tasks: set[asyncio.Task] = set()
valkey = cache_manager  # Eski kod bilan moslik uchun alias


# =========================================================
# 🧠 AI CACHE BRAIN v2 (HOOK LAYER)
# =========================================================
class AICacheBrain:
    """
    🔥 USER BEHAVIOR LEARNING + PREDICTIVE CACHE
    """
    def __init__(self):
        self.user_stats = {}
        self.hot_users = set()

    async def observe(self, user_id: int, action: str):
        stat = self.user_stats.setdefault(user_id, {
            "hits": 0,
            "miss": 0,
            "actions": []
        })

        stat["actions"].append(action)
        stat["hits"] += 1

        if stat["hits"] > 50:
            self.hot_users.add(user_id)

    def predict_warm(self, user_id: int) -> bool:
        return user_id in self.hot_users


ai_brain = AICacheBrain()


# =========================================================
# 🚀 WORKER BOOTSTRAP
# =========================================================
async def start_workers():
    """Fonda ishlovchi distributed workerlarni xavfsiz ishga tushirish"""
    outbox = OutboxWorker(AsyncSessionLocal)
    cache = CacheInvalidationWorker(AsyncSessionLocal)

    async def safe(name, coro):
        try:
            logger.info(f"🚀 Worker starting: {name}")
            await coro
        except asyncio.CancelledError:
            logger.info(f"ℹ️ System release signal received. Gracefully closing {name}...")
        except Exception as e:
            logger.error(f"💥 Worker crash {name}: {e}")

    # Workerlarni alohida asyncio task qilib fonda yuritish
    tasks = [
        asyncio.create_task(safe("outbox", outbox.start())),
        asyncio.create_task(safe("cache", cache.run())),
    ]

    for t in tasks:
        background_tasks.add(t)
        t.add_done_callback(background_tasks.discard)

    logger.info("🚀 All background workers deployed successfully.")


# =========================================================
# 🧠 SYSTEM MONITOR & RENDER KEEP-ALIVE
# =========================================================
async def system_monitor():
    """Tizim barqarorligini tekshiruvchi asinxron monitor"""
    while True:
        try:
            # Render resurslarini tejash uchun 30 soniyalik interval
            await asyncio.sleep(30) 

            # AI cache prediction trigger Logics
            hot_list = list(ai_brain.hot_users)
            if hot_list:
                for uid in hot_list[:10]:
                    if ai_brain.predict_warm(uid):
                        pass # Pre-warming mantig'i kerak bo'lsa shu yerga yoziladi

            # Valkey/Redis health check
            if valkey.redis and getattr(valkey, 'is_alive', True):
                await valkey.redis.ping()

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"⚠️ System Monitor issue: {e}")


# =========================================================
# ⚡ STARTUP & SHUTDOWN HANDLERS
# =========================================================
async def on_startup(bot: Bot):
    logger.info("⚡ SYSTEM BOOTING ULTRA MODE")

    # 1. Eski webhooklarni tozalash
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("🧹 Pending updates cleared from Telegram servers.")
    except Exception as e:
        logger.error(f"❌ Error deleting webhook: {e}")

    # 2. Core infratuzilmalarni parallel ulash
    try:
        await asyncio.gather(
            check_db(),
            valkey.start() if hasattr(valkey, 'start') else asyncio.sleep(0)
        )
        logger.info("🔋 Database and Valkey storage systems connected.")
    except Exception as e:
        logger.critical(f"💥 Core Infrastructure Failure: {e}")
        raise e
    try:
        if valkey.redis:
            await valkey.redis.flushdb()
            logger.warning("🧹 Deploy: Valkey cache cleared.")
    except Exception as e:
        logger.error(f"Cache clear failed: {e}")
    # 3. DB sxemalarni sinxronizatsiya qilish
    try:
        async with engine.begin() as conn:
            from database.models import Base
            await conn.run_sync(Base.metadata.create_all)
        logger.info("📚 Database schemas verified.")
    except Exception as e:
        logger.error(f"⚠️ Database sync warning: {e}")

    # 4. Kesh tinglovchilarini ulash (Event Listeners)
    attach_cache_listeners()

    # 5. Workerlarni ishga tushirish
    await start_workers()

    # 6. Telegram Webhook o'rnatish
    if not config.WEBHOOK_URL:
        logger.critical("❌ WEBHOOK_URL is missing in configuration!")
        raise RuntimeError("WEBHOOK_URL environment variable is required!")

    try:
        await bot.set_webhook(
            url=config.WEBHOOK_URL,
            allowed_updates=["message", "callback_query"]
        )
        logger.info(f"📡 Webhook registered successfully at: {config.WEBHOOK_URL}")
    except Exception as e:
        logger.critical(f"💥 Failed to set webhook: {e}")
        raise e

    # 7. Monitoringni fonda yoqish
    monitor_task = asyncio.create_task(system_monitor())
    background_tasks.add(monitor_task)
    monitor_task.add_done_callback(background_tasks.discard)

    logger.info("🌍 ANIMNOWUZ PLATFORM IS ONLINE & FULLY OPERATIONAL")


async def on_shutdown(bot: Bot):
    logger.info("🛑 SHUTDOWN SEQUENCE INITIATED")

    # 1. Barcha fondagi tasklarni bekor qilish
    for t in background_tasks:
        t.cancel()

    with suppress(Exception):
        await asyncio.gather(*background_tasks, return_exceptions=True)

    # 2. Resurslarni xavfsiz yopish
    if hasattr(valkey, 'stop'):
        await valkey.stop()
    await engine.dispose()
    await bot.session.close()

    logger.info("✅ CLEAN SHUTDOWN COMPLETE. SYSTEM OFFLINE.")


# =========================================================
# 🚀 MAIN ENTRY (AIOHTTP ARCHITECTURE FOR RENDER)
# =========================================================
def main():
    # 1. Bot va bitta unifikatsiyalangan Dispatcher yaratish
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    
    # 2. MIDDLEWARE'LARNI ULAB QO'YISH
    # Yangi arxitekturaga mos xavfsiz parametrlar bilan chaqiriladi
    dp.update.outer_middleware(DbSessionMiddleware(session_pool=AsyncSessionLocal))
    dp.update.outer_middleware(CheckSubscriptionMiddleware())

    # 3. Routerlarni global dispatcherga ulash
    dp.include_router(main_router)

    # 4. Startup va Shutdown signallarini ro'yxatdan o'tkazish
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # 5. Asosiy Web Application yaratish (AIOHTTP)
    app = web.Application()

    # 🚀 RENDER UCHUN MAJBURIY HEALTH CHECK 
    # UptimeRobot yoki shunga o'xshash xizmat orqali har 5 daqiqada shu URL'ga ping tashlab turilsa, Render uxlab qolmaydi.
    async def render_health_check(request):
        return web.Response(text="AniNowuz Bot is live and healthy!", status=200)
    app.router.add_get('/', render_health_check)

    # 6. ADMIN DASHBOARD ENDPOINTLARI
    async def admin_health(_):
        return web.json_response({"status": "ok", "mode": "ultra", "engine": "Valkey-AI-CacheFirst"})

    async def cache_metrics(_):
        l1_size = 0
        if hasattr(valkey, "_l1_cache"):
            l1_size = len(getattr(valkey, "_l1_cache"))
        
        return web.json_response({
            "cache_alive": getattr(valkey, 'is_alive', False),
            "l1_size": l1_size,
        })

    async def worker_status(_):
        return web.json_response({
            "active_tasks_count": len(background_tasks)
        })

    async def dlq_view(_):
        try:
            if valkey.redis:
                # Xatoliklar yig'iladigan navbatni xavfsiz tekshirish
                data = await valkey.redis.lrange("{app}:outbox:dlq", 0, 49)
                
                cleaned_data = []
                for d in data:
                    try:
                        cleaned_data.append(orjson.loads(d))
                    except Exception:
                        cleaned_data.append(d.decode("utf-8")) 
                
                return web.json_response(cleaned_data)
                
            return web.json_response({"error": "Valkey disconnected"}, status=503)
        except Exception as e:
            logger.error(f"Error in admin dlq endpoint: {e}")
            return web.json_response({"error": str(e)}, status=500)

    # Admin routerlarini asosiy ilovaga qo'shish
    app.router.add_get("/admin/health", admin_health)
    app.router.add_get("/admin/metrics/cache", cache_metrics)
    app.router.add_get("/admin/metrics/workers", worker_status)
    app.router.add_get("/admin/dlq", dlq_view)

    # 7. Webhook Handler integratsiyasi
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=config.WEBHOOK_PATH) 
    
    # Aiogram kontekstini aiohttp ilovasiga xavfsiz bog'lash
    setup_application(app, dp, bot=bot)

    # 8. Render PORT binding sozlamasi
    # Render o'zi dynamik port beradi, shu portni eshitish shart!
    server_port = int(os.getenv("PORT", config.PORT))
    logger.info(f"🚀 SERVER STARTING ON PORT {server_port}")
    
    # Ilovani ishga tushirish
    web.run_app(app, host="0.0.0.0", port=server_port)


if __name__ == "__main__":
    main()