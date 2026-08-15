from __future__ import annotations

import logging
import time
from typing import Any, Dict, Tuple, List
from repositories.subscription_repository import SubscriptionRepository

logger = logging.getLogger("SubscriptionService")

# ⚡ oddiy va tezkor 30 soniyalik In-Memory Cache
# Kalit: (user_id, anime_id) -> Qiymat: (is_subbed: bool, expire_time: float)
_SUB_CACHE: Dict[Tuple[int, int], Tuple[bool, float]] = {}
CACHE_TTL = 30  # 30 soniya


class SubscriptionService:

    def __init__(self, session: Any):
        self.session = session
        self.repo = SubscriptionRepository()

    def _get_cache(self, user_id: int, anime_id: int) -> bool | None:
        key = (user_id, anime_id)
        if key in _SUB_CACHE:
            is_sub, expire_at = _SUB_CACHE[key]
            if time.time() < expire_at:
                return is_sub
            else:
                del _SUB_CACHE[key]  # Eski keshni o'chirish
        return None

    def _set_cache(self, user_id: int, anime_id: int, is_sub: bool) -> None:
        key = (user_id, anime_id)
        _SUB_CACHE[key] = (is_sub, time.time() + CACHE_TTL)

    def _clear_cache(self, user_id: int, anime_id: int) -> None:
        key = (user_id, anime_id)
        _SUB_CACHE.pop(key, None)

    # ================= PUBLIC METHODS =================

    async def is_subscribed(self, user_id: int, anime_id: int) -> bool:
        """30 soniyalik kesh bilan obunani tekshirish"""
        cached_status = self._get_cache(user_id, anime_id)
        if cached_status is not None:
            return cached_status

        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        status = await self.repo.is_subscribed(self.session, user_id, anime_id)
        self._set_cache(user_id, anime_id, status)
        return status

    async def toggle_subscription(self, user_id: int, anime_id: int) -> bool:
        """Obuna bo'lish / Obunani bekor qilish (Keshni darhol yangilaydi)"""
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        try:
            new_status = await self.repo.toggle_subscription(self.session, user_id, anime_id)
            
            if hasattr(self.session, "commit"):
                await self.session.commit()

            # Keshni darhol yangi holat bo'yicha to'g'rilaymiz
            self._set_cache(user_id, anime_id, new_status)
            return new_status

        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            self._clear_cache(user_id, anime_id)
            logger.error(f"❌ Obuna toggle qilishda xatolik: {e}")
            raise e

    async def add_subscription(self, user_id: int, anime_id: int) -> bool:
        """Faqat obuna qo'shish"""
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        try:
            res = await self.repo.add_subscription(self.session, user_id, anime_id)
            if hasattr(self.session, "commit"):
                await self.session.commit()
            self._set_cache(user_id, anime_id, True)
            return res
        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            self._clear_cache(user_id, anime_id)
            raise e

    async def remove_subscription(self, user_id: int, anime_id: int) -> bool:
        """Faqat obunani o'chirish"""
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        try:
            res = await self.repo.remove_subscription(self.session, user_id, anime_id)
            if hasattr(self.session, "commit"):
                await self.session.commit()
            self._set_cache(user_id, anime_id, False)
            return res
        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            self._clear_cache(user_id, anime_id)
            raise e

    async def get_user_subscription_anime_count(self, user_id: int) -> int:
        """Foydalanuvchi jami nechta animega obuna bo'lganini qaytaradi"""
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

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
        """
        Foydalanuvchining ma'lum bir sahifadagi obuna bo'lgan animelar ro'yxatini keshdan/DBdan oladi.
        """
        cache_sub_key = f"{user_id}:{page}:{per_page}"
        
        # 1. Keshni tekshiramiz
        cached_list = await self.cache.get("user_sub_page", cache_sub_key)
        if cached_list is not None:
            return cached_list

        # 2. Keshda bo'lmasa DBdan JOIN so'rovi bilan bittada olamiz
        offset = (page - 1) * per_page
        anime_list = await self.repo.get_user_subscribed_anime_list(
            self.session, 
            user_id=user_id, 
            offset=offset, 
            limit=per_page
        )

        # 3. Keshga yozamiz (TTL: 30 soniya)
        await self.cache.set("user_sub_page", cache_sub_key, anime_list, ttl=30)

        return anime_list