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


@pytest.mark.parametrize(
    "changes",
    [
        dict(date_start="2099-11-15T18:00:00"),
        dict(date_end="2099-11-15T17:00:00+05:00"),
        dict(price_max=50),
        dict(age_limit=7),
        dict(source_url="javascript:bad"),
        dict(is_free=True),
        dict(confidence=2),
        dict(lat=91),
        dict(duration_min=20),
    ],
)
def test_validation_rejects_inconsistent_fields(changes):
    with pytest.raises(ValidationError):
        EventInput.model_validate(event_row(**changes))


@pytest.mark.asyncio
async def test_csv_import_with_tags_and_row_rejection(database):
    stream = io.StringIO()
    rows = [event_row(tags="дети,музыка"), event_row(title="bad", price_min=-1, tags="[]")]
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    async with database.sessions() as session:
        report = await ImporterService(session).import_bytes(
            stream.getvalue().encode("utf-8-sig"), "events.csv"
        )
        assert (report.added, report.rejected) == (1, 1)
        assert {"дети", "музыка", "концерт", "6+"} <= set(
            (await SqlCatalogRepository(session).search(SearchFilters())).items[0].tags
        )
        assert (
            await ImporterService(session).import_bytes(stream.getvalue().encode(), "events.csv")
        ).unchanged == 1
        assert (await ImporterService(session).import_bytes(b"bad", "events.json")).errors[0][
            "code"
        ] == "invalid_file"


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_key", ["source_hash", "dedup_key"])
async def test_unique_source_hash_and_dedup_database_constraints(database, changed_key):
    values = EventInput.model_validate(event_row()).model_dump(exclude={"id"})
    async with database.sessions() as session:
        session.add(Event(**values))
        await session.commit()
        duplicate = dict(values)
        duplicate[changed_key] = "0" * 64
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(Event(**duplicate))
                await session.flush()
        assert await session.scalar(select(func.count()).select_from(Event)) == 1


@pytest.mark.asyncio
async def test_agent_timeout_errors_and_unknown_ids_fall_back(database):
    class Slow:
        async def ask(self, **kwargs):
            await asyncio.Event().wait()

    class Broken:
        async def ask(self, **kwargs):
            raise RuntimeError("bridge unavailable")

    class Unknown:
        async def ask(self, **kwargs):
            return AgentReply(text="bad", event_ids=[uuid4()])

    async with database.sessions() as session:
        repo = SqlCatalogRepository(session)
        await load(session, [event_row()])
        for agent in (None, Slow(), Broken(), Unknown()):
            service = BotService(repo, agent, timeout=0.01)
            assert await service.ask("1", "s", "концерт", []) is None
            assert (await service.search(SearchFilters())).total == 1

        class Good:
            async def ask(self, **kwargs):
                assert kwargs["history"] == ["1", "2", "3", "4", "5"]
                return AgentReply(text="Уточните город", clarification="Какой город?")

        assert (
            await BotService(repo, Good()).ask("1", "s", "x", ["1", "2", "3", "4", "5"])
        ).clarification == "Какой город?"


@pytest.mark.asyncio
async def test_reschedule_updates_stable_id_and_cancelled_state(database):
    event_id = str(uuid4())
    async with database.sessions() as session:
        assert (await load(session, [event_row(id=event_id)])).added == 1
        report = await load(
            session,
            [
                event_row(
                    id=event_id,
                    date_start="2099-11-17T18:00:00+05:00",
                    date_end="2099-11-17T19:30:00+05:00",
                    status="отменено",
                )
            ],
        )
        assert report.updated == 1
        repo = SqlCatalogRepository(session)
        from uuid import UUID

        record = await repo.get_event(UUID(event_id))
        assert record.status == "отменено"
        assert record.date_start.day == 17
        assert (await repo.search(SearchFilters())).total == 0
        assert await session.scalar(select(func.count()).select_from(Event)) == 1


@pytest.mark.asyncio
async def test_periods_and_past_exclusion(database, monkeypatch):
    import tg_bot.repositories.catalog_repo as catalog

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2099, 11, 14, 12, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(catalog, "datetime", FixedDatetime)
    async with database.sessions() as session:
        await load(
            session,
            [
                event_row(date_start="2099-11-14T18:00:00+05:00", date_end=None),
                event_row(title="Tomorrow", date_start="2099-11-15T18:00:00+05:00", date_end=None),
                event_row(title="Past", date_start="2099-11-13T18:00:00+05:00", date_end=None),
            ],
        )
        repo = SqlCatalogRepository(session)
        assert (await repo.search(SearchFilters(period="today"))).total == 1
        assert (await repo.search(SearchFilters(period="tomorrow"))).total == 1
        assert (await repo.search(SearchFilters(period="week"))).total == 2
        assert (await repo.search(SearchFilters())).total == 2


def test_postgres_schema_compiles():
    for table in Event.metadata.sorted_tables:
        assert "CREATE TABLE" in str(CreateTable(table).compile(dialect=postgresql.dialect()))


@pytest.mark.asyncio
async def test_sample_data_explicitly_fictional_and_importable(database):
    path = Path(__file__).parents[1] / "data" / "sample_events.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    assert len(rows) == 15
    assert sum(row["status"] == "отменено" for row in rows) == 1
    assert any(row["language"] == "ba" for row in rows)
    for row in rows:
        assert row["is_demo"] and "DEMO" in row["title"]
        assert "вымышленное" in row["description"]
        assert "example.invalid" in row["source_url"]
        assert datetime.fromisoformat(row["date_start"]) > datetime(
            2026, 11, 14, tzinfo=timezone.utc
        )
    async with database.sessions() as session:
        report = await ImporterService(session).import_bytes(path.read_bytes(), path.name)
        assert report.added == 15 and report.rejected == 0
        assert (
            await ImporterService(session).import_bytes(path.read_bytes(), path.name)
        ).unchanged == 15
