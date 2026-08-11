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
    async def _invalidate_comment_caches(self, anime_id: int, user_id: int, parent_id: Optional[int] = None) -> None:
        """Izoh o'zgarganda tegishli barcha kesh to'plamini tozalash."""
        await self.cache.invalidate("anime_comments_count", anime_id, broadcast=True)
        await self.cache.invalidate("anime_comments_list", anime_id, broadcast=True)
        await self.cache.invalidate(f"user_comments_count:{user_id}", anime_id, broadcast=True)
        await self.cache.invalidate(f"user_comments_list:{user_id}", anime_id, broadcast=True)
        if parent_id is not None:
            await self.cache.invalidate(f"comment_replies:{parent_id}", "all", broadcast=True)

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
        """
        Yangi izoh yozish yoki ota-izohga reply berish.
        Muvaffaqiyatli commit'dan so'ng keshlar tozalanadi.
        """
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
            await self._invalidate_comment_caches(anime_id, user_id)

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
        """Anime izohlarini kesh-first usulida pagination bilan yuklaydi."""
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
        """Anime izohlarining umumiy sonini oladi."""
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
        """Foydalanuvchining ma'lum bir animega yozgan izohlari soni."""
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
        """Foydalanuvchining ma'lum animega yozgan barcha izohlari ro'yxati."""
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
    # 🗑 DELETE COMMENT (TRANSACTION SAFE)
    # ==================================================
    async def delete_comment(
        self, 
        comment_id: int, 
        anime_id: int, 
        user_id: Optional[int] = None
    ) -> bool:
        """
        Izohni o'chirish.
        user_id yuborilsa — faqat izoh egasi o'chira oladi.
        user_id=None bo'lsa — Admin istalgan izohni o'chira oladi.
        """
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        try:
            ok = await self.repo.delete(self.session, comment_id, user_id)
            if not ok:
                return False

            if hasattr(self.session, "commit"):
                await self.session.commit()

            # 🔥 CACHE INVALIDATION
            if user_id:
                await self._invalidate_comment_caches(anime_id, user_id)
            else:
                await self.cache.invalidate("anime_comments_count", anime_id, broadcast=True)
                await self.cache.invalidate("anime_comments_list", anime_id, broadcast=True)

            logger.info(f"🗑 Izoh o'chirildi: ID={comment_id} | Anime={anime_id}")
            return True

        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.error(f"❌ Izohni o'chirishda xato yuz berdi: {e}")
            raise e
        

    async def get_user_comment_by_index(
        self, anime_id: int, user_id: int, index: int = 0
    ) -> Optional[Dict[str, Any]]:
        """
        Kesh bilan integratsiyalashgan holda foydalanuvchining index-inchi izohini olish.
        """
        cache_key = f"user_comment_idx:{index}"
        cached = await self.cache.get(f"user_comments_list:{user_id}:{anime_id}", cache_key)
        if cached is not None:
            return cached

        comment_data = await self.repo.get_user_comment_by_index(
            self.session, anime_id, user_id, index
        )

        if comment_data:
            await self.cache.set(
                f"user_comments_list:{user_id}:{anime_id}",
                cache_key,
                comment_data,
                ttl=600
            )

        return comment_data

    
    # ==================================================
    # 💬 GET COMMENT & REPLIES (CACHE-FIRST WITH PAGINATION)
    # ==================================================
    async def get_comment_replies_count(self, comment_id: int) -> int:
        """
        💬 Izoh javoblari sonini kesh-first yondashuvi bilan olish.
        """
        cache_namespace = f"comment_replies_count:{comment_id}"
        cached_count = await self.cache.get(cache_namespace, "count")
        
        if cached_count is not None:
            return cached_count

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
        """
        🚀 Izoh javoblarini kesh orqali tezkor oladi.
        """
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
        """
        🚀 ID bo'yicha izohni kesh/repository orqali olish.
        """
        cache_namespace = f"comment_detail:{comment_id}"
        cached_data = await self.cache.get(cache_namespace, "data")

        if cached_data is not None:
            return cached_data

        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

    # Repository'dagi real metod nomi: get_by_id
        comment = await self.repo.get_by_id(self.session, comment_id)
        if comment:
            await self.cache.set(cache_namespace, "data", comment, ttl=600)

        return comment
    



    async def delete_comment(self, comment_id: int, user_id: int, anime_id: int) -> bool:
        """
        🗑 Izohni bazadan o'chiradi va tegishli keshni tozalaydi.
        """
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        # 1. Izohni o'chirishdan oldin parent_id sini bilib olamiz (kesh tozalash uchun)
        comment = await self.repo.get_by_id(self.session, comment_id)
        if not comment:
            return False

        parent_id = comment.get("parent_id")

        # 2. Bazadan o'chiramiz
        deleted = await self.repo.delete(self.session, comment_id, user_id)
        if not deleted:
            await self.session.rollback()
            return False

        await self.session.commit()

        # 3. Keshni invalidatsiya qilamiz
        await self._invalidate_comment_caches(
            anime_id=anime_id, 
            user_id=user_id, 
            parent_id=parent_id
        )

        return True