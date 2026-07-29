import logging
from typing import Any, List, Dict
from sqlalchemy import select, delete, desc
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from database.models import UserFavoriteAnime

logger = logging.getLogger("FavoriteRepository")


class FavoriteRepository:
    """
    🚀 Favorite Repository
    - Tranzaksiyani tashqaridan boshqarish (flush/commit talab qilinmaydi)
    - on_conflict_do_nothing orqali Race Condition himoyasi
    - Eager Loading va qisqartirilgan serializatsiya
    """

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
        # flush() olib tashlandi. Commit tashqarida qilinadi.
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
    async def get_user_favorites(session: Any, user_id: int) -> List[Dict]:
        session = await FavoriteRepository._prepare_session(session)

        stmt = (
            select(UserFavoriteAnime)
            .where(UserFavoriteAnime.user_id == user_id)
            .options(
                selectinload(UserFavoriteAnime.anime)
            )
            .order_by(desc(UserFavoriteAnime.created_at))
        )

        result = await session.execute(stmt)
        favorites = result.scalars().all()

        favorites_list = []
        for fav in favorites:
            fav_data = fav.to_dict()
            
            # Modelning to_api_dict() funksiyasidan foydalanamiz
            fav_data["anime"] = fav.anime.to_api_dict() if fav.anime else None
                
            favorites_list.append(fav_data)

        return favorites_list