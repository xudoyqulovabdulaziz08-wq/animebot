import logging
from typing import Any
from repositories.comment_repository import CommentRepository
from database.cache import cache_manager

logger = logging.getLogger("CommentService")

class CommentService:

    def __init__(self, session: Any):
        self.session = session
        self.repo = CommentRepository()
        self.cache = cache_manager

    async def get_comments_count(self, anime_id: int) -> int:
        """
        💬 Anime izohlar sonini keshdan (Cache-First) oladi.
        Keshda bo'lmasa DB'dan o'qib, TTL bilan keshga yozadi.
        """
        # 1. Keshdan qidiramiz
        cached_count = await self.cache.get("anime_comments_count", anime_id)
        if cached_count is not None:
            logger.debug(f"🎯 CACHE HIT: anime_comments_count anime_id={anime_id}")
            return int(cached_count)

        # 2. Bazadan olamiz
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        count = await self.repo.get_comments_count_by_anime_id(self.session, anime_id)

        # 3. Keshga yozamiz (1 soat TTL)
        await self.cache.set("anime_comments_count", anime_id, count, ttl=3600)
        logger.info(f"💾 CACHE SET: Comment count for anime_id={anime_id} is {count}")

        return count