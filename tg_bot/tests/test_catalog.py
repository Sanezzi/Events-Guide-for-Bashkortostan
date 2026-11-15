"""Real SQLite integration tests for persistence, import and application fallback."""

import asyncio
import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from tg_bot.models import AuditLog, Database, Event, RawImport
from tg_bot.models.schemas import AgentReply, EventInput, SearchFilters
from tg_bot.repositories import SqlCatalogRepository
from tg_bot.services import BotService, ImporterService


def event_row(**overrides):
    row = dict(
        title="Тестовый концерт",
        category="концерт",
        date_start="2099-11-15T18:00:00+05:00",
        date_end="2099-11-15T19:30:00+05:00",
        city="Уфа",
        venue="Зал",
        address="Адрес 1",
        description="Концерт для семьи",
        price_min=100,
        price_max=500,
        age_limit=6,
        language="ba",
        source_url="https://example.invalid/event/1",
    )
    row.update(overrides)
    return row


@pytest_asyncio.fixture
async def database(tmp_path):
    db = Database("sqlite+aiosqlite:///" + str(tmp_path / "catalog.sqlite"))
    await db.create_tables()
    yield db
    await db.close()


async def load(session, rows):
    return await ImporterService(session).import_bytes(
        json.dumps(rows, ensure_ascii=False).encode(), "events.json"
    )


@pytest.mark.asyncio
async def test_import_idempotency_persistence_and_unicode_search(database):
    async with database.sessions() as session:
        report = await load(session, [event_row()])
        assert (report.added, report.rejected) == (1, 0)
        assert (await load(session, [event_row()])).unchanged == 1
    async with database.sessions() as session:
        result = await SqlCatalogRepository(session).search(
            SearchFilters(q="КОНЦЕРТ", city="уФА", language="ba", max_price=100, age=8)
        )
        assert result.total == 1
        assert result.items[0].date_start.utcoffset().total_seconds() == 0
        assert result.items[0].duration_min == 90
        assert result.items[0].sources == ["https://example.invalid/event/1"]
        assert await session.scalar(select(func.count()).select_from(Event)) == 1
        assert await session.scalar(select(func.count()).select_from(RawImport)) == 2


@pytest.mark.asyncio
async def test_row_isolation_rejection_and_audit_privacy(database):
    async with database.sessions() as session:
        invalid = event_row(title="bad", price_min=-1, user_email="private@example.invalid")
        report = await ImporterService(session).import_bytes(
            json.dumps(
                [
                    event_row(),
                    invalid,
                    event_row(title="Второй", source_url="https://example.invalid/2"),
                ]
            ).encode(),
            "rows.json",
            actor="private@example.invalid",
        )
        assert (report.added, report.rejected) == (2, 1)
        assert report.errors[0]["row"] == 2
        assert "private@" not in json.dumps(report.errors)
        assert await session.scalar(select(func.count()).select_from(Event)) == 2
        raw = list((await session.scalars(select(RawImport))).all())
        assert len(raw) == 3 and raw[1].status == "rejected"
        assert "user_email" not in raw[1].payload
        audits = list((await session.scalars(select(AuditLog))).all())
        assert len(audits) == 3
        assert all(len(a.actor) == 64 and "private@" not in json.dumps(a.details) for a in audits)


@pytest.mark.asyncio
async def test_dedup_merges_sources_and_stable_id(database):
    async with database.sessions() as session:
        await load(session, [event_row()])
        first = (await SqlCatalogRepository(session).search(SearchFilters())).items[0]
        update = event_row(
            title="ТЕСТОВЫЙ  КОНЦЕРТ!",
            source_url="https://example.invalid/second",
            description="Обновлённое описание",
        )
        report = await load(session, [update])
        assert report.updated == 1
        result = (await SqlCatalogRepository(session).search(SearchFilters())).items[0]
        assert result.id == first.id
        assert len(result.sources) == 2
        assert result.description == "Обновлённое описание"
        assert (await load(session, [update])).unchanged == 1


@pytest.mark.asyncio
async def test_cancelled_and_drafts_visibility_pagination_and_stats(database):
    async with database.sessions() as session:
        rows = [
            event_row(title=str(i), status=status, price_min=0, price_max=0)
            for i, status in enumerate(["опубликовано", "опубликовано", "отменено", "черновик"])
        ]
        await load(session, rows)
        repo = SqlCatalogRepository(session)
        result = await repo.search(SearchFilters(page_size=1, page=2, is_free=True))
        assert result.total == 2 and len(result.items) == 1
        all_rows = list((await session.scalars(select(Event))).all())
        cancelled = next(row for row in all_rows if row.status == "отменено")
        draft = next(row for row in all_rows if row.status == "черновик")
        assert (await repo.get_event(cancelled.id)).status == "отменено"
        assert await repo.get_event(draft.id) is None
        assert await repo.get_event(uuid4()) is None
        assert await repo.stats() == {"total": 2, "free": 2, "cities": ["Уфа"]}
        assert (await repo.search(SearchFilters(age=5))).total == 0


@pytest.mark.asyncio
async def test_timezone_date_boundary(database):
    async with database.sessions() as session:
        await load(session, [event_row(date_start="2099-11-16T00:30:00+05:00", date_end=None)])
        repo = SqlCatalogRepository(session)
        assert (await repo.search(SearchFilters(date="2099-11-16"))).total == 1
        assert (await repo.search(SearchFilters(date="2099-11-15"))).total == 0


@pytest.mark.asyncio
async def test_subscription_dedup_ownership_and_language_persistence(database):
    async with database.sessions() as session:
        repo = SqlCatalogRepository(session)
        first = await repo.subscribe("1", "Уфа", "концерт")
        assert (await repo.subscribe("1", "УФА", "концерт")).id == first.id
        assert await repo.unsubscribe("2", first.id) == 0
        await repo.set_lang("1", "ba")
        assert await repo.get_lang("2") == "ru"
        with pytest.raises(ValueError):
            await repo.set_lang("1", "xx")
    async with database.sessions() as session:
        repo = SqlCatalogRepository(session)
        assert await repo.get_lang("1") == "ba"
        assert len(await repo.list_subscriptions("1")) == 1
        assert await repo.unsubscribe("1") == 1
        assert await repo.list_subscriptions("1") == []
