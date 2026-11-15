from pathlib import Path

from sqlalchemy import select

from tg_bot.models.db import AuditLog
from tg_bot.models.schemas import digest

STARTER_EVENTS = Path(__file__).resolve().parents[1] / "contour" / "data" / "starter_events.json"
ACTOR = "starter-catalog-v1"


async def seed_confirmed(catalog):
    async with catalog.database.sessions() as session:
        imported = await session.scalar(select(AuditLog.id).where(
            AuditLog.actor == digest(ACTOR), AuditLog.action == "seed_complete"
        ).limit(1))
        if imported is not None:
            return

    report = await catalog.import_file(STARTER_EVENTS.read_bytes(), STARTER_EVENTS.name, ACTOR,
                                       preserve_reviewed=True)
    if report.rejected:
        raise RuntimeError(f"Starter catalog import rejected rows: {report.errors}")

    async with catalog.database.sessions() as session:
        session.add(AuditLog(action="seed_complete", actor=digest(ACTOR), details=report.model_dump()))
        await session.commit()
