#=============== untils.py ===============
import asyncio
import orjson
import logging
from typing import Optional

from sqlalchemy import case, or_, update
from sqlalchemy.dialects.postgresql import insert

# MODELLAR VA CORE
from models import DBUser  
from core import SessionLocal, bot_cache

# LOGGING SOZLAMASI (To'g'ri varianti)
logger = logging.getLogger(__name__)

#=======================================================================================================

async def increment_referral(session, referrer_id: int, bonus_points: int = 50):
    """
    Referral sonini va ballarni atomik oshirish + cache invalidation
    """

    
    try:
        async with session.begin():
            # DB UPDATE
            stmt = (
                update(DBUser)
                .where(DBUser.user_id == referrer_id)
                .values(
                    referral_count=DBUser.referral_count + 1,
                    points=DBUser.points + bonus_points
                )
                .returning(DBUser.user_id, DBUser.referral_count, DBUser.points)
            )
            result = await session.execute(stmt)
            row = result.fetchone()

            if not row:
                logger.warning(f"Referral update failed for user_id: {referrer_id}")
                return None

            # CACHE INVALIDATION
            cache_key = f"u:{referrer_id}"
            try:
                await bot_cache.delete(cache_key)
            except Exception as e:
                logger.warning(f"Valkey DELETE error: {e}")

            return {
                "user_id": row[0],
                "referral_count": row[1],
                "points": row[2]
            }
    except Exception as e:
        logger.error(f"Error in increment_referral: {e}")
        return False

#=======================================================================================================

async def get_or_create_user(user_id: int, username: str = None):
    cache_key = f"u:{user_id}"

    # ================= CACHE =================
    # CACHE
    try:
        cached = await bot_cache.get(cache_key)
        if cached:
            data = cached

            if username and data.get("un") != username:
                # username o‘zgargan → DB update kerak
                pass
            else:
                await bot_cache.expire(cache_key, 1800)
                return data
    except Exception as e:
        logger.warning(f"Valkey GET error: {e}")

    # ================= DB =================
    async with SessionLocal() as session:
        stmt = insert(DBUser).values(
            user_id=user_id,
            username=username,
            status="user"
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "username": case(
                    (
                        or_(
                            DBUser.username != stmt.excluded.username,
                            DBUser.username.is_(None)
                        ),
                        stmt.excluded.username
                    ),
                    else_=DBUser.username
                )
            }
        ).returning(
            DBUser.user_id,
            DBUser.status,
            DBUser.points
        )

        try:
            result = await session.execute(stmt)
            await session.commit()
            row = result.fetchone()
        except Exception as e:
            await session.rollback()
            logger.error(f"DB Error in get_or_create: {e}")
            return None

        if not row:
            return None

        user_dict = {
            "id": row[0],
            "st": row[1],
            "pts": row[2],
            "un": username
        }

    # ================= CACHE =================
    try:
        await bot_cache.set(cache_key, user_dict, ttl=1800)
    except Exception as e:
        logger.warning(f"Valkey SET error: {e}")

    is_new = row[2] == 0
    return user_dict, is_new


#=======================================================================================================

async def check_subscription(user_id: int, channels: list, bot):
    cache_key = f"sub:{user_id}"

    # ================= CACHE =================
    try:
        cached = await bot_cache.get(cache_key)
        if cached == "1": return True
        if cached == "0": return False
    except Exception as e:
        logger.warning(f"Valkey GET error: {e}")

    # ================= TELEGRAM API =================
    tasks = [
        bot.get_chat_member(chat_id=ch.channel_id, user_id=user_id)
        for ch in channels
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    checked_any = False  # 🔥 MUHIM FLAG

    for res in results:
        if isinstance(res, Exception):
            logger.warning(f"Telegram API Error: {res}")
            continue

        checked_any = True

        if res.status not in ['member', 'administrator', 'creator']:
            try:
                await bot_cache.set(cache_key, "0", ttl=30)
            except:
                pass
            return False

    # 🔴 AGAR HECH QANDAY CHANNEL TEKSHIRILMAGAN BO‘LSA
    if not checked_any:
        logger.error("No valid channels checked!")
        return False  # FAIL SAFE

    # ================= SUCCESS =================
    try:
        
        await bot_cache.set(cache_key, "1", ttl=600)
    except Exception as e:
        logger.warning(f"Valkey SET error: {e}")

    return True