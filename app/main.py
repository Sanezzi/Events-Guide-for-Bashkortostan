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


@app.post("/api/v1/subscriptions", response_model=ActionResult, tags=["events"])
async def subscribe(body: SubscribeInput, request: Request, response: Response):
    owner = web_identity(request, response)
    if not body.city.strip():
        raise HTTPException(422, "Укажите город")
    row = await app.state.catalog.subscribe(owner, body.city, body.category, body.period)
    return ActionResult(id=subscription_uuid(row), success=True, message="Подписка сохранена.")


@app.get("/api/v1/subscriptions", tags=["events"])
async def subscriptions(request: Request, response: Response):
    owner = web_identity(request, response)
    return [{"id": subscription_uuid(row), "city": row.city, "category": row.category, "period": row.period}
            for row in await app.state.catalog.subscriptions(owner)]


@app.delete("/api/v1/subscriptions/{identifier}", tags=["events"])
async def unsubscribe(identifier: UUID, request: Request, response: Response):
    owner = web_identity(request, response)
    for row in await app.state.catalog.subscriptions(owner):
        if subscription_uuid(row) == identifier:
            await app.state.catalog.unsubscribe(owner, row.id)
            return {"message": "Подписка удалена."}
    raise HTTPException(404, "Подписка не найдена")


@app.post("/api/v1/feedback", response_model=ActionResult, tags=["events"])
async def feedback(body: FeedbackInput, request: Request, response: Response):
    if body.website:
        raise HTTPException(422, "Не удалось проверить форму")
    if not body.text.strip():
        raise HTTPException(422, "Введите текст обращения")
    identifier = await app.state.catalog.feedback(web_identity(request, response), body.event_id, body.text.strip())
    if not identifier:
        raise HTTPException(404, "Событие не найдено")
    return ActionResult(id=identifier, success=True, message="Обращение сохранено для модератора.")


class OrganizerEvent(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    category: Category
    date_start: datetime
    city: str = Field(min_length=1, max_length=150)
    venue: str = Field(min_length=1, max_length=300)
    address: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=4000)
    price_min: float = Field(ge=0, le=1000000)
    age_limit: Literal[0, 6, 12, 16, 18]
    source_url: str = Field(max_length=2048)

    @model_validator(mode="after")
    def check_proposal(self):
        if self.date_start.tzinfo is None or self.date_start <= datetime.now(timezone.utc):
            raise ValueError("Укажите предстоящую дату и часовой пояс")
        EventInput.model_validate({**self.model_dump(), "status": "черновик"})
        return self


class EventSubmission(BaseModel):
    event: OrganizerEvent
    website: str = Field(default="", max_length=250)


@app.post("/api/v1/event-submissions", response_model=ActionResult, status_code=201, tags=["events"])
async def submit_event(body: EventSubmission):
    if body.website:
        raise HTTPException(422, "Не удалось проверить форму")
    identifier = uuid4()
    data = {**body.event.model_dump(mode="json"), "id": str(identifier), "status": "черновик", "source_type": "manual"}
    report = await app.state.catalog.import_file(
        json.dumps([data], ensure_ascii=False).encode(), "proposal.json", "organizer-form", merge_existing=False
    )
    if report.added != 1:
        raise HTTPException(409, "Событие уже есть в каталоге или на проверке")
    return ActionResult(id=identifier, success=True, message="Событие отправлено на модерацию.")


class ChatInput(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=12000)
    confirm_action: bool = False
    confirmation_version: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_confirmation(self):
        if self.confirm_action and not self.confirmation_version:
            raise ValueError("confirmation version is required")
        return self


@app.post("/api/chat", response_model=ChatResponse, tags=["chat"])
async def chat(body: ChatInput, request: Request, response: Response):
    identity = web_identity(request, response)
    result = await app.state.dialogues.ask(identity, body.session_id, body.message,
                                           body.confirmation_version if body.confirm_action else None)
    return chat_result(result)


@app.post("/agent/message", include_in_schema=False, dependencies=[Depends(require_bot)])
async def agent_message(body: AgentRequest):
    if not body.user_id.isdecimal() or len(body.user_id) > 20 or len(body.session_id) > 80:
        raise HTTPException(422, "Некорректный идентификатор сессии")
    if body.confirm_action and not body.confirmation_version:
        raise HTTPException(422, "Требуется версия подтверждения")
    identity = bot_identity(body.user_id)
    reply = await app.state.dialogues.ask(identity, f"{identity}:{body.session_id}", body.message,
                                          body.confirmation_version if body.confirm_action else None)
    return chat_result(reply)


@app.get("/agent/health", tags=["service"])
def agent_health():
    return {"status": "ok", "mode": "llm" if app.state.agent.settings.api_key.strip() else "offline"}


@app.get("/widget", response_class=HTMLResponse)
def widget_page():
    return FileResponse(FRONTEND / "widget.html")


@app.get("/widget.js")
def widget_js():
    return FileResponse(FRONTEND / "widget.js", media_type="application/javascript")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    html = (PORTAL if PORTAL.is_file() else FRONTEND / "index.html").read_text(encoding="utf-8")
    meta = discovery.metadata(discovery.SITE_TITLE, discovery.DESCRIPTION, discovery.root_url(request) + "/",
                              noindex=bool(request.query_params))
    cards = ""
    if not request.query_params:
        rows, _, _ = await app.state.catalog.filtered(SearchEventsArgs())
        cards = discovery.catalog_html(rows)
    return HTMLResponse(html.replace("<!-- metadata -->", meta, 1).replace("<!-- catalog -->", cards, 1))


@app.get("/event", response_class=HTMLResponse)
async def event_page(request: Request, id: UUID | None = None):
    event = await public_event(id) if id else None
    html = (PORTAL if PORTAL.is_file() else FRONTEND / "event.html").read_text(encoding="utf-8")
    canonical = discovery.root_url(request) + (discovery.event_path(event) if event else "/event")
    title = f"{event.title} — {discovery.SITE_TITLE}" if event else discovery.SITE_TITLE
    meta = discovery.metadata(title, event.description[:160] if event else discovery.DESCRIPTION, canonical,
                              noindex=not event, structured=discovery.event_schema(event, canonical) if event else None)
    detail = discovery.detail_html(event) if event else "Выберите событие в каталоге."
    return HTMLResponse(html.replace("<!-- metadata -->", meta, 1).replace("<!-- event -->", detail, 1))


@app.get("/chat")
def chat_page():
    return FileResponse(PORTAL if PORTAL.is_file() else FRONTEND / "chat.html")


@app.get("/about")
def about_page():
    return FileResponse(PORTAL if PORTAL.is_file() else FRONTEND / "about.html")


@app.get("/admin")
def admin_page():
    return FileResponse(FRONTEND / "admin.html")


@app.get("/subscribe")
def subscribe_page():
    return FileResponse(PORTAL if PORTAL.is_file() else FRONTEND / "subscribe.html")


@app.get("/planner", include_in_schema=False)
@app.get("/organizers", include_in_schema=False)
def portal_page():
    if not PORTAL.is_file():
        raise HTTPException(404, "Соберите веб-интерфейс командой npm run build")
    return FileResponse(PORTAL)


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
