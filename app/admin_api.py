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
