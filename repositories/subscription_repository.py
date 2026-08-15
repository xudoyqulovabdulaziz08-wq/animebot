from __future__ import annotations

import logging
from typing import Any, List, Dict
from sqlalchemy import select, func, delete, desc
from database.models import AnimeSubscription, Anime, DBUser

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

    @staticmethod
    async def get_user_subscribed_anime_list(
        session: Any, 
        user_id: int, 
        offset: int = 0, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Foydalanuvchining obuna bo'lgan animelarini JOIN orqali 
        BITTA SQL so'rovida olib keladi (Yangi AnimeTitle strukturasi bo'yicha).
        """
        from database.models import Anime, AnimeSubscription, AnimeTitle
        from sqlalchemy import func

        session = await SubscriptionRepository._prepare_session(session)

        stmt = (
            select(
                Anime.anime_id,
                func.coalesce(AnimeTitle.title_uz, AnimeTitle.title_en, "Nomsiz anime").label("title"),
                Anime.year,
                Anime.poster_id
            )
            .join(AnimeSubscription, AnimeSubscription.anime_id == Anime.anime_id)
            .outerjoin(AnimeTitle, AnimeTitle.anime_id == Anime.anime_id)
            .where(AnimeSubscription.user_id == user_id)
            .group_by(Anime.anime_id, AnimeTitle.id, AnimeSubscription.id)
            .order_by(AnimeSubscription.id.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await session.execute(stmt)
        rows = result.all()

        return [
            {
                "anime_id": row.anime_id,
                "title": row.title,
                "year": row.year,
                "poster": row.poster_id
            }
            for row in rows
        ]