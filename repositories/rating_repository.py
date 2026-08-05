# repositories/rating_repository.py
import logging
from typing import Any, Optional, Tuple
from sqlalchemy import select, func, update, delete
from sqlalchemy.dialects.postgresql import insert

from database.models import Anime, AnimeRating

logger = logging.getLogger("RatingRepository")


class RatingRepository:

    @staticmethod
    def _get_real_session(session: Any):
        if hasattr(session, "_session"):
            return session._session
        return session

    @staticmethod
    async def _prepare_session(session: Any):
        if hasattr(session, "_ensure_session"):
            await session._ensure_session()
        return RatingRepository._get_real_session(session)

    @staticmethod
    async def upsert_rating(session: Any, user_id: int, anime_id: int, score: int) -> None:
        """Foydalanuvchi bahosini kiritadi yoki eskisini yangilaydi (UPSERT)."""
        session = await RatingRepository._prepare_session(session)

        stmt = insert(AnimeRating).values(
            user_id=user_id,
            anime_id=anime_id,
            score=score
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "anime_id"],
            set_={"score": stmt.excluded.score}
        )
        await session.execute(stmt)

    @staticmethod
    async def get_user_rating(session: Any, user_id: int, anime_id: int) -> Optional[int]:
        """Foydalanuvchi shu animega avval baho berganmi — bo'lsa, ballini qaytaradi."""
        session = await RatingRepository._prepare_session(session)

        stmt = select(AnimeRating.score).where(
            AnimeRating.user_id == user_id,
            AnimeRating.anime_id == anime_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_rating(session: Any, user_id: int, anime_id: int) -> bool:
        """Mavjud reytingni o'chiradi."""
        session = await RatingRepository._prepare_session(session)

        stmt = delete(AnimeRating).where(
            AnimeRating.user_id == user_id,
            AnimeRating.anime_id == anime_id
        )
        result = await session.execute(stmt)
        return result.rowcount > 0

    @staticmethod
    async def recalculate_anime_rating(session: Any, anime_id: int) -> Tuple[float, int]:
        """
        anime_ratings jadvalidan haqiqiy SUM/COUNT ni qayta hisoblab,
        Anime.rating_sum va Anime.rating_count ustunlarini yangilaydi.
        Increment o'rniga har safar qayta hisoblash — drift bo'lmaydi.
        """
        session = await RatingRepository._prepare_session(session)

        agg_stmt = select(
            func.coalesce(func.sum(AnimeRating.score), 0),
            func.count(AnimeRating.id)
        ).where(AnimeRating.anime_id == anime_id)

        result = await session.execute(agg_stmt)
        rating_sum, rating_count = result.one()

        await session.execute(
            update(Anime)
            .where(Anime.anime_id == anime_id)
            .values(rating_sum=rating_sum, rating_count=rating_count)
        )

        average = round(float(rating_sum) / rating_count, 1) if rating_count else 0.0
        return average, rating_count