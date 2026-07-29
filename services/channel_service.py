import logging
from typing import Any, Optional, Dict, List

from repositories.channel_repository import ChannelRepository
from database.cache import cache_manager

logger = logging.getLogger("ChannelService")


class ChannelService:
    """
    🚀 Business Logic Layer for Channels (CACHE-AWARE & TRANSACTION-SAFE)
    """

    def __init__(self, session: Any):
        self.session = session
        self.repo = ChannelRepository
        self.cache = cache_manager

    # ==================================================
    # 🧹 HELPER: INVALIDATE LISTS
    # ==================================================
    async def _invalidate_channel_lists(self, specific_channel_id: Optional[int] = None):
        """
        Kanal qo'shilganda, o'chirilganda yoki statusi o'zgarganda 
        ro'yxatlarni (all_list, active_list) keshdan tozalash.
        """
        await self.cache.invalidate("channels", "all_list", broadcast=True)
        await self.cache.invalidate("channels", "active_list", broadcast=True)
        
        if specific_channel_id:
            await self.cache.invalidate("channels", str(specific_channel_id), broadcast=True)

    # ==================================================
    # 📋 GET ALL CHANNELS
    # ==================================================
    async def get_all_channels(self) -> List[Dict[str, Any]]:
        # 1. Keshdan qidirish
        cached_data = await self.cache.get("channels", "all_list")
        if cached_data is not None:
            logger.debug("🎯 CACHE HIT: all_channels")
            return cached_data

        # 2. DB dan olish (bu yerda repo keshsiz chaqiriladi)
        channels = await self.repo.get_all(self.session)

        # 3. Keshni yangilash
        await self.cache.set("channels", "all_list", channels, ttl=3600)
        return channels

    # ==================================================
    # ✅ GET ACTIVE CHANNELS
    # ==================================================
    async def get_active_channels(self) -> List[Dict[str, Any]]:
        cached_data = await self.cache.get("channels", "active_list")
        if cached_data is not None:
            logger.debug("🎯 CACHE HIT: active_channels")
            return cached_data

        channels = await self.repo.get_active(self.session)

        await self.cache.set("channels", "active_list", channels, ttl=3600)
        return channels

    # ==================================================
    # 🎯 GET CHANNEL BY ID
    # ==================================================
    async def get_channel(self, channel_id: int) -> Optional[Dict[str, Any]]:
        obj_key = str(channel_id)
        
        cached_data = await self.cache.get("channels", obj_key)
        if cached_data is not None:
            logger.debug(f"🎯 CACHE HIT: channel {channel_id}")
            return cached_data

        channel = await self.repo.get_by_id(self.session, channel_id)
        if not channel:
            return None

        await self.cache.set("channels", obj_key, channel, ttl=3600)
        return channel

    # ==================================================
    # ➕ CREATE CHANNEL
    # ==================================================
    async def create_channel(self, channel_id: int, title: str, url: Optional[str] = None) -> Dict[str, Any]:
        try:
            # DB ga yozish (flush bo'ladi)
            channel_data = await self.repo.create(self.session, channel_id, title, url)
            
            # Tranzaksiyani yopish
            await self.session.commit()
            
            # Yangi kanal qo'shilgani uchun umumiy ro'yxatlar keshini tozalaymiz
            await self._invalidate_channel_lists()
            
            logger.info(f"✅ Channel {channel_id} created successfully.")
            return channel_data
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to create channel {channel_id}: {e}")
            raise e

    # ==================================================
    # 🔄 TOGGLE STATUS
    # ==================================================
    async def toggle_status(self, channel_id: int) -> bool:
        try:
            ok = await self.repo.toggle_status(self.session, channel_id)
            if not ok:
                await self.session.rollback()
                return False

            await self.session.commit()
            
            # Status o'zgargani active_list va kanalning o'ziga ta'sir qiladi
            await self._invalidate_channel_lists(specific_channel_id=channel_id)
            
            logger.info(f"🔄 Channel {channel_id} status toggled.")
            return True
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to toggle status for channel {channel_id}: {e}")
            raise e

    # ==================================================
    # 🗑 DELETE CHANNEL
    # ==================================================
    async def delete_channel(self, channel_id: int) -> bool:
        try:
            ok = await self.repo.delete(self.session, channel_id)
            if not ok:
                await self.session.rollback()
                return False

            await self.session.commit()
            
            # Kanal o'chib ketdi, hamma joydan tozalaymiz
            await self._invalidate_channel_lists(specific_channel_id=channel_id)
            
            logger.info(f"🗑 Channel {channel_id} completely deleted.")
            return True
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"❌ Failed to delete channel {channel_id}: {e}")
            raise e