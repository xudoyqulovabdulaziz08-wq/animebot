import logging
from typing import Tuple, List, Dict, Any
from sqlalchemy.exc import SQLAlchemyError

from repositories.favorite_repository import FavoriteRepository
from database.cache import cache_manager  # Markaziy CacheManager import qilindi

logger = logging.getLogger("FavoriteService")

class FavoriteService:
    """
    🚀 Favorite Service (CACHE-AWARE & TRANSACTION-SAFE)
    - Valkey/Redis L1+L2 kesh bilan integratsiyalangan
    - Tranzaksiyaviy xavfsiz (Commit / Rollback)
    - Kesh avtomatik invalidatsiya qilinadi
    """

    def __init__(self, session):
        self.session = session
        self.repo = FavoriteRepository()
        self.cache = cache_manager

    # ==================================================
    # 🎯 CHECK IS FAVORITE (CACHE-FIRST)
    # ==================================================
    async def check_is_favorite(self, user_id: int, anime_id: int) -> bool:
        """Kesh orqali tezkor tekshirish (Bot Inline tugmalari uchun ultra-fast)."""
        fav_ids = await self.get_user_favorite_ids(user_id)
        return anime_id in fav_ids

    # ==================================================
    # 📋 GET USER FAVORITE IDS (CACHE-FIRST)
    # ==================================================
    async def get_user_favorite_ids(self, user_id: int) -> List[int]:
        """User sevgan barcha anime_id lar ro'yxatini keshdan/DBdan oladi."""
        cached_ids = await self.cache.get("user_fav_ids", user_id)
        if cached_ids is not None:
            return cached_ids

        fav_ids = await self.repo.get_user_favorite_ids(self.session, user_id)
        await self.cache.set("user_fav_ids", user_id, fav_ids, ttl=30)
        return fav_ids

    # ==================================================
    # 🔄 TOGGLE FAVORITE (TRANSACTION SAFE & CACHE INVALIDATE)
    # ==================================================
    async def toggle_favorite(self, user_id: int, anime_id: int) -> Tuple[bool, str]:
        """
        Telegram Bot Inline tugmalari uchun (❤️/🤍).
        O'zgarish bo'lsa DBga commit qiladi va keshni majburiy tozalaydi.
        """
        try:
            if hasattr(self.session, "_ensure_session"):
                await self.session._ensure_session()

            is_fav = await self.check_is_favorite(user_id, anime_id)

            if is_fav:
                success = await self.repo.remove_favorite(self.session, user_id, anime_id)
                action = "removed"
            else:
                success = await self.repo.add_favorite(self.session, user_id, anime_id)
                action = "added"

            if success:
                if hasattr(self.session, "commit"):
                    await self.session.commit()

                # 🔥 Keshni aniq va to'g'ri tozalaymiz (Invalidate)
                await self.cache.invalidate("user_fav_ids", user_id, broadcast=True)
                await self.cache.invalidate("user_fav_count", user_id, broadcast=True)
                
                # 💥 BARCHA SAHIFALAR KESHINI TOZALASH:
                # Wildcard keshda ishlamasligi mumkinligi sababli pattern yoki barcha umumiy prefiksni o'chiramiz
                if hasattr(self.cache, "delete_pattern"):
                    await self.cache.delete_pattern(f"user_fav_page:{user_id}:*")
                else:
                    # Agar delete_pattern bo'lmasa, eng ko'p kiriladigan 10 ta sahifa keshini tozalaymiz
                    for page_num in range(1, 11):
                        for limit_num in [6, 10]:
                            await self.cache.invalidate("user_fav_page", f"{user_id}:{page_num}:{limit_num}", broadcast=True)

                return True, action

            return False, "error"

        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.exception(f"Error in toggle_favorite (User: {user_id}, Anime: {anime_id}): {e}")
            return False, "error"

    
    # ==================================================
    # 📊 GET USER FAVORITES COUNT (CACHE-FIRST)
    # ==================================================
    async def get_user_favorites_count(self, user_id: int) -> int:
        """
        Foydalanuvchi yoqtirgan animelar sonini qaytaradi.
        """
        cached_count = await self.cache.get("user_fav_count", user_id)
        if cached_count is not None:
            return int(cached_count)

        count = await self.repo.get_user_favorites_count(self.session, user_id)
        await self.cache.set("user_fav_count", user_id, count, ttl=30)

        return count

    # ==================================================
    # ⚡️ GET USER FAVORITES PAGE (CACHE-FIRST + PAGINATED)
    # ==================================================
    async def get_user_favorite_anime_list(
        self, 
        user_id: int, 
        page: int = 1, 
        per_page: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Foydalanuvchining ma'lum bir sahifadagi sevimlilar ro'yxatini keshdan/DBdan oladi.
        """
        cache_sub_key = f"{user_id}:{page}:{per_page}"
        
        # 1. Keshni tekshiramiz
        cached_list = await self.cache.get("user_fav_page", cache_sub_key)
        if cached_list is not None:
            return cached_list

        # 2. Keshda bo'lmasa DBdan JOIN so'rovi bilan bittada olamiz
        offset = (page - 1) * per_page
        anime_list = await self.repo.get_user_favorite_anime_list(
            self.session, 
            user_id=user_id, 
            offset=offset, 
            limit=per_page
        )

        # 3. Keshga yozamiz (TTL: 1 soat)
        await self.cache.set("user_fav_page", cache_sub_key, anime_list, ttl=30)

        return anime_list