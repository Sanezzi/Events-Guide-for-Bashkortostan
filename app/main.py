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


def limited(request, group, limit):
    buckets = request.app.state.limits
    key = group, request.client.host if request.client else ""
    hits = buckets.setdefault(key, deque())
    buckets.move_to_end(key)
    if len(buckets) > 4096:
        buckets.popitem(last=False)
    now = time.monotonic()
    while hits and hits[0] <= now - 60:
        hits.popleft()
    if len(hits) >= limit:
        return True
    hits.append(now)
    return False


@app.middleware("http")
async def observe(request, call_next):
    identifier, start = uuid4().hex, time.monotonic()
    request.state.request_id = identifier
    path = request.url.path
    public_read = request.method == "GET" and path.startswith("/api/v1/") and not path.startswith("/api/v1/admin")
    try:
        if path in {"/api/v1/feedback", "/api/v1/event-submissions"} and request.method == "POST" and limited(request, "feedback", 6):
            response = error(429, "RATE_LIMITED", "Попробуйте через минуту.", headers={"Retry-After": "60"})
        elif path in {"/api/chat", "/api/v1/subscriptions", "/agent/message"} and limited(request, "chat", 60):
            response = error(429, "RATE_LIMITED", "Попробуйте через минуту.", headers={"Retry-After": "60"})
        elif public_read and limited(request, "read", 180):
            response = error(429, "RATE_LIMITED", "Попробуйте через минуту.", headers={"Retry-After": "60"})
        else:
            response = await call_next(request)
    except Exception as exc:
        LOG.error("request_failed request_id=%s error_type=%s", identifier, type(exc).__name__)
        response = error(500, "INTERNAL_ERROR", "Сервис временно недоступен.")
    response.headers["X-Request-Id"] = identifier
    if public_read and response.status_code == 200 and not path.startswith("/api/v1/subscriptions"):
        response.headers.setdefault("Cache-Control", "public, max-age=30")
    if path.startswith(("/admin", "/internal/", "/agent/", "/api/v1/admin", "/api/chat", "/api/v1/subscriptions")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex"
    csp = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
           "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; object-src 'none'; base-uri 'self'")
    if path != "/widget":
        csp += "; frame-ancestors 'self'"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
    if path not in {"/docs", "/redoc"}:
        response.headers["Content-Security-Policy"] = csp
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    duration = (time.monotonic() - start) * 1000
    metrics = request.app.state.metrics
    metrics["requests"] += 1
    metrics["errors"] += response.status_code >= 400
    metrics["duration_ms_sum"] += duration
    for bound in metrics["latency_le_ms"]:
        metrics["latency_le_ms"][bound] += duration <= int(bound)
    route = request.scope.get("route")
    LOG.info("%s", json.dumps({"request_id": identifier, "route": getattr(route, "path", None),
                              "method": request.method, "status": response.status_code, "duration_ms": round(duration, 2)}))
    return response


@app.get("/health", tags=["service"])
async def health():
    try:
        result = await app.state.catalog.search(SearchFilters(page_size=1))
    except Exception as exc:
        LOG.warning("health_failed error_type=%s", type(exc).__name__)
        raise HTTPException(503, "База каталога временно недоступна") from exc
    return {"status": "ok", "version": app.version, "events_published": result.total}


@app.get("/metrics", tags=["service"])
def metrics():
    return app.state.metrics


@app.get("/api/v1/events/search", response_model=SearchResult, tags=["events"])
@app.get("/api/v1/events", response_model=SearchResult, tags=["events"])
async def list_events(
    city: str | None = Query(None, max_length=150),
    venue: str | None = Query(None, max_length=300),
    category: Category | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    price_max: float | None = Query(None, ge=0, allow_inf_nan=False),
    is_free: bool | None = None,
    age_limit: int | None = Query(None, ge=0, le=120),
    duration_max: int | None = Query(None, gt=0, le=10080),
    text: str | None = Query(None, max_length=2000),
    sort: Literal["date_start", "price_min", "price_max", "price_max_desc", "title"] = "date_start",
    period: Literal["today", "tomorrow", "weekend", "week"] | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    if date_from and date_to and aware(date_from) > aware(date_to):
        raise HTTPException(422, "Начало периода позже окончания")
    args = SearchEventsArgs(city=city, venue=venue, category=category, date_from=aware(date_from) if date_from else None,
                           date_to=aware(date_to) if date_to else None, price_max=price_max, is_free=is_free,
                           age_limit=age_limit, duration_max=duration_max, text=text)
    cards, total, reason = await app.state.catalog.filtered(args, page_size=limit, offset=offset, sort=sort, period=period)
    return SearchResult(events=cards, total=total, limit=limit, offset=offset, explanation=reason)


@app.get("/api/v1/events/changes", tags=["events"])
async def event_changes(since: datetime | None = None, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    rows = [e for e in await app.state.catalog.events() if e.updated_at and (since is None or e.updated_at > aware(since))]
    changes = [{"id": e.id, "type": {"отменено": "cancelled", "черновик": "removed"}.get(e.status, "updated"),
                "changed_at": e.updated_at, **({"event": e} if e.status != "черновик" else {})}
               for e in sorted(rows, key=lambda e: (e.updated_at, e.id))]
    return {"changes": changes[offset:offset + limit], "total": len(changes), "limit": limit, "offset": offset}


async def public_event(event_id):
    card = await app.state.catalog.event(event_id)
    if card is None:
        raise HTTPException(404, "Событие не найдено")
    return card


@app.get("/api/v1/events/{event_id}", response_model=EventCard, tags=["events"])
async def get_event(event_id: UUID):
    return await public_event(event_id)


@app.get("/api/v1/events/{event_id}/similar", response_model=list[EventCard], tags=["events"])
async def similar_events(event_id: UUID, city: str | None = Query(None, max_length=150)):
    card = await public_event(event_id)
    rows, _, _ = await app.state.catalog.filtered(SearchEventsArgs(city=city or card.city, category=card.category), page_size=6)
    return [row for row in rows if row.id != event_id][:5]


@app.get("/api/v1/cities", tags=["events"])
@app.get("/api/v1/categories", tags=["events"])
async def dictionary(request: Request):
    name = request.url.path.rsplit("/", 1)[-1]
    field = {"cities": "city", "categories": "category"}[name]
    rows = await app.state.catalog.events(status="опубликовано")
    return JSONResponse({name: sorted({getattr(row, field) for row in rows})},
                        headers={"Cache-Control": "public, max-age=300"})


@app.get("/api/v1/venues", tags=["events"])
async def venues(city: str | None = Query(None, max_length=150)):
    async with app.state.database.sessions() as session:
        values = await SqlCatalogRepository(session).venues(city)
    return JSONResponse({"venues": values}, headers={"Cache-Control": "public, max-age=30"})


@app.get("/api/v1/venue-schedule", response_model=list[EventCard], tags=["events"])
async def venue_schedule(venue: str = Query(..., min_length=1, max_length=300), date_from: datetime | None = None, date_to: datetime | None = None):
    rows, _, _ = await app.state.catalog.filtered(SearchEventsArgs(
        venue=venue, date_from=aware(date_from) if date_from else None,
        date_to=aware(date_to) if date_to else None,
    ), page_size=100)
    return rows
