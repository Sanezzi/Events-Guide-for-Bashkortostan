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
