"""Conservative Russian filter parser used independently of the LLM."""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from calendar import monthrange
from datetime import datetime, timedelta, time
import re
from uuid import UUID

from .schemas import EventCard, SearchEventsArgs

CITIES = {"уф": "Уфа", "стерлит": "Стерлитамак", "салават": "Салават"}
CATEGORY_ROOTS = {"концерт": "концерт", "спектак": "спектакль", "выстав": "выставка", "фестивал": "фестиваль", "кино": "кино", "экскурс": "экскурсия"}
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")
NUMBER_WORDS = {
    word: number
    for number, forms in enumerate((
        "ноль нуль нуля", "один одна одного одной", "два две двух", "три трех",
        "четыре четырех", "пять пяти", "шесть шести", "семь семи", "восемь восьми",
        "девять девяти", "десять десяти", "одиннадцать одиннадцати", "двенадцать двенадцати",
        "тринадцать тринадцати", "четырнадцать четырнадцати", "пятнадцать пятнадцати",
        "шестнадцать шестнадцати", "семнадцать семнадцати", "восемнадцать восемнадцати",
        "девятнадцать девятнадцати",
    ))
    for word in forms.split()
}
_WORD_NUMBER = "|".join(NUMBER_WORDS)
_AGE = rf"\b(?P<age>\d{{1,2}}|{_WORD_NUMBER})\s*(?:лет|года|год)\b"
_AGE_WITH_CHILD = re.compile(rf"\b(?:ребен\w*|дет\w*)\s+{_AGE}")
_AGE_RE = re.compile(_AGE)
_MONEY_NUMBER = r"\d+(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d+)?"
_RUBLES = r"(?:руб(?:лей|ля|ль)?\b\.?|₽)"
_BUDGET_RE = re.compile(
    rf"\b(?:до|бюджет(?:ом)?|не более)\s*(?:"
    rf"(?:(?P<count>{_MONEY_NUMBER}|{_WORD_NUMBER})\s+)?тысяч(?:а|и|у)?\b(?:\s*{_RUBLES})?"
    rf"|(?P<amount>{_MONEY_NUMBER})\s*{_RUBLES})"
)
_CITY_OVERVIEW_RE = re.compile(
    r"(?:привет[,.!]?\s+)?(?:куда\s+(?:мне\s+)?(?:сходить|пойти)|"
    r"какие\s+мероприятия\s+есть|что\s+(?:посмотреть|есть))\s+в\s+([а-я-]+)[?!.\s]*"
)


def _number(value: str) -> float:
    if value in NUMBER_WORDS:
        return NUMBER_WORDS[value]
    return float("".join(value.split()).replace(",", "."))


def overview_city(message: str) -> str | None:
    match = _CITY_OVERVIEW_RE.fullmatch(message.lower().replace("ё", "е").strip())
    if not match:
        return None
    return next((city for root, city in CITIES.items() if match[1].startswith(root)), None)


@dataclass
class Constraints:
    city: str | None = None
    category: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    budget: float | None = None
    party: int = 1
    is_free: bool | None = None
    age: int | None = None
    duration_max: int | None = None
    end_hour: int | None = None
    end_minute: int = 0
    start_after: time | None = None
    route: bool = False
    span_min: int | None = None
    text: str | None = None
    exclude: set[UUID] = field(default_factory=set)
    cheaper: bool = False
    question: str | None = None

    def query(self) -> SearchEventsArgs:
        return SearchEventsArgs(city=self.city, category=self.category,
            date_from=self.date_from, date_to=self.date_to,
            price_max=self.budget / self.party if self.budget is not None else None,
            is_free=self.is_free, age_limit=self.age, duration_max=self.duration_max, text=self.text)
