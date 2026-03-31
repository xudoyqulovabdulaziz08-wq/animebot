#========= core.py =========
import os
import logging
import time
import orjson
import ssl
from sqlalchemy import text
import redis.asyncio as redis

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# .env yuklash
load_dotenv()

logger = logging.getLogger(__name__)

# ================= DATABASE =================

def get_database_url():
    url = os.getenv("DATABASE_URL")
    
    # 1. Agar tayyor URL bo‘lsa
    if url:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

        return url  # 🔥 MUHIM

    # 2. Agar yo‘q bo‘lsa — qismlardan yig‘amiz
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME")

    if not all([user, password, host, name]):
        raise ValueError("DATABASE_URL yoki DB_ ma'lumotlari topilmadi!")

    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}?ssl=require"


DATABASE_URL = get_database_url()

# SSL context (production uchun)
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

connect_args = {}

if "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL:
    connect_args["ssl"] = ssl_ctx

engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=5,
    pool_recycle=1800,
    pool_pre_ping=True,
    connect_args=connect_args
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# ================= REDIS =================

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", 6379)
REDIS_PASS = os.getenv("REDIS_PASSWORD", "")
REDIS_USER = os.getenv("REDIS_USER", "default")

if REDIS_PASS:
    VALKEY_URL = f"redis://{REDIS_USER}:{REDIS_PASS}@{REDIS_HOST}:{REDIS_PORT}/0"
else:
    VALKEY_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"


class RedisCache:
    def __init__(self, url):
        self.client = redis.from_url(
            url,
            decode_responses=False,
            max_connections=50,
            socket_timeout=5,
            health_check_interval=30
        )
        self._last_error_log = 0

    async def get(self, key):
        try:
            data = await self.client.get(key)
            if data is None:
                return None

            try:
                return orjson.loads(data)
            except orjson.JSONDecodeError:
                await self.client.delete(key)  # 🔥 corrupted cache clean
                return None

        except Exception as e:
            self._log_error(e)
            return None

    async def set(self, key, value, ttl=1800):
        try:
            await self.client.set(key, orjson.dumps(value), ex=ttl)
        except Exception as e:
            self._log_error(e)

    async def delete(self, key):
        try:
            await self.client.delete(key)
        except Exception as e:
            self._log_error(e)

    async def expire(self, key, ttl):
        try:
            await self.client.expire(key, ttl)
        except Exception as e:
            self._log_error(e)

    def _log_error(self, e):
        now = time.time()
        if now - self._last_error_log > 300:
            logger.warning(f"Redis error: {e}")
            self._last_error_log = now

    async def close(self):
        try:
            await self.client.aclose()
        except Exception:
            await self.client.close()


bot_cache = RedisCache(VALKEY_URL)

#=======================================================================================================

async def sync_user(user_id: int):
    cache_key = f"u:{user_id}"

    # ================= CACHE =================
    cached = await bot_cache.get(cache_key)
    if cached:
        return cached

    # ================= DATABASE =================
    async with SessionLocal() as session:
        try:
            upsert_sql = text("""
                INSERT INTO users (user_id, status)
                VALUES (:uid, 'active')
                ON CONFLICT (user_id) 
                DO UPDATE SET user_id = EXCLUDED.user_id
                RETURNING user_id, status
            """)

            result = await session.execute(upsert_sql, {"uid": user_id})
            user = result.fetchone()

            await session.commit()

        except Exception as e:
            await session.rollback()
            logger.error(f"Sync user DB error: {e}")
            return None

    if not user:
        return None

    data = {
        "id": user[0],
        "st": user[1]
    }

    # ================= CACHE SET =================
    try:
        await bot_cache.set(cache_key, data, ttl=1800)
    except Exception as e:
        logger.warning(f"Cache set error: {e}")

    return data

#=======================================================================================================


    
#=======================================================================================================

async def on_startup(app):
    """Bot ishga tushganda"""
    logger.info("🚀 Bot ishga tushmoqda...")

    # ================= REDIS CHECK =================
    try:
        await bot_cache.client.ping()
        logger.info("✅ Valkey/Redis ulandi")
    except Exception as e:
        logger.warning(f"⚠️ Redis mavjud emas, cache o'chirilgan: {e}")

    logger.info("🔥 Bot tayyor!")


async def on_shutdown(app):
    """Bot to'xtaganda"""
    logger.info("💤 Bot to'xtatilmoqda...")

    # ================= REDIS CLOSE =================
    try:
        await bot_cache.close()
        logger.info("✅ Redis yopildi")
    except Exception as e:
        logger.warning(f"Redis close error: {e}")

    # ================= DB CLOSE =================
    try:
        await engine.dispose()
        logger.info("✅ DB pool yopildi")
    except Exception as e:
        logger.warning(f"DB dispose error: {e}")

    logger.info("🧹 Tozalash tugadi. Bot o'chdi.")