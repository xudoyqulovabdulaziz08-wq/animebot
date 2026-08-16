import logging
from typing import Any, Optional, Dict, List
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from database.models import Anime, Episode, Genre, Dubber  

logger = logging.getLogger("AnimeRepository")

class AnimeRepository:

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
        return AnimeRepository._get_real_session(session)

    # ================= 🏷 SERIALIZER (foydalanuvchiga ko'rsatiladigan dict) =================
    @staticmethod
    def _serialize_anime(anime: Anime) -> Dict:
        data = anime.to_dict()

        titles = anime.titles if hasattr(anime, "titles") and anime.titles else []
        primary_title = titles[0] if titles else None

        data["title"] = (primary_title.title_uz if primary_title else None) or "Nomsiz anime"
        data["titles"] = {
            "uz": primary_title.title_uz if primary_title else None,
            "en": primary_title.title_en if primary_title else None,
            "jp": primary_title.title_jp if primary_title else None,
            "jp_romaji": primary_title.title_jp_romaji if primary_title else None,
            "ru": primary_title.title_ru if primary_title else None,
        }

        data["genres"] = [g.id for g in anime.genres] if hasattr(anime, "genres") else []
        data["dubbers"] = [d.id for d in anime.dubbers] if hasattr(anime, "dubbers") else []

        episodes_list = []
        if hasattr(anime, "episodes"):
            for ep in anime.episodes:
                streams_data = [
                    {
                        "id": st.id,
                        "file_id": st.file_id,
                        "dub_group": st.dub_group,
                        "is_vip": st.is_vip
                    }
                    for st in ep.streams
                ] if hasattr(ep, "streams") else []

                episodes_list.append({
                    "id": ep.id,
                    "episode": ep.episode,
                    "is_filler": ep.is_filler,
                    "episode_title": ep.episode_title,
                    "streams": streams_data,
                    "file_id": streams_data[0]["file_id"] if streams_data else None
                })

        # ✅ Epizodlar tartibini to'g'ri joylashtiramiz
        episodes_list.sort(key=lambda x: x["episode"])
        data["episodes"] = episodes_list
        data["episodes_count"] = len(episodes_list)

        return data

    # ================= GET BY ID =================
    @staticmethod
    async def get_by_id(session: Any, anime_id: int) -> Optional[Dict]:
        session = await AnimeRepository._prepare_session(session)

        stmt = (
            select(Anime)
            .where(Anime.anime_id == anime_id)
            .options(
                selectinload(Anime.titles),
                selectinload(Anime.genres),
                # Epizodlarni yuklash bilan birga uning streams munosabatini ham nested yuklaymiz
                selectinload(Anime.episodes).selectinload(Episode.streams),
                selectinload(Anime.dubbers)
            )
        )

        result = await session.execute(stmt)
        anime = result.scalar_one_or_none()

        if not anime:
            return None

        return AnimeRepository._serialize_anime(anime)

    #================= INCREMENT VIEWS =================
    @staticmethod
    async def increment_views(session: Any, anime_id: int) -> bool:
        """
        ⚡ SQL darajasida views_week va views_total ustunlarini +1 taga oshiradi.
        Atomic update bo'lgani uchun Race Condition xavfi yo'q.
        """
        from sqlalchemy import update
        from database.models import Anime
        
        session = await AnimeRepository._prepare_session(session)
        
        try:
            stmt = (
                update(Anime)
                .where(Anime.anime_id == anime_id)
                .values(
                    views_week=Anime.views_week + 1,
                    views_total=Anime.views_total + 1
                )
            )
            await session.execute(stmt)
            return True
        except Exception as e:
            logger.error(f"❌ AnimeRepository.increment_views da xato: {e}")
            return False

    # ================= GET EPISODES BY ANIME ID =================
    @staticmethod
    async def get_episodes_by_anime_id(session: Any, anime_id: int) -> List[Dict]:
        """
        🎬 Bazadan ma'lum bir animening barcha qismlarini 
        qism raqami bo'yicha tartiblangan holatda tortib beradi.
        """
        real_session = await AnimeRepository._prepare_session(session)

        stmt = (
            select(Episode)
            .where(Episode.anime_id == anime_id)
            .options(selectinload(Episode.streams))  # Video manbalarini (streams) yuklaymiz
            .order_by(Episode.episode)
        )

        result = await real_session.execute(stmt)
        episodes_list = result.scalars().all()

        formatted_episodes = []
        for ep in episodes_list:
            ep_dict = ep.to_dict()

            # Streams ma'lumotlarini lug'at shaklida yig'amiz
            streams = [
                {
                    "id": st.id,
                    "file_id": st.file_id,
                    "dub_group": st.dub_group,
                    "is_vip": st.is_vip
                }
                for st in ep.streams
            ] if hasattr(ep, "streams") else []

            ep_dict["streams"] = streams
            # Eskicha kodlar buzilmasligi uchun birinchi/asosiy file_id ni qaytaramiz
            ep_dict["file_id"] = streams[0]["file_id"] if streams else None

            formatted_episodes.append(ep_dict)

        return formatted_episodes

    # ================= LIST =================
    @staticmethod
    async def list(session: Any) -> List[Dict]:
        session = await AnimeRepository._prepare_session(session)

        stmt = (
            select(Anime)
            .options(
                selectinload(Anime.titles),
                selectinload(Anime.genres),
                selectinload(Anime.episodes).selectinload(Episode.streams),
                selectinload(Anime.dubbers)
            )
            .order_by(desc(Anime.anime_id))
        )

        result = await session.execute(stmt)
        return [AnimeRepository._serialize_anime(anime) for anime in result.scalars().all()]

    # ================= MULTI-GENRE SEARCH (OPTIMIZED) =================
    @staticmethod
    async def get_by_genres(session: Any, genre_ids: List[int]) -> List[Dict]:
        from database.models import anime_genres
        from sqlalchemy import func

        unique_genre_ids = list(set(genre_ids))
        if not unique_genre_ids:
            return []

        session = await AnimeRepository._prepare_session(session)

        stmt = (
            select(Anime)
            .join(anime_genres)
            .where(anime_genres.c.genre_id.in_(unique_genre_ids))
            .group_by(Anime.anime_id)
            .having(func.count(func.distinct(anime_genres.c.genre_id)) == len(unique_genre_ids))
            .options(
                selectinload(Anime.titles),
                selectinload(Anime.genres),
                selectinload(Anime.episodes).selectinload(Episode.streams),
                selectinload(Anime.dubbers)
            )
            .order_by(desc(Anime.anime_id))
        )

        result = await session.execute(stmt)
        return [AnimeRepository._serialize_anime(anime) for anime in result.scalars().unique().all()]
    
    @staticmethod
    async def get_by_dubbers(session: Any, dubber_ids: List[int]) -> List[Dict]:
        from database.models import anime_dubbers
        from sqlalchemy import func

        unique_dubber_ids = list(set(dubber_ids))
        if not unique_dubber_ids:
            return []

        session = await AnimeRepository._prepare_session(session)

        stmt = (
            select(Anime)
            .join(anime_dubbers)
            .where(anime_dubbers.c.dubber_id.in_(unique_dubber_ids))
            .group_by(Anime.anime_id)
            .having(func.count(func.distinct(anime_dubbers.c.dubber_id)) == len(unique_dubber_ids))
            .options(
                selectinload(Anime.titles),
                selectinload(Anime.genres),
                selectinload(Anime.episodes).selectinload(Episode.streams),
                selectinload(Anime.dubbers)
            )
            .order_by(desc(Anime.anime_id))
        )

        result = await session.execute(stmt)
        return [AnimeRepository._serialize_anime(anime) for anime in result.scalars().unique().all()]

    

    # ================= CREATE ANIME =================
    @staticmethod
    async def create(
        session: Any,
        title_uz: str,
        title_en: Optional[str],
        poster_id: Optional[str],
        trailer_id: Optional[str],
        type: str,                  # 👈 QO'SHILDI: Anime formati (TV_SERIES, MOVIE, OVA)
        year: int,
        is_completed: bool,
        genres: List[int],
        dubbers: List[int],
        description: str,
        languages: list
    ) -> Dict:
        # 💡 CIRCULAR IMPORT OLDIRI OLISH UCHUN: Kechikib import qilamiz
        from database.models import Dubber, Genre, Anime, AnimeTitle
        from sqlalchemy import select

        session = await AnimeRepository._prepare_session(session)

        # 1. Janrlar va Dubberlarni ma'lumotlar bazasidan yuklab olish
        genre_objs = []
        if genres:
            stmt = select(Genre).where(Genre.id.in_(genres))
            res = await session.execute(stmt)
            genre_objs = list(res.scalars().all())

        dubber_objs = []
        if dubbers:
            stmt = select(Dubber).where(Dubber.id.in_(dubbers))
            res = await session.execute(stmt)
            dubber_objs = list(res.scalars().all())

        # 2. Anime obyektini yaratish
        anime = Anime(
            poster_id=poster_id,
            trailer_id=trailer_id,
            type=type,              # 👈 QO'SHILDI
            year=year,
            is_completed=is_completed, # Texnik / Tranzaksiya holati
            is_finished=False,         # Yangi qo'shilgan anime odatda hali davom etayotgan bo'ladi
            description=description,
            languages=languages,
            genres=genre_objs,
            dubbers=dubber_objs
        )

        session.add(anime)
        await session.flush()  # ID bazadan darhol olinishi uchun

        # 3. Sarlavhalarni (AnimeTitle) alohida jadvalga yozish
        anime_title = AnimeTitle(
            anime_id=anime.anime_id,
            title_uz=title_uz,
            title_en=title_en
        )
        session.add(anime_title)
        
        # O'zgarishlar tasdiqlanishidan oldin yana bir bor flush
        await session.flush()

        # 4. Ustunlarni dict qilamiz va munosabatlarni foydalanuvchiga qaytarish uchun yig'amiz
        data = anime.to_dict()
        
        # Serializer ( _serialize_anime ) kabi ma'lumotni to'g'rilab qaytaramiz
        data["title"] = title_uz
        data["titles"] = {
            "uz": title_uz,
            "en": title_en,
            "jp": None,
            "jp_romaji": None,
            "ru": None,
        }
        data["type"] = type         # 👈 QO'SHILDI
        
        data["genres"] = [g.id for g in anime.genres] if hasattr(anime, "genres") else []
        data["dubbers"] = [d.id for d in anime.dubbers] if hasattr(anime, "dubbers") else []
        
        data["episodes"] = []  # Yangi yaratilganda epizodlar bo'lmaydi
        data["episodes_count"] = 0
        
        return data
    

    # ================= ADD EPISODE =================
    @staticmethod
    async def add_episode(
        session: Any, 
        anime_id: int, 
        episode_num: int, 
        file_id: str,
        dub_group: str = "default",
        is_vip: bool = False
    ) -> bool:
        from database.models import Episode, EpisodeStream
        from sqlalchemy import select

        real_session = await AnimeRepository._prepare_session(session)

        stmt = select(Episode).where(
            Episode.anime_id == anime_id,
            Episode.episode == episode_num
        )
        res = await real_session.execute(stmt)
        episode = res.scalar_one_or_none()

        if not episode:
            episode = Episode(anime_id=anime_id, episode=episode_num)
            real_session.add(episode)
            await real_session.flush()

        # ✅ Stream takrorlanishini oldini olamiz
        stmt_st = select(EpisodeStream).where(
            EpisodeStream.episode_id == episode.id,
            EpisodeStream.dub_group == dub_group,
            EpisodeStream.is_vip == is_vip
        )
        res_st = await real_session.execute(stmt_st)
        existing_stream = res_st.scalar_one_or_none()

        if existing_stream:
            existing_stream.file_id = file_id
        else:
            stream = EpisodeStream(
                episode_id=episode.id,
                dub_group=dub_group,
                is_vip=is_vip,
                file_id=file_id
            )
            real_session.add(stream)

        await real_session.flush()
        return True
    # ================= DELETE EPISODE =================
    @staticmethod
    async def delete_episode(session: Any, anime_id: int, episode_num: int) -> bool:
        from sqlalchemy import delete
        from database.models import Episode
        
        real_session = await AnimeRepository._prepare_session(session)

        # Episode o'chirilganda, db-level cascade orqali unga ulangan 
        # EpisodeStream'lar ham avtomatik o'chib ketishi kerak.
        stmt = delete(Episode).where(
            Episode.anime_id == anime_id,
            Episode.episode == episode_num
        )
        result = await real_session.execute(stmt)
        await real_session.flush()
        
        # Agar kamida 1 ta qator o'chirilgan bo'lsa True qaytadi
        return result.rowcount > 0

    # ================= DELETE ANIME =================
    @staticmethod
    async def delete(session: Any, anime_id: int) -> bool:
        from sqlalchemy import select
        from database.models import Anime
        
        real_session = await AnimeRepository._prepare_session(session)

        result = await real_session.execute(
            select(Anime).where(Anime.anime_id == anime_id)
        )
        anime = result.scalar_one_or_none()

        if not anime:
            return False

        await real_session.delete(anime)   # ✅ await bilan obyekti o'chiramiz
        await real_session.flush()
        return True
    
    # ================= UPDATE EPISODE FILE (STREAM) =================
    @staticmethod
    async def update_episode_file(
        session: Any, 
        anime_id: int, 
        episode_num: int, 
        new_file_id: str,
        dub_group: str = "default",  # 👈 QO'SHILDI: qaysi dublyaj
        is_vip: bool = False         # 👈 QO'SHILDI: VIP yoki Free fayl ekanligi
    ) -> bool:
        from sqlalchemy import select, update
        from database.models import Episode, EpisodeStream
        
        real_session = await AnimeRepository._prepare_session(session)

        # 1. Avval anime_id va episode_num orqali Episode ID'ni topib olamiz
        stmt_ep = select(Episode.id).where(
            Episode.anime_id == anime_id,
            Episode.episode == episode_num
        )
        res_ep = await real_session.execute(stmt_ep)
        episode_id = res_ep.scalar_one_or_none()

        if not episode_id:
            return False  # Epizod topilmadi

        # 2. Endi mos keluvchi EpisodeStream'ning file_id'sini yangilaymiz
        stmt = (
            update(EpisodeStream)
            .where(
                EpisodeStream.episode_id == episode_id,
                EpisodeStream.dub_group == dub_group,
                EpisodeStream.is_vip == is_vip
            )
            .values(file_id=new_file_id)
        )
        result = await real_session.execute(stmt)
        await real_session.flush()
        
        return result.rowcount > 0

    # ================= UNIVERSAL UPDATE ANIME =================
    @staticmethod
    async def update(session: Any, anime_id: int, update_data: Dict[str, Any]) -> bool:
        from database.models import AnimeTitle, Genre, Dubber
        from sqlalchemy.orm import selectinload

        session = await AnimeRepository._prepare_session(session)
        
        stmt = (
            select(Anime)
            .options(
                selectinload(Anime.titles),
                selectinload(Anime.genres),
                selectinload(Anime.dubbers)
            )
            .where(Anime.anime_id == anime_id)
        )
        result = await session.execute(stmt)
        anime = result.scalar_one_or_none()
        
        if not anime:
            logger.warning(f"⚠️ Yangilash g'alati: Anime ID={anime_id} topilmadi.")
            return False
            
        title_uz = update_data.pop("title_uz", None)
        title_en = update_data.pop("title_en", None)
        genre_ids = update_data.pop("genres", None)
        dubber_ids = update_data.pop("dubbers", None)

        if title_uz is not None or title_en is not None:
            stmt_title = select(AnimeTitle).where(AnimeTitle.anime_id == anime_id)
            res_title = await session.execute(stmt_title)
            anime_title = res_title.scalars().first()  # ✅ Crash bermaydigan xavfsiz usul
            
            if anime_title:
                if title_uz is not None:
                    anime_title.title_uz = title_uz
                if title_en is not None:
                    anime_title.title_en = title_en
            else:
                session.add(AnimeTitle(anime_id=anime_id, title_uz=title_uz or "", title_en=title_en))

        if genre_ids is not None:
            stmt_g = select(Genre).where(Genre.id.in_(genre_ids))
            res_g = await session.execute(stmt_g)
            anime.genres = list(res_g.scalars().all())

        if dubber_ids is not None:
            stmt_d = select(Dubber).where(Dubber.id.in_(dubber_ids))
            res_d = await session.execute(stmt_d)
            anime.dubbers = list(res_d.scalars().all())

        for key, value in update_data.items():
            if hasattr(anime, key):
                setattr(anime, key, value)
                logger.debug(f"✍️ Anime ID={anime_id}: {key} -> {value}")

        return True

    

    @staticmethod
    async def update_anime_genres(session: Any, anime_id: int, genre_ids: list[int]) -> bool:
        """Anime janrlarini Many-to-Many munosabati orqali xavfsiz yangilash"""
        from sqlalchemy.orm import selectinload
        session = await AnimeRepository._prepare_session(session)
        
        # Animeni janrlari bilan birga yuklaymiz
        stmt = select(Anime).where(Anime.anime_id == anime_id).options(selectinload(Anime.genres))
        result = await session.execute(stmt)
        anime = result.scalar_one_or_none()
        
        if not anime:
            return False
            
        if genre_ids:
            # Yangi janrlarni bazadan qidirib topamiz
            genre_stmt = select(Genre).where(Genre.id.in_(genre_ids))
            genre_result = await session.execute(genre_stmt)
            new_genres = genre_result.scalars().all()
            anime.genres = list(new_genres)
        else:
            anime.genres = [] # Agar hamma janr olib tashlansa
            
        return True
    
    @staticmethod
    async def update_anime_dubbers(session: Any, anime_id: int, dubber_ids: list[int]) -> bool:
        """🎙 Anime dubberlarini Many-to-Many munosabati orqali xavfsiz yangilash"""
        from sqlalchemy.orm import selectinload
        from database.models import Dubber
        
        session = await AnimeRepository._prepare_session(session)
        
        # Animeni dubberlari bilan birga yuklaymiz
        stmt = select(Anime).where(Anime.anime_id == anime_id).options(selectinload(Anime.dubbers))
        result = await session.execute(stmt)
        anime = result.scalar_one_or_none()
        
        if not anime:
            return False
            
        if dubber_ids:
            # Yangi tanlangan dubberlarni bazadan qidirib topamiz
            dubber_stmt = select(Dubber).where(Dubber.id.in_(dubber_ids))
            dubber_result = await session.execute(dubber_stmt)
            new_dubbers = dubber_result.scalars().all()
            anime.dubbers = list(new_dubbers)
        else:
            anime.dubbers = []  # Agar hamma dubber olib tashlansa
            
        return True

    # ================= DUBBER METHODS =================
    @staticmethod
    async def get_dubber_by_name(session: Any, name: str) -> Optional[Any]:
        """Dubberni ismi orqali qidirish (Dublikat oldini olish uchun)"""
        # Kechikib import qilish orqali circular import xavfini yo'qotamiz
        from database.models import Dubber
        session = await AnimeRepository._prepare_session(session)
        
        stmt = select(Dubber).where(Dubber.name == name)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def add_dubber(session: Any, name: str) -> Any:
        """Yangi dubber ob'ektini yaratish va sessiyaga qo'shish"""
        from database.models import Dubber
        session = await AnimeRepository._prepare_session(session)
        
        new_dubber = Dubber(name=name)
        session.add(new_dubber)
        
        # 💡 TAVSIYA: Obyektga bazadan darhol ID biriktirilishi uchun flush qilamiz
        await session.flush() 
        return new_dubber

    # ================= GET COMPLETED ANIMES =================
    @staticmethod
    async def get_completed_animes(
        session: Any, 
        offset: int = 0, 
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Tugallangan (is_finished = True) animelar ro'yxatini va ularning umumiy sonini qaytaradi.
        """
        from sqlalchemy import func
        session = await AnimeRepository._prepare_session(session)

        # 1. Tugallangan animelarning umumiy sonini hisoblash (Count query)
        count_stmt = (
            select(func.count(Anime.anime_id))
            .where(Anime.is_finished == True)
        )
        total_count = (await session.execute(count_stmt)).scalar() or 0

        # 2. Tugallangan animelar ro'yxatini yuklash (Data query)
        stmt = (
            select(Anime)
            .where(Anime.is_finished == True)
            .options(
                selectinload(Anime.titles),
                selectinload(Anime.genres),
                selectinload(Anime.episodes).selectinload(Episode.streams),
                selectinload(Anime.dubbers)
            )
            .order_by(desc(Anime.anime_id))
            .offset(offset)
            .limit(limit)
        )

        result = await session.execute(stmt)
        animes = result.scalars().all()

        return {
            "total_count": total_count,
            "animes": [AnimeRepository._serialize_anime(anime) for anime in animes]
        }

    
    # ================= GET ONGOING / UNFINISHED ANIMES =================
    @staticmethod
    async def get_ongoing_animes(
        session: Any, 
        offset: int = 0, 
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Davom etayotgan / tugallanmagan (is_finished = False) animelar ro'yxatini va ularning umumiy sonini qaytaradi.
        """
        from sqlalchemy import func
        session = await AnimeRepository._prepare_session(session)

        # 1. Tugallanmagan animelarning umumiy sonini hisoblash
        count_stmt = (
            select(func.count(Anime.anime_id))
            .where(Anime.is_finished == False)
        )
        total_count = (await session.execute(count_stmt)).scalar() or 0

        # 2. Tugallanmagan animelar ro'yxatini yuklash
        stmt = (
            select(Anime)
            .where(Anime.is_finished == False)
            .options(
                selectinload(Anime.titles),
                selectinload(Anime.genres),
                selectinload(Anime.episodes).selectinload(Episode.streams),
                selectinload(Anime.dubbers)
            )
            .order_by(desc(Anime.anime_id))
            .offset(offset)
            .limit(limit)
        )

        result = await session.execute(stmt)
        animes = result.scalars().all()

        return {
            "total_count": total_count,
            "animes": [AnimeRepository._serialize_anime(anime) for anime in animes]
        }