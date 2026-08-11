from __future__ import annotations

import logging
from typing import Any, Optional, Dict, List
from sqlalchemy import select, func, delete, update
from sqlalchemy.orm import selectinload
from database.models import Comment, DBUser
from sqlalchemy.orm import aliased

logger = logging.getLogger("CommentRepository")


class CommentRepository:
    """
    📂 Data Access Layer for Comments
    - Atomik SQL so'rovlar
    - Session unifikatsiyasi va xavfsiz yuklash
    """

    # ================= SESSION HELPERS =================
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

    # ================= CREATE COMMENT =================
    @staticmethod
    async def create(
        session: Any,
        anime_id: int,
        user_id: int,
        text: str,
        parent_id: Optional[int] = None
    ) -> Dict:
        """Yangi izoh yozish yoki javob (reply) berish."""
        real_session = await CommentRepository._prepare_session(session)

        comment = Comment(
            anime_id=anime_id,
            user_id=user_id,
            text=text,
            parent_id=parent_id
        )

        real_session.add(comment)
        await real_session.flush()  # ID va created_at generatsiya bo'lishi uchun

        # Munosabatlar xavfsiz formatga o'tkaziladi
        data = comment.to_dict()
        data["replies_count"] = 0
        return data

    # ================= GET BY ID =================
    @staticmethod
    async def get_by_id(session: Any, comment_id: int) -> Optional[Dict]:
        """Izohni ID bo'yicha olish (muallif va javoblar bilan birga)."""
        real_session = await CommentRepository._prepare_session(session)

        stmt = (
            select(Comment)
            .where(Comment.id == comment_id)
            .options(
                selectinload(Comment.user),
                selectinload(Comment.replies)
            )
        )
        result = await real_session.execute(stmt)
        comment = result.scalar_one_or_none()

        if not comment:
            return None

        data = comment.to_dict()
        if hasattr(comment, "user") and comment.user:
            data["user"] = comment.user.to_dict()
        data["replies_count"] = len(comment.replies) if hasattr(comment, "replies") else 0
        return data

    # ================= LIST ANIME COMMENTS (PAGINATED) =================
    @staticmethod
    async def get_anime_comments(
        session: Any, 
        anime_id: int, 
        limit: int = 20, 
        offset: int = 0
    ) -> List[Dict]:
        """
        Anime izohlarini pagination bilan olish.
        Faqat asosiy izohlar (parent_id IS NULL) olinadi.
        """
        real_session = await CommentRepository._prepare_session(session)

        stmt = (
            select(Comment)
            .where(Comment.anime_id == anime_id, Comment.parent_id.is_(None))
            .options(
                selectinload(Comment.user),
                selectinload(Comment.replies).selectinload(Comment.user)
            )
            .order_by(Comment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await real_session.execute(stmt)
        comments_list = []

        for comment in result.scalars().all():
            c_data = comment.to_dict()
            if hasattr(comment, "user") and comment.user:
                c_data["user"] = comment.user.to_dict()
            
            # Javoblarni tayyorlash
            replies_data = []
            if hasattr(comment, "replies") and comment.replies:
                for reply in comment.replies:
                    r_data = reply.to_dict()
                    if hasattr(reply, "user") and reply.user:
                        r_data["user"] = reply.user.to_dict()
                    replies_data.append(r_data)

            c_data["replies"] = replies_data
            c_data["replies_count"] = len(replies_data)
            comments_list.append(c_data)

        return comments_list

    # ================= COUNTS =================
    @staticmethod
    async def get_comments_count_by_anime_id(session: Any, anime_id: int) -> int:
        """Animening jami izohlar soni (SQL aggregate)."""
        real_session = await CommentRepository._prepare_session(session)
        stmt = select(func.count(Comment.id)).where(Comment.anime_id == anime_id)
        result = await real_session.execute(stmt)
        return result.scalar() or 0

    @staticmethod
    async def get_user_comments_count_by_anime_id(
        session: Any, anime_id: int, user_id: int
    ) -> int:
        """Foydalanuvchining ma'lum bir animega yozgan izohlari soni."""
        real_session = await CommentRepository._prepare_session(session)
        stmt = select(func.count(Comment.id)).where(
            Comment.anime_id == anime_id,
            Comment.user_id == user_id
        )
        result = await real_session.execute(stmt)
        return result.scalar() or 0

    # ================= DELETE COMMENT =================
    @staticmethod
    async def delete(session: Any, comment_id: int, user_id: Optional[int] = None) -> bool:
        """
        Izohni o'chirish. 
        Agar user_id berilsa — faqat o'zining izohini o'chira oladi.
        """
        real_session = await CommentRepository._prepare_session(session)

        stmt = delete(Comment).where(Comment.id == comment_id)
        if user_id is not None:
            stmt = stmt.where(Comment.user_id == user_id)

        result = await real_session.execute(stmt)
        await real_session.flush()
        return result.rowcount > 0
    
    @staticmethod
    async def get_user_comments_by_anime_id(
        session: Any, anime_id: int, user_id: int
    ) -> List[Dict]:
        """
        Foydalanuvchining izohlarini ota-izoh (parent) va uning muallifi bilan birga olish.
        """
        real_session = await CommentRepository._prepare_session(session)

        # Ota izoh va uning muallifi uchun alias yaratamiz
        ParentComment = aliased(Comment)
        ParentUser = aliased(DBUser)

        stmt = (
            select(Comment, ParentComment, ParentUser)
            .outerjoin(ParentComment, Comment.parent_id == ParentComment.id)
            .outerjoin(ParentUser, ParentComment.user_id == ParentUser.user_id)  # <-- ParentUser.id -> ParentUser.user_id
            .where(
                Comment.anime_id == anime_id,
                Comment.user_id == user_id
            )
            .order_by(Comment.created_at.desc())
        )

        result = await real_session.execute(stmt)
    
        comments = []
        for row in result.all():
            comment, parent, parent_author = row
            c_dict = comment.to_dict()
        
            # Agar bu javob (reply) bo'lsa, ota izoh ma'lumotlarini biriktiramiz
            if parent:
                c_dict["parent"] = {
                    "id": parent.id,
                    "text": parent.text,
                    "author_id": parent.user_id,
                    "author_name": parent_author.username if parent_author and parent_author.username else "Noma'lum"  # <-- first_name -> username
                }
            else:
                c_dict["parent"] = None

            comments.append(c_dict)

        return comments
    

    @staticmethod
    async def get_user_comment_by_index(
        session: Any, anime_id: int, user_id: int, index: int = 0
    ) -> Optional[Dict[str, Any]]:
        """
        Foydalanuvchining ma'lum bir animega yozgan izohlaridan index-inchisini olish.
        Unda ota-izoh (agar bu reply bo'lsa) va unga kelgan javoblar soni ham hisoblanadi.
        """
        real_session = await CommentRepository._prepare_session(session)

        ParentComment = aliased(Comment)
        ParentUser = aliased(DBUser)
        ReplyComment = aliased(Comment)

        # 1. Asosiy so'rov: Izoh, uning Parent'i va Parent muallifi
        stmt = (
            select(
                Comment,
                ParentComment,
                ParentUser,
                func.count(ReplyComment.id).label("replies_count")
            )
            .outerjoin(ParentComment, Comment.parent_id == ParentComment.id)
            .outerjoin(ParentUser, ParentComment.user_id == ParentUser.user_id)  # <-- ParentUser.id -> ParentUser.user_id
            .outerjoin(ReplyComment, ReplyComment.parent_id == Comment.id)
            .where(
                Comment.anime_id == anime_id,
                Comment.user_id == user_id
            )
            .group_by(Comment.id, ParentComment.id, ParentUser.user_id)  # <-- ParentUser.id -> ParentUser.user_id
            .order_by(Comment.created_at.desc())
            .limit(1)
            .offset(index)
        )

        result = await real_session.execute(stmt)
        row = result.first()

        if not row:
            return None

        comment, parent, parent_author, replies_count = row
        c_dict = comment.to_dict()
        c_dict["replies_count"] = replies_count

        if parent:
            c_dict["parent"] = {
                "id": parent.id,
                "text": parent.text,
                "author_name": parent_author.username if parent_author and parent_author.username else "Noma'lum"  # <-- first_name -> username
            }
        else:
            c_dict["parent"] = None

        return c_dict
    
    # ================= GET COMMENT WITH REPLIES (OPTIMIZED) =================
    @staticmethod
    async def get_comment_replies_count(session: Any, comment_id: int) -> int:
        """
        💬 Bitta izohga qancha javob (reply) yozilganini sonini qaytaradi.
        """
        real_session = await CommentRepository._prepare_session(session)
        stmt = select(func.count(Comment.id)).where(Comment.parent_id == comment_id)
        result = await real_session.execute(stmt)
        return result.scalar() or 0
    

    @staticmethod
    async def get_comment_replies(
        session: Any, 
        comment_id: int, 
        limit: int = 10, 
        offset: int = 0
    ) -> List[Dict]:
        """
        💬 Izohga yozilgan javoblarni muallifi bilan birga tortib beradi.
        """
        real_session = await CommentRepository._prepare_session(session)
        
        stmt = (
            select(Comment)
            .where(Comment.parent_id == comment_id)
            .options(selectinload(Comment.user))
            .order_by(Comment.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await real_session.execute(stmt)
        replies = result.scalars().all()

        replies_data = []
        for r in replies:
            r_dict = r.to_dict()
            if hasattr(r, "user") and r.user:
                r_dict["user"] = r.user.to_dict()
            replies_data.append(r_dict)

        return replies_data