"""Catalog operations shared by the bot, agent and web application."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Protocol, runtime_checkable
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import String, cast, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tg_bot.config import get_settings
from tg_bot.models import Event, Subscription, UserSettings
from tg_bot.models.schemas import EventOut, SearchFilters, SearchResult, digest, normalize


@runtime_checkable
class CatalogRepositoryProtocol(Protocol):
    async def search(self, filters: SearchFilters) -> SearchResult: ...
    async def get_event(self, event_id: UUID) -> EventOut | None: ...
    async def stats(self, filters: SearchFilters | None = None) -> dict: ...
    async def get_lang(self, user_id: str) -> str: ...
    async def set_lang(self, user_id: str, lang: str) -> None: ...
    async def subscribe(
        self, user_id: str, city: str | None = None, category: str | None = None
    ) -> Subscription: ...
    async def list_subscriptions(self, user_id: str) -> list[Subscription]: ...
    async def unsubscribe(self, user_id: str, subscription_id: int | None = None) -> int: ...


class SqlCatalogRepository:
    def __init__(self, session: AsyncSession, timezone_name: str | None = None):
        self.session = session
        self.timezone = ZoneInfo(timezone_name or get_settings().timezone)

    def _query(self, filters: SearchFilters):
        stmt = select(Event).where(Event.status == "опубликовано")
        if not filters.include_demo:
            stmt = stmt.where(Event.is_demo.is_(False))
        now = datetime.now(self.timezone)
        start = end = None
        if filters.date is not None:
            start = filters.date
            end = start + timedelta(days=1)
        elif filters.period:
            start = now.date()
            if filters.period == "tomorrow":
                start += timedelta(days=1)
            elif filters.period == "weekend":
                start += timedelta(days=(5 - start.weekday()) % 7 if start.weekday() < 5 else 0)
            end = start + timedelta(
                days=7
                if filters.period == "week"
                else (7 - start.weekday() if filters.period == "weekend" else 1)
            )
        if start is not None:
            lower = datetime.combine(start, time.min, self.timezone)
            upper = datetime.combine(end, time.min, self.timezone)
            stmt = stmt.where(
                func.coalesce(Event.date_end, Event.date_start) >= lower, Event.date_start < upper
            )
        else:
            stmt = stmt.where(func.coalesce(Event.date_end, Event.date_start) >= now)
        if filters.category:
            stmt = stmt.where(Event.category == filters.category)
        if filters.max_price is not None:
            price = Event.price_max if filters.full_price else Event.price_min
            stmt = stmt.where(price <= filters.max_price)
        if filters.is_free is not None:
            stmt = stmt.where(Event.is_free == filters.is_free)
        if filters.language:
            stmt = stmt.where(
                Event.language.in_([filters.language, "ru/ba"])
                if filters.language in {"ru", "ba"}
                else Event.language == filters.language
            )
        if filters.age is not None:
            stmt = stmt.where(Event.age_limit <= filters.age)
        if filters.city:
            stmt = stmt.where(self._normalized(Event.city) == normalize(filters.city))
        if filters.venue:
            stmt = stmt.where(self._normalized(Event.venue) == normalize(filters.venue))
        if filters.date_from is not None:
            stmt = stmt.where(Event.date_start >= filters.date_from)
        if filters.date_to is not None:
            stmt = stmt.where(Event.date_start <= filters.date_to)
        if filters.duration_max is not None:
            stmt = stmt.where(Event.duration_min <= filters.duration_max)
        if filters.q:
            searchable = (
                Event.title
                + " "
                + Event.description
                + " "
                + Event.city
                + " "
                + Event.venue
                + " "
                + Event.category
                + " "
                + cast(Event.tags, String)
            )
            expression = self._normalized(searchable)
            for term in normalize(filters.q).split():
                stmt = stmt.where(expression.contains(term, autoescape=True))
        sort_column = {
            "date_start": Event.date_start,
            "price_min": Event.price_min,
            "price_max": Event.price_max,
            "price_max_desc": Event.price_max.desc(),
            "title": Event.normalized_title,
        }[filters.sort]
        return stmt.order_by(sort_column, Event.date_start, Event.id)

    def _normalized(self, expression):
        if self.session.bind.dialect.name == "sqlite":
            return func.catalog_normalize(expression)
        unicode_text = expression.collate("pg_unicode_fast")
        lowered = func.replace(func.lower(unicode_text), "ё", "е")
        punctuation = func.regexp_replace(lowered, r"[^\w\s]", " ", "g")
        return func.trim(func.regexp_replace(punctuation, r"\s+", " ", "g"))

    async def _count(self, filters: SearchFilters) -> int:
        query = self._query(filters).order_by(None).subquery()
        return int(await self.session.scalar(select(func.count()).select_from(query)) or 0)

    async def venues(self, city: str | None = None) -> list[str]:
        query = self._query(SearchFilters(city=city, include_demo=False))
        venues = query.with_only_columns(Event.venue).order_by(None).order_by(Event.venue).distinct()
        return list(await self.session.scalars(venues))

    async def search(self, filters: SearchFilters) -> SearchResult:
        total = await self._count(filters)
        stmt = (
            self._query(filters)
            .offset(filters.offset if filters.offset is not None else (filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        rows = (await self.session.scalars(stmt)).all()
        explanation = None
        if not total:
            for field in (
                "q",
                "city",
                "category",
                "date",
                "period",
                "max_price",
                "is_free",
                "language",
                "age",
                "venue",
                "date_from",
                "date_to",
                "duration_max",
            ):
                if getattr(filters, field) is not None:
                    if await self._count(filters.model_copy(update={field: None})):
                        explanation = field
                        break
            explanation = explanation or "combined"
        return SearchResult(
            items=[EventOut.model_validate(row) for row in rows],
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            explanation=explanation,
        )

    async def get_event(self, event_id: UUID) -> EventOut | None:
        row = await self.session.get(Event, event_id)
        return (
            EventOut.model_validate(row) if row is not None and row.status != "черновик" else None
        )

    async def stats(self, filters: SearchFilters | None = None) -> dict:
        filters = filters or SearchFilters()
        subquery = self._query(filters).order_by(None).subquery()
        total = int(await self.session.scalar(select(func.count()).select_from(subquery)) or 0)
        free = int(
            await self.session.scalar(
                select(func.count()).select_from(subquery).where(subquery.c.is_free.is_(True))
            )
            or 0
        )
        cities = list(
            (
                await self.session.scalars(
                    select(subquery.c.city).distinct().order_by(subquery.c.city)
                )
            ).all()
        )
        return {"total": total, "free": free, "cities": cities}

    async def get_lang(self, user_id: str) -> str:
        row = await self.session.get(UserSettings, str(user_id))
        return row.lang if row else "ru"

    async def set_lang(self, user_id: str, lang: str) -> None:
        if lang not in {"ru", "ba", "en"}:
            raise ValueError("unsupported language")
        await self.session.merge(UserSettings(user_id=str(user_id), lang=lang))
        await self.session.commit()

    async def subscribe(
        self, user_id: str, city: str | None = None, category: str | None = None,
        period: str = "weekly",
    ) -> Subscription:
        filters = SearchFilters(city=city, category=category)
        key = digest([normalize(filters.city or ""), filters.category or "", period])
        stmt = select(Subscription).where(
            Subscription.user_id == str(user_id), Subscription.filter_key == key
        )
        existing = await self.session.scalar(stmt)
        if existing is not None:
            return existing
        subscription = Subscription(
            user_id=str(user_id),
            city=filters.city or None,
            category=filters.category,
            filter_key=key,
            period=period,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(subscription)
                await self.session.flush()
        except IntegrityError:
            existing = await self.session.scalar(stmt)
            if existing is None:
                raise
            await self.session.commit()
            return existing
        await self.session.commit()
        return subscription

    async def list_subscriptions(self, user_id: str) -> list[Subscription]:
        return list(
            (
                await self.session.scalars(
                    select(Subscription)
                    .where(Subscription.user_id == str(user_id))
                    .order_by(Subscription.id)
                )
            ).all()
        )

    async def unsubscribe(self, user_id: str, subscription_id: int | None = None) -> int:
        stmt = delete(Subscription).where(Subscription.user_id == str(user_id))
        if subscription_id is not None:
            stmt = stmt.where(Subscription.id == subscription_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount
