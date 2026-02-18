from sqlalchemy import BigInteger, String, Integer, Float, DateTime, Text, ForeignKey, Boolean, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from datetime import datetime
from typing import List, Optional
from database.db import engines

class Base(DeclarativeBase):
    pass

# --- 1. USER GURUHI (U1, U2, U3 bazalari uchun) ---
class User(Base):
    __tablename__ = "users"
    
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(255))
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    points: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="user")
    vip_expire_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    health_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    referral_count: Mapped[int] = mapped_column(Integer, default=0)

class Favorite(Base):
    __tablename__ = "favorites"
    # Turli bazalar bo'lgani uchun ForeignKey ishlatmaymiz, faqat ID saqlaymiz
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    anime_id: Mapped[int] = mapped_column(Integer, primary_key=True)

class History(Base):
    __tablename__ = "history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    anime_id: Mapped[int] = mapped_column(Integer)
    last_episode: Mapped[int] = mapped_column(Integer)
    watched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# --- 2. ANIME GURUHI (A1, A2, A3 bazalari uchun) ---
class Anime(Base):
    __tablename__ = "anime_list"
    
    anime_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    poster_id: Mapped[Optional[str]] = mapped_column(Text)
    lang: Mapped[Optional[str]] = mapped_column(String(100))
    genre: Mapped[Optional[str]] = mapped_column(String(255))
    year: Mapped[Optional[str]] = mapped_column(String(20))
    fandub: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    rating_sum: Mapped[float] = mapped_column(Float, default=0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    views_week: Mapped[int] = mapped_column(Integer, default=0)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Bir xil baza ichida relationship ishlaydi
    episodes: Mapped[List["Episode"]] = relationship(back_populates="anime", cascade="all, delete-orphan")

class Episode(Base):
    __tablename__ = "anime_episodes"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anime_id: Mapped[int] = mapped_column(ForeignKey("anime_list.anime_id", ondelete="CASCADE"))
    episode: Mapped[int] = mapped_column(Integer)
    file_id: Mapped[str] = mapped_column(Text)
    
    anime: Mapped["Anime"] = relationship(back_populates="episodes")


# --- 3. FEEDBACK GURUHI (FB bazasi uchun) ---
class Comment(Base):
    __tablename__ = "comments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    anime_id: Mapped[int] = mapped_column(Integer)
    comment_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# database/db.py fayliga qo'shing


    
