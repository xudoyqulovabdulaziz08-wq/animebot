import asyncio
import orjson
import logging
import zlib
from uuid import uuid4
from datetime import datetime, timezone
from typing import Any, Optional, Dict, List, Tuple

from sqlalchemy import event, insert  
from sqlalchemy.ext.asyncio import AsyncSession

# Loyihangizdagi joriy modellar
from database.models import OutboxEvent

logger = logging.getLogger("OutboxService")


# ================= AI PRIORITY ENGINE =================
class EventPriorityEngine:
    HIGH = 3
    MEDIUM = 2
    LOW = 1

    @staticmethod
    def score(event_type: str) -> int:
        if event_type in ("user_created", "payment", "vip_upgrade"):
            return EventPriorityEngine.HIGH
        elif event_type in ("comment", "like", "history_update", "cache_update", "anime_update"):
            return EventPriorityEngine.MEDIUM
        return EventPriorityEngine.LOW


# ================= EVENT COMPRESSOR (POSTGRES JSONB SAFE) =================
class EventCompressor:
    """
    Payload compression with robust nested diff engine.
    PostgreSQL JSONB ustuniga mos tushishi uchun siqilgan ma'lumotlar Hex formatda saqlanadi.
    """

    @staticmethod
    def compress(payload: dict) -> dict:
        json_bytes = orjson.dumps(
            payload, 
            option=orjson.OPT_SERIALIZE_DATETIME | orjson.OPT_SERIALIZE_UUID | orjson.OPT_NON_STR_KEYS
        )
        compressed_hex = zlib.compress(json_bytes, level=6).hex()
        return {
            "is_compressed": True,
            "data": compressed_hex
        }

    @staticmethod
    def decompress(compressed_payload: dict) -> dict:
        if not compressed_payload or not compressed_payload.get("is_compressed"):
            return compressed_payload or {}
            
        try:
            compressed_hex = compressed_payload.get("data", "")
            raw_bytes = bytes.fromhex(compressed_hex)
            json_bytes = zlib.decompress(raw_bytes)
            return orjson.loads(json_bytes)
        except Exception as e:
            logger.error(f"Decompression error: {e}")
            return {}

    @staticmethod
    def diff(old: Optional[dict], new: dict) -> Optional[dict]:
        if not old:
            return new
            
        delta = {}
        for k, v in new.items():
            if k not in old:
                delta[k] = v
            elif old[k] != v:
                if isinstance(v, dict) and isinstance(old[k], dict):
                    deep_diff = EventCompressor.diff(old[k], v)
                    if deep_diff:
                        delta[k] = deep_diff
                else:
                    delta[k] = v
                    
        # Iteratsiya davomida xato chiqmasligi uchun dict.keys() listga o'girildi
        for k in list(old.keys()):
            if k not in new:
                delta[k] = None
                
        return delta


# ================= DLQ HANDLER =================
class DeadLetterQueue:
    def __init__(self, redis):
        self.redis = redis
        # Cluster safe tag
        self.key = "{app}:outbox:dlq"

    async def push(self, event_data: dict):
        if self.redis:
            try:
                pipe = self.redis.pipeline(transaction=False)
                safe_event = orjson.dumps(
                    event_data, 
                    option=orjson.OPT_SERIALIZE_DATETIME | orjson.OPT_SERIALIZE_UUID
                )
                pipe.lpush(self.key, safe_event)
                pipe.ltrim(self.key, 0, 9999)
                await pipe.execute()
            except Exception as e:
                logger.critical(f"🚨 FAILED TO WRITE TO DLQ REDIS: {e}")

    async def fetch(self, limit: int = 50) -> List[dict]:
        if not self.redis:
            return []
        items = await self.redis.lrange(self.key, 0, limit - 1)
        return [orjson.loads(i) for i in items]


# ================= RETRY QUEUE =================
class RetryQueue:
    def __init__(self, redis):
        self.redis = redis
        self.key = "{app}:outbox:retry"

    async def push(self, event_id: str, delay: int = 5):
        if self.redis:
            ready_timestamp = datetime.now(timezone.utc).timestamp() + delay
            await self.redis.zadd(self.key, {event_id: ready_timestamp})

    async def pop_ready(self) -> List[str]:
        if not self.redis:
            return []
        
        now = datetime.now(timezone.utc).timestamp()
        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.zrangebyscore(self.key, 0, now)
                pipe.zremrangebyscore(self.key, 0, now) 
                results, _ = await pipe.execute()
                
            return [r.decode("utf-8") if isinstance(r, bytes) else r for r in results]
        except Exception as e:
            logger.error(f"❌ RetryQueue pop_ready failed: {e}")
            return []


# ================= OUTBOX SERVICE CORE =================
class OutboxService:
    def __init__(self, redis):
        self.redis = redis
        self.dlq = DeadLetterQueue(redis)
        self.retry = RetryQueue(redis)

    async def create_event(
        self,
        session: AsyncSession,
        aggregate: str,
        agg_id: Any,
        event_type: str,
        payload: dict,
        previous_state: Optional[dict] = None,
        commit: bool = False,
    ) -> Optional[str]:
        # Haqiqiy UUID obyekti
        event_id = uuid4()
        event_id_str = str(event_id)
        priority = EventPriorityEngine.score(event_type)

        try:
            if previous_state is not None:
                diff_payload = EventCompressor.diff(previous_state, payload)
                if not diff_payload:
                    return None
                payload = diff_payload

            # Payload endi xavfsiz dict holatida (JSONB uchun) qaytadi
            compressed_payload = EventCompressor.compress(payload)

            stmt = insert(OutboxEvent).values(
                id=event_id,
                aggregate=aggregate,
                aggregate_id=str(agg_id),
                event_type=event_type,
                payload=compressed_payload, 
                priority=priority,
                retry_count=0,
                processed=False,
                created_at=datetime.now(timezone.utc),
            )
            await session.execute(stmt)

            async def sync_with_redis():
                if self.redis:
                    try:
                        redis_key = f"{{app}}:outbox:{aggregate}:{agg_id}"
                        priority_queue_key = "{app}:outbox:priority_queue"

                        pipe = self.redis.pipeline(transaction=False)
                        # Oqimga yozish uchun yana byte formatiga o'tkazib saqlaymiz
                        cache_data = orjson.dumps(compressed_payload)
                        pipe.set(redis_key, cache_data, ex=3600)
                        pipe.zadd(priority_queue_key, {event_id_str: priority})
                        await pipe.execute()
                        logger.info(f"🚀 Post-Commit: Redis integratsiyasi bajarildi [ID: {event_id_str}]")
                    except Exception as re:
                        logger.error(f"⚠️ Redis post-commit sync error: {re}. Worker DB orqali qayta ishlaydi.")

            if commit:
                await session.commit()
                await sync_with_redis()
            else:
                # Xavfsiz Thread-Safe Hook
                current_loop = asyncio.get_running_loop()

                def after_commit_hook(target_session):
                    if not current_loop.is_closed():
                        asyncio.run_coroutine_threadsafe(sync_with_redis(), current_loop)

                event.listen(session.sync_session, "after_commit", after_commit_hook, once=True)

            return event_id_str

        except Exception as e:
            logger.error(f"❌ Critical Outbox Service DB Failure: {e}")
            
            await self.dlq.push({
                "event_id": event_id_str,
                "aggregate": aggregate,
                "agg_id": str(agg_id),
                "event_type": event_type,
                "payload": payload,
                "error": f"OUTBOX_STAGE_ERROR: {str(e)}",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            raise

    # ================= EVENT RETRIEVER =================
    async def get_event(self, aggregate: str, agg_id: str) -> Optional[dict]:
        if not self.redis:
            return None
            
        key = f"{{app}}:outbox:{aggregate}:{agg_id}"
        data = await self.redis.get(key)
        
        if not data:
            return None

        # Redishdan olingan byteslarni avval dict ga, so'ngra to'liq ochilgan ma'lumotga o'giramiz
        compressed_dict = orjson.loads(data)
        return EventCompressor.decompress(compressed_dict)

    # ================= ZERO-LOSS PRIORITY FETCH =================
    async def get_next_events(self, limit: int = 10) -> List[Tuple[str, float]]:
        if not self.redis:
            return []
        
        priority_queue_key = "{app}:outbox:priority_queue"
        results = await self.redis.zrevrange(priority_queue_key, 0, limit - 1, withscores=True)
        
        formatted_results = []
        for event_id_bytes, score in results:
            ev_id = event_id_bytes.decode("utf-8") if isinstance(event_id_bytes, bytes) else event_id_bytes
            formatted_results.append((ev_id, score))
            
        return formatted_results

    async def acknowledge_event(self, event_id: str) -> bool:
        if self.redis:
            priority_queue_key = "{app}:outbox:priority_queue"
            return await self.redis.zrem(priority_queue_key, event_id) > 0
        return False