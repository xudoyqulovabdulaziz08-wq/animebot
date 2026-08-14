from __future__ import annotations

import logging
from typing import Any, List
from sqlalchemy import select, func, delete
from database.models import AnimeSubscription

logger = logging.getLogger("SubscriptionRepository")


class SubscriptionRepository:

    @staticmethod
    def _get_real_session(session: Any):
        if hasattr(session, "_session"):
            return session._session
        return session

    @staticmethod
    async def _prepare_session(session: Any):
        if hasattr(session, "_ensure_session"):
            await session._ensure_session()
        return SubscriptionRepository._get_real_session(session)

    # 🔍 Obuna holatini bazadan tekshirish
    @staticmethod
    async def is_subscribed(session: Any, user_id: int, anime_id: int) -> bool:
        real_session = await SubscriptionRepository._prepare_session(session)
        stmt = select(func.count(AnimeSubscription.id)).where(
            AnimeSubscription.user_id == user_id,
            AnimeSubscription.anime_id == anime_id
        )
        result = await real_session.execute(stmt)
        return (result.scalar() or 0) > 0

    # ➕ Obuna qo'shish
    @staticmethod
    async def add_subscription(session: Any, user_id: int, anime_id: int) -> bool:
        real_session = await SubscriptionRepository._prepare_session(session)
        
        # Allaqachon bor-yo'qligini xavfsizlik uchun tekshiramiz
        already_sub = await SubscriptionRepository.is_subscribed(real_session, user_id, anime_id)
        if already_sub:
            return True

        new_sub = AnimeSubscription(user_id=user_id, anime_id=anime_id)
        real_session.add(new_sub)
        await real_session.flush()
        return True

    # ➖ Obunani o'chirish
    @staticmethod
    async def remove_subscription(session: Any, user_id: int, anime_id: int) -> bool:
        real_session = await SubscriptionRepository._prepare_session(session)
        
        stmt = delete(AnimeSubscription).where(
            AnimeSubscription.user_id == user_id,
            AnimeSubscription.anime_id == anime_id
        )
        result = await real_session.execute(stmt)
        await real_session.flush()
        return result.rowcount > 0

    # 🔄 Toggle (Yoqish / O'chirish)
    @staticmethod
    async def toggle_subscription(session: Any, user_id: int, anime_id: int) -> bool:
        """
        Qaytaradi: 
        True  -> Obuna bo'lindi (Qo'shildi)
        False -> Obuna bekor qilindi (O'chirildi)
        """
        real_session = await SubscriptionRepository._prepare_session(session)
        
        stmt = select(AnimeSubscription).where(
            AnimeSubscription.user_id == user_id,
            AnimeSubscription.anime_id == anime_id
        )
        result = await real_session.execute(stmt)
        existing_sub = result.scalar_one_or_none()

        if existing_sub:
            await real_session.delete(existing_sub)
            await real_session.flush()
            return False
        else:
            new_sub = AnimeSubscription(user_id=user_id, anime_id=anime_id)
            real_session.add(new_sub)
            await real_session.flush()
            return True
        
    # 🔢 Foydalanuvchining jami obuna bo'lgan animelari sonini olish
    @staticmethod
    async def get_user_subscription_anime_count(session: Any, user_id: int) -> int:
        real_session = await SubscriptionRepository._prepare_session(session)
        stmt = select(func.count(AnimeSubscription.id)).where(
            AnimeSubscription.user_id == user_id
        )
        result = await real_session.execute(stmt)
        return result.scalar() or 0