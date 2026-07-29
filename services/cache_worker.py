import os
import uuid
import time
import asyncio
import logging
import orjson
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional, Dict

from sqlalchemy import select, delete, and_, or_, update
from sqlalchemy.exc import SQLAlchemyError
from database.models import OutboxEvent
from database.cache import cache_manager  # Markaziy kesh drayverimiz

logger = logging.getLogger("CacheInvalidationWorker")


class CacheInvalidationWorker:
    """
    🚀 ULTRA PRO MAX DISTRIBUTED ZERO-LOSS EVENT SYSTEM (PROD READY)
    Outbox pattern asosida ishlovchi keshni sinxronizatsiya qilish va tozalash tizimi.
    """

    def __init__(self, session_factory: Any):
        self.session_factory = session_factory
        self.cache = cache_manager  # Markaziy L1 + L2 cache menejeri
        
        # cache_manager ichidagi redis drayveridan to'g'ridan-to'g'ri foydalanamiz
        self.redis = getattr(cache_manager, 'redis', None)

        self._running = True
        self.instance_id = str(uuid.uuid4())

        # ================= TUNING =================
        self.batch_size = 50  # Optiral batch hajmi
        self.fast_sleep = 0.05  # Yuklama bor paytdagi pauza
        self.idle_sleep = 0.5   # Navbat bo'sh bo'lgandagi pauza
        self.cleanup_interval = 300  # 5 daqiqa

        self.max_retries = 5
        self._last_cleanup = time.time()

        # Cluster xavfsiz hashtag kalitlari
        self.dlq_key = "{cache}:dlq"
        self.lock_key = "{cache}:worker_lock"
        self.stream_key = "{cache}:invalidate"
        
        # 🔒 CONNECTION POOL PROTECTION SEMAPHORE
        self.db_semaphore = asyncio.Semaphore(10) 

    # ================= DISTRIBUTED LOCK =================
    async def _acquire_lock(self) -> bool:
        if not self.redis:
            return True
        try:
            # Faqat bitta worker instance parallel ishlashini ta'minlash
            return await self.redis.set(
                self.lock_key,
                self.instance_id,
                nx=True,
                ex=45  # Lock muddati optimize qilindi
            )
        except Exception as e:
            logger.error(f"❌ Lock acquire error: {e}")
            return False

    async def _release_lock(self):
        if not self.redis:
            return
        try:
            # Atomar ravishda lockni faqat uni qo'ygan instance o'chira oladi
            lua_release = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            else
                return 0
            end
            """
            await self.redis.eval(lua_release, 1, self.lock_key, self.instance_id)
        except Exception as e:
            logger.debug(f"Lock release error: {e}")

    # ================= REDIS STREAM SETUP =================
    async def _setup_redis_stream(self):
        if not self.redis:
            return
        group_name = "cache_group"
        try:
            await self.redis.xgroup_create(self.stream_key, group_name, id='0', mkstream=True)
            logger.info(f"✅ Redis/Valkey Stream Group '{group_name}' verified.")
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                logger.error(f"❌ Redis Stream setup error: {e}")

    # ================= MAIN LOOP =================
    async def run(self):
        logger.info(f"🚀 Cache Invalidation Worker STARTED [Instance ID: {self.instance_id}]")
        await self._setup_redis_stream()

        while self._running:
            try:
                if not await self._acquire_lock():
                    await asyncio.sleep(self.idle_sleep)
                    continue

                try:
                    processed = await self.process_events()
                finally:
                    await self._release_lock()

                # Dinamik uxlash mantiqi
                if processed > 0:
                    await asyncio.sleep(self.fast_sleep)
                else:
                    await asyncio.sleep(self.idle_sleep)

                await self._maybe_cleanup()

            except asyncio.CancelledError:
                logger.warning("🛑 Worker execution cancelled by orchestrator")
                break
            except Exception as e:
                logger.error(f"🔥 Worker unexpected loop crash: {e}", exc_info=True)
                await asyncio.sleep(2.0)

    # ================= EVENT PROCESS (CONCURRENT-SAFE) =================
    async def process_events(self) -> int:
        async with self.session_factory() as main_session:
            try:
                now = datetime.now(timezone.utc)
                
                # Qayta ishlanmagan va vaqti kelgan outbox tadbirlarini olish
                stmt = (
                    select(OutboxEvent)
                    .where(
                        and_(
                            OutboxEvent.processed.is_(False),
                            or_(
                                OutboxEvent.created_at.is_(None),
                                OutboxEvent.created_at <= now
                            )
                        )
                    )
                    .order_by(OutboxEvent.priority.desc(), OutboxEvent.created_at.asc())
                    .limit(self.batch_size)
                )

                result = await main_session.execute(stmt)
                events = result.scalars().all()

                if not events:
                    return 0

                # Ma'lumotlarni sessiyadan tashqariga ajratib (detach) olamiz
                event_data_list = [
                    {
                        "id": ev.id,
                        "aggregate": ev.aggregate,
                        "aggregate_id": ev.aggregate_id,
                        "retry_count": ev.retry_count
                    } for ev in events
                ]

                # Asosiy sessiyani tezda yopamiz yoki resursni bo'shatamiz
                await main_session.commit()

                async def safe_process_single(ev_data: dict):
                    # DB Semaphore orqali Pool ulanishlarini himoya qilish
                    async with self.db_semaphore:
                        async with self.session_factory() as ev_session:
                            try:
                                # 1. Keshni va Stream xabarlarini tarqatish
                                await self._process_cache_and_stream(ev_data)
                                
                                # 2. Statusni muvaffaqiyatli deb yangilash
                                u_stmt = (
                                    update(OutboxEvent)
                                    .where(OutboxEvent.id == ev_data["id"])
                                    .values(processed=True, processed_at=datetime.now(timezone.utc))
                                )
                                await ev_session.execute(u_stmt)
                                await ev_session.commit()
                            except Exception as e:
                                await ev_session.rollback()
                                logger.error(f"❌ Event execution failed [ID: {ev_data['id']}]: {e}")
                                
                                # Xatolikni boshqarish uchun alohida toza sessiya ochiladi
                                async with self.session_factory() as fail_session:
                                    await self._handle_failure(fail_session, ev_data, str(e))
                                    await fail_session.commit()

                # Batch ichidagi barcha ob'ektlarni parallel qayta ishlash
                await asyncio.gather(*(safe_process_single(ev) for ev in event_data_list))
                return len(events)

            except SQLAlchemyError as e:
                logger.error(f"❌ Database execution error in cache batch: {e}")
                return 0

    # ================= INVALIDATION LOGIC =================
    async def _process_cache_and_stream(self, ev_data: dict):
        """Keshni markaziy menejer orqali tozalash va o'zgarishni oqimga (Stream) chiqarish"""
        table_name = str(ev_data["aggregate"])
        obj_id = str(ev_data["aggregate_id"])

        # 1. Kesh menejeri orqali L1 va L2 keshdan tozalash
        # cache_manager ichida delete yoki invalidate metodi borligiga qarab chaqiramiz
        if hasattr(self.cache, 'delete'):
            await self.cache.delete(table_name, obj_id)
        elif hasattr(self.cache, 'invalidate'):
            await self.cache.invalidate(table=table_name, obj_id=obj_id)
        
        # 2. Boshqa mikroxizmatlar yoki guruh a'zolari bilishi uchun Redis Streamga yozish
        if self.redis:
            await self.redis.xadd(
                self.stream_key,
                {
                    "action": "invalidate",
                    "table": table_name,
                    "obj_id": obj_id,
                    "sender": self.instance_id
                },
                maxlen=10000,
                approximate=True
            )

    # ================= FAILURE HANDLING (EXPONENTIAL BACKOFF) =================
    async def _handle_failure(self, session: Any, ev_data: dict, error: str):
        new_retry_count = ev_data["retry_count"] + 1

        if new_retry_count <= self.max_retries:
            # Haqiqiy eksponentsial vaqt ortishi (5s, 10s, 20s, 40s...)
            delay_seconds = min(5 * (2 ** new_retry_count), 300)
            next_run = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
            
            u_stmt = (
                update(OutboxEvent)
                .where(OutboxEvent.id == ev_data["id"])
                .values(retry_count=new_retry_count, created_at=next_run)
            )
            await session.execute(u_stmt)
            logger.warning(f"🔁 Event [ID: {ev_data['id']}] scheduled for retry {new_retry_count}/{self.max_retries} in {delay_seconds}s")
            return

        # Agar urinishlar tugasa, hodisa o'lik xabarlar navbatiga (DLQ) otiladi
        await self._send_to_dlq(ev_data, error, new_retry_count)
        
        u_stmt = (
            update(OutboxEvent)
            .where(OutboxEvent.id == ev_data["id"])
            .values(processed=True, processed_at=datetime.now(timezone.utc), retry_count=new_retry_count)
        )
        await session.execute(u_stmt)

    # ================= DEAD LETTER QUEUE =================
    async def _send_to_dlq(self, ev_data: dict, error: str, final_retry_count: int):
        try:
            payload = {
                "id": str(ev_data["id"]),
                "aggregate": str(ev_data["aggregate"]),
                "aggregate_id": str(ev_data["aggregate_id"]),
                "error": error,
                "retry_count": final_retry_count,
                "time": datetime.now(timezone.utc).isoformat()
            }

            if self.redis:
                # Cluster xavfsiz bo'lishi uchun transaction=False (Pipeline o'zi yetarli)
                async with self.redis.pipeline(transaction=False) as pipe:
                    pipe.lpush(self.dlq_key, orjson.dumps(payload))
                    pipe.ltrim(self.dlq_key, 0, 9999)  # DLQ hajmini 10k da saqlaymiz (O'sib ketmasligi uchun)
                    await pipe.execute()

            logger.critical(f"💀 EVENT PERMANENTLY MOVED TO DLQ: {ev_data['id']} | Cause: {error}")
        except Exception as e:
            logger.critical(f"🚨 CRITICAL: Failed to push to DLQ stream: {e}")

    # ================= CLEANUP OLD PROCESSED EVENTS =================
    async def _maybe_cleanup(self):
        """Ma'lumotlar bazasi shishib ketmasligi uchun eski qayta ishlangan outbox tadbirlarini tozalash"""
        now = time.time()
        if now - self._last_cleanup < self.cleanup_interval:
            return

        self._last_cleanup = now
        try:
            async with self.session_factory() as session:
                # 24 soatdan eski va qayta ishlangan xabarlarni o'chirish
                cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
                
                stmt = (
                    delete(OutboxEvent)
                    .where(
                        and_(
                            OutboxEvent.processed.is_(True),
                            OutboxEvent.processed_at <= cutoff
                        )
                    )
                )
                result = await session.execute(stmt)
                await session.commit()
                
                if result.rowcount > 0:
                    logger.info(f"🧹 Purged {result.rowcount} old processed outbox events (older than 24h).")
        except Exception as e:
            logger.error(f"❌ Cleanup storage error: {e}")

    # ================= GRACEFUL STOP =================
    async def stop(self):
        self._running = False
        if self.redis:
            await self._release_lock()
        logger.info("🛑 Cache Invalidation Worker SHUTDOWN GRACEFULLY")