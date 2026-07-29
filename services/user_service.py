from __future__ import annotations

import logging
from typing import Any, Optional, Dict
from datetime import datetime, timezone

from repositories.user_repository import UserRepository
from database.cache import cache_manager  # Universal CacheManager
from database.models import UserStatus
from services.orchestrator import state
logger = logging.getLogger("UserService")


class UserService:
    """
    🚀 Business Logic Layer for Users (CACHE-AWARE & TRANSACTION-SAFE)
    - Kesh birinchi strategiyasi (Cache-first)
    - Tranzaksiyaviy xavfsizlik (Commit / Rollback)
    - Dinamik VIP validatsiyasi
    """

    def __init__(self, session):
        self.session = session
        self.repo = UserRepository
        self.cache = cache_manager

    # ==================================================
    # 🕵️‍♂️ INTERNAL HELPER: DYNAMIC VIP CHECK
    # ==================================================
    def _ensure_fresh_vip_status(self, user: Dict) -> Dict:
        """
        Keshdan kelgan yoki DBdan olingan user datasi ichidagi is_vip qiymatini
        ayni joriy vaqt (datetime.now) bilan dinamik tekshirib beradi.
        """
        if user["status"] != UserStatus.VIP.value:
            user["is_vip"] = False
            return user

        if user["vip_expire_date"] is None:
            user["is_vip"] = True
            return user

        try:
            # ISO formatdagi stringni ob'ektga o'tkazamiz
            expire_dt = datetime.fromisoformat(user["vip_expire_date"])
            now = datetime.now(timezone.utc)
            
            # Agar muddati o'tib ketgan bo'lsa dinamik o'zgartiramiz
            if now > expire_dt:
                user["is_vip"] = False
                # Eslatma: DBda status hamon VIP bo'lishi mumkin, uni fon ishlari (cron) tozalaydi,
                # lekin foydalanuvchiga xizmat ko'rsatishda biz unga VIP bermaymiz.
            else:
                user["is_vip"] = True
        except Exception as e:
            logger.error(f"Error parsing vip_expire_date: {e}")
            user["is_vip"] = False

        return user

    # ==================================================
    # 🔥 GET OR CREATE USER (SESSION & CACHE SYNC)
    # ==================================================
    async def get_or_create_user(self, tg_user: Any) -> Dict:
        try:
            # 1. DB write / upsert via repo
            user = await self.repo.get_or_create(self.session, tg_user)
            
            # 2. Commit transaction (Outbox eventlar ham birga yoziladi)
            await self.session.commit()
            
            # 3. Keshni yangilash
            user = self._ensure_fresh_vip_status(user)
            await self.cache.set("users", str(tg_user.id), user, ttl=7200) # 2 soat kesh

            return user
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed in get_or_create_user for {tg_user.id}: {e}")
            raise e

    # ==================================================
    # 🎯 GET USER BY ID (CACHE-FIRST WITH EXPIRE VALIDATION)
    # ==================================================
    async def get_user(self, user_id: int) -> Optional[Dict]:
        # 1. Keshdan qidirish
        cached_user = await self.cache.get("users", str(user_id))
        if cached_user:
            logger.debug(f"🎯 CACHE HIT user_id={user_id}")
            return self._ensure_fresh_vip_status(cached_user)

        # 2. DB Fallback
        user = await self.repo.get_by_id(self.session, user_id)
        if not user:
            return None

        # 3. Keshni to'ldirish
        user = self._ensure_fresh_vip_status(user)
        await self.cache.set("users", str(user_id), user, ttl=7200)

        return user

    # ==================================================
    # 💎 SET VIP STATUS
    # ==================================================
    async def grant_vip(self, user_id: int, days: int) -> bool:
        try:
            ok = await self.repo.set_vip(self.session, user_id, days)
            if not ok:
                await self.session.rollback()
                return False

            await self.session.commit()

            # Keshni invalidatsiya qilish (Kesh o'chadi, keyingi so'rovda DB dan yangisi olinadi)
            await self.cache.invalidate("users", str(user_id), broadcast=True)
            logger.info(f"✅ VIP granted to user {user_id} for {days} days.")
            return True
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to set VIP for user {user_id}: {e}")
            raise e

    # ==================================================
    # ❌ REMOVE VIP STATUS
    # ==================================================
    async def revoke_vip(self, user_id: int) -> bool:
        try:
            ok = await self.repo.remove_vip(self.session, user_id)
            if not ok:
                await self.session.rollback()
                return False

            await self.session.commit()

            await self.cache.invalidate("users", str(user_id), broadcast=True)
            logger.info(f"✅ VIP revoked from user {user_id}.")
            return True
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to revoke VIP for user {user_id}: {e}")
            raise e

    # ==================================================
    # 💰 UPDATE POINTS
    # ==================================================
    async def increment_points(self, user_id: int, points: int) -> bool:
        try:
            ok = await self.repo.update_points(self.session, user_id, points)
            if not ok:
                await self.session.rollback()
                return False

            await self.session.commit()

            # Points tez-tez o'zgarishi mumkinligi sababli kesh darhol o'chiriladi
            await self.cache.invalidate("users", str(user_id), broadcast=True)
            return True
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to update points for user {user_id}: {e}")
            raise e

    # ==================================================
    # 🔔 TOGGLE SLEEP REMINDER
    # ==================================================
    async def toggle_reminder(self, user_id: int) -> bool:
        try:
            ok = await self.repo.toggle_sleep_reminder(self.session, user_id)
            if not ok:
                await self.session.rollback()
                return False

            await self.session.commit()

            await self.cache.invalidate("users", str(user_id), broadcast=True)
            return True
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to toggle reminder for user {user_id}: {e}")
            raise e

    # ==================================================
    # 🗑 DELETE USER
    # ==================================================
    async def terminate_user(self, user_id: int) -> bool:
        try:
            ok = await self.repo.delete(self.session, user_id)
            if not ok:
                await self.session.rollback()
                return False

            await self.session.commit()

            # Keshni butunlay tozalash
            await self.cache.invalidate("users", str(user_id), broadcast=True)
            logger.info(f"🗑 User {user_id} completely deleted from system.")
            return True
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to delete user {user_id}: {e}")
            raise e
        

    # ==================================================
    # 📊 ADMIN STATS (CACHE-AWARE)
    # ==================================================
    async def get_admin_statistics(self) -> Dict[str, int]:
        # Avval keshdan tekshiramiz
        cached_stats = await self.cache.get("admin", "stats")
        if cached_stats:
            logger.debug("🎯 Admin stats loaded from cache")
            return cached_stats

        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        # 🔥 TO'G'RI VARIANT: UserRepository metodidan foydalanamiz
        from repositories.user_repository import UserRepository
        stats = await UserRepository.get_admin_stats(self.session)
        
        # 5 daqiqaga keshga yozib qo'yamiz
        await self.cache.set("admin", "stats", stats, ttl=300)
        return stats
    

    # ==================================================
    # 💎 LIST ALL VIP USERS (TRANSACTION-SAFE)
    # ==================================================
    async def list_vip_users(self) -> list[dict]:
        """
        Bazadan barcha faol VIP foydalanuvchilarni muddati bilan tartiblab oladi.
        """
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        from sqlalchemy import select
        from database.models import DBUser, UserStatus

        # Faqat statusi VIP bo'lgan foydalanuvchilarni muddati bo'yicha tartiblab olamiz
        stmt = select(DBUser).where(DBUser.status == UserStatus.VIP).order_by(DBUser.vip_expire_date.asc())
        result = await self.session.execute(stmt)
        
        # Olingan modellarni to_dict (dict) formatiga o'tkazib qaytaramiz
        return [self.repo._to_dict(user) for user in result.scalars().all()]
    

    # ==================================================
    # 🎯 GET USER IDS FOR ADVERTISEMENT (SAFE ENGINE)
    # ==================================================
    async def get_target_user_ids(self, target_group: str) -> list[int]:
        """
        Target guruh bo'yicha foydalanuvchilar ID ro'yxatini qaytaradi.
        Hech qanday Aiogram drayverlariga bog'liq bo'lmagan toza biznes mantiqi.
        """
        from sqlalchemy import select
        from database.models import DBUser, UserStatus
        from repositories.user_repository import UserRepository

        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()
            
        real_session = UserRepository._get_real_session(self.session)
        stmt = select(DBUser.user_id)

        if target_group == "vip":
            stmt = stmt.where(DBUser.status == UserStatus.VIP)
        elif target_group == "user":
            stmt = stmt.where(DBUser.status == UserStatus.USER)
        elif target_group == "admin":
            stmt = stmt.where(DBUser.status == UserStatus.ADMIN)
        # 'all' bo'lsa hech qanday filtersiz barchasini oladi

        result = await real_session.execute(stmt)
        return list(result.scalars().all())
    
    # ==================================================
    # 👑 PROMOTE TO ADMIN
    # ==================================================
    async def make_admin(self, user_id: int) -> bool:
        try:
            # 1. Repository orqali DB statusini ADMIN qilamiz
            ok = await self.repo.set_admin(self.session, user_id)
            if not ok:
                await self.session.rollback()
                return False

            # 2. O'zgarishni DB ga tasdiqlaymiz (Commit)
            await self.session.commit()

            # 3. 🧹 KESHNI TOZALASH (Invalidatsiya)
            # Bu juda muhim! L1 va L2 keshlar darhol o'chadi. Foydalanuvchi keyingi 
            # marta botga yozganda kesh-first tufayli eski USER statusida qolib ketmaydi,
            # uning yangi ADMIN statusi bazadan qayta yuklanadi.
            await self.cache.invalidate("users", str(user_id), broadcast=True)
            await state.user_l1_cache.delete(user_id)
            
            logger.info(f"👑 User {user_id} has been promoted to ADMIN successfully.")
            return True
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to make admin for user {user_id}: {e}")
            raise e
        

    # ==================================================
    # 📋 LIST ALL ADMINS
    # ==================================================
    async def list_admin_users(self) -> list[dict]:
        """
        Botdagi barcha ADMIN statusiga ega foydalanuvchilar ro'yxatini qaytaradi.
        """
        from sqlalchemy import select
        from database.models import DBUser, UserStatus
        
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()
            
        real_session = self.repo._get_real_session(self.session)
        
        # Status admin bo'lgan barcha userlarni tanlaymiz
        stmt = select(DBUser).where(DBUser.status == UserStatus.ADMIN).order_by(DBUser.joined_at.desc())
        result = await real_session.execute(stmt)
        
        # Modellarni to_dict formatiga o'tkazib list ko'rinishida qaytaramiz
        return [self.repo._to_dict(user) for user in result.scalars().all()]
    
    # ==================================================
    # 📉 DEMOTE FROM ADMIN
    # ==================================================
    async def revoke_admin(self, user_id: int) -> bool:
        try:
            # 1. DB da statusni USER ga tushiramiz
            ok = await self.repo.remove_admin(self.session, user_id)
            if not ok:
                await self.session.rollback()
                return False

            # 2. Tranzaksiyani yakunlaymiz
            await self.session.commit()

            # 3. 🧹 KESHNI TOZALASH (L1/L2 keshlar darhol o'chadi)
            await self.cache.invalidate("users", str(user_id), broadcast=True)
            await state.user_l1_cache.delete(user_id)
            
            logger.info(f"📉 User {user_id} has been demoted from ADMIN to USER.")
            return True
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to revoke admin for user {user_id}: {e}")
            raise e
        
    

    # ==================================================
    # 📊 GET DB DISK SPACE
    # ==================================================
    async def get_database_storage_info(self) -> str:
        """
        Bazaning diskda egallagan real hajmini qaytaradi.
        """
        try:
            if hasattr(self.session, "_ensure_session"):
                await self.session._ensure_session()
            return await self.repo.get_db_size(self.session)
        except Exception:
            return "Noma'lum"
        

    # ==================================================
    # 🧹 CLEAN OUTBOX LOGS
    # ==================================================
    async def clean_outbox_events(self) -> int:
        try:
            deleted_count = await self.repo.clear_processed_outbox(self.session)
            await self.session.commit()
            logger.info(f"🧹 Cleaned {deleted_count} processed outbox events.")
            return deleted_count
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to clear outbox events: {e}")
            raise e
        
    # ==================================================
    # 📤 EXPORT DATABASE TO SQL SCRIPT
    # ==================================================
    async def export_database_dump(self) -> str:
        """
        Baza ma'lumotlarini toliq SQL script ko'rinishida generatsiya qiladi.
        """
        try:
            if hasattr(self.session, "_ensure_session"):
                await self.session._ensure_session()
            return await self.repo.generate_sql_dump(self.session)
        except Exception as e:
            logger.error(f"❌ Service layer export failed: {e}")
            raise e
        
    # ==================================================
    # 🔑 GENERATE WEB AUTH CODE (CACHE-AWARE & SAFE)
    # ==================================================
    async def generate_web_auth_code(self, user_id: int) -> Optional[str]:
        """
        🤖 Saytga login qilish uchun vaqtinchalik parol yaratadi.
        Tranzaksiyaviy xavfsiz va keshni darhol yangilaydi (Invalidation).
        """
        try:
            # 1. Repository orqali bazada vaqtinchalik kod va muddatini yangilaymiz
            code = await self.repo.generate_auth_code(self.session, user_id)
            if not code:
                await self.session.rollback()
                return None

            # 2. O'zgarishlarni bazaga saqlaymiz
            await self.session.commit()

            # 3. 🧹 KESHNI TOZALASH
            # Foydalanuvchining yangi paroli sayt (backend) tomonidan ham darhol 
            # bazadan to'g'ri o'qilishi uchun keshni butunlay invalidatsiya qilamiz.
            await self.cache.invalidate("users", str(user_id), broadcast=True)
            
            logger.info(f"🔑 Auth code generated for user {user_id}.")
            return code

        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to generate auth code for user {user_id}: {e}")
            raise e

    # ==================================================
    # 🔄 RESET/REFRESH AUTH CODE
    # ==================================================
    async def refresh_web_auth_code(self, user_id: int) -> Optional[str]:
        """
        🔒 Agar foydalanuvchi parolini kimdir bilib qolgan bo'lsa yoki muddati o'tgan bo'lsa,
        eski parolni bekor qilib, xavfsiz ravishda qayta yangilab beradi.
        """
        # Xavfsizlik mantiqi bo'yicha generate_web_auth_code bilan bir xil ishlaydi,
        # lekin semantik jihatdan qayta tiklash (reset) uchun alohida xizmat qiladi.
        logger.warning(f"🔒 Security trigger: Resetting auth code for user {user_id}...")
        return await self.generate_web_auth_code(user_id)