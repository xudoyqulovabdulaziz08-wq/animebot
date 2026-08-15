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

# ================= GET BY ID =================
    @staticmethod
    async def get_by_id(session: Any, anime_id: int) -> Optional[Dict]:
        session = await AnimeRepository._prepare_session(session)

        stmt = (
            select(Anime)
            .where(Anime.anime_id == anime_id)
            .options(
                selectinload(Anime.genres),
                # 1. Epizodlarni yuklash bilan birga uning streams munosabatini ham nested yuklaymiz
                selectinload(Anime.episodes).selectinload(Episode.streams),
                selectinload(Anime.dubbers)
            )
        )

        result = await session.execute(stmt)
        anime = result.scalar_one_or_none()

        if not anime:
            return None

        # Ustunlarni dict qilamiz va munosabatlarni qo'lda xavfsiz qo'shamiz
        data = anime.to_dict()
        data["genres"] = [g.id for g in anime.genres] if hasattr(anime, "genres") else []
        data["dubbers"] = [d.id for d in anime.dubbers] if hasattr(anime, "dubbers") else []
        
        # 2. Epizodlar ro'yxatini yangi streams strukturasiga moslab shakllantiramiz
        episodes_list = []
        if hasattr(anime, "episodes"):
            for ep in anime.episodes:
                # Epizodga tegishli barcha video manbalarini (streams) olamiz
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
                    # Eskicha kodlar buzilmasligi uchun birinchi/asosiy stream fayl ID sini ham qo'shib qo'yamiz:
                    "file_id": streams_data[0]["file_id"] if streams_data else None
                })

        data["episodes"] = episodes_list
        
        return data
    
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
            .options(selectinload(Episode.streams))  # 1. Video manbalarini (streams) yuklaymiz
            .order_by(Episode.episode)
        )

        result = await real_session.execute(stmt)
        episodes_list = result.scalars().all()

        formatted_episodes = []
        for ep in episodes_list:
            ep_dict = ep.to_dict()

            # 2. Streams ma'lumotlarini lug'at shaklida yig'amiz
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
            .options(selectinload(Anime.genres), selectinload(Anime.episodes), selectinload(Anime.dubbers))
            .order_by(desc(Anime.anime_id))
        )

        result = await session.execute(stmt)
        anime_list = []
        
        for anime in result.scalars().all():
            data = anime.to_dict()
            data["genres"] = [g.id for g in anime.genres] if hasattr(anime, "genres") else []
            data["dubbers"] = [d.id for d in anime.dubbers] if hasattr(anime, "dubbers") else []
            data["episodes"] = [
                {"id": ep.id, "episode": ep.episode, "file_id": ep.file_id} 
                for ep in anime.episodes
            ] if hasattr(anime, "episodes") else []
            anime_list.append(data)
            
        return anime_list

    # ================= CREATE ANIME =================
    @staticmethod
    async def create(
        session: Any,
        title: str,
        poster_id: Optional[str],
        year: int,
        is_completed: bool,
        genres: List[Any],
        dubbers: List[Any],
        description: str,
        languages: list
    ) -> Dict:
        # 💡 CIRCULAR IMPORT OLDIRI OLISH UCHUN: Kechikib import qilamiz
        from database.models import Dubber

        session = await AnimeRepository._prepare_session(session)

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

        anime = Anime(
            title=title,
            poster_id=poster_id,
            year=year,
            is_completed=is_completed,
            description=description,
            languages=languages,
            genres=genre_objs,
            dubbers=dubber_objs
        )

        session.add(anime)
        await session.flush()  # ID bazadan darhol olinishi uchun
        
        # Ustunlarni dict qilamiz va munosabatlarni qo'lda xavfsiz qo'shamiz
        data = anime.to_dict()
        data["genres"] = [g.id for g in anime.genres] if hasattr(anime, "genres") else []
        data["dubbers"] = [d.id for d in anime.dubbers] if hasattr(anime, "dubbers") else []
        data["episodes"] = []  # Yangi yaratilganda epizodlar bo'lmaydi
        
        return data

    # ================= ADD EPISODE =================
    @staticmethod
    async def add_episode(
        session: Any,
        anime_id: int,
        episode_num: int,
        file_id: str
    ) -> bool:
        session = await AnimeRepository._prepare_session(session)

        ep = Episode(
            anime_id=anime_id,
            episode=episode_num,
            file_id=file_id
        )

        session.add(ep)
        await session.flush()
        return True
    
    # ================= DELETE EPISODE =================
    @staticmethod
    async def delete_episode(session: Any, anime_id: int, episode_num: int) -> bool:
        from sqlalchemy import delete
        real_session = await AnimeRepository._prepare_session(session)

        stmt = delete(Episode).where(
            Episode.anime_id == anime_id,
            Episode.episode == episode_num
        )
        result = await real_session.execute(stmt)
        await real_session.flush()
        
        # Agar kamida 1 ta qator o'chirilgan bo'lsa True qaytadi
        return result.rowcount > 0

    # ================= DELETE =================
    @staticmethod
    async def delete(session: Any, anime_id: int) -> bool:
        real_session = await AnimeRepository._prepare_session(session)

        result = await real_session.execute(
            select(Anime).where(Anime.anime_id == anime_id)
        )
        anime = result.scalar_one_or_none()

        if not anime:
            return False

        await real_session.delete(anime)   # ✅ await qo'shing!
        await real_session.flush()
        return True
    
    # ================= UPDATE EPISODE FILE =================
    @staticmethod
    async def update_episode_file(session: Any, anime_id: int, episode_num: int, new_file_id: str) -> bool:
        from sqlalchemy import update
        real_session = await AnimeRepository._prepare_session(session)

        stmt = (
            update(Episode)
            .where(Episode.anime_id == anime_id, Episode.episode == episode_num)
            .values(file_id=new_file_id)
        )
        result = await real_session.execute(stmt)
        await real_session.flush()
        
        return result.rowcount > 0
    


    # ================= MULTI-GENRE SEARCH (OPTIMIZED) =================
    @staticmethod
    async def get_by_genres(session: Any, genre_ids: List[int]) -> List[Dict]:
        from database.models import anime_genres  # Many-to-Many o'rtadagi jadval
        from sqlalchemy import func

        session = await AnimeRepository._prepare_session(session)

        # SQL mantiqi: Tanlangan janrlar ichidan qidir, anime bo'yicha guruhla
        # va faqat guruhdagi janrlar soni biz yuborgan janrlar soniga teng bo'lganlarini ol!
        stmt = (
            select(Anime)
            .join(anime_genres)
            .where(anime_genres.c.genre_id.in_(genre_ids))
            .group_by(Anime.anime_id)
            .having(func.count(anime_genres.c.genre_id) == len(genre_ids))
            .options(selectinload(Anime.genres), selectinload(Anime.episodes))
            .order_by(desc(Anime.anime_id))
        )

        result = await session.execute(stmt)
        anime_list = []
        
        for anime in result.scalars().all():
            data = anime.to_dict()
            data["genres"] = [g.id for g in anime.genres] if hasattr(anime, "genres") else []
            data["episodes"] = [
                {"id": ep.id, "episode": ep.episode, "file_id": ep.file_id} 
                for ep in anime.episodes
            ] if hasattr(anime, "episodes") else []
            anime_list.append(data)
            
        return anime_list
    
    @staticmethod
    async def get_by_dubbers(session: Any, dubber_ids: List[int]) -> List[Dict]:
        """Tanlangan barcha dubberlar ishtirok etgan animelarni bazadan eng tezkor usulda filtrlab beradi."""
        # Many-to-Many o'rtadagi jadval va modellarni kechikib import qilamiz
        from database.models import anime_dubbers  # O'rtadagi jadval nomi (models.py dagi nomga qarab o'zgartiring)
        from sqlalchemy import func

        if not dubber_ids:
            return []

        session = await AnimeRepository._prepare_session(session)

        # SQL mantiqi: Tanlangan dubberlar ichidan qidir, anime bo'yicha guruhla
        # va faqat guruhdagi dubberlar soni biz yuborgan dubberlar soniga teng bo'lganlarini ol!
        stmt = (
            select(Anime)
            .join(anime_dubbers)
            .where(anime_dubbers.c.dubber_id.in_(dubber_ids))
            .group_by(Anime.anime_id)
            .having(func.count(anime_dubbers.c.dubber_id) == len(dubber_ids))
            .options(
                selectinload(Anime.genres), 
                selectinload(Anime.episodes),
                selectinload(Anime.dubbers)  # 🎙 Dubberlarni ham yuklab olamiz
            )
            .order_by(desc(Anime.anime_id))
        )

        result = await session.execute(stmt)
        anime_list = []
        
        for anime in result.scalars().all():
            data = anime.to_dict()
            data["genres"] = [g.id for g in anime.genres] if hasattr(anime, "genres") else []
            data["dubbers"] = [d.id for d in anime.dubbers] if hasattr(anime, "dubbers") else [] # 🎙 Dubber ID ro'yxati
            data["episodes"] = [
                {"id": ep.id, "episode": ep.episode, "file_id": ep.file_id} 
                for ep in anime.episodes
            ] if hasattr(anime, "episodes") else []
            anime_list.append(data)
            
        return anime_list
    # ================= UNIVERSAL UPDATE ANIME =================
    @staticmethod
    async def update(session: Any, anime_id: int, update_data: Dict[str, Any]) -> bool:
        """
        Bazadagi animening istalgan ustunlarini dinamik yangilash uchun universal metod.
        update_data format: {"title": "Yangi nom", "year": 2026}
        """
        session = await AnimeRepository._prepare_session(session)
        
        # 1. Animeni bazadan qidiramiz
        stmt = select(Anime).where(Anime.anime_id == anime_id)
        result = await session.execute(stmt)
        anime = result.scalar_one_or_none()
        
        if not anime:
            logger.warning(f"⚠️ Yangilash g'alati: Anime ID={anime_id} topilmadi.")
            return False
            
        # 2. Kelgan ma'lumotlarni setattr orqali dinamik ustunlarga yozamiz
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