from __future__ import annotations

import logging
from typing import Any, Dict, Tuple, List
from repositories.subscription_repository import SubscriptionRepository
from database.cache import cache_manager  # 👈 Kesh menejerini chaqiramiz

logger = logging.getLogger("SubscriptionService")

class SubscriptionService:

    def __init__(self, session: Any):
        self.session = session
        self.repo = SubscriptionRepository()
        self.cache = cache_manager  # 👈 self.cache ga biriktiramiz

    # ================= PUBLIC METHODS =================

    async def is_subscribed(self, user_id: int, anime_id: int) -> bool:
        cache_key = f"{user_id}:{anime_id}"
        cached_status = await self.cache.get("user_subscription", cache_key)
        
        if cached_status is not None:
            return cached_status

        # Repo o'zi sessiyani tayyorlaydi
        status = await self.repo.is_subscribed(self.session, user_id, anime_id)
        await self.cache.set("user_subscription", cache_key, status, ttl=30)
        return status

    async def toggle_subscription(self, user_id: int, anime_id: int) -> bool:
        try:
            new_status = await self.repo.toggle_subscription(self.session, user_id, anime_id)
            
            if hasattr(self.session, "commit"):
                await self.session.commit()

            cache_key = f"{user_id}:{anime_id}"
            await self.cache.set("user_subscription", cache_key, new_status, ttl=30)
            
            # Yangi obuna qo'shilsa yoki o'chirilsa, umumiy ro'yxat keshini tozalaymiz
            await self.cache.invalidate("user_sub_page", f"{user_id}:*", broadcast=True)
            
            return new_status

        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.error(f"❌ Obuna toggle qilishda xatolik: {e}")
            raise e

    async def add_subscription(self, user_id: int, anime_id: int) -> bool:
        try:
            res = await self.repo.add_subscription(self.session, user_id, anime_id)
            if hasattr(self.session, "commit"):
                await self.session.commit()
                
            cache_key = f"{user_id}:{anime_id}"
            await self.cache.set("user_subscription", cache_key, True, ttl=30)
            await self.cache.invalidate("user_sub_page", f"{user_id}:*", broadcast=True)
            
            return res
        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            raise e

    async def remove_subscription(self, user_id: int, anime_id: int) -> bool:
        try:
            res = await self.repo.remove_subscription(self.session, user_id, anime_id)
            if hasattr(self.session, "commit"):
                await self.session.commit()
                
            cache_key = f"{user_id}:{anime_id}"
            await self.cache.set("user_subscription", cache_key, False, ttl=30)
            await self.cache.invalidate("user_sub_page", f"{user_id}:*", broadcast=True)
            
            return res
        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            raise e

    async def get_user_subscription_anime_count(self, user_id: int) -> int:
        try:
            return await self.repo.get_user_subscription_anime_count(self.session, user_id)
        except Exception as e:
            logger.error(f"❌ User obunalari sonini olishda xatolik (user_id={user_id}): {e}")
            return 0
        
    async def get_user_subscribed_anime_list(
        self, 
        user_id: int, 
        page: int = 1, 
        per_page: int = 10
    ) -> List[Dict[str, Any]]:
        cache_sub_key = f"{user_id}:{page}:{per_page}"
        
        cached_list = await self.cache.get("user_sub_page", cache_sub_key)
        if cached_list is not None:
            return cached_list

        offset = (page - 1) * per_page
        anime_list = await self.repo.get_user_subscribed_anime_list(
            self.session, 
            user_id=user_id, 
            offset=offset, 
            limit=per_page
        )

        await self.cache.set("user_sub_page", cache_sub_key, anime_list, ttl=30)
        return anime_list