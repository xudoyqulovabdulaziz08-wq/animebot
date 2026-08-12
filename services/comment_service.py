from __future__ import annotations

import logging
from typing import Any, Optional, Dict, List

from repositories.comment_repository import CommentRepository
from database.cache import cache_manager

logger = logging.getLogger("CommentService")


class CommentService:
    """
    🚀 Business Logic Layer for Comments (CACHE-AWARE & TRANSACTION-SAFE)
    - Tranzaksiyalarni to'liq nazorat qiladi (Commit / Rollback)
    - Cascade invalidation (Izoh qo'shilganda/o'chirilganda tegishli keshlar o'chadi)
    """

    def __init__(self, session: Any):
        self.session = session
        self.repo = CommentRepository()
        self.cache = cache_manager

    # ==================================================
    # 🧹 CACHE INVALIDATION HELPER
    # ==================================================
    async def _invalidate_comment_caches(
        self,
        anime_id: int,
        user_id: int,
        comment_id: Optional[int] = None,
        parent_id: Optional[int] = None
    ) -> None:
        """Izoh o'zgarganda tegishli barcha kesh to'plamini tozalash."""

        # 1. Aniq komment keshini va uning o'z javoblari keshini o'chirish
        #    (komment o'chirilganda yoki tahrirlanganda uning replies keshi ham eskiradi)
        if comment_id:
            await self.cache.invalidate(f"comment_detail:{comment_id}", broadcast=True)
            await self.cache.invalidate(f"comment_replies_count:{comment_id}", broadcast=True)
            await self.cache.invalidate(f"comment_replies_list:{comment_id}", broadcast=True)

        # 2. Umumiy ro'yxatlar keshini tozalash
        await self.cache.invalidate("anime_comments_count", anime_id, broadcast=True)
        await self.cache.invalidate(f"anime_comments_list:{anime_id}", broadcast=True)
        await self.cache.invalidate(f"user_comments_count:{user_id}", anime_id, broadcast=True)

        # 🟢 Pattern/Wildcard bo'yicha yoki ushbu kalitga tegishli barcha sub-keshlarni o'chirish
        await self.cache.invalidate(f"user_comments_list:{user_id}", broadcast=True)
        await self.cache.invalidate(f"user_comments_list:{user_id}:{anime_id}", broadcast=True)

        # Agar kesh menderjerda delete_by_pattern bo'lsa (Redis/Valkey):
        if hasattr(self.cache, "delete_by_pattern"):
            await self.cache.delete_by_pattern(f"*user_comments_list:{user_id}:*")
            if comment_id:
                await self.cache.delete_by_pattern(f"*comment_detail:{comment_id}*")

        if parent_id is not None:
            await self.cache.invalidate(f"comment_replies_count:{parent_id}", broadcast=True)
            await self.cache.invalidate(f"comment_replies_list:{parent_id}", broadcast=True)

    # ==================================================
    # ➕ ADD COMMENT / REPLY (TRANSACTION SAFE)
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
            if parent_id:
                parent_comment = await self.repo.get_by_id(self.session, parent_id)
                if not parent_comment or parent_comment["anime_id"] != anime_id:
                    logger.warning(f"⚠️ Noto'g'ri parent_id={parent_id} berildi.")
                    return None

            comment = await self.repo.create(
                self.session, anime_id, user_id, text, parent_id
            )

            if hasattr(self.session, "commit"):
                await self.session.commit()

            # 🔥 CASCADE CACHE INVALIDATION
            await self._invalidate_comment_caches(anime_id, user_id, parent_id=parent_id)

            logger.info(f"💬 Izoh qo'shildi: ID={comment['id']} | Anime={anime_id} | User={user_id}")
            return comment

        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.error(f"❌ Izoh qo'shishda xato yuz berdi: {e}")
            raise e

    # ==================================================
    # 📋 GET ANIME COMMENTS (CACHE-FIRST)
    # ==================================================
    async def get_anime_comments(
        self,
        anime_id: int,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict]:
        cache_key = f"{limit}:{offset}"
        cached = await self.cache.get(f"anime_comments_list:{anime_id}", cache_key)
        if cached is not None:
            logger.debug(f"🎯 CACHE HIT: comments for anime_id={anime_id}, offset={offset}")
            return cached

        comments = await self.repo.get_anime_comments(
            self.session, anime_id, limit, offset
        )

        await self.cache.set(
            f"anime_comments_list:{anime_id}", cache_key, comments, ttl=600
        )
        return comments

    # ==================================================
    # 📊 GET COMMENTS COUNT (CACHE-FIRST)
    # ==================================================
    async def get_comments_count(self, anime_id: int) -> int:
        cached_count = await self.cache.get("anime_comments_count", anime_id)
        if cached_count is not None:
            return int(cached_count)

        count = await self.repo.get_comments_count_by_anime_id(self.session, anime_id)
        await self.cache.set("anime_comments_count", anime_id, count, ttl=3600)
        return count

    # ==================================================
    # 👤 GET USER COMMENTS COUNT (CACHE-FIRST)
    # ==================================================
    async def get_user_comments_count(self, anime_id: int, user_id: int) -> int:
        cache_key = f"user_comments_count:{user_id}"
        cached_count = await self.cache.get(cache_key, anime_id)
        if cached_count is not None:
            return int(cached_count)

        count = await self.repo.get_user_comments_count_by_anime_id(
            self.session, anime_id, user_id
        )

        await self.cache.set(cache_key, anime_id, count, ttl=900)
        return count

    # ==================================================
    # 📝 GET USER COMMENTS (CACHE-FIRST)
    # ==================================================
    async def get_user_comments(self, anime_id: int, user_id: int) -> List[Dict]:
        cache_key = f"user_comments_list:{user_id}"
        cached = await self.cache.get(cache_key, anime_id)
        if cached is not None:
            return cached

        comments = await self.repo.get_user_comments_by_anime_id(
            self.session, anime_id, user_id
        )

        await self.cache.set(cache_key, anime_id, comments, ttl=600)
        return comments

    # ==================================================
    # 📌 GET USER COMMENT BY INDEX
    # ==================================================
    async def get_user_comment_by_index(
        self, anime_id: int, user_id: int, index: int = 0
    ) -> Optional[Dict[str, Any]]:
        cache_key = f"user_comment_idx:{index}"
        namespace = f"user_comments_list:{user_id}:{anime_id}"

        cached = await self.cache.get(namespace, cache_key)
        if cached is not None:
            return cached

        comment_data = await self.repo.get_user_comment_by_index(
            self.session, anime_id, user_id, index
        )

        if comment_data:
            await self.cache.set(
                namespace,
                cache_key,
                comment_data,
                ttl=600
            )

        return comment_data

    # ==================================================
    # 💬 GET COMMENT & REPLIES
    # ==================================================
    async def get_comment_replies_count(self, comment_id: int) -> int:
        cache_namespace = f"comment_replies_count:{comment_id}"
        cached_count = await self.cache.get(cache_namespace, "count")

        if cached_count is not None:
            return int(cached_count)

        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        count = await self.repo.get_comment_replies_count(self.session, comment_id)
        await self.cache.set(cache_namespace, "count", count, ttl=600)
        return count

    async def get_comment_replies(
        self,
        comment_id: int,
        limit: int = 10,
        offset: int = 0
    ) -> List[Dict]:
        cache_namespace = f"comment_replies_list:{comment_id}"
        cache_key = f"limit_{limit}:offset_{offset}"

        cached_data = await self.cache.get(cache_namespace, cache_key)
        if cached_data is not None:
            return cached_data

        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        data = await self.repo.get_comment_replies(
            self.session, comment_id, limit, offset
        )

        await self.cache.set(cache_namespace, cache_key, data, ttl=600)
        return data

    async def get_comment_by_id(self, comment_id: int) -> Optional[Dict]:
        cache_namespace = f"comment_detail:{comment_id}"
        cached_data = await self.cache.get(cache_namespace, "data")

        if cached_data is not None:
            return cached_data

        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        comment = await self.repo.get_by_id(self.session, comment_id)
        if comment:
            await self.cache.set(cache_namespace, "data", comment, ttl=600)

        return comment

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

            parent_id = comment.get("parent_id")
            actual_anime_id = anime_id or comment.get("anime_id", 0)
            actual_user_id = user_id or comment.get("user_id")

            deleted = await self.repo.delete(self.session, comment_id, user_id)
            if not deleted:
                if hasattr(self.session, "rollback"):
                    await self.session.rollback()
                return False

            if hasattr(self.session, "commit"):
                await self.session.commit()

            # 🔥 CACHE INVALIDATION
            # comment_id beriladi — shu orqali comment_detail HAMDA shu kommentning
            # o'z javoblari (comment_replies_count/list) keshi ham tozalanadi.
            await self._invalidate_comment_caches(
                anime_id=actual_anime_id,
                user_id=actual_user_id,
                comment_id=comment_id,
                parent_id=parent_id
            )

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
            # 1. Avval izohni topamiz
            comment = await self.repo.get_by_id(self.session, comment_id)
            if not comment:
                return False

            # Dictionary yoki ORM obyektligiga qarab parent_id olish
            parent_id = comment.get("parent_id") if isinstance(comment, dict) else getattr(comment, "parent_id", None)

            # 2. Bazada matnni yangilash
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

            # 🟢 MUHIM: ORM Sessiya xotirasini (Identity Map) majburiy tozalash
            # Bu get_user_comment_by_index chaqirilganda bazadan YANGI ma'lumotni o'qishga majbur qiladi
            if hasattr(self.session, "expire_all"):
                self.session.expire_all()

            # 🔥 CACHE INVALIDATION
            await self._invalidate_comment_caches(
                anime_id=anime_id,
                user_id=user_id,
                comment_id=comment_id,
                parent_id=parent_id
            )

            logger.info(f"✏️ Izoh tahrirlandi: ID={comment_id} | User={user_id}")
            return True

        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.error(f"❌ Izohni tahrirlashda xato yuz berdi: {e}")
            raise e