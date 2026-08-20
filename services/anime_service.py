from __future__ import annotations

import logging
from typing import Any, Optional, Dict, List

from repositories.anime_repository import AnimeRepository
from database.cache import cache_manager  # yagona universal cache manager

logger = logging.getLogger("AnimeService")


class AnimeService:
    """
    🚀 Business Logic Layer (CACHE-AWARE & TRANSACTION-SAFE)
    - Tranzaksiyani to'liq nazorat qiladi (Commit / Rollback)
    - Faqatgina muvaffaqiyatli Commitdan keyin keshga tegadi
    """

    def __init__(self, session):
        self.session = session
        # 💡 TO'G'RI: Repozitoriy klassini instansiya (obyekt) sifatida yaratamiz
        self.repo = AnimeRepository() 
        self.cache = cache_manager

    # ==================================================
    # 🔥 GET BY ID (CACHE-FIRST)
    # ==================================================
    async def get_anime(self, anime_id: int) -> Optional[Dict]:
        cached = await self.cache.get("anime", anime_id)
        if cached:
            logger.debug(f"🎯 CACHE HIT anime_id={anime_id}")
            return cached

        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        anime = await self.repo.get_by_id(self.session, anime_id)
        if not anime:
            return None

        await self.cache.set("anime", anime_id, anime, ttl=3600)
        return anime


    # ==================================================
    # 🔥 UPDATE ANIME (TRANSACTION-SAFE & CACHE-AWARE)
    # ==================================================
    async def update_anime(self, anime_id: int, update_data: Dict[str, Any]) -> bool:
        if not update_data:
            return False

        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

    # ✅ Repozitoriy pop() qilishidan oldin sezgir kalitlarni tekshirib olamiz
        sensitive_keys = {"title_uz", "title_en", "genres", "dubbers", "is_finished", "is_completed"}
        has_sensitive_changes = any(key in update_data for key in sensitive_keys)

        try:
            success = await self.repo.update(self.session, anime_id, update_data)
            if not success:
                return False
            
            if hasattr(self.session, "commit"):
                await self.session.commit()
            
            await self.cache.invalidate("anime", anime_id)

        # ✅ Oldindan saqlangan mantiq bo'yicha kesh tozalanadi
            if has_sensitive_changes:
                await self.cache.invalidate("anime", "all", broadcast=True)
                await self.cache.invalidate("search_map", "all", broadcast=True)
                await self.cache.invalidate("dubber", "all", broadcast=True)
                await self.cache.invalidate("anime_completed", "all", broadcast=True)
            await self.cache.invalidate("anime_ongoing", "all", broadcast=True)

            logger.info(f"✅ Anime ID={anime_id} muvaffaqiyatli yangilandi va keshi tozalandi.")
            return True
        
        except Exception as e:
            logger.error(f"🚨 Service ichida animeni yangilashda xato yuz berdi: {e}")
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            return False
        

    # ==================================================
    # 📋 LIST ANIME (CACHE-FIRST)
    # ==================================================
    async def list_anime(self) -> List[Dict]:
        cached = await self.cache.get("anime", "all")
        if cached is not None:  # Bo'sh ro'yxat kelsa ham kesh ishlashi uchun
            return cached

        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        data = await self.repo.list(self.session)
        await self.cache.set("anime", "all", data, ttl=1800)
        return data
# ==================================================
    # ➕ CREATE ANIME (TRANSACTION SAFE & CACHE-AWARE)
    # ==================================================
    async def create_anime(
        self,
        title_uz: str,
        title_en: Optional[str],
        poster_id: Optional[str],
        trailer_id: Optional[str],
        type: str,
        year: int,
        is_completed: bool,
        genres: List[int],
        dubbers: List[int],
        description: str,
        languages: list
    ) -> Dict:
        try:
            if hasattr(self.session, "_ensure_session"):
                await self.session._ensure_session()

            # Yangilangan AnimeRepository.create metodiga mos argumentlarni uzatamiz
            anime = await self.repo.create(
                session=self.session,
                title_uz=title_uz,
                title_en=title_en,
                poster_id=poster_id,
                trailer_id=trailer_id,
                type=type,
                year=year,
                is_completed=is_completed,
                genres=genres,
                dubbers=dubbers,
                description=description,
                languages=languages
            )
            
            await self.session.commit()
            anime_id = anime["anime_id"]

            # Kesh operatsiyalari
            await self.cache.set("anime", anime_id, anime, ttl=180)
            await self.cache.invalidate("anime", "all", broadcast=True)
            await self.cache.invalidate("search_map", "all", broadcast=True)
            await self.cache.invalidate("anime_completed", "all", broadcast=True)
            await self.cache.invalidate("anime_ongoing", "all", broadcast=True)
            
            # O'zgarish bo'lgani uchun dubber qidiruv keshi ham majburiy tozalanadi
            await self.cache.invalidate("dubber", "all", broadcast=True)

            logger.info(f"✅ Anime created + cached with new architecture: {anime_id}")
            return anime

        except Exception as e:
            # SAFE ROLLBACK: AttributeError (NoneType) xavfi yo'q qilingan holatda
            if self.session and hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.error(f"❌ Failed to create anime: {e}")
            raise e

    # ==================================================
    # 🎬 ADD EPISODE (TRANSACTION SAFE)
    # ==================================================
    async def add_episode(
        self,
        anime_id: int,
        episode_num: int,
        file_id: str,
        dub_group: str = "default",  # 👈 QO'SHILDI
        is_vip: bool = False,         # 👈 QO'SHILDI
        is_filler: bool = False
    ) -> bool:
        try:
            if hasattr(self.session, "_ensure_session"):
                await self.session._ensure_session()

            # Argumentlar endi repository logikasiga mos ravishda to'liq uzatiladi
            ok = await self.repo.add_episode(
                self.session, anime_id, episode_num, file_id, dub_group, is_vip, is_filler
            )
            
            await self.session.commit()

            if ok:
                await self.cache.invalidate("anime", anime_id, broadcast=True)
                await self.cache.invalidate("anime", "all", broadcast=True)
                await self.cache.invalidate("anime_episodes", anime_id, broadcast=True)
                await self.cache.invalidate("anime_completed", "all", broadcast=True)
                await self.cache.invalidate("anime_ongoing", "all", broadcast=True)
                logger.info(f"➕ Episode added + cache invalidated: Anime {anime_id}, Ep {episode_num} [{dub_group}, VIP={is_vip}]")
            return ok

        except Exception as e:
            if self.session and hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.error(f"❌ Failed to add episode: {e}")
            raise e


    # ==================================================
    # 🗑 DELETE EPISODE (TRANSACTION SAFE)
    # ==================================================
    async def delete_episode(self, anime_id: int, episode_num: int) -> bool:
        try:
            # Session'ni oldindan xavfsiz "uyg'otamiz"
            if hasattr(self.session, "_ensure_session"):
                await self.session._ensure_session()
            
            # Repozitoriy orqali o'chirishni ijro etamiz (Bu db-level cascade orqali EpisodeStream larni ham o'chiradi)
            ok = await self.repo.delete_episode(self.session, anime_id, episode_num)
            
            # Muammosiz o'chsa, tranzaksiyani saqlaymiz
            await self.session.commit()

            if ok:
                # Keshni invalidatsiya qilamiz, shunda ro'yxat darhol yangilanadi
                await self.cache.invalidate("anime", anime_id, broadcast=True)
                await self.cache.invalidate("anime", "all", broadcast=True)
                await self.cache.invalidate("anime_episodes", anime_id, broadcast=True)
                await self.cache.invalidate("anime_completed", "all", broadcast=True)
                await self.cache.invalidate("anime_ongoing", "all", broadcast=True)
                logger.info(f"🗑 Episode cache invalidated: Anime {anime_id}, Ep {episode_num}")

            return ok

        except Exception as e:
            if self.session and hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.error(f"❌ Failed to delete episode: {e}")
            raise e


    # ==================================================
    # 🗑 DELETE ANIME (TRANSACTION SAFE)
    # ==================================================
    async def delete_anime(self, anime_id: int) -> bool:
        try:
            # Session'ni oldin "uyg'otamiz"
            if hasattr(self.session, "_ensure_session"):
                await self.session._ensure_session()
            
            ok = await self.repo.delete(self.session, anime_id)
        
            await self.session.commit()

            if ok:
                await self.cache.invalidate("anime", anime_id, broadcast=True)
                await self.cache.invalidate("anime", "all", broadcast=True)
                await self.cache.invalidate("search_map", "all", broadcast=True)
                await self.cache.invalidate("anime_episodes", anime_id, broadcast=True)
                await self.cache.invalidate("anime_completed", "all", broadcast=True)
                await self.cache.invalidate("anime_ongoing", "all", broadcast=True)
                logger.info(f"🗑 Anime deleted + cache invalidated: {anime_id}")

            return ok

        except Exception as e:
            if self.session and hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.error(f"❌ Failed to delete anime: {e}")
            raise e
        
        
    # ==================================================
    # 🔄 UPDATE EPISODE FILE (TRANSACTION SAFE)
    # ==================================================
    async def update_episode_file(
        self, 
        anime_id: int, 
        episode_num: int, 
        new_file_id: str,
        dub_group: str = "default",  # 👈 QO'SHILDI
        is_vip: bool = False         # 👈 QO'SHILDI
    ) -> bool:
        try:
            if hasattr(self.session, "_ensure_session"):
                await self.session._ensure_session()
            
            # Repozitoriyga endi stream xususiyatlari bilan murojaat qilinadi
            ok = await self.repo.update_episode_file(
                self.session, anime_id, episode_num, new_file_id, dub_group, is_vip
            )
            await self.session.commit()

            if ok:
                # Keshni invalidatsiya qilamiz, shunda yangi video pleerda darhol ko'rinadi
                await self.cache.invalidate("anime", anime_id, broadcast=True)
                await self.cache.invalidate("anime", "all", broadcast=True)
                await self.cache.invalidate("anime_episodes", anime_id, broadcast=True)
                await self.cache.invalidate("anime_completed", "all", broadcast=True)
                await self.cache.invalidate("anime_ongoing", "all", broadcast=True)
                logger.info(f"🔄 Episode file updated + cache invalidated: Anime {anime_id}, Ep {episode_num} [{dub_group}, VIP={is_vip}]")

            return ok

        except Exception as e:
            if self.session and hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.error(f"❌ Failed to update episode file: {e}")
            raise e
    # ==================================================
    # 🔎 SEARCH MAP 
    # ==================================================
    async def get_search_map(self) -> Dict:
        cached = await self.cache.get("search_map", "all")
        if cached:
            return cached
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()
        all_anime = await self.repo.list(self.session)
        search_map = {
            str(a["anime_id"]): f'{a.get("title_uz") or a.get("title")} ({a.get("year")})'
            for a in all_anime
        }

        await self.cache.set("search_map", "all", search_map, ttl=180)
        return search_map
    

    # ==================================================
    # 🔎 SEARCH BY GENRES MULTI (OPTIMIZED DB-LEVEL)
    # ==================================================
    async def search_by_genres(self, genre_ids: List[int]) -> List[Dict]:
        """Tanlangan barcha janrlarga mos keluvchi animelarni bazadan eng tezkor usulda filtrlab beradi."""
        if not genre_ids:
            return []
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()
        return await self.repo.get_by_genres(self.session, genre_ids)
    

    # ==================================================
    # 🔎 SEARCH BY DUBBERS MULTI (OPTIMIZED DB-LEVEL)
    # ==================================================
    async def search_by_dubbers(self, dubber_ids: List[int]) -> List[Dict]:
        """Tanlangan barcha dubberlarga mos keluvchi animelarni bazadan eng tezkor usulda filtrlab beradi."""
        if not dubber_ids:
            return []
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()
        return await self.repo.get_by_dubbers(self.session, dubber_ids)

    # ==================================================
    # 📹 GET ANIME EPISODES CACHE (CACHE-FIRST)
    # ==================================================
    async def get_anime_episodes_cache(self, anime_id: int) -> List[Dict]:
        """
        🚀 Anime qismlarini keshdan (Cache-First) tezkor yuklab berish funksiyasi.
        Keshda bo'lmasa DBdan oladi va 1 soatga (ttl=3600) saqlaydi.
        """
        # 1. Avval kesh menedjerdan ushbu animening qismlarini so'raymiz
        cached_episodes = await self.cache.get("anime_episodes", anime_id)
        if cached_episodes is not None:
            logger.debug(f"🎯 CACHE HIT: anime_episodes loaded from cache for anime_id={anime_id}")
            return cached_episodes

        # 2. Agar keshda bo'lmasa, sessiyani tekshirib repozitoriyga yuzlanamiz
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        episodes = await self.repo.get_episodes_by_anime_id(self.session, anime_id)
        
        # 3. Kelgan ma'lumotni 1 soatga (3600 soniya) keshga yozib qo'yamiz
        await self.cache.set("anime_episodes", anime_id, episodes, ttl=3600)
        logger.info(f"💾 CACHE SET: Anime episodes cached for anime_id={anime_id} (TTL: 1h)")
        
        return episodes
    

    async def update_genres(self, anime_id: int, genre_ids: list[int]) -> bool:
        """Business Logic: Janrlarni yangilash, commit qilish va keshni invalidatsiya qilish"""
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()
            
        try:
            success = await self.repo.update_anime_genres(self.session, anime_id, genre_ids)
            if not success:
                return False
                
            if hasattr(self.session, "commit"):
                await self.session.commit()
                
            # Keshni va barcha qidiruv xaritalarini majburiy tozalaymiz
            await self.cache.invalidate("anime", anime_id)
            await self.cache.invalidate("anime", "all", broadcast=True)
            await self.cache.invalidate("anime_completed", "all", broadcast=True)
            await self.cache.invalidate("anime_ongoing", "all", broadcast=True)
            await self.cache.invalidate("search_map", "all", broadcast=True)
            return True
        except Exception as e:
            logger.error(f"🚨 Janrlarni yangilashda service xatosi: {e}")
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            return False

    async def update_dubbers(self, anime_id: int, dubber_ids: list[int]) -> bool:
        """🎙 Business Logic: Dubberlarni yangilash, commit qilish va keshni invalidatsiya qilish"""
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()
            
        try:
            success = await self.repo.update_anime_dubbers(self.session, anime_id, dubber_ids)
            if not success:
                return False
                
            if hasattr(self.session, "commit"):
                await self.session.commit()
                
            # 🔥 Ushbu animening va umumiy ro'yxatning keshini majburiy tozalaymiz
            await self.cache.invalidate("anime", anime_id)
            await self.cache.invalidate("anime", "all", broadcast=True)
            await self.cache.invalidate("dubber", "all", broadcast=True)
            logger.info(f"✅ Anime ID={anime_id} dubberlari yangilandi va kesh tozalandi.")
            return True
            
        except Exception as e:
            logger.error(f"🚨 Dubberlarni yangilashda service xatosi: {e}")
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            return False
    
    # ==================================================
    # 🎙 QUICK DUBBERS ADD (TRANSACTION-SAFE & CACHE-AWARE)
    # ==================================================
    async def add_quick_dubbers(self, dubbers_list: list[str]) -> tuple[int, list[str]]:
        """
        Tezkor dubberlarni bazaga qo'shish biznes logikasi.
        Qaytaradi: (qo'shilganlar_soni, tashlab_ketilgan_dubberlar_ro'yxati)
        """
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        added_count = 0
        skipped_dubbers = []

        try:
            for dubber_name in dubbers_list:
                # 1. Repozitoriy orqali dublikat borligini tekshiramiz
                existing = await self.repo.get_dubber_by_name(self.session, dubber_name)
                
                if not existing:
                    # 2. Mavjud bo'lmasa yangisini qo'shamiz
                    await self.repo.add_dubber(self.session, dubber_name)
                    added_count += 1
                else:
                    skipped_dubbers.append(dubber_name)

            # 3. Tranzaksiyani saqlaymiz
            if added_count > 0 and hasattr(self.session, "commit"):
                await self.session.commit()
                # 🔥 Dubberlar ro'yxati o'zgargani sababli dubber keshlarini majburiy tozalaymiz
                await self.cache.invalidate("dubber", "all", broadcast=True)
                logger.info(f"💾 DUBBER CACHE INVALIDATED: Added {added_count} new dubbers.")
            
            return added_count, skipped_dubbers

        except Exception as e:
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.error(f"❌ Service Layer Error while adding dubbers: {e}")
            raise e
    
    
    
    
    async def track_anime_view(self, anime_id: int) -> bool:
        """
        🚀 Animeni ko'rilishlar sonini oshiradi, tranzaksiyani commit qiladi
        va keshni tozalaydi (invalidate), shunda keyingi safar yangi statistika yuklanadi.
        """
        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()
            
        try:
            # 1. Repozitoriy orqali bazada +1 qilamiz
            success = await self.repo.increment_views(self.session, anime_id)
            
            if success:
                # 2. Tranzaksiyani bazaga saqlaymiz (Commit)
                if hasattr(self.session, "commit"):
                    await self.session.commit()
                
                # 3. 🔥 KESHNI INVALIdATE QILAMIZ: Eski kesh o'chib, yangi ko'rishlar soni keshga o'tiradi
                await self.cache.invalidate("anime", anime_id)
                logger.info(f"📊 COUNTER UPDATED & CACHE INVALIDATED: anime_id={anime_id}")
                return True
                
            return False
        except Exception as e:
            logger.error(f"❌ AnimeService.track_anime_view da xato: {e}")
            if hasattr(self.session, "rollback"):
                await self.session.rollback()
            return False
    

    # ==================================================
    # 🏁 GET COMPLETED ANIMES (CACHE-AWARE)
    # ==================================================
    async def get_completed_animes(self, offset: int = 0, limit: int = 10) -> Dict[str, Any]:
        """
        Tugallangan animelar ro'yxati hamda umumiy sonini qaytaradi (Kesh bilan ishlaydi).
        """
        cache_key = f"completed_offset_{offset}_limit_{limit}"
        cached_data = await self.cache.get("anime_completed", cache_key)
        
        if cached_data is not None:
            logger.debug(f"🎯 CACHE HIT: Completed animes loaded from cache (offset={offset}, limit={limit})")
            return cached_data

        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        data = await self.repo.get_completed_animes(self.session, offset=offset, limit=limit)
        
        # 30 daqiqaga keshga saqlaymiz (TTL: 1800s)
        await self.cache.set("anime_completed", cache_key, data, ttl=180)
        return data
    


    # ==================================================
    # ⏳ GET ONGOING ANIMES (CACHE-AWARE)
    # ==================================================
    async def get_ongoing_animes(self, offset: int = 0, limit: int = 10) -> Dict[str, Any]:
        """
        Davom etayotgan (tugallanmagan) animelar ro'yxati hamda umumiy sonini qaytaradi (Kesh bilan ishlaydi).
        """
        cache_key = f"ongoing_offset_{offset}_limit_{limit}"
        cached_data = await self.cache.get("anime_ongoing", cache_key)
        
        if cached_data is not None:
            logger.debug(f"🎯 CACHE HIT: Ongoing animes loaded from cache (offset={offset}, limit={limit})")
            return cached_data

        if hasattr(self.session, "_ensure_session"):
            await self.session._ensure_session()

        data = await self.repo.get_ongoing_animes(self.session, offset=offset, limit=limit)
        
        # 3 daqiqaga keshga saqlaymiz (TTL: 180s)
        await self.cache.set("anime_ongoing", cache_key, data, ttl=180)
        return data
    



    # ==================================================
    # 🏷 SET EPISODE FILLER (TRANSACTION SAFE)
    # ==================================================
    async def set_episode_filler(self, anime_id: int, episode_num: int, is_filler: bool) -> bool:
        """
        Epizodning filler maqomini yangilaydi va tegishli keshni tozalaydi.
        """
        try:
            if hasattr(self.session, "_ensure_session"):
                await self.session._ensure_session()

            ok = await self.repo.set_episode_filler(self.session, anime_id, episode_num, is_filler)
            await self.session.commit()

            if ok:
                # Epizod ma'lumotlari o'zgargani uchun keshlar tozalanadi
                await self.cache.invalidate("anime", anime_id, broadcast=True)
                await self.cache.invalidate("anime", "all", broadcast=True)
                await self.cache.invalidate("anime_episodes", anime_id, broadcast=True)

                await self.cache.invalidate("anime_completed", "all", broadcast=True)
                await self.cache.invalidate("anime_ongoing", "all", broadcast=True)
                logger.info(f"🏷 Episode filler status updated: Anime {anime_id}, Ep {episode_num} -> {is_filler}")

            return ok

        except Exception as e:
            if self.session and hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.error(f"❌ Failed to update episode filler status: {e}")
            raise e
    


    # ==================================================
    # 🗑 DELETE EPISODE VIP (TRANSACTION SAFE & CACHE-AWARE)
    # ==================================================
    async def delete_episode_vip(
        self, 
        anime_id: int, 
        episode_num: int, 
        dub_group: str = "default"
    ) -> bool:
        """
        VIP qism (stream)ni o'chiradi, tranzaksiyani commit qiladi va keshni invalidatsiya qiladi.
        """
        try:
            if hasattr(self.session, "_ensure_session"):
                await self.session._ensure_session()

            # Repozitoriy orqali VIP stream o'chiriladi
            ok = await self.repo.delete_episode_vip(
                self.session, 
                anime_id, 
                episode_num, 
                dub_group
            )
            
            # Tranzaksiyani tasdiqlaymiz
            await self.session.commit()

            if ok:
                # Barcha aloqador keshlar tozalanadi
                await self.cache.invalidate("anime", anime_id, broadcast=True)
                await self.cache.invalidate("anime", "all", broadcast=True)
                await self.cache.invalidate("anime_episodes", anime_id, broadcast=True)
                await self.cache.invalidate("anime_completed", "all", broadcast=True)
                await self.cache.invalidate("anime_ongoing", "all", broadcast=True)
                logger.info(
                    f"🗑 VIP Episode stream deleted + cache invalidated: Anime {anime_id}, Ep {episode_num} [{dub_group}]"
                )

            return ok

        except Exception as e:
            if self.session and hasattr(self.session, "rollback"):
                await self.session.rollback()
            logger.error(f"❌ Failed to delete VIP episode stream: {e}")
            raise e