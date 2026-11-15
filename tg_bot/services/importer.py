"""Idempotent CSV/JSON import with independent row transactions and savepoints."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select, text as sql_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from contour.tags import event_tags
from tg_bot.models import AuditLog, Event, RawImport
from tg_bot.models.schemas import EventInput, ImportReport, digest


class ImporterService:
    MAX_BYTES = 10 * 1024 * 1024
    MAX_ROWS = 10000

    def __init__(self, session: AsyncSession):
        self.session = session

    async def import_bytes(
        self, data: bytes, filename: str, actor: str = "cli", *, merge_existing=True,
        preserve_reviewed=False,
    ) -> ImportReport:
        report = ImportReport()
        try:
            if len(data) > self.MAX_BYTES:
                raise ValueError("file exceeds 10 MiB")
            text = data.decode("utf-8-sig")
            extension = Path(filename).suffix.lower()
            if extension == ".json":
                rows = json.loads(text)
                if isinstance(rows, dict):
                    rows = rows.get("events")
                if not isinstance(rows, list):
                    raise ValueError("JSON must be an array or an object containing events")
            elif extension == ".csv":
                # Infer delimiter from the header: quoted multiline descriptions
                # and uneven content otherwise confuse Sniffer on valid CSV.
                dialect = csv.Sniffer().sniff(
                    text.splitlines()[0] if text.splitlines() else "", delimiters=",;\t"
                )
                rows = list(csv.DictReader(io.StringIO(text), dialect=dialect))
            else:
                raise ValueError("only .csv and .json files are supported")
            if len(rows) > self.MAX_ROWS:
                raise ValueError("file exceeds 10000 rows")
        except (ValueError, UnicodeError, csv.Error):
            report.rejected = 1
            report.errors.append(
                {
                    "row": 0,
                    "code": "invalid_file",
                    "message": "Invalid CSV/JSON file or exceeded import limits",
                }
            )
            return report
        batch_id = uuid4()
        actor_hash = digest(actor)
        for number, original in enumerate(rows, 1):
            row = original
            if isinstance(row, dict) and extension == ".csv":
                row = {key: value for key, value in row.items() if value not in ("", None)}
                if "age_limit" in row:
                    try:
                        row["age_limit"] = int(row["age_limit"])
                    except (TypeError, ValueError):
                        pass
                for key in ("tags", "sources"):
                    if key in row and isinstance(row[key], str) and row[key].startswith("["):
                        try:
                            row[key] = json.loads(row[key])
                        except ValueError:
                            pass
            source_hash = digest(row)
            # Restrict retained source payload to documented event fields. Unknown
            # user/account fields never enter raw storage, errors or audit records.
            payload = (
                {key: value for key, value in row.items() if key in EventInput.model_fields}
                if isinstance(row, dict)
                else {}
            )
            changes = {}
            outcome = "rejected"
            event_id = None
            error = None
            try:
                if self.session.bind.dialect.name == "postgresql":
                    await self.session.execute(sql_text("SELECT pg_advisory_xact_lock(8177632337211)"))
                async with self.session.begin_nested():
                    item = EventInput.model_validate(row)
                    source_hash = item.source_hash
                    existing = await self.session.scalar(
                        select(Event).where(Event.source_hash == item.source_hash)
                    )
                    if existing is not None:
                        if not merge_existing:
                            raise ValueError("event already exists")
                        outcome = "unchanged"
                        event_id = existing.id
                    else:
                        keyed = await self.session.scalar(
                            select(Event).where(Event.dedup_key == item.dedup_key).with_for_update()
                        )
                        identified = (
                            await self.session.get(Event, item.id, with_for_update=True)
                            if item.id is not None
                            else None
                        )
                        if keyed is not None and identified is not None and keyed.id != identified.id:
                            raise ValueError("event ID conflicts with another event's deduplication key")
                        existing = identified or keyed
                        if existing is not None and not merge_existing:
                            raise ValueError("event already exists")
                        values = item.model_dump(exclude={"id"})
                        values["tags"] = event_tags(item.title, item.description, item.category,
                                                    item.age_limit, item.is_free, item.tags)
                        if existing is not None and preserve_reviewed and existing.status != "черновик":
                            outcome = "unchanged"
                        elif existing is None:
                            existing = Event(id=item.id or uuid4(), **values)
                            self.session.add(existing)
                            outcome = "added"
                        else:
                            if (existing.status == "отменено" or
                                    existing.status == "черновик" and item.status == "опубликовано"):
                                values["status"] = existing.status
                            values["sources"] = list(
                                dict.fromkeys([*existing.sources, *item.sources])
                            )
                            for key, value in values.items():
                                before = getattr(existing, key)
                                if before != value:
                                    changes[key] = {
                                        "before": json.loads(json.dumps(before, default=str)),
                                        "after": json.loads(json.dumps(value, default=str)),
                                    }
                                setattr(existing, key, value)
                            outcome = "updated"
                        await self.session.flush()
                        event_id = existing.id
            except ValidationError as exc:
                # Exclude input and context: both may contain sensitive source data.
                error = "; ".join(
                    ".".join(map(str, entry["loc"])) + ": " + entry["type"]
                    for entry in exc.errors(
                        include_input=False, include_context=False, include_url=False
                    )
                )
            except IntegrityError:
                error = "database uniqueness or integrity constraint violated"
            except (ValueError, TypeError):
                error = "invalid event record"
            if error is not None:
                outcome = "rejected"
                report.errors.append({"row": number, "code": "invalid_row", "message": error})
            raw = RawImport(
                batch_id=batch_id,
                row_number=number,
                source_hash=source_hash,
                payload=payload,
                status=outcome,
                error=error,
            )
            self.session.add(raw)
            self.session.add(
                AuditLog(
                    action="import_" + outcome,
                    actor=actor_hash,
                    event_id=event_id,
                    details={
                        "batch_id": str(batch_id),
                        "row": number,
                        "source_hash": source_hash,
                        "changes": changes if error is None else {},
                    },
                )
            )
            await self.session.commit()
            setattr(report, outcome, getattr(report, outcome) + 1)
        return report
