import json
from uuid import UUID, NAMESPACE_URL, uuid5

from sqlalchemy import func, select

from ai_agent import schemas as agent
from tg_bot.models.db import AuditLog, Event, Feedback, StoredTrace, Subscription
from tg_bot.models.schemas import EventOut, SearchFilters, digest
from tg_bot.repositories import SqlCatalogRepository
from tg_bot.services import ImporterService

from .models import EventCard, SearchEventsArgs

SOURCE_TYPES = {"manual": "ручной ввод", "import": "импорт", "page": "страница",
                "rss": "RSS", "api": "API", "demo": "импорт"}
SOURCE_CODES = {label: code for code, label in SOURCE_TYPES.items() if code != "demo"}


def public_card(event) -> EventCard:
    data = EventOut.model_validate(event).model_dump()
    data["source_type"] = SOURCE_TYPES[data["source_type"]]
    return EventCard.model_validate(data)


def agent_card(event: EventCard) -> agent.EventCard:
    fields = event.model_dump(mode="json", include=set(agent.EventCard.model_fields))
    fields["tags"] = [tag.strip()[:300] for tag in fields["tags"][:40] if tag.strip()]
    if fields["date_end"] == fields["date_start"]:
        fields["date_end"] = None
    return agent.EventCard.model_validate_json(json.dumps(fields))


class Catalog:
    def __init__(self, database):
        self.database = database

    async def search(self, filters: SearchFilters):
        async with self.database.sessions() as session:
            return await SqlCatalogRepository(session).search(filters.model_copy(update={"include_demo": False}))

    async def events(self, *, status=None):
        query = select(Event).order_by(Event.date_start, Event.id)
        if status is not None:
            query = query.where(Event.status == status)
        async with self.database.sessions() as session:
            return [public_card(row) for row in await session.scalars(query) if not row.is_demo]

    async def event(self, event_id: UUID):
        async with self.database.sessions() as session:
            row = await SqlCatalogRepository(session).get_event(event_id)
            return public_card(row) if row and not row.is_demo else None

    async def record(self, event_id: UUID):
        async with self.database.sessions() as session:
            row = await session.get(Event, event_id)
            return public_card(row) if row and not row.is_demo else None

    async def filtered(self, args: SearchEventsArgs, **kwargs):
        filters = SearchFilters(
            q=args.text, city=args.city, venue=args.venue, category=args.category,
            date_from=args.date_from, date_to=args.date_to, max_price=args.price_max,
            is_free=args.is_free, age=args.age_limit, duration_max=args.duration_max,
            full_price=True, **kwargs,
        )
        result = await self.search(filters)
        return [public_card(row) for row in result.items], result.total, result.explanation

    async def import_file(self, data: bytes, name: str, actor: str, *, merge_existing=True,
                          preserve_reviewed=False):
        async with self.database.sessions() as session:
            return await ImporterService(session).import_bytes(
                data, name, actor=actor, merge_existing=merge_existing, preserve_reviewed=preserve_reviewed
            )

    async def status(self, event_id: UUID, status: str, actor: str):
        async with self.database.sessions() as session:
            row = await session.get(Event, event_id, with_for_update=True)
            if row is None:
                return None
            if row.status != status:
                previous = row.status
                row.status = status
                session.add(AuditLog(
                    action="moderation", actor=digest(actor), event_id=row.id,
                    details={"status": {"before": previous, "after": status}},
                ))
                await session.flush()
                await session.refresh(row)
                await session.commit()
            return public_card(row)
