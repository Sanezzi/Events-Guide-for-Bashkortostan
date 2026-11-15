from __future__ import annotations

from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import (AwareDatetime, BaseModel, ConfigDict, Field,
                      StringConstraints, TypeAdapter, HttpUrl, field_validator,
                      model_validator)

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12000)]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Category = Literal["концерт", "спектакль", "выставка", "фестиваль", "кино", "экскурсия", "другое"]
EventStatus = Literal["опубликовано", "черновик", "отменено"]
SourceType = Literal["ручной ввод", "импорт", "RSS", "API", "страница"]
AgeRating = Literal[0, 6, 12, 16, 18]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class EventCard(StrictModel):
    id: UUID
    title: ShortText
    normalized_title: ShortText = Field(default_factory=lambda data: data["title"].casefold().strip())
    category: Category
    tags: list[ShortText] = Field(default_factory=list, max_length=40)
    date_start: AwareDatetime
    date_end: AwareDatetime | None = None
    duration_min: Annotated[int, Field(gt=0, le=10080)] | None = None
    city: ShortText
    venue: ShortText
    address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    lat: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)] | None = None
    lon: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)] | None = None
    description: LongText
    price_min: NonNegativeFloat
    price_max: NonNegativeFloat
    is_free: bool
    age_limit: AgeRating = 0
    language: ShortText | None = None
    org_link: Annotated[str, StringConstraints(min_length=1, max_length=2048)] | None = None
    source_url: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    source_type: SourceType = "ручной ввод"
    source_hash: ShortText | None = None
    verified_at: AwareDatetime | None = None
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 1.0
    status: EventStatus = "опубликовано"
    dedup_key: ShortText | None = None
    created_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None

    @field_validator("source_url", "org_link")
    @classmethod
    def http_links(cls, value: str | None) -> str | None:
        if value is not None:
            TypeAdapter(HttpUrl).validate_python(value)
        return value

    @field_validator("age_limit", mode="before")
    @classmethod
    def integer_age(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("age_limit must be an integer age rating")
        return value

    @model_validator(mode="after")
    def consistent_event(self) -> Self:
        if self.date_end is not None:
            seconds = (self.date_end - self.date_start).total_seconds()
            if seconds <= 0:
                raise ValueError("date_end must be later than date_start")
            if self.duration_min is not None and abs(seconds - self.duration_min * 60) > 0.001:
                raise ValueError("duration_min must match date_end - date_start")
        if self.price_max < self.price_min:
            raise ValueError("price_max must be at least price_min")
        if self.is_free != (self.price_min == 0 and self.price_max == 0):
            raise ValueError("is_free must agree with both prices being zero")
        return self


class Message(StrictModel):
    role: Literal["user", "assistant"]
    content: LongText


class AgentRequest(StrictModel):
    session_id: Identifier
    user_id: Identifier
    message: LongText
    history: list[Message] = Field(default_factory=list, max_length=40,
        description="Last at least five messages when available; fewer allowed for a new dialogue.")
    confirm_action: bool = False
    confirmation_version: Identifier | None = None


class ToolCallTrace(StrictModel):
    name: ShortText = "unknown"
    args: dict[str, Any] = Field(default_factory=dict)
    result_ids: list[UUID] = Field(default_factory=list)
    duration_ms: NonNegativeFloat = 0.0
    error: LongText | None = None


class AgentTrace(StrictModel):
    request: dict[str, Any] = Field(default_factory=dict)
    plan: list[ShortText] = Field(default_factory=list)
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    event_ids: list[UUID] = Field(default_factory=list)
    latency_ms: NonNegativeFloat = 0.0
    tokens_input: Annotated[int, Field(ge=0)] = 0
    tokens_output: Annotated[int, Field(ge=0)] = 0
    total_tokens: Annotated[int, Field(ge=0)] = 0
    cost_usd: NonNegativeFloat = 0.0
    cost_estimated: bool = True
    fallback_reason: ShortText | None = None


class AgentResponse(StrictModel):
    reply_text: LongText
    events: list[EventCard] = Field(default_factory=list, max_length=5)
    clarifying_question: LongText | None = None
    requires_confirmation: dict[str, Any] | None = None
    is_fallback: bool = False
    trace: AgentTrace = Field(default_factory=AgentTrace)


class DateRangeArgs(StrictModel):
    date_from: AwareDatetime | None = None
    date_to: AwareDatetime | None = None

    @model_validator(mode="after")
    def ordered_range(self) -> Self:
        if self.date_from is not None and self.date_to is not None and self.date_to < self.date_from:
            raise ValueError("date_to must be at least date_from")
        return self


class SearchEventsArgs(DateRangeArgs):
    city: ShortText | None = None
    category: Category | None = None
    price_max: NonNegativeFloat | None = Field(default=None, description="Maximum upper ticket price, in RUB.")
    is_free: bool | None = None
    age_limit: Annotated[int, Field(ge=0, le=120)] | None = Field(default=None, description="Visitor/child age: event rating must not exceed this age.")
    duration_max: Annotated[int, Field(gt=0, le=10080)] | None = None
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)] | None = None


class GetEventArgs(StrictModel):
    event_id: UUID


class FindSimilarArgs(DateRangeArgs):
    event_id: UUID
    city: ShortText | None = None


class VenueScheduleArgs(DateRangeArgs):
    venue: ShortText


class SubscribeArgs(StrictModel):
    user_id: Identifier
    city: ShortText
    category: Category | None = None
    period: Literal["daily", "weekly", "monthly"] = "weekly"


class FeedbackArgs(StrictModel):
    user_id: Identifier
    event_id: UUID
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class ActionResult(StrictModel):
    id: UUID
    success: bool
    message: LongText


class SearchResult(StrictModel):
    events: list[EventCard] = Field(default_factory=list, max_length=100)
