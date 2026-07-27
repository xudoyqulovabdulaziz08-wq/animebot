import asyncio
import time
import logging
import copy
import inspect
from collections import OrderedDict
from typing import Any, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import User
from sqlalchemy.ext.asyncio import async_sessionmaker

# Endi to'g'ridan-to'g'ri Repository yoki Valkey emas, Service chaqiriladi!
from services.user_service import UserService 
from services.orchestrator import state
from services.data_service import DataService
logger = logging.getLogger("DbMiddleware")


# ======================================================
# 🔥 L1 CACHE (LRU IN-MEMORY - EXTREME SPEED)
# ======================================================
class L1Cache:
    def __init__(self, max_size: int = 5000):
        self.max_size = max_size
        self._cache = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key) -> Optional[Dict[str, Any]]:
        async with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return copy.deepcopy(self._cache[key])

    async def set(self, key, value):
        async with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = copy.deepcopy(value)
            if len(self._cache) > self.max_size:
                removed = self._cache.popitem(last=False)
                logger.debug(f"🧹 L1 cache evicted: user_id={removed[0]}")
    async def delete(self, key):
        async with self._lock:
            self._cache.pop(key, None)

            
# Global state initsializatsiyasi
if getattr(state, 'user_l1_cache', None) is None:
    state.user_l1_cache = L1Cache(max_size=5000)
if not hasattr(state, 'db_status'): state.db_status = True
if not hasattr(state, 'db_fail_count'): state.db_fail_count = 0
if not hasattr(state, 'db_last_retry'): state.db_last_retry = 0.0
if not hasattr(state, 'db_lock'): state.db_lock = asyncio.Lock()
if not hasattr(state, 'cb_threshold'): state.cb_threshold = 5
if not hasattr(state, 'cb_recovery_time'): state.cb_recovery_time = 30.0

# ======================================================
# 🔥 SAFE SESSION PROXY
# ======================================================
class SafeSession:
    """
    🧠 Aqlli Lazy Proxy. Faqat kerak bo'lganda bazaga ulanadi.
    """
    def __init__(self, session=None, session_pool=None):
        self.__dict__["_session"] = session
        self.__dict__["_session_pool"] = session_pool

    async def commit(self):
        if self._session is not None:
            await self._session.commit()
            logger.debug("💾 [DB PROXY] Global commit muvaffaqiyatli bajarildi.")

    async def rollback(self):
        if self._session is not None:
            await self._session.rollback()
            logger.warning("🔄 [DB PROXY] Rollback bajarildi.")

    async def _ensure_session(self):
        if self._session is None:
            if self._session_pool is None:
                raise RuntimeError("❌ DB session is None va session_pool berilmagan.")
            self.__dict__["_session"] = self._session_pool()
            logger.debug("⚡ Lazy Loading: Dinamik sessiya ochildi.")
        return self._session

    def __getattr__(self, item):
        if self._session is not None:
            return getattr(self._session, item)

        def lazy_wrapper(*args, **kwargs):
            async def async_executor():
                sess = await self._ensure_session()
                attr = getattr(sess, item)
                if inspect.iscoroutinefunction(attr):
                    return await attr(*args, **kwargs)
                return attr(*args, **kwargs) if callable(attr) else attr
            return async_executor()
        return lazy_wrapper

    async def close(self):
        if self._session is not None:
            await self._session.close()
            self.__dict__["_session"] = None


# ======================================================
# 🔥 MIDDLEWARE CORE
# ======================================================
class DbSessionMiddleware(BaseMiddleware):

    def __init__(self, session_pool: async_sessionmaker):
        self.session_pool = session_pool
        super().__init__()

    async def __call__(self, handler, event, data):
        user_obj: Optional[User] = data.get("event_from_user")
        
        # 1. Global DB Proxy yaratamiz
        session_proxy = SafeSession(session_pool=self.session_pool)
        data["session"] = session_proxy
        
        # 2. Service obyektini yaratamiz (Inyeksiyaga tayyor)
        user_service = UserService(session=session_proxy)
        data_service = DataService(session=session_proxy)
        data["user_service"] = user_service  # Handlerlar to'g'ridan-to'g'ri ishlata oladi
        data["data_service"] = data_service
        
        try:
            # Fallback: Agar foydalanuvchi obyekti yo'q bo'lsa (System/Channel/Chat)
            if not user_obj:
                data["user"] = self._emergency_user(0, "System", True)
                return await handler(event, data)
            
            user_id = user_obj.id

            # ======================================================
            # 🚀 LEVEL 1: IN-MEMORY CACHE (ULTRA FAST)
            # ======================================================
            # ✅ TO'G'RI: await olib tashlandi
            cached_l1 = await state.user_l1_cache.get(user_id)
            if cached_l1:
                # Username o'zgargan bo'lsa L1 ni yangilaymiz (L2 keyingi so'rovda yangilanadi)
                if (cached_l1.get("username") or "") != (user_obj.username or ""):
                    cached_l1["username"] = user_obj.username
                    await state.user_l1_cache.set(user_id, cached_l1)

                data["user"] = cached_l1
                asyncio.create_task(self._touch_last_active(user_id))
                return await handler(event, data)

            # ======================================================
            # 🛡️ CIRCUIT BREAKER CHECK
            # ======================================================
            async with state.db_lock:
                if not state.db_status:
                    if time.time() - state.db_last_retry < state.cb_recovery_time:
                        logger.warning(f"🚫 DB blocked (Circuit Open). Emergency mode: {user_id}")
                        data["user"] = self._emergency_user(user_obj.id, user_obj.username, True)
                        return await handler(event, data)
                    else:
                        logger.info("🔄 Circuit Breaker: HALF-OPEN. Bazani sinab ko'ramiz...")
                        state.db_status = True
                        state.db_fail_count = 0

            # ======================================================
            # 🎯 LEVEL 2 & 3: L2 CACHE OR DB (VIA SERVICE LAYER)
            # ======================================================
            try:
                async with asyncio.timeout(10.0):
                    # Service orqali keshdan yoki bazadan olamiz
                    user_data = await user_service.get_user(user_id)
                    
                    if not user_data:
                        # Bazada ham yo'q bo'lsa, yaratamiz (get_or_create Service ichida L2 ni yozadi)
                        user_data = await user_service.get_or_create_user(user_obj)

                await self._reset_circuit_breaker()

                # Kelajakdagi tezkor so'rovlar uchun L1 ga yozamiz
                # ✅ TO'G'RI: Standart OrderedDict uslubida ma'lumot yozish (await-siz)
                await state.user_l1_cache.set(user_id, user_data)
                asyncio.create_task(self._touch_last_active(user_id))
                data["user"] = copy.deepcopy(user_data)
                
                # Handler ishga tushadi
                result = await handler(event, data)
                
                # Agar handler ishida session ishlatilgan bo'lsa, xavfsiz tasdiqlash
                await session_proxy.commit()
                return result

            except Exception as e:
                await session_proxy.rollback()
                await self._handle_db_failure(e)
                logger.exception(f"❌ DB CORE ERROR user_id={user_id}: {e}")
                
                data["user"] = self._emergency_user(user_obj.id, user_obj.username, True)
                return await handler(event, data)

        finally:
            # ======================================================
            # 🧹 GLOBAL CLEANUP (NO MEMORY LEAKS)
            # ======================================================
            try:
                await session_proxy.close()
            except Exception as e:
                logger.debug(f"Proxy close error: {e}")
            
            data.pop("session", None)
            data.pop("user_service", None)

    # --- INTERNAL HELPERS ---
    def _emergency_user(self, uid: int, username: str, is_sys: bool = False) -> Dict[str, Any]:
        return {
            "user_id": uid,
            "username": username,
            "status": "user",
            "points": 0,
            "is_vip": False,
            "vip_expire_date": None,
            "is_system": is_sys,
            "is_emergency": True
        }

    async def _reset_circuit_breaker(self):
        async with state.db_lock:
            if not state.db_status or state.db_fail_count > 0:
                logger.info("🎉 DB connection is healthy. Circuit CLOSED.")
                state.db_fail_count = 0
                state.db_status = True

    async def _touch_last_active(self, user_id: int):
        from database.cache import valkey
        from sqlalchemy import text
        try:
            if not valkey.redis:
                return
            was_new = await valkey.redis.set(f"active:{user_id}", "1", nx=True, ex=600)
            if not was_new:
                return  # oxirgi 10 daqiqada allaqachon yozilgan

            async with self.session_pool() as s:
                await s.execute(
                    text("UPDATE users SET last_active_at = now() WHERE user_id = :uid"),
                    {"uid": user_id}
                )
                await s.commit()
        except Exception as e:
            logger.debug(f"last_active touch error: {e}")

    async def _handle_db_failure(self, e):
        async with state.db_lock:
            state.db_fail_count += 1
            if state.db_fail_count >= state.cb_threshold:
                state.db_status = False
                state.db_last_retry = time.time()
                logger.critical("🚨 CIRCUIT BREAKER OPENED: Baza quladi!")