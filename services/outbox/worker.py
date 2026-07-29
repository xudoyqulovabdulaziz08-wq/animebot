import zlib
import orjson
import asyncio
import logging
import time
import random
import hashlib
from datetime import datetime, timezone
from collections import defaultdict, deque
from typing import Any, Dict, Optional

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

# Hozirgi arxitekturadagi modellar va kesh menejeri
from database.models import OutboxEvent
from database.cache import cache_manager

logger = logging.getLogger("PRO_WORKER")


# ==========================================
# 🧠 AI CACHE + METRICS ENGINE (REAL O(1) & ASYNC SAFE)
# ==========================================
class MetricsBrain:
    def __init__(self):
        self.cache_hits = 0
        self.cache_misses = 0
        self.db_calls = 0
        self.events_processed = 0
        self.failures = 0

        self.window_size = 200
        self.latency_window = deque(maxlen=self.window_size)
        self._latency_sum = 0.0  # Real O(1) uchun yig'indi
        
        # user_id -> [heat_score, last_active_timestamp]
        self.user_heat = defaultdict(list)
        self._user_cleanup_counter = 0

    def cache_ratio(self) -> float:
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total) * 100 if total else 0

    def add_latency(self, value: float):
        if len(self.latency_window) == self.window_size:
            self._latency_sum -= self.latency_window[0]
        
        self.latency_window.append(value)
        self._latency_sum += value

    def avg_latency(self) -> float:
        count = len(self.latency_window)
        return self._latency_sum / count if count > 0 else 0.0

    def mark_user(self, user_id: int):
        current_time = time.time()
        if user_id in self.user_heat:
            self.user_heat[user_id][0] += 1
            self.user_heat[user_id][1] = current_time
        else:
            self.user_heat[user_id] = [1, current_time]

        self._user_cleanup_counter += 1

    def is_hot_user(self, user_id: int) -> bool:
        return self.user_heat[user_id][0] > 20 if user_id in self.user_heat else False

    async def maybe_clear_cold_users(self):
        """ ✅ Asinxron yield orqali Event Loop muzlashini oldini olish """
        if self._user_cleanup_counter <= 10000:
            return

        self._user_cleanup_counter = 0
        logger.info("🧹 Optimizing MetricsBrain user heat map asynchronously...")
        
        current_time = time.time()
        uids = list(self.user_heat.keys())
        chunk_size = 400

        for i, uid in enumerate(uids):
            user_data = self.user_heat.get(uid)
            if not user_data:
                continue
            
            score, last_active = user_data
            # 20 minut aktiv bo'lmagan yoki balli past foydalanuvchini o'chirish
            if current_time - last_active > 1200 or score <= 2:
                self.user_heat.pop(uid, None)
            else:
                self.user_heat[uid][0] = score // 2

            if i % chunk_size == 0:
                await asyncio.sleep(0)  # Loopga nafas beramiz


metrics = MetricsBrain()


# ==========================================
# 🚀 PRO ULTRA WORKER (CRASH + CLUSTER SAFE)
# ==========================================
class OutboxWorker:
    def __init__(self, session_factory: Any):
        # session_factory hozirgi loyihangizdagi AsyncSessionLocal hisoblanadi
        self.session_factory = session_factory
        self.cache = cache_manager  
        self.redis = getattr(cache_manager, 'redis', None)

        self.running = True

        # Tuning parameters
        self.batch_size = 100
        self.max_retry = 6
        self.parallel_limit = 20  

        # DLQ keys (Global namespace kiritildi)
        self.dlq_key = "{app}:dlq:outbox"

        # Circuit Breaker state
        self.failure_threshold = 10
        self.failure_count = 0
        self.circuit_open = False
        self.last_fail_time = 0.0

    def dynamic_ttl(self, user_id: int) -> int:
        base = 300
        if metrics.is_hot_user(user_id):
            return base * 5  # Hot user keshda 25 daqiqa saqlanadi
        return base + random.randint(0, 120)

    def shard_key(self, key: str) -> str:
        if not self.redis:
            return key
        hasher = hashlib.md5(key.encode('utf-8'))
        shard = int(hasher.hexdigest(), 16) % 3
        return f"{{shard:{shard}}}:{key}"

    def check_circuit(self):
        if self.failure_count >= self.failure_threshold:
            if not self.circuit_open:
                self.circuit_open = True
                self.last_fail_time = time.time()
                logger.critical("🚨 CIRCUIT BREAKER OPENED! WORKER PAUSED.")

        if self.circuit_open and time.time() - self.last_fail_time > 30:
            self.circuit_open = False
            self.failure_count = 0
            logger.info("✅ CIRCUIT BREAKER CLOSED. RESUMING OPERATIONS.")

    async def start(self):
        logger.info("🚀 PRO ULTRA WORKER STARTED SUCCESSFULLY")

        while self.running:
            try:
                self.check_circuit()

                if self.circuit_open:
                    await asyncio.sleep(2)
                    continue

                # Davriy tozalashni xavfsiz chaqirish
                await metrics.maybe_clear_cold_users()

                start_time = time.time()
                processed = await self.process_batch()
                
                metrics.add_latency(time.time() - start_time)

                if processed:
                    await asyncio.sleep(0.01)  
                else:
                    await asyncio.sleep(0.5)   

            except Exception as e:
                metrics.failures += 1
                self.failure_count += 1
                logger.error(f"🔥 WORKER MAIN LOOP ERROR: {e}")
                await asyncio.sleep(1)

    # ==========================================
    # 📦 BATCH PROCESSING (RACE-CONDITION SAFE)
    # ==========================================
    async def process_batch(self) -> int:
        async with self.session_factory() as main_session:
            try:
                # 1. Vazifalarni bazadan olish
                stmt = (
                    select(OutboxEvent)
                    .where(OutboxEvent.processed.is_(False))
                    .order_by(OutboxEvent.priority.desc(), OutboxEvent.created_at.asc()) 
                    .limit(self.batch_size)
                )

                result = await main_session.execute(stmt)
                events = result.scalars().all()

                if not events:
                    return 0

                # 2. Xavfsiz Detach: Obyektlarni dict ga o'giramiz (Session cross-bound error bermasligi uchun)
                event_data_list = [
                    {
                        "id": ev.id,
                        "event_type": ev.event_type,
                        "aggregate": ev.aggregate,
                        "payload": ev.payload,
                        "priority": ev.priority,
                        "retry_count": ev.retry_count
                    } for ev in events
                ]
                
                # Asosiy sessiyani tezda yopamiz (Locklarni bo'shatish uchun)
                await main_session.commit()

                semaphore = asyncio.Semaphore(self.parallel_limit)

                # 3. Parallel Ishchi Funksiya
                async def safe_process(ev_data: dict):
                    async with semaphore:
                        try:
                            success = await self.handle_event(ev_data)
                            if success:
                                # O'zining shaxsiy sessiyasida to'g'ridan-to'g'ri bazani yangilaydi (Merge emas, Update ishlatamiz)
                                async with self.session_factory() as local_session:
                                    u_stmt = (
                                        update(OutboxEvent)
                                        .where(OutboxEvent.id == ev_data["id"])
                                        .values(
                                            processed=True,
                                            processed_at=datetime.now(timezone.utc)
                                        )
                                    )
                                    await local_session.execute(u_stmt)
                                    await local_session.commit()
                                metrics.events_processed += 1

                        except Exception as res_err:
                            # Xatoliklarni mutlaqo izolatsiya qilingan sessiyada bajarish
                            async with self.session_factory() as fail_session:
                                await self.handle_failure(fail_session, ev_data, res_err)
                                await fail_session.commit()

                # Tasklarni parallel asinxron ishga tushiramiz
                await asyncio.gather(*(safe_process(ev_data) for ev_data in event_data_list))
                
                if self.failure_count > 0:
                    self.failure_count = max(0, self.failure_count - 1)
                
                return len(event_data_list)

            except SQLAlchemyError as e:
                logger.error(f"❌ DB BATCH ERROR IN WORKER: {e}")
                self.failure_count += 1
                return 0

    # ==========================================
    # ⚙️ EVENT HANDLER (SAFE PARSING & EXECUTION)
    # ==========================================
    async def handle_event(self, ev_data: dict) -> bool:
        try:
            raw_payload = ev_data["payload"]
            
            # PostgreSQL JSONB odatda to'g'ridan-to'g'ri dict qaytaradi, lekin string bo'lsa parse qilamiz
            if isinstance(raw_payload, (str, bytes)):
                payload = orjson.loads(raw_payload)
            else:
                payload = raw_payload

            # Zlib orqali siqilgan formatni ochish (events.py logikasiga mos)
            if isinstance(payload, dict) and payload.get("is_compressed"):
                compressed_hex = payload.get("data")
                raw_bytes = bytes.fromhex(compressed_hex)
                decompressed_bytes = zlib.decompress(raw_bytes)
                payload = orjson.loads(decompressed_bytes)
            
        except Exception as e:
            logger.critical(f"🚨 PAYLOAD PARSING ERROR [ID: {ev_data['id']}]: {e}")
            await self.send_to_dlq_raw(ev_data, f"Parsing failed: {e}")
            return True  # Zanjir buzilmasligi uchun True qaytarib, Outbox'dan o'chiramiz

        try:
            # Asosiy biznes logikani bajarish (Sizning qo'shimcha servislar)
            await asyncio.gather(
                self.fake_telegram(payload),
                self.fake_notify(payload)
            )

            # Dinamik Kesh Yozish
            user_id = payload.get("user_id")
            if user_id:
                metrics.mark_user(int(user_id))
                ttl = self.dynamic_ttl(int(user_id))
                await self.cache_event(payload, ttl, str(ev_data['id']), aggregate=ev_data.get("aggregate", "users"))

            return True

        except Exception as biz_err:
            raise biz_err

    # ==========================================
    # 💀 RAW DLQ FOR BROKEN JSON
    # ==========================================
    async def send_to_dlq_raw(self, ev_data: dict, err_msg: str):
        if self.redis:
            try:
                dlq_sharded_key = self.shard_key(self.dlq_key)
                safe_payload = str(ev_data.get("payload", "EMPTY"))
                
                # Cluster xavfsizligi uchun transaction=False (Pipeline o'zi yetarli)
                async with self.redis.pipeline(transaction=False) as pipe:
                    pipe.lpush(
                        dlq_sharded_key,
                        orjson.dumps({
                            "id": str(ev_data["id"]),
                            "event_type": ev_data.get("event_type"),
                            "error": err_msg,
                            "raw_payload": safe_payload,
                            "time": datetime.now(timezone.utc).isoformat()
                        })
                    )
                    pipe.ltrim(dlq_sharded_key, 0, 4999) # Max 5000 ta saqlanadi
                    await pipe.execute()
            except Exception as redis_err:
                logger.error(f"🚨 FAILED TO PUSH TO REDIS RAW DLQ: {redis_err}")
        logger.critical(f"💀 BROKEN EVENT FORCED TO DLQ: {ev_data['id']}")

    # ==========================================
    # 🧠 CACHE ACTION (RACE-CONDITION SAFE)
    # ==========================================
    async def cache_event(self, payload: Dict[str, Any], ttl: int, event_id: str, aggregate: str):
        try:
            # Aggregate orqali dinamik jadvalni aniqlash
            obj_id = payload.get("user_id") or payload.get("anime_id") or payload.get("id")
            
            if obj_id:
                # Yangi arxitekturadagi cache_manager funksiyasiga murojaat
                await self.cache.set(
                    table=aggregate.lower(),
                    obj_id=str(obj_id),
                    data=payload,
                    ttl=ttl
                )
                metrics.cache_hits += 1
            else:
                metrics.cache_misses += 1
        except Exception as e:
            metrics.cache_misses += 1
            logger.error(f"❌ Cache operation error in worker: {e}")

    # ==========================================
    # 📡 EXTERNAL FAKE SERVICES
    # ==========================================
    async def fake_telegram(self, payload: Dict[str, Any]):
        await asyncio.sleep(0.005)

    async def fake_notify(self, payload: Dict[str, Any]):
        await asyncio.sleep(0.005)

    # ==========================================
    # 💀 FAILURE + DLQ MANAGEMENT
    # ==========================================
    async def handle_failure(self, session: Any, ev_data: dict, err: Exception):
        metrics.failures += 1
        new_retry_count = ev_data["retry_count"] + 1
        
        logger.warning(f"⚠️ Event failure [ID: {ev_data['id']} | Attempt: {new_retry_count}]: {err}")

        if new_retry_count >= self.max_retry:
            await self.send_to_dlq(ev_data, str(err))
            
            u_stmt = (
                update(OutboxEvent)
                .where(OutboxEvent.id == ev_data["id"])
                .values(
                    processed=True, 
                    processed_at=datetime.now(timezone.utc),
                    retry_count=new_retry_count
                )
            )
        else:
            # Priority pasaytiriladi (Next retry yo'qligi uchun)
            new_priority = max(0, ev_data["priority"] - 1)
            u_stmt = (
                update(OutboxEvent)
                .where(OutboxEvent.id == ev_data["id"])
                .values(
                    retry_count=new_retry_count,
                    priority=new_priority
                )
            )

        await session.execute(u_stmt)

    async def send_to_dlq(self, ev_data: dict, err_msg: str):
        if self.redis:
            try:
                dlq_sharded_key = self.shard_key(self.dlq_key)
                
                async with self.redis.pipeline(transaction=False) as pipe:
                    pipe.lpush(
                        dlq_sharded_key,
                        orjson.dumps({
                            "id": str(ev_data["id"]),
                            "event_type": ev_data.get("event_type"),
                            "error": err_msg,
                            "time": datetime.now(timezone.utc).isoformat()
                        })
                    )
                    pipe.ltrim(dlq_sharded_key, 0, 4999)
                    await pipe.execute()
            except Exception as redis_err:
                logger.error(f"🚨 FAILED TO PUSH TO REDIS DLQ: {redis_err}")
        logger.critical(f"💀 PERMANENT OUTBOX FAILURE MOVED TO DLQ: {ev_data['id']}")

    async def stop(self):
        self.running = False
        logger.info("🛑 PRO WORKER SHUTTING DOWN...")