from datetime import datetime, timezone
import enum
import uuid
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    BigInteger, Table, String, DateTime, Column, ForeignKey, 
    Integer, Enum, Boolean, UniqueConstraint, Index, func, 
    Text, Numeric, Float, text, cast, case
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property  # <-- Hybrid alohida moduldan keladi
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy import event as sqla_event
from sqlalchemy import CheckConstraint
#========================================================================#
class Base(DeclarativeBase):
    def to_dict(self) -> dict:
        data = {}

        for column in self.__table__.columns:
            value = getattr(self, column.name)

            if isinstance(value, datetime):
                value = value.isoformat()

            elif isinstance(value, uuid.UUID):
                value = str(value)

            elif isinstance(value, Decimal):
                value = float(value)

            elif isinstance(value, enum.Enum):
                value = value.value

            data[column.name] = value

        return data
#========================================================================#
class UserStatus(enum.Enum):
    USER = "user"
    VIP = "vip"
    ADMIN = "admin"

#========================================================================#
anime_genres = Table(
    "anime_genres",
    Base.metadata,
    Column(
        "anime_id",
        ForeignKey("anime_list.anime_id", ondelete="CASCADE"),
        primary_key=True
    ),
    Column(
        "genre_id",
        ForeignKey("genres.id", ondelete="CASCADE"),
        primary_key=True
    ),
)

#========================================================================#
anime_dubbers = Table(
    "anime_dubbers",
    Base.metadata,
    Column(
        "anime_id",
        ForeignKey("anime_list.anime_id", ondelete="CASCADE"),
        primary_key=True
    ),
    Column(
        "dubber_id",
        ForeignKey("dubbers.id", ondelete="CASCADE"),
        primary_key=True
    ),
)

#========================================================================#
class DBUser(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True
    )

    username: Mapped[Optional[str]] = mapped_column(
        String(255),
        index=True
    )
    password_hash: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )

    # 🤖 BOT LOGINI UCHUN YANGI USTUNLAR:
    temporary_code: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True # Qidiruv tezlashishi uchun index qo'shildi
    )

    code_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )

    points: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False
    )

    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"),
        default=UserStatus.USER,
        nullable=False
    )

    vip_expire_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    sleep_reminder_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False
    )

    __table_args__ = (
        Index("idx_user_status_points", status, points), 
    )

    @hybrid_property
    def is_vip(self) -> bool:
        if self.status != UserStatus.VIP:
            return False
        if self.vip_expire_date is None:
            return True
        return self.vip_expire_date > datetime.now(timezone.utc)

    @is_vip.expression
    def is_vip(cls):
        return (cls.status == UserStatus.VIP) & (
            (cls.vip_expire_date == None) | (cls.vip_expire_date > func.now())
        )

#========================================================================#
class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True
    )

    animes: Mapped[list["Anime"]] = relationship(
        "Anime",
        secondary="anime_genres",
        back_populates="genres",
        lazy="selectin"
    )

#========================================================================#
class Dubber(Base):
    __tablename__ = "dubbers"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True
    )

    # Dubber sahifasiga kirganda u ovoz bergan barcha animelarni chiqarish uchun
    animes: Mapped[list["Anime"]] = relationship(
        "Anime",
        secondary="anime_dubbers",
        back_populates="dubbers",
        lazy="selectin"
    )

#========================================================================#
class Anime(Base):
    __tablename__ = "anime_list"

    anime_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True
    )

    poster_id: Mapped[Optional[str]] = mapped_column(
        String(255)
    )
    poster_r2_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )
    year: Mapped[Optional[int]] = mapped_column(
        Integer,
        index=True
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text
    )

    languages: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        default=lambda: [],  # <-- Tuzatildi: lambda qo'shildi
        server_default=text("ARRAY[]::varchar[]")  # <-- Tuzatildi: PG array formati
    )

    rating_sum: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), # Ovozlar ko'payganda sig'im yetishi uchun 12 ga o'tkazildi
        default=Decimal("0"),
        server_default="0"
    )

    rating_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0"
    )

    views_week: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        index=True
    )
    views_total: Mapped[int] = mapped_column(
        BigInteger,  # Ko'rishlar milliondan oshib ketishi uchun BigInteger qildik
        default=0,
        server_default="0",
        index=True
    )
    is_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false"
    )

    genres: Mapped[list["Genre"]] = relationship(
        secondary="anime_genres",
        back_populates="animes",
        lazy="selectin"
    )
    
    comments: Mapped[list["Comment"]] = relationship(
        "Comment",
        back_populates="anime",
        cascade="all, delete-orphan",
        order_by=lambda: Comment.created_at.desc(), # Oxirgi yozilgan izohlar birinchi chiqadi
        lazy="selectin"
    )

    # Anime class'ining ichiga (masalan, genres munosabatidan keyin) qo'shing:
    dubbers: Mapped[list["Dubber"]] = relationship(
        secondary="anime_dubbers",
        back_populates="animes",
        lazy="selectin"
    )

    episodes: Mapped[list["Episode"]] = relationship(
        "Episode",
        back_populates="anime",
        cascade="all, delete-orphan",
        order_by=lambda: Episode.episode,
        lazy="selectin"
    )

    @hybrid_property
    def average_rating(self) -> float:
        if self.rating_count == 0:
            return 0.0
        raw_avg = float(self.rating_sum / self.rating_count)
        return min(round(raw_avg, 1), 10.0) # 10 tadan oshib ketmasligini ta'minlaydi

    @average_rating.expression
    def average_rating(cls):
        calculated_avg = case(
            (cls.rating_count == 0, 0.0),
            else_=cast(cls.rating_sum, Float) / cls.rating_count
        )
        # SQL darajasida ham 10.0 dan oshmasligini kafolatlaymiz
        return case(
            (calculated_avg > 10.0, 10.0),
            else_=calculated_avg
        )

    # 🔒 BAZA DARAJASIDA XAVFSIZLIK:
    # Kimdir tasodifan xato kod yozib, reytingni buzib yubormasligi uchun cheklov
    __table_args__ = (
        CheckConstraint('rating_count >= 0', name='check_rating_count_positive'),
    )

#========================================================================#
class Episode(Base):
    __tablename__ = "anime_episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    anime_id: Mapped[int] = mapped_column(
        ForeignKey("anime_list.anime_id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )

    episode: Mapped[int] = mapped_column(
        Integer,
        index=True,
        nullable=False
    )

    file_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    anime: Mapped["Anime"] = relationship(
        back_populates="episodes",
        lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("anime_id", "episode"),
    )

#========================================================================#
class Comment(Base):
    __tablename__ = "anime_comments"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    # Izoh qaysi animega tegishli ekanligi
    anime_id: Mapped[int] = mapped_column(
        ForeignKey("anime_list.anime_id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )

    # Izohni qaysi foydalanuvchi yozgani
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )

    # Izoh matni
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    # 🌟 PRO REPLIES TIZIMI (Self-referencing Foreign Key)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("anime_comments.id", ondelete="CASCADE"),
        index=True,
        nullable=True
    )

    # Izoh yozilgan vaqt
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )

    # Munosabatlar (Relationships)
    anime: Mapped["Anime"] = relationship(
        back_populates="comments",
        lazy="selectin"
    )

    # 🟢 1. Bitta izohga yozilgan barcha javoblar (One-to-Many)
    # Bu yerda remote_side BO'LMAYDI! Cascade aynan shu yerda qoladi.
    replies: Mapped[list["Comment"]] = relationship(
        "Comment",
        back_populates="parent",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin"
    )

    # 🟢 2. Ushbu javobning ota izohi (Many-to-One)
    # 🎯 remote_side FAQAT SHU YERDA bo'lishi shart! (id ustuniga ishora qiladi)
    parent: Mapped[Optional["Comment"]] = relationship(
        "Comment",
        back_populates="replies",
        remote_side=[id],
        lazy="selectin"
    )
#========================================================================#
class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True
    )

    channel_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    __table_args__ = (
        Index("idx_channel_active", is_active),  # <-- Tuzatildi: string olib tashlandi
    )




#========================================================================#
class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    aggregate: Mapped[str] = mapped_column(String(255), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(255), index=True)
    event_type: Mapped[str] = mapped_column(String(255), index=True)

    payload: Mapped[dict] = mapped_column(
        JSONB,
        default=lambda: {},  # <-- Tuzatildi: lambda qo'shildi
        server_default=text("'{}'::jsonb")
    )

    event_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    __table_args__ = (
        Index("idx_outbox_processing", processed, priority, created_at),
    )

#========================================================================#
MODELS_TO_WATCH = {
    "DBUser",
    "Anime",
    "Episode",
    "Genre",
    "Channel",
    "Dubber",
    "Comment",
}

WATCHED_EVENTS = (
    "after_insert", "after_update", "after_delete",
)

#========================================================================#
def create_outbox_event(mapper, connection, target):
    model_name = target.__class__.__name__

    if hasattr(target, "user_id"):
        aggregate_id = target.user_id
    elif hasattr(target, "anime_id"):
        aggregate_id = target.anime_id
    else:
        aggregate_id = getattr(target, "id", "unknown")

    payload = {}
    if hasattr(target, "to_dict"):
        payload = target.to_dict()

    event_data = {
        "aggregate": model_name,
        "aggregate_id": str(aggregate_id) if aggregate_id is not None else None,
        "event_type": f"{model_name.lower()}_changed",
        "payload": payload,
    }

    connection.execute(
        OutboxEvent.__table__.insert().values(**event_data)
    )

#========================================================================#
def setup_outbox_listeners(models: list):
    for model in models:
        if model.__name__ in MODELS_TO_WATCH:
            for event_type in WATCHED_EVENTS:
                sqla_event.listen(model, event_type, create_outbox_event)