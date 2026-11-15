import hmac
import json
import os
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select

from tg_bot.models.db import AuditLog, Feedback, StoredTrace, Subscription
from tg_bot.models.schemas import EventInput
from tg_bot.services import ImporterService

from .catalog import SOURCE_CODES
from .discovery import safe_link
from .models import EventCard


def require_admin(request: Request):
    expected = os.environ.get("ADMIN_TOKEN", "")
    actual = request.headers.get("X-Admin-Token", "")
    if not expected or not hmac.compare_digest(actual.encode(), expected.encode()):
        raise HTTPException(401, "Нужен токен администратора")


router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class StatusUpdate(BaseModel):
    status: Literal["опубликовано", "черновик", "отменено"]


@router.get("/overview")
async def overview(request: Request):
    events = await request.app.state.catalog.events()
    async with request.app.state.database.sessions() as session:
        subs = await session.scalar(select(func.count()).select_from(Subscription))
        feedback = await session.scalar(select(func.count()).select_from(Feedback))
    return {
        "events_total": len(events),
        "published": sum(e.status == "опубликовано" for e in events),
        "draft": sum(e.status == "черновик" for e in events),
        "cancelled": sum(e.status == "отменено" for e in events),
        "subscriptions": subs, "feedback": feedback,
    }


@router.get("/events", response_model=list[EventCard])
async def admin_events(request: Request, status: Literal["опубликовано", "черновик", "отменено"] | None = None):
    return await request.app.state.catalog.events(status=status)


@router.post("/import")
async def import_events(request: Request, file: UploadFile = File(...)):
    try:
        content = await file.read(ImporterService.MAX_BYTES + 1)
    finally:
        await file.close()
    if len(content) > ImporterService.MAX_BYTES:
        raise HTTPException(413, "Файл превышает 10 МиБ")
    return await request.app.state.catalog.import_file(content, file.filename or "", "web-admin")


async def save(request, event, *, existing=None):
    data = event.model_dump(mode="json", include=set(EventInput.model_fields))
    data["source_type"] = SOURCE_CODES[event.source_type]
    data.pop("source_hash", None)
    data.pop("dedup_key", None)
    if not safe_link(event.source_url) or (event.org_link and not safe_link(event.org_link)):
        raise HTTPException(422, "Укажите действительную ссылку HTTP или HTTPS")
    if existing:
        data["status"] = existing.status
    report = await request.app.state.catalog.import_file(
        json.dumps([data], ensure_ascii=False).encode(), "manual.json", "web-admin",
        merge_existing=existing is not None,
    )
    if report.rejected:
        raise HTTPException(422, {"code": "INVALID_EVENT", "message": "Проверьте поля карточки", "details": report.errors})
    return await request.app.state.catalog.record(event.id)


@router.post("/events", status_code=201, response_model=EventCard)
async def create_event(request: Request, body: EventCard):
    if await request.app.state.catalog.record(body.id):
        raise HTTPException(409, "Событие с таким идентификатором уже существует")
    row = await save(request, body)
    if row is None:
        raise HTTPException(409, "Импорт объединён с существующей карточкой")
    return row


@router.put("/events/{event_id}", response_model=EventCard)
async def edit_event(request: Request, event_id: UUID, body: EventCard):
    existing = await request.app.state.catalog.record(event_id)
    if existing is None:
        raise HTTPException(404, "Событие не найдено")
    return await save(request, body.model_copy(update={"id": event_id}), existing=existing)


@router.delete("/events/{event_id}")
async def hide_event(request: Request, event_id: UUID):
    row = await request.app.state.catalog.status(event_id, "отменено", "web-admin")
    if row is None:
        raise HTTPException(404, "Событие не найдено")
    return {"deleted": str(event_id), "status": row.status}


@router.patch("/events/{event_id}/status", response_model=EventCard)
async def set_status(request: Request, event_id: UUID, body: StatusUpdate):
    row = await request.app.state.catalog.status(event_id, body.status, "web-admin")
    if row is None:
        raise HTTPException(404, "Событие не найдено")
    return row


@router.get("/journal")
async def journal(request: Request):
    async with request.app.state.database.sessions() as session:
        rows = await session.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(100))
        return [{"action": row.action, "actor": row.actor, "event_id": row.event_id,
                 "details": row.details, "created_at": row.created_at} for row in rows]


@router.get("/subscriptions")
async def admin_subscriptions(request: Request):
    async with request.app.state.database.sessions() as session:
        rows = await session.scalars(select(Subscription).order_by(Subscription.id.desc()).limit(100))
        return [{"id": row.id, "city": row.city, "category": row.category, "period": row.period} for row in rows]


@router.get("/feedback")
async def admin_feedback(request: Request):
    async with request.app.state.database.sessions() as session:
        rows = await session.scalars(select(Feedback).order_by(Feedback.created_at.desc()).limit(100))
        return [{"id": row.id, "event_id": row.event_id, "text": row.text} for row in rows]
