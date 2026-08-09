import logging
from typing import Any, Dict, Optional

from repositories.rating_repository import RatingRepository
from database.cache import cache_manager

logger = logging.getLogger("RatingService")

MIN_SCORE = 1
MAX_SCORE = 10


class RatingService:

    def __init__(self, session):
        self.session = session
        self.repo = RatingRepository()
        self.cache = cache_manager

    # ==================================================
    # 🎯 GET USER RATING FOR SPECIFIC ANIME (CACHE-FIRST)
    # ==================================================
    async def get_user_rating(self, user_id: int, anime_id: int) -> Optional[int]:
        """
        Foydalanuvchining bitta animega bergan bahosini keshdan/DBdan oladi.
        """
        user_ratings_map = await self.get_user_ratings_map(user_id)
        return user_ratings_map.get(anime_id)

    # ==================================================
    # 📋 GET ALL USER RATINGS MAP (CACHE-FIRST)
    # ==================================================
    async def get_user_ratings_map(self, user_id: int) -> Dict[int, int]:
        """
        User baholagan barcha {anime_id: score} lug'atini keshdan yoki DBdan oladi.
        """
        cached_map = await self.cache.get("user_ratings_map", user_id)
        if cached_map is not None:
            return cached_map

        ratings_map = await self.repo.get_user_ratings_map(self.session, user_id)
        await self.cache.set("user_ratings_map", user_id, ratings_map, ttl=3600)
        return ratings_map

    # ==================================================
    # 📊 GET USER RATINGS COUNT (CACHE-FIRST)
    # ==================================================
    async def get_user_ratings_count(self, user_id: int) -> int:
        """
        Foydalanuvchi jami nechta animega ovoz berganini keshdan/DBdan qaytaradi.
        """
        cached_count = await self.cache.get("user_ratings_count", user_id)
        if cached_count is not None:
            return int(cached_count)

        count = await self.repo.get_user_ratings_count(self.session, user_id)
        await self.cache.set("user_ratings_count", user_id, count, ttl=3600)
        return count

    # ==================================================
    # 🔄 RATE ANIME (TRANSACTION-SAFE & CACHE INVALIDATION)
    # ==================================================
    async def rate_anime(self, user_id: int, anime_id: int, score: int) -> Dict[str, Any]:
        """Animega baho berish yoki mavjud bahoni yangilash."""
        if not isinstance(score, int) or not (MIN_SCORE <= score <= MAX_SCORE):
            return {"success": False, "error": f"Baho {MIN_SCORE}-{MAX_SCORE} oralig'ida bo'lishi kerak"}

        try:
            if hasattr(self.session, "_ensure_session"):
                await self.session._ensure_session()

            await self.repo.upsert_rating(self.session, user_id, anime_id, score)
            average, count = await self.repo.recalculate_anime_rating(self.session, anime_id)

            if hasattr(self.session, "commit"):
                await self.session.commit()

            # 🔥 KESH INVALIDATSIYASI
            await self._invalidate_anime_cache(anime_id)
            await self.cache.invalidate("user_ratings_map", user_id, broadcast=True)
            await self.cache.invalidate("user_ratings_count", user_id, broadcast=True)

            return {"success": True, "average_rating": average, "rating_count": count}

        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.exception(f"rate_anime xatoligi (user={user_id}, anime={anime_id}): {e}")
            return {"success": False, "error": "internal_error"}

    # ==================================================
    # ❌ REMOVE RATING (TRANSACTION-SAFE & CACHE INVALIDATION)
    # ==================================================
    async def remove_rating(self, user_id: int, anime_id: int) -> Dict[str, Any]:
        """Foydalanuvchi bergan bahoni bekor qiladi."""
        try:
            if hasattr(self.session, "_ensure_session"):
                await self.session._ensure_session()

            deleted = await self.repo.delete_rating(self.session, user_id, anime_id)
            if not deleted:
                return {"success": False, "error": "rating_not_found"}

            average, count = await self.repo.recalculate_anime_rating(self.session, anime_id)

            if hasattr(self.session, "commit"):
                await self.session.commit()

            # 🔥 KESH INVALIDATSIYASI
            await self._invalidate_anime_cache(anime_id)
            await self.cache.invalidate("user_ratings_map", user_id, broadcast=True)
            await self.cache.invalidate("user_ratings_count", user_id, broadcast=True)

            return {"success": True, "average_rating": average, "rating_count": count}

        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.exception(f"remove_rating xatoligi (user={user_id}, anime={anime_id}): {e}")
            return {"success": False, "error": "internal_error"}

    async def _invalidate_anime_cache(self, anime_id: int) -> None:
        """Anime ma'lumotlari yangilanganda anime keshini tozalash."""
        await self.cache.invalidate("anime", anime_id, broadcast=True)
        await self.cache.invalidate("anime", "all", broadcast=True)