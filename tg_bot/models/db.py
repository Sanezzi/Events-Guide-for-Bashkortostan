"""Portable SQLAlchemy 2 asynchronous persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, synonym
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("datetime must include timezone")
        value = value.astimezone(timezone.utc)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        return (
            value.replace(tzinfo=timezone.utc)
            if value is not None and value.tzinfo is None
            else value
        )


class Base(DeclarativeBase):
    """Shared metadata for bot and website migrations."""


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("price_min >= 0 AND price_max >= price_min", name="valid_prices"),
        CheckConstraint("age_limit IN (0,6,12,16,18)", name="valid_age"),
        CheckConstraint(
            "category IN ('концерт','спектакль','выставка','фестиваль','кино','экскурсия','другое')",
            name="valid_category",
        ),
        CheckConstraint(
            "source_type IN ('manual','import','rss','api','page','demo')", name="valid_source_type"
        ),
        CheckConstraint("lat IS NULL OR (lat >= -90 AND lat <= 90)", name="valid_latitude"),
        CheckConstraint("lon IS NULL OR (lon >= -180 AND lon <= 180)", name="valid_longitude"),
        CheckConstraint("duration_min IS NULL OR duration_min > 0", name="valid_duration"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="valid_confidence"),
        CheckConstraint(
            "language IS NULL OR language IN ('ru','ba','en','ru/ba')", name="valid_event_language"
        ),
        CheckConstraint("status IN ('опубликовано','черновик','отменено')", name="valid_status"),
        CheckConstraint("date_end IS NULL OR date_end >= date_start", name="valid_dates"),
        CheckConstraint("NOT is_free OR (price_min = 0 AND price_max = 0)", name="valid_free"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(300))
    normalized_title: Mapped[str] = mapped_column(String(300), index=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    date_start: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    date_end: Mapped[datetime | None] = mapped_column(UTCDateTime())
    duration_min: Mapped[int | None] = mapped_column(Integer)
    city: Mapped[str] = mapped_column(String(150), index=True)
    venue: Mapped[str] = mapped_column(String(300))
    address: Mapped[str] = mapped_column(String(500))
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lon: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    description: Mapped[str] = mapped_column(Text)
    price_min: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    price_max: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    is_free: Mapped[bool] = mapped_column(Boolean, default=False)
    age_limit: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str | None] = mapped_column(String(30))
    org_link: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(30), default="import")
    source_hash: Mapped[str] = mapped_column(String(64), unique=True)
    sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=1)
    status: Mapped[str] = mapped_column(String(20), default="черновик", index=True)
    dedup_key: Mapped[str] = mapped_column(String(64), unique=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("tg_user_id", "filter_key", name="unique_subscription"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tg_user_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id = synonym("tg_user_id")
    city: Mapped[str | None] = mapped_column(String(150))
    category: Mapped[str | None] = mapped_column(String(30))
    filter_key: Mapped[str] = mapped_column(String(64))
    period: Mapped[str] = mapped_column(String(10), default="weekly")
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class UserSettings(Base):
    __tablename__ = "user_settings"
    __table_args__ = (CheckConstraint("lang IN ('ru','ba','en')", name="valid_ui_language"),)
    tg_user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id = synonym("tg_user_id")
    lang: Mapped[str] = mapped_column(String(5), default="ru")


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(128))
    event_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class StoredTrace(Base):
    __tablename__ = "agent_traces"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    session_ref: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(128))


class RawImport(Base):
    __tablename__ = "raw_imports"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    source_hash: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(64))  # irreversible actor digest; never raw identity
    event_id: Mapped[UUID | None] = mapped_column(Uuid)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Database:
    def __init__(self, url: str):
        if url.startswith("sqlite://"):
            url = url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        elif url.startswith(("postgres://", "postgresql://")):
            url = "postgresql+asyncpg://" + url.split("://", 1)[1]
        self.engine = create_async_engine(url, pool_pre_ping=True)
        if self.engine.dialect.name == "sqlite":

            @event.listens_for(self.engine.sync_engine, "connect")
            def configure_sqlite(connection, _):
                from tg_bot.models.schemas import normalize

                connection.create_function("catalog_normalize", 1, normalize, deterministic=True)
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.close()

        self.sessions = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def create_tables(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()
