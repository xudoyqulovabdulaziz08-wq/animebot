import logging
from typing import Any, Optional, Dict
from datetime import datetime, timezone, timedelta
from sqlalchemy import case, select, update
from sqlalchemy.dialects.postgresql import insert

from database.models import DBUser, UserStatus

logger = logging.getLogger("UserRepository")


class UserRepository:
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
        return UserRepository._get_real_session(session)

    # ================= SERIALIZER =================
    @staticmethod
    def _to_dict(user: DBUser) -> Dict:
        return {
            "user_id": user.user_id,
            "username": user.username,
            "status": user.status.value if user.status else None,
            "points": user.points,
            "vip_expire_date": (
                user.vip_expire_date.isoformat()
                if user.vip_expire_date else None
            ),
            "sleep_reminder_enabled": user.sleep_reminder_enabled,
            "joined_at": user.joined_at.isoformat() if user.joined_at else None,
            "is_vip": user.status == UserStatus.VIP,  # Dinamik tekshiruv
            "password_hash": getattr(user, "password_hash", None)
        }

    # ================= GET OR CREATE =================
    @staticmethod
    async def get_or_create(session: Any, tg_user: Any) -> Dict:
        session = await UserRepository._prepare_session(session)

        stmt = (
            insert(DBUser)
            .values(
                user_id=tg_user.id,
                username=tg_user.username,
                status=UserStatus.USER,
                points=0,
                sleep_reminder_enabled=True,
            )
            .on_conflict_do_update(
                index_elements=[DBUser.user_id],
                set_={"username": tg_user.username}
            )
            .returning(DBUser)
        )

        result = await session.execute(stmt)
        user = result.scalar_one()
        
        await session.flush()  # DBga vaqtincha yozish
        return UserRepository._to_dict(user)

    # ================= GET BY ID =================
    @staticmethod
    async def get_by_id(session: Any, user_id: int) -> Optional[Dict]:
        session = await UserRepository._prepare_session(session)

        result = await session.execute(
            select(DBUser).where(DBUser.user_id == user_id)
        )

        user = result.scalar_one_or_none()
        if not user:
            return None

        return UserRepository._to_dict(user)

    # ================= UPDATE POINTS =================
    @staticmethod
    async def update_points(session: Any, user_id: int, points: int) -> bool:
        session = await UserRepository._prepare_session(session)

        result = await session.execute(
            update(DBUser)
            .where(DBUser.user_id == user_id)
            .values(points=DBUser.points + points)
        )

        await session.flush()
        return result.rowcount > 0

    # ================= VIP SET =================
    @staticmethod
    async def set_vip(session: Any, user_id: int, days: int) -> bool:
        session = await UserRepository._prepare_session(session)

        expire = datetime.now(timezone.utc) + timedelta(days=days)

        result = await session.execute(
            update(DBUser)
            .where(DBUser.user_id == user_id)
            .values(
                status=UserStatus.VIP,
                vip_expire_date=expire
            )
        )

        await session.flush()
        return result.rowcount > 0

    # ================= REMOVE VIP =================
    @staticmethod
    async def remove_vip(session: Any, user_id: int) -> bool:
        session = await UserRepository._prepare_session(session)

        result = await session.execute(
            update(DBUser)
            .where(DBUser.user_id == user_id)
            .values(
                status=UserStatus.USER,
                vip_expire_date=None
            )
        )

        await session.flush()
        return result.rowcount > 0

    # ================= TOGGLE REMINDER =================
    @staticmethod
    async def toggle_sleep_reminder(session: Any, user_id: int) -> bool:
        session = await UserRepository._prepare_session(session)

        result = await session.execute(
            update(DBUser)
            .where(DBUser.user_id == user_id)
            .values(
                sleep_reminder_enabled=case((DBUser.sleep_reminder_enabled == True, False), else_=True)
            )
        )

        await session.flush()
        return result.rowcount > 0

    # ================= EXISTS =================
    @staticmethod
    async def exists(session: Any, user_id: int) -> bool:
        session = await UserRepository._prepare_session(session)

        result = await session.execute(
            select(DBUser.user_id).limit(1).where(DBUser.user_id == user_id)
        )

        return result.scalar_one_or_none() is not None

    # ================= DELETE USER =================
    @staticmethod
    async def delete(session: Any, user_id: int) -> bool:
        session = await UserRepository._prepare_session(session)

        result = await session.execute(
            select(DBUser).where(DBUser.user_id == user_id)
        )

        user = result.scalar_one_or_none()
        if not user:
            return False

        session.delete(user)  # SINXRON METOD (await olib tashlandi)
        await session.flush()
        return True
    
    # ================= GET ADMIN STATS =================
    @staticmethod
    async def get_admin_stats(session: Any) -> Dict[str, int]:
        from sqlalchemy import func, text
        # Aylanma importni oldini olish uchun qolgan modellarni shu yerda chaqiramiz
        from database.models import Anime, Episode, Channel

        session = await UserRepository._prepare_session(session)

        # 1. Jami foydalanuvchilar soni
        total_users_stmt = select(func.count(DBUser.user_id))
        total_users = await session.scalar(total_users_stmt) or 0

        # 2. VIP foydalanuvchilar soni (is_vip gibrid ustuni orqali)
        vip_users_stmt = select(func.count(DBUser.user_id)).where(DBUser.is_vip)
        vip_users = await session.scalar(vip_users_stmt) or 0

        # 3. Jami Animelar soni
        total_anime_stmt = select(func.count(Anime.anime_id))
        total_anime = await session.scalar(total_anime_stmt) or 0

        # 4. Jami yuklangan Qismlar (Epizodlar) soni
        total_episodes_stmt = select(func.count(Episode.id))
        total_episodes = await session.scalar(total_episodes_stmt) or 0

        # 5. Jami faol majburiy obuna kanallari soni
        active_channels_stmt = select(func.count(Channel.id)).where(Channel.is_active == True)
        active_channels = await session.scalar(active_channels_stmt) or 0

        # 6. Faollik statistikasi (DAU / WAU / MAU) — last_active_at asosida, bitta so'rovda
        activity_stmt = text("""
            SELECT
                COUNT(*) FILTER (WHERE last_active_at >= now() - interval '1 day')   AS dau,
                COUNT(*) FILTER (WHERE last_active_at >= now() - interval '7 days')  AS wau,
                COUNT(*) FILTER (WHERE last_active_at >= now() - interval '30 days') AS mau
            FROM users
        """)
        activity_row = (await session.execute(activity_stmt)).fetchone()

        return {
            "total_users": total_users,
            "vip_users": vip_users,
            "total_anime": total_anime,
            "total_episodes": total_episodes,
            "active_channels": active_channels,
            "daily_active": activity_row.dau or 0,
            "weekly_active": activity_row.wau or 0,
            "monthly_active": activity_row.mau or 0,
        }
    
    # ================= SET ADMIN STATUS =================
    @staticmethod
    async def set_admin(session: Any, user_id: int) -> bool:
        session = await UserRepository._prepare_session(session)

        result = await session.execute(
            update(DBUser)
            .where(DBUser.user_id == user_id)
            .values(
                status=UserStatus.ADMIN,
                vip_expire_date=None  # Admin bo'gach, VIP muddatini tozalaymiz
            )
        )

        await session.flush()
        return result.rowcount > 0
    
    # ================= REMOVE ADMIN huquqi =================
    @staticmethod
    async def remove_admin(session: Any, user_id: int) -> bool:
        session = await UserRepository._prepare_session(session)

        result = await session.execute(
            update(DBUser)
            .where(DBUser.user_id == user_id)
            .values(
                status=UserStatus.USER  # Statusni oddiy foydalanuvchiga qaytaramiz
            )
        )

        await session.flush()
        return result.rowcount > 0
    
    

    @staticmethod
    async def generate_auth_code(session: Any, user_id: int) -> Optional[str]:
        """
        🤖 Saytga kirish uchun vaqtinchalik 6 xonali kod yaratadi.
        Amal qilish muddati: 15 daqiqa.
        """
        import random
        session = await UserRepository._prepare_session(session)

        # 6 xonali tasodifiy son ko'rinishidagi parol (Masalan: 482915)
        # Boshiga AN- qo'shib shakllantiramiz: AN-482915
        random_code = f"AN-{random.randint(100000, 999999)}"
        expire_time = datetime.now(timezone.utc) + timedelta(minutes=15)

        result = await session.execute(
            update(DBUser)
            .where(DBUser.user_id == user_id)
            .values(
                temporary_code=random_code,
                code_expires_at=expire_time
            )
        )

        await session.flush()
        if result.rowcount > 0:
            return random_code
        return None

    # ================= RESET AUTH CODE =================
    @staticmethod
    async def reset_auth_code(session: Any, user_id: int) -> Optional[str]:
        """
        🔒 Parol buzilgan yoki eskirgan bo'lsa, uni xavfsiz qayta shakllantiradi.
        """
        # generate_auth_code bilan bir xil mantiqda ishlaydi, eski kod ustidan yangisini yozadi
        return await UserRepository.generate_auth_code(session, user_id)


        # user_repository.py ga qo'shiladigan metod
    