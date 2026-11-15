from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from tg_bot.models.db import Event, Subscription
from tg_bot.models.schemas import AgentReply, Category, ImportReport, SearchFilters, SearchResult
from tg_bot.repositories import SqlCatalogRepository
from tg_bot.services import ImporterService

from .identity import bot_identity, require_bot


router = APIRouter(prefix="/internal/bot", dependencies=[Depends(require_bot)], include_in_schema=False)


class BotUser(BaseModel):
    user_id: str = Field(pattern=r"^[0-9]{1,20}$")


class Language(BotUser):
    lang: Literal["ru", "ba", "en"]


class Subscribe(BotUser):
    city: str | None = Field(default=None, max_length=150)
    category: Category | None = None


class Unsubscribe(BotUser):
    subscription_id: int | None = None


class Ask(BotUser):
    session_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=12000)
    confirmation_version: str | None = Field(default=None, max_length=128)


class Delivered(BotUser):
    subscription_id: int
    through: datetime


@router.post("/search", response_model=SearchResult)
async def search(request: Request, filters: SearchFilters):
    return await request.app.state.catalog.search(filters.model_copy(update={"full_price": True}))


@router.get("/events/{event_id}")
async def event(request: Request, event_id: UUID):
    async with request.app.state.database.sessions() as session:
        result = await SqlCatalogRepository(session).get_event(event_id)
        if result is not None and result.is_demo:
            return None
        return result


@router.post("/language")
async def get_language(request: Request, body: BotUser):
    async with request.app.state.database.sessions() as session:
        return await SqlCatalogRepository(session).get_lang(body.user_id)


@router.put("/language")
async def set_language(request: Request, body: Language):
    async with request.app.state.database.sessions() as session:
        await SqlCatalogRepository(session).set_lang(body.user_id, body.lang)
    return {"ok": True}
