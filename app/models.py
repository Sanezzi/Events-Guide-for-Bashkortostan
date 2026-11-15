from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

Category = Literal['концерт', 'спектакль', 'выставка', 'фестиваль', 'кино', 'экскурсия', 'другое']
Status = Literal['опубликовано', 'черновик', 'отменено']
SourceType = Literal['ручной ввод', 'импорт', 'RSS', 'API', 'страница']


class EventCard(BaseModel):
    id: UUID
    title: str = Field(min_length=1, max_length=300)
    normalized_title: str = ''
    category: Category
    tags: list[str] = Field(default_factory=list, max_length=40)
    date_start: datetime
    date_end: Optional[datetime] = None
    duration_min: Optional[int] = None
    city: str = Field(min_length=1, max_length=300)
    venue: str = Field(min_length=1, max_length=300)
    address: str = Field(min_length=1, max_length=1000)
    lat: Optional[float] = None
    lon: Optional[float] = None
    description: str = Field(min_length=1, max_length=12000)
    price_min: float = Field(ge=0)
    price_max: float = Field(ge=0)
    is_free: bool
    age_limit: int = 0
    language: Optional[str] = None
    org_link: Optional[str] = None
    source_url: str = Field(min_length=1, max_length=2048)
    source_type: SourceType = 'ручной ввод'
    source_hash: Optional[str] = None
    sources: list[str] = Field(default_factory=list)
    verified_at: Optional[datetime] = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    status: Status = 'опубликовано'
    dedup_key: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    source: Optional[str] = None
    source_event_id: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    price_known: bool = True


class Message(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=12000)


class AgentRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=12000)
    history: list[Message] = Field(default_factory=list, max_length=40)
    confirm_action: bool = False


class ToolCallTrace(BaseModel):
    name: str = 'unknown'
    args: dict[str, Any] = Field(default_factory=dict)
    result_ids: list[UUID] = Field(default_factory=list)
    duration_ms: float = 0.0
    error: Optional[str] = None


class AgentTrace(BaseModel):
    request: dict[str, Any] = Field(default_factory=dict)
    plan: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    event_ids: list[UUID] = Field(default_factory=list)
    latency_ms: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    cost_estimated: bool = True
    fallback_reason: Optional[str] = None


class AgentResponse(BaseModel):
    reply_text: str = Field(min_length=1, max_length=12000)
    events: list[EventCard] = Field(default_factory=list, max_length=5)
    clarifying_question: Optional[str] = None
    requires_confirmation: Optional[dict[str, Any]] = None
    is_fallback: bool = False
    trace: AgentTrace = Field(default_factory=AgentTrace)


class ChatInput(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=12000)
    confirm_action: bool = False


class ChatResponse(BaseModel):
    reply_text: str
    events: list[EventCard] = Field(default_factory=list, max_length=5)
    clarifying_question: Optional[str] = None
    requires_confirmation: Optional[dict[str, Any]] = None
    is_fallback: bool = False


class SearchEventsArgs(BaseModel):
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    city: Optional[str] = None
    venue: Optional[str] = None
    category: Optional[Category] = None
    price_max: Optional[float] = Field(default=None, ge=0)
    is_free: Optional[bool] = None
    age_limit: Optional[int] = Field(default=None, ge=0, le=120)
    duration_max: Optional[int] = Field(default=None, gt=0, le=10080)
    text: Optional[str] = Field(default=None, max_length=2000)


class SearchResult(BaseModel):
    events: list[EventCard] = Field(default_factory=list, max_length=100)
    total: int = 0
    limit: int = 20
    offset: int = 0
    explanation: Optional[str] = None


class SubscribeInput(BaseModel):
    city: str = Field(min_length=1, max_length=150)
    category: Optional[Category] = None
    period: Literal['daily', 'weekly', 'monthly'] = 'weekly'


class FeedbackInput(BaseModel):
    event_id: UUID
    text: str = Field(min_length=1, max_length=4000)
    website: str = Field(default="", max_length=250)


class ActionResult(BaseModel):
    id: UUID
    success: bool
    message: str


class ApiError(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None
