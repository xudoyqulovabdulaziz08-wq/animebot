import logging
from typing import Any, List, Dict
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload
from sqlalchemy import func

from database.models import UserFavoriteAnime, Anime

logger = logging.getLogger("FavoriteRepository")


class FavoriteRepository:

    @staticmethod
    def _get_real_session(session: Any):
        if hasattr(session, "_session"):
            return session._session
        return session

    @staticmethod
    async def _prepare_session(session: Any):
        if hasattr(session, "_ensure_session"):
            await session._ensure_session()
        return FavoriteRepository._get_real_session(session)

    @staticmethod
    async def add_favorite(session: Any, user_id: int, anime_id: int) -> bool:
        session = await FavoriteRepository._prepare_session(session)

        stmt = (
            insert(UserFavoriteAnime)
            .values(user_id=user_id, anime_id=anime_id)
            .on_conflict_do_nothing(index_elements=['user_id', 'anime_id'])
        )

        result = await session.execute(stmt)
        return result.rowcount > 0

    @staticmethod
    async def remove_favorite(session: Any, user_id: int, anime_id: int) -> bool:
        session = await FavoriteRepository._prepare_session(session)

        stmt = delete(UserFavoriteAnime).where(
            UserFavoriteAnime.user_id == user_id,
            UserFavoriteAnime.anime_id == anime_id
        )
        
        result = await session.execute(stmt)
        return result.rowcount > 0

    @staticmethod
    async def is_favorite(session: Any, user_id: int, anime_id: int) -> bool:
        session = await FavoriteRepository._prepare_session(session)

        stmt = (
            select(UserFavoriteAnime.id)
            .where(
                UserFavoriteAnime.user_id == user_id,
                UserFavoriteAnime.anime_id == anime_id
            )
            .limit(1)
        )

        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_user_favorite_ids(session: Any, user_id: int) -> List[int]:
        """Foydalanuvchi yoqtirgan anime ID-lari ro'yxati (Keshda saqlash uchun juda yengil va qulay)"""
        session = await FavoriteRepository._prepare_session(session)

        stmt = (
            select(UserFavoriteAnime.anime_id)
            .where(UserFavoriteAnime.user_id == user_id)
        )

        result = await session.execute(stmt)
        return list(result.scalars().all())
    
    @staticmethod
    async def get_user_favorites_count(session: Any, user_id: int) -> int:
        """Foydalanuvchining sevimlilar ro'yxatidagi umumiy animelar soni"""
        session = await FavoriteRepository._prepare_session(session)

        stmt = (
            select(func.count(UserFavoriteAnime.id))
            .where(UserFavoriteAnime.user_id == user_id)
        )

        result = await session.execute(stmt)
        return result.scalar() or 0
    

    @staticmethod
    async def get_user_favorite_anime_list(
        session: Any, 
        user_id: int, 
        offset: int = 0, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Foydalanuvchining sevimlilar ro'yxatidagi animelarni JOIN orqali 
        BITTA SQL so'rovida olib keladi (Yangi AnimeTitle strukturasi bo'yicha).
        """
        from database.models import Anime, UserFavoriteAnime, AnimeTitle
        from sqlalchemy import func

        session = await FavoriteRepository._prepare_session(session)

        stmt = (
            select(
                Anime.anime_id,
                func.coalesce(AnimeTitle.title_uz, AnimeTitle.title_en, "Nomsiz anime").label("title"),
                Anime.year,
                Anime.poster_id
            )
            .join(UserFavoriteAnime, UserFavoriteAnime.anime_id == Anime.anime_id)
            .outerjoin(AnimeTitle, AnimeTitle.anime_id == Anime.anime_id)
            .where(UserFavoriteAnime.user_id == user_id)
            .group_by(Anime.anime_id, AnimeTitle.id, UserFavoriteAnime.id)
            .order_by(UserFavoriteAnime.id.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await session.execute(stmt)
        rows = result.all()

        return [
            {
                "anime_id": row.anime_id,
                "title": row.title,
                "year": row.year,
                "poster": row.poster_id
            }
            for row in rows
        ]