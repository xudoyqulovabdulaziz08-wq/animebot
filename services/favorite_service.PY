import logging
from typing import List, Dict, Optional, Tuple
from sqlalchemy.exc import SQLAlchemyError

from repositories.favorite_repository import FavoriteRepository

# Loggerni sozlash
logger = logging.getLogger("FavoriteService")

class FavoriteService:
    """
    🚀 Favorite Service
    - Tranzaksiyalarni xavfsiz boshqarish (Commit / Rollback)
    - Xatoliklarni (Exception) global ushlash va loglash
    - Telegram bot / API frontend uchun qulay bo'lgan metodlar (Toggle)
    """

    @staticmethod
    async def add_to_favorites(session, user_id: int, anime_id: int) -> bool:
        """Animeni sevimlilarga qo'shish va tranzaksiyani yopish."""
        try:
            added = await FavoriteRepository.add_favorite(session, user_id, anime_id)
            if added:
                await session.commit()
                logger.info(f"User {user_id} added anime {anime_id} to favorites.")
            return added
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"DB Error in add_to_favorites for User {user_id}, Anime {anime_id}: {e}")
            return False
        except Exception as e:
            await session.rollback()
            logger.exception(f"Unexpected error in add_to_favorites: {e}")
            return False

    @staticmethod
    async def remove_from_favorites(session, user_id: int, anime_id: int) -> bool:
        """Animeni sevimlilardan o'chirish va tranzaksiyani yopish."""
        try:
            removed = await FavoriteRepository.remove_favorite(session, user_id, anime_id)
            if removed:
                await session.commit()
                logger.info(f"User {user_id} removed anime {anime_id} from favorites.")
            return removed
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"DB Error in remove_from_favorites: {e}")
            return False
        except Exception as e:
            await session.rollback()
            logger.exception(f"Unexpected error in remove_from_favorites: {e}")
            return False

    @staticmethod
    async def toggle_favorite(session, user_id: int, anime_id: int) -> Tuple[bool, str]:
        """
        Telegram Bot Inline tugmalari uchun maxsus metod (❤️/🤍).
        Agar anime sevimlilarda bo'lsa - o'chiradi, bo'lmasa - qo'shadi.
        
        Qaytaradi: (Status, Harakat nomi)
        - (True, "added") -> Muvaffaqiyatli qo'shildi
        - (True, "removed") -> Muvaffaqiyatli o'chirildi
        - (False, "error") -> Xatolik yuz berdi
        """
        try:
            is_fav = await FavoriteRepository.is_favorite(session, user_id, anime_id)
            
            if is_fav:
                success = await FavoriteRepository.remove_favorite(session, user_id, anime_id)
                action = "removed"
            else:
                success = await FavoriteRepository.add_favorite(session, user_id, anime_id)
                action = "added"
                
            if success:
                await session.commit()
                return True, action
                
            return False, "error"
        except Exception as e:
            await session.rollback()
            logger.exception(f"Error in toggle_favorite (User: {user_id}, Anime: {anime_id}): {e}")
            return False, "error"

    @staticmethod
    async def check_is_favorite(session, user_id: int, anime_id: int) -> bool:
        """Animening sevimlilarda bor-yo'qligini tekshirish (Read-Only)."""
        try:
            return await FavoriteRepository.is_favorite(session, user_id, anime_id)
        except Exception as e:
            logger.error(f"Error checking favorite status: {e}")
            return False

    @staticmethod
    async def get_user_favorites_list(session, user_id: int) -> List[Dict]:
        """
        Foydalanuvchining barcha sevimlilarini API formatida qaytarish (Read-Only).
        """
        try:
            return await FavoriteRepository.get_user_favorites(session, user_id)
        except Exception as e:
            logger.error(f"Error getting user {user_id} favorites: {e}")
            return []   
        

    @staticmethod
    async def check_is_favorite(session, user_id: int, anime_id: int) -> bool:
        """Anime foydalanuvchining sevimlilar ro'yxatida bor-yo'qligini tekshiradi."""
        try:
            return await FavoriteRepository.is_favorite(session, user_id, anime_id)
        except SQLAlchemyError as e:
            logger.error(f"DB Error in check_is_favorite for User {user_id}, Anime {anime_id}: {e}")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error in check_is_favorite: {e}")
            return False


    @staticmethod
    async def get_user_favorites(session, user_id: int) -> List[Dict]:
        """Foydalanuvchining barcha sevimli animelarini qaytaradi."""
        try:
            return await FavoriteRepository.get_user_favorites(session, user_id)
        except SQLAlchemyError as e:
            logger.error(f"DB Error in get_user_favorites for User {user_id}: {e}")
            return []
        except Exception as e:
            logger.exception(f"Unexpected error in get_user_favorites: {e}")
            return []