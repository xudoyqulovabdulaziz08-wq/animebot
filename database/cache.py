from __future__ import annotations

import asyncio
import logging
import socket
import uuid
import orjson
import os
import hashlib

from datetime import datetime, timezone, timedelta
from collections import OrderedDict
from typing import Any, Optional, Dict, List

import redis.asyncio as redis
from redis.exceptions import ResponseError

from config import config

logger = logging.getLogger("CacheManager")


# ======================================================
# 📊 METRICS
# ======================================================
class CacheMetrics:
    def __init__(self):
        self.l1_hits = 0
        self.l2_hits = 0
        self.misses = 0
        self.inflight_hits = 0
        self.errors = 0
        self.events_processed = 0

    def log(self):
        logger.info(
            f"📊 CACHE | L1:{self.l1_hits} L2:{self.l2_hits} MISS:{self.misses} "
            f"INF:{self.inflight_hits} ERR:{self.errors} EVT:{self.events_processed}"
        )


metrics = CacheMetrics()
 

# ======================================================
# 🧭 SHARDING
# ======================================================
class ShardRouter:
    def __init__(self, shards: int = 8):
        self.shards = shards

    def get_shard(self, key: str) -> int:
        return int(hashlib.sha256(key.encode()).hexdigest(), 16) % self.shards


sharder = ShardRouter()


# ======================================================
# 🚀 CACHE MANAGER
# ======================================================
class CacheManager:
    def __init__(self, url: str):
        self.namespace = "app"
        self.version = "v5"

        self.redis_url = url
        self.redis: Optional[redis.Redis] = None

        self.node_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"

        # L1 CACHE
        self._l1_cache: OrderedDict[str, tuple[Any, datetime]] = OrderedDict()
        self._l1_max_size = min(8000, max(2000, (os.cpu_count() or 2) * 1200))
        self._l1_lock = asyncio.Lock()

        # SINGLEFLIGHT
        self._inflight: Dict[str, asyncio.Future] = {}
        self._inflight_lock = asyncio.Lock()

        # STREAMS
        self._stream_name = "cache:invalidate"
        self._group_name = "cache_group"
        self._consumer = self.node_id
        self._replication_stream = "cache:replicate"

        self._main_stream_maxlen = 10000
        self._repl_stream_maxlen = 5000

        self.is_alive = True
        self._tasks: List[asyncio.Task] = []

    # ==================================================
    # CONNECT
    # ==================================================
    async def _connect(self):
        self.redis = redis.from_url(
            self.redis_url,
            max_connections=120,
            decode_responses=False,
            socket_keepalive=True,
            health_check_interval=30
        )

    async def start(self):
        await self._connect()
        await self.redis.ping()

        await self._ensure_stream_setup()

        self._tasks = [
            asyncio.create_task(self._stream_listener()),
            asyncio.create_task(self._pel_recovery()), # Bo'sh metod pastda yaratildi
            asyncio.create_task(self._l1_cleanup()),
            asyncio.create_task(self._metrics_logger()),
        ]

        logger.info(f"🚀 CACHE ONLINE [{self.node_id}]")

    # ==================================================
    # KEY ENGINE
    # ==================================================
    def _key(self, table: str, obj_id: Any) -> str:
        shard = sharder.get_shard(f"{table}:{obj_id}")
        return f"{self.namespace}:{shard}:{table}:{obj_id}:{self.version}"

    # ==================================================
    # L1 SET
    # ==================================================
    async def _set_l1(self, key: str, data: Any, ttl: int):
        exp = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        async with self._l1_lock:
            self._l1_cache[key] = (data, exp)
            self._l1_cache.move_to_end(key)

            if len(self._l1_cache) > self._l1_max_size:
                self._l1_cache.popitem(last=False)

    # ==================================================
    # CORE GET
    # ==================================================
    async def get(self, table: str, obj_id: Any):
        key = self._key(table, obj_id)
        now = datetime.now(timezone.utc)

        # L1
        async with self._l1_lock:
            if key in self._l1_cache:
                val, exp = self._l1_cache[key]
                if now < exp:
                    metrics.l1_hits += 1
                    self._l1_cache.move_to_end(key)
                    return val
                self._l1_cache.pop(key, None)

        # SINGLE FLIGHT
        async with self._inflight_lock:
            fut = self._inflight.get(key)
            if fut:
                metrics.inflight_hits += 1
                return await fut

            fut = asyncio.get_running_loop().create_future()
            self._inflight[key] = fut

        try:
            data = None

            if self.redis:
                raw = await self.redis.get(key)
                if raw:
                    data = orjson.loads(raw)
                    metrics.l2_hits += 1
                    await self._set_l1(key, data, 180)

            if not data:
                metrics.misses += 1

            if not fut.done():
                fut.set_result(data)

            return data

        except Exception as e:
            metrics.errors += 1
            if not fut.done():
                fut.set_result(None)
            logger.error(f"GET ERROR: {e}")
            return None

        finally:
            async with self._inflight_lock:
                self._inflight.pop(key, None)

    # ==================================================
    # SET
    # ==================================================
    async def set(self, table: str, obj_id: Any, data: dict, ttl: int = 3600):
        key = self._key(table, obj_id)

        try:
            raw = orjson.dumps(data)
            event_payload = orjson.dumps({"key": key, "action": "set"})

            if self.redis:
                async with self.redis.pipeline(transaction=True) as pipe:
                    pipe.setex(key, ttl, raw)
                    pipe.xadd(
                        self._stream_name,
                        {"data": event_payload},
                        maxlen=self._main_stream_maxlen,
                        approximate=True
                    )
                    await pipe.execute()

            await self._set_l1(key, data, min(ttl // 10, 180))

        except Exception as e:
            metrics.errors += 1
            logger.error(f"SET ERROR: {e}")

    # ==================================================
    # INVALIDATE 
    # ==================================================
    async def invalidate(self, table: str = None, obj_id: Any = None, broadcast: bool = True):
        if not table or not obj_id:
            return

        key = self._key(table, obj_id)

        async with self._l1_lock:
            self._l1_cache.pop(key, None)

        if table == "users":
            try:
                from services.orchestrator import state
                await state.user_l1_cache.delete(int(obj_id))
            except Exception as e:
                logger.error(f"L1 USER CACHE INVALIDATE ERROR: {e}")

        try:
            if self.redis:
                await self.redis.delete(key)
                if broadcast:
                    await self.redis.xadd(
                        self._stream_name,
                        {"data": orjson.dumps({"key": key, "action": "invalidate"})},
                        maxlen=self._main_stream_maxlen,
                        approximate=True
                    )
        except Exception as e:
            metrics.errors += 1
            logger.error(f"INVALIDATE ERROR: {e}")

    # ==================================================
    # STREAM SETUP
    # ==================================================
    async def _ensure_stream_setup(self):
        try:
            await self.redis.xgroup_create(
                self._stream_name,
                self._group_name,
                id="0",
                mkstream=True
            )
        except ResponseError:
            pass

    # ==================================================
    # STREAM LISTENER (AUTO-HEAL BILAN MUSTAHKAMLASH)
    # ==================================================
    async def _stream_listener(self):
        while self.is_alive:
            try:
                res = await self.redis.xreadgroup(
                    self._group_name,
                    self._consumer,
                    {self._stream_name: ">"},
                    count=50,
                    block=2000
                )

                if not res:
                    continue

                for _, msgs in res:
                    for msg_id, payload in msgs:
                        raw = payload.get(b"data")
                        if raw:
                            data = orjson.loads(raw)
                            async with self._l1_lock:
                                self._l1_cache.pop(data.get("key", ""), None)

                            metrics.events_processed += 1

                        await self.redis.xack(self._stream_name, self._group_name, msg_id)

            except ResponseError as re:
                # 🎯 AGAR BAZADA GURUH TOPILMASA (NOGROUP XATOSI):
                if "NOGROUP" in str(re):
                    logger.warning(
                        f"⚠️ Stream guruh topilmadi, qayta tiklanmoqda... {self._stream_name} -> {self._group_name}"
                    )
                    # Guruhni oqim ichida real-time qayta yaratib olamiz!
                    await self._ensure_stream_setup()
                    await asyncio.sleep(1)
                else:
                    logger.error(f"STREAM RESPONSE ERROR: {re}")
                    await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"STREAM UNEXPECTED ERROR: {e}")
                await asyncio.sleep(2)

    # ==================================================
    # PEL RECOVERY (TUZATILDI - SINFDAN O'RIN OLDI)
    # ==================================================
    async def _pel_recovery(self):
        """Kelajakda qayta ishlanmay qolgan stream xabarlari uchun stub"""
        while self.is_alive:
            await asyncio.sleep(60)

    # ==================================================
    # L1 CLEANUP SAFE
    # ==================================================
    async def _l1_cleanup(self):
        while self.is_alive:
            await asyncio.sleep(30)
            now = datetime.now(timezone.utc)

            async with self._l1_lock:
                expired = [k for k, (_, exp) in self._l1_cache.items() if now > exp]
                for k in expired:
                    self._l1_cache.pop(k, None)

    # ==================================================
    # METRICS
    # ==================================================
    async def _metrics_logger(self):
        while self.is_alive:
            await asyncio.sleep(60)
            metrics.log()

    # ==================================================
    # STOP
    # ==================================================
    async def stop(self):
        self.is_alive = False

        for t in self._tasks:
            t.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)

        async with self._l1_lock:
            self._l1_cache.clear()

        if self.redis:
            await self.redis.close()

        logger.info("CACHE STOPPED CLEANLY")


cache_manager = CacheManager(config.VALKEY_URL)
valkey = cache_manager