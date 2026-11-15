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
