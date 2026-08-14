from __future__ import annotations

import logging
from typing import Any, Optional, Dict, List

from repositories.comment_repository import CommentRepository

logger = logging.getLogger("CommentService")


class CommentService:
    """
    🚀 Business Logic Layer for Comments (REAL-TIME, TRANSACTION-SAFE)
    - Tranzaksiyalarni to'liq nazorat qiladi (Commit / Rollback)
    - Kesh QATLAMI OLIB TASHLANDI: har bir chaqiruv to'g'ridan-to'g'ri bazadan o'qiydi/yozadi.
      Shu sabab sayt (web) va bot orasida ma'lumot mos kelmasligi (stale cache) muammosi
      butunlay yo'qoladi — izohlar har doim real vaqtda (real-time) ko'rinadi.
    """

    def __init__(self, session: Any):
        self.session = session
        self.repo = CommentRepository()
# ==================================================
    # ➕ ADD COMMENT / REPLY (TRANSACTION SAFE)
    # ==================================================
    # ==================================================
    # ➕ ADD COMMENT / REPLY (TRANSACTION SAFE & MAX 2-LEVEL)
    # ==================================================
    async def add_comment(
        self,
        anime_id: int,
        user_id: int,
        text: str,
        parent_id: Optional[int] = None
    ) -> Optional[Dict]:
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        try:
            target_parent_id = parent_id

            if parent_id:
                parent_comment = await self.repo.get_by_id(self.session, parent_id)
                if not parent_comment or parent_comment["anime_id"] != anime_id:
                    logger.warning(f"⚠️ Noto'g'ri parent_id={parent_id} berildi.")
                    return None

                # 🚀 2-DARAJA CHEKLOVI (FLATTENING LOGIC):
                # Agar javob yozilayotgan izohning O'ZI HAM javob bo'lsa (parent'i bo'lsa)
                if parent_comment.get("parent") and parent_comment["parent"].get("id"):
                    # Javobni ichma-ich kiritmaymiz, asosiy (root) izoh ID'siga bog'laymiz!
                    target_parent_id = parent_comment["parent"]["id"]
                    
                    # Foydalanuvchi kimga javob yozganini bildirib qo'yish uchun (opsional)
                    author_name = parent_comment.get("user", {}).get("username") or "Foydalanuvchi"
                    text = f"{author_name}, {text}"

            comment = await self.repo.create(
                self.session, anime_id, user_id, text, target_parent_id
            )

            if hasattr(self.session, "commit"):
                await self.session.commit()

            logger.info(f"💬 Izoh qo'shildi: ID={comment['id']} | Anime={anime_id} | User={user_id} | Parent={target_parent_id}")
            return comment

        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.error(f"❌ Izoh qo'shishda xato yuz berdi: {e}")
            raise e
    # ==================================================
    # 📋 GET ANIME COMMENTS
    # ==================================================
    async def get_anime_comments(
        self,
        anime_id: int,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict]:
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        return await self.repo.get_anime_comments(
            self.session, anime_id, limit, offset
        )

    # ==================================================
    # 📊 GET COMMENTS COUNT
    # ==================================================
    async def get_comments_count(self, anime_id: int) -> int:
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        return await self.repo.get_comments_count_by_anime_id(self.session, anime_id)

    # ==================================================
    # 👤 GET USER COMMENTS COUNT
    # ==================================================
    async def get_user_comments_count(self, anime_id: int, user_id: int) -> int:
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        return await self.repo.get_user_comments_count_by_anime_id(
            self.session, anime_id, user_id
        )

    # ==================================================
    # 📝 GET USER COMMENTS
    # ==================================================
    async def get_user_comments(self, anime_id: int, user_id: int) -> List[Dict]:
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        return await self.repo.get_user_comments_by_anime_id(
            self.session, anime_id, user_id
        )

    # ==================================================
    # 🆔 GET ANIME COMMENT IDs (index o'rniga — navigatsiya shu ID ro'yxati bo'yicha yuradi)
    # ==================================================
    async def get_anime_comment_ids(self, anime_id: int) -> List[int]:
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        return await self.repo.get_anime_comment_ids(self.session, anime_id)

    # ==================================================
    # 🆔 GET USER COMMENT IDs (index o'rniga)
    # ==================================================
    async def get_user_comment_ids(self, anime_id: int, user_id: int) -> List[int]:
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        return await self.repo.get_user_comment_ids(self.session, anime_id, user_id)

    # ==================================================
    # 💬 GET COMMENT & REPLIES
    # ==================================================
    async def get_comment_replies_count(self, comment_id: int) -> int:
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        return await self.repo.get_comment_replies_count(self.session, comment_id)

    async def get_comment_replies(
        self,
        comment_id: int,
        limit: int = 10,
        offset: int = 0
    ) -> List[Dict]:
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        return await self.repo.get_comment_replies(
            self.session, comment_id, limit, offset
        )

    async def get_comment_by_id(self, comment_id: int) -> Optional[Dict]:
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        return await self.repo.get_by_id(self.session, comment_id)

    # ==================================================
    # 🗑 DELETE COMMENT (TRANSACTION SAFE)
    # ==================================================
    async def delete_comment(self, comment_id: int, user_id: Optional[int] = None, anime_id: int = 0) -> bool:
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        try:
            comment = await self.repo.get_by_id(self.session, comment_id)
            if not comment:
                return False

            actual_user_id = user_id or comment.get("user_id")

            deleted = await self.repo.delete(self.session, comment_id, user_id)
            if not deleted:
                if hasattr(self.session, "rollback"):
                    await self.session.rollback()
                return False

            if hasattr(self.session, "commit"):
                await self.session.commit()

            logger.info(f"🗑 Izoh o'chirildi: ID={comment_id} | User={actual_user_id}")
            return True

        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.error(f"❌ Izohni o'chirishda xato yuz berdi: {e}")
            raise e

    # ==================================================
    # ✏️ EDIT COMMENT (TRANSACTION SAFE)
    # ==================================================
    async def update_comment(
        self,
        comment_id: int,
        user_id: int,
        anime_id: int,
        new_text: str
    ) -> bool:
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        try:
            comment = await self.repo.get_by_id(self.session, comment_id)
            if not comment:
                return False

            updated = await self.repo.update_text(
                self.session,
                comment_id=comment_id,
                user_id=user_id,
                new_text=new_text
            )

            if not updated:
                if hasattr(self.session, "rollback"):
                    await self.session.rollback()
                return False

            if hasattr(self.session, "commit"):
                await self.session.commit()

            # 🟢 ORM Sessiya xotirasini (Identity Map) majburiy tozalash — keyingi
            # get_comment_by_id chaqiruvi bazadan YANGI ma'lumotni o'qishini kafolatlaydi
            if hasattr(self.session, "expire_all"):
                self.session.expire_all()

            logger.info(f"✏️ Izoh tahrirlandi: ID={comment_id} | User={user_id}")
            return True

        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.error(f"❌ Izohni tahrirlashda xato yuz berdi: {e}")
            raise e