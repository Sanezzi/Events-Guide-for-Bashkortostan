from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date as Date
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

Category = Literal["концерт", "спектакль", "выставка", "фестиваль", "кино", "экскурсия", "другое"]
Status = Literal["опубликовано", "черновик", "отменено"]


def normalize(value: str) -> str:
    return " ".join(
        re.sub(
            r"[^\w\s]", " ", unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
        ).split()
    )


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")
        ).encode()
    ).hexdigest()


class EventInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    id: UUID | None = None
    title: str = Field(min_length=1, max_length=300)
    normalized_title: str = ""
    category: Category
    tags: list[str] = Field(default_factory=list, max_length=40)
    date_start: datetime
    date_end: datetime | None = None
    duration_min: int | None = Field(default=None, gt=0, le=10080)
    city: str = Field(min_length=1, max_length=150)
    venue: str = Field(min_length=1, max_length=300)
    address: str = Field(min_length=1, max_length=500)
    lat: Decimal | None = Field(default=None, ge=-90, le=90)
    lon: Decimal | None = Field(default=None, ge=-180, le=180)
    description: str = Field(min_length=1, max_length=12000)
    price_min: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    price_max: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    is_free: bool | None = None
    age_limit: Literal[0, 6, 12, 16, 18] = 0
    language: Literal["ru", "ba", "en", "ru/ba"] | None = None
    org_link: str | None = None
    source_url: str
    source_type: Literal["manual", "import", "rss", "api", "page", "demo"] = "import"
    source_hash: str = ""
    sources: list[str] = Field(default_factory=list)
    verified_at: datetime | None = None
    confidence: Decimal = Field(default=Decimal("0.5"), ge=0, le=1)
    status: Status = "опубликовано"
    dedup_key: str = ""
    is_demo: bool = False

    @field_validator("source_url", "org_link")
    @classmethod
    def validate_url(cls, value):
        if value is None:
            return None
        url = HttpUrl(value)
        if url.username or url.password:
            raise ValueError("credentials in event URLs are forbidden")
        return str(url)

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, value):
        return list(dict.fromkeys(cls.validate_url(url) for url in value))

    @field_validator("date_start", "date_end", "verified_at")
    @classmethod
    def aware_timestamp(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("timezone offset required")
        return value.astimezone(timezone.utc) if value is not None else None

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, value):
        if isinstance(value, str):
            return (
                json.loads(value)
                if value.strip().startswith("[")
                else [part.strip() for part in value.split(",") if part.strip()]
            )
        return value

    @model_validator(mode="after")
    def consistent_fields(self):
        if self.date_end is not None:
            if self.date_end < self.date_start:
                raise ValueError("date_end precedes date_start")
            minutes = int((self.date_end - self.date_start).total_seconds() / 60)
            if self.duration_min is not None and self.duration_min != minutes:
                raise ValueError("duration_min conflicts with date_end")
            self.duration_min = minutes or None
        self.price_max = self.price_min if self.price_max is None else self.price_max
        if self.price_max < self.price_min:
            raise ValueError("price_max is below price_min")
        free = self.price_min == self.price_max == 0
        if self.is_free is not None and self.is_free != free:
            raise ValueError("is_free conflicts with prices")
        self.is_free = free
        self.normalized_title = normalize(self.title)
        if not self.normalized_title:
            raise ValueError("title must contain letters or numbers")
        self.dedup_key = digest(
            [
                self.normalized_title,
                self.date_start.isoformat(),
                normalize(self.city),
                normalize(self.venue),
            ]
        )
        self.sources = list(dict.fromkeys([self.source_url, *self.sources]))
        content = self.model_dump(mode="json", exclude={"id", "source_hash", "dedup_key"})
        self.source_hash = digest(content)
        if self.is_demo and "demo" not in self.title.casefold():
            raise ValueError("fictional demo title must be explicitly labelled DEMO")
        return self


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    normalized_title: str
    category: str
    tags: list[str]
    date_start: datetime
    date_end: datetime | None
    duration_min: int | None
    city: str
    venue: str
    address: str
    lat: Decimal | None
    lon: Decimal | None
    description: str
    price_min: Decimal
    price_max: Decimal
    is_free: bool
    age_limit: int
    language: str | None
    org_link: str | None
    source_url: str
    source_type: str
    source_hash: str
    sources: list[str]
    verified_at: datetime | None
    confidence: Decimal
    status: str
    dedup_key: str
    is_demo: bool
    created_at: datetime
    updated_at: datetime


class SearchFilters(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    q: str | None = Field(default=None, max_length=2000)
    city: str | None = Field(default=None, max_length=150)
    category: Category | None = None
    period: Literal["today", "tomorrow", "weekend", "week"] | None = None
    date: Date | None = None
    max_price: Decimal | None = Field(default=None, ge=0)
    is_free: bool | None = None
    language: Literal["ru", "ba", "en", "ru/ba"] | None = None
    age: int | None = Field(default=None, ge=0, le=120)
    venue: str | None = Field(default=None, max_length=300)
    date_from: datetime | None = None
    date_to: datetime | None = None
    duration_max: int | None = Field(default=None, gt=0, le=10080)
    full_price: bool = False
    include_demo: bool = True
    sort: Literal["date_start", "price_min", "price_max", "price_max_desc", "title"] = "date_start"
    offset: int | None = Field(default=None, ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=5, ge=1, le=100)


class SearchResult(BaseModel):
    items: list[EventOut]
    total: int
    page: int
    page_size: int
    explanation: str | None = None


class ImportReport(BaseModel):
    added: int = 0
    updated: int = 0
    rejected: int = 0
    unchanged: int = 0
    errors: list[dict] = Field(default_factory=list)


class AgentReply(BaseModel):
    text: str
    event_ids: list[UUID] = Field(default_factory=list)
    clarification: str | None = None
    confirmation_version: str | None = None
    is_fallback: bool = False
