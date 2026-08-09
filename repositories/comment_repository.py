import logging
from typing import Any
from sqlalchemy import select, func
from database.models import Comment

logger = logging.getLogger("CommentRepository")

class CommentRepository:

    @staticmethod
    def _get_real_session(session: Any):
        if hasattr(session, "_session"):
            return session._session
        return session

    @staticmethod
    async def _prepare_session(session: Any):
        if hasattr(session, "_ensure_session"):
            await session._ensure_session()
        return CommentRepository._get_real_session(session)

    @staticmethod
    async def get_comments_count_by_anime_id(session: Any, anime_id: int) -> int:
        """
        ⚡ Bazadan muayyan animening jami izohlar sonini unumli oladi.
        """
        real_session = await CommentRepository._prepare_session(session)
        stmt = (
            select(func.count(Comment.id))
            .where(Comment.anime_id == anime_id)
        )
        result = await real_session.execute(stmt)
        return result.scalar() or 0