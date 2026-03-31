#========= models.py =========
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    String, Integer, BigInteger, Boolean, Text, Float,
    DateTime, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func





#================= BASE =================
class Base(DeclarativeBase):
    pass


# ================= USER =================
class DBUser(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), index=True)

    joined_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), default="user", index=True, nullable=False
    )  # user / admin / vip

    vip_expire_date: Mapped[Optional[datetime]] = mapped_column(DateTime)

    health_mode: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    referral_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    favorites: Mapped[List["Favorite"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    history: Mapped[List["History"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    comments: Mapped[List["Comment"]] = relationship(
        back_populates="user"
    )


# ================= ANIME =================
class Anime(Base):
    __tablename__ = "anime_list"

    __table_args__ = (
        Index("idx_anime_name", "name"),
        Index("idx_anime_year", "year"),
    )

    anime_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    poster_id: Mapped[Optional[str]] = mapped_column(String(255))

    lang: Mapped[Optional[str]] = mapped_column(String(100))
    genre: Mapped[Optional[str]] = mapped_column(String(255))

    year: Mapped[Optional[int]] = mapped_column(Integer)

    fandub: Mapped[Optional[str]] = mapped_column(String(255))

    description: Mapped[Optional[str]] = mapped_column(Text)

    rating_sum: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    views_week: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False) 

    # Relationships
    episodes: Mapped[List["Episode"]] = relationship(
        back_populates="anime", cascade="all, delete-orphan"
    )
    favorites: Mapped[List["Favorite"]] = relationship(
        back_populates="anime", cascade="all, delete-orphan"
    )
    history: Mapped[List["History"]] = relationship(
        back_populates="anime", cascade="all, delete-orphan"
    )
    comments: Mapped[List["Comment"]] = relationship(
        back_populates="anime", cascade="all, delete-orphan"
    )


# ================= EPISODE =================
class Episode(Base):
    __tablename__ = "anime_episodes"

    __table_args__ = (
        Index("idx_episode_anime", "anime_id"),
        UniqueConstraint("anime_id", "episode", name="uix_anime_episode"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    anime_id: Mapped[int] = mapped_column(
        ForeignKey("anime_list.anime_id", ondelete="CASCADE")
    )

    episode: Mapped[int] = mapped_column(Integer)

    file_id: Mapped[str] = mapped_column(String(255))

    anime: Mapped["Anime"] = relationship(back_populates="episodes")


# ================= FAVORITE =================
class Favorite(Base):
    __tablename__ = "favorites"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True
    )
    anime_id: Mapped[int] = mapped_column(
        ForeignKey("anime_list.anime_id", ondelete="CASCADE"),
        primary_key=True
    )

    user: Mapped["DBUser"] = relationship(back_populates="favorites")
    anime: Mapped["Anime"] = relationship(back_populates="favorites")


# ================= HISTORY =================
class History(Base):
    __tablename__ = "history"

    __table_args__ = (
    Index("idx_history_user_anime", "user_id", "anime_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE")
    )

    anime_id: Mapped[int] = mapped_column(
        ForeignKey("anime_list.anime_id", ondelete="CASCADE")
    )

    last_episode: Mapped[int] = mapped_column(Integer)

    watched_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    user: Mapped["DBUser"] = relationship(back_populates="history")
    anime: Mapped["Anime"] = relationship(back_populates="history")


# ================= COMMENT =================
class Comment(Base):
    __tablename__ = "comments"

    __table_args__ = (
        Index("idx_comment_anime", "anime_id"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True
    )

    anime_id: Mapped[int] = mapped_column(
        ForeignKey("anime_list.anime_id", ondelete="CASCADE")
    )

    comment_text: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    user: Mapped["DBUser"] = relationship(back_populates="comments")
    anime: Mapped["Anime"] = relationship(back_populates="comments")


# ================= CHANNEL =================
class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    channel_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False
    )

    title: Mapped[str] = mapped_column(String(255))

    url: Mapped[str] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )