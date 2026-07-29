from __future__ import annotations

import logging
from typing import Any, Optional, Dict
from datetime import datetime, timezone

from repositories.data_repository import DataRepository
from database.cache import cache_manager  # Universal CacheManager

# Logger nomini DataService qildik, chalkashlik bo'lmasligi uchun!
logger = logging.getLogger("DataService")

class DataService:
    """
    🚀 Business Logic Layer for System & Database Operations (TRANSACTION-SAFE)
    - Global backup eksport va import (Dump)
    - Outbox tizimini tozalash mexanizmi
    - Tizim keshlarini to'liq sinxronizatsiya va invalidatsiya qilish
    """

    def __init__(self, session):
        self.session = session
        self.repo = DataRepository
        self.cache = cache_manager

    # ==================================================
    # 📥 IMPORT DATABASE BACKUP & FLUSH CACHE
    # ==================================================
    async def import_database_dump(self, sql_content: str) -> bool:
        try:
            # 1. SQL Dumpni bazaga xavfsiz yozamiz
            success = await self.repo.execute_sql_backup(self.session, sql_content)
            
            if not success:
                await self.session.rollback()
                return False
                
            # 2. Tranzaksiyani tasdiqlaymiz
            await self.session.commit()
            
            # 3. 🧹 CRITICAL UX: Butun tizim keshini tozalaymiz (Flush All L1/L2)
            # Chunki yangi baza import bo'lgach, eski keshlar butunlay o'z kuchini yoqotadi
            await self.cache.clear_all()
            
            logger.info("📥 Database successfully restored from backup. Cache flushed completely.")
            return True
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to restore database: {e}")
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
        except Exception as e:
            logger.error(f"❌ Failed to get database size: {e}")
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