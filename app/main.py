from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import time
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text as sql_text
from starlette.exceptions import HTTPException as StarletteHTTPException

from ai_agent.agent import CultureAgentService
from ai_agent.config import AgentSettings
from ai_agent.schemas import AgentRequest
from tg_bot.models import Database
from tg_bot.models.schemas import EventInput, SearchFilters
from tg_bot.repositories import SqlCatalogRepository

from . import discovery
from .admin_api import router as admin_router
from .bootstrap import seed_confirmed
from .bot_api import router as bot_router
from .catalog import AgentCatalog, Catalog, DatabaseTraceSink, subscription_uuid
from .db_config import database_url
from .dates import aware
from .identity import Dialogues, bot_identity, chat_result, require_bot, session_secret, web_identity
from .models import ActionResult, Category, ChatResponse, EventCard, FeedbackInput, SearchEventsArgs, SearchResult, SubscribeInput

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
PORTAL = FRONTEND / "portal" / "index.html"
LOG = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app):
    database = Database(database_url())
    async with database.engine.connect() as conn:
        await conn.execute(sql_text("SELECT 1"))
    catalog = Catalog(database)
    app.state.database = database
    app.state.catalog = catalog
    app.state.limits = OrderedDict()
    app.state.metrics = {"requests": 0, "errors": 0, "duration_ms_sum": 0.0,
                         "latency_le_ms": {str(n): 0 for n in (50, 100, 250, 500, 1500, 6000, 8000)}}
    agent = CultureAgentService(AgentCatalog(catalog), AgentSettings.from_env(), trace_sink=DatabaseTraceSink(database))
    app.state.dialogues = Dialogues(agent)
    app.state.agent = agent
    try:
        if os.environ.get("AFISHA_CREATE_TABLES") == "1" or (
            database.engine.dialect.name == "sqlite" and os.environ.get("AFISHA_CREATE_TABLES") != "0"
        ):
            await database.create_tables()
        app.state.session_secret = await session_secret(database)
        if os.environ.get("SEED_CONFIRMED_EVENTS", "1") == "1":
            await seed_confirmed(catalog)
        yield
    finally:
        await agent.aclose()
        await database.close()


app = FastAPI(title="Афиша культуры Башкортостана", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware,
                   allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
                   allow_methods=["GET"], allow_headers=["Accept"])
app.include_router(admin_router)
app.include_router(bot_router)
app.include_router(discovery.router)


def error(status, code, message, details=None, headers=None):
    return JSONResponse({"code": code, "message": message, "details": details}, status_code=status, headers=headers)


@app.exception_handler(StarletteHTTPException)
async def http_error(request, exc):
    if isinstance(exc.detail, dict):
        return JSONResponse(exc.detail, status_code=exc.status_code, headers=exc.headers)
    return error(exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail), headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    details = [{"field": ".".join(map(str, item["loc"])), "type": item["type"]} for item in exc.errors()]
    return error(422, "INVALID_REQUEST", "Проверьте параметры запроса.", details)
