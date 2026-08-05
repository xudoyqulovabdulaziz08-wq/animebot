# services/rating_service.py
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

    async def rate_anime(self, user_id: int, anime_id: int, score: int) -> Dict[str, Any]:
        """Animega baho berish/yangilash."""
        if not isinstance(score, int) or not (MIN_SCORE <= score <= MAX_SCORE):
            return {"success": False, "error": f"Baho {MIN_SCORE}-{MAX_SCORE} oralig'ida bo'lishi kerak"}

        try:
            if hasattr(self.session, "_ensure_session"):
                await self.session._ensure_session()

            await self.repo.upsert_rating(self.session, user_id, anime_id, score)
            average, count = await self.repo.recalculate_anime_rating(self.session, anime_id)

            if hasattr(self.session, "commit"):
                await self.session.commit()

            await self._invalidate_anime_cache(anime_id)
            return {"success": True, "average_rating": average, "rating_count": count}

        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.exception(f"rate_anime xatoligi (user={user_id}, anime={anime_id}): {e}")
            return {"success": False, "error": "internal_error"}

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

            await self._invalidate_anime_cache(anime_id)
            return {"success": True, "average_rating": average, "rating_count": count}

        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.exception(f"remove_rating xatoligi (user={user_id}, anime={anime_id}): {e}")
            return {"success": False, "error": "internal_error"}

    async def get_user_rating(self, user_id: int, anime_id: int) -> Optional[int]:
        return await self.repo.get_user_rating(self.session, user_id, anime_id)

    async def _invalidate_anime_cache(self, anime_id: int) -> None:
        """anime_service.py bilan bir xil keshlash konventsiyasi."""
        await self.cache.invalidate("anime", anime_id, broadcast=True)
        await self.cache.invalidate("anime", "all", broadcast=True)