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


def parse(message: str, old: Constraints, now: datetime, previous: list[EventCard]) -> Constraints:
    city = overview_city(message)
    if city is not None:
        return Constraints(city=city)
    c = replace(old, exclude=set(old.exclude), question=None)
    s = message.lower().replace("ё", "е")
    for root, city in CITIES.items():
        if re.search(r"(?<![а-я])" + root, s):
            c.city = city
    # A named unsupported city must produce no data, never another city silently.
    named_city = re.search(r"(?:^|\s)в\s+([А-ЯЁ][а-яё-]{2,})", message)
    if named_city and not any(root in named_city[1].lower() for root in CITIES):
        c.city = named_city[1]
    for root, category in CATEGORY_ROOTS.items():
        if root in s:
            c.category = category
    if "любая категор" in s or "все категор" in s:
        c.category = None
    if c.city != old.city or c.category != old.category:
        c.text = None
    if "обычный поиск" in s or "не маршрут" in s:
        c.route = False
    day = None
    weekdays = {"понедельник": 0, "вторник": 1, "сред": 2, "четверг": 3, "пятниц": 4, "суббот": 5, "воскресен": 6}
    for root, weekday in weekdays.items():
        if root in s:
            day = now.date() + timedelta(days=(weekday - now.weekday()) % 7)
    if "сегодня" in s:
        day = now.date()
    if "завтра" in s:
        day = now.date() + timedelta(days=2 if "послезавтра" in s else 1)
    weekend = "выходн" in s and day is None
    if weekend:
        day = now.date() + timedelta(days=max(0, 5 - now.weekday()))
    iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", s)
    if iso:
        try:
            day = datetime.strptime(iso[1], "%Y-%m-%d").date()
        except ValueError:
            c.question = "Какую корректную дату выбрать (ГГГГ-ММ-ДД)?"
    if "другой день" in s:
        day = (c.date_from or now).date() + timedelta(days=1)
    if day:
        c.date_from = datetime.combine(day, time.min, now.tzinfo)
        extra_days = 1 if weekend and day.weekday() == 5 and not iso else 0
        c.date_to = datetime.combine(day + timedelta(days=extra_days), time.max, now.tzinfo)
    elif re.search(r"\b(?:в этом месяце|до конца (?:этого )?месяца)\b", s):
        last_day = now.date().replace(day=monthrange(now.year, now.month)[1])
        c.date_from = datetime.combine(now.date(), time.min, now.tzinfo)
        c.date_to = datetime.combine(last_day, time.max, now.tzinfo)
    elif re.search(r"недел", s):
        next_week = "следующ" in s
        start = now.date() + timedelta(days=7 - now.weekday()) if next_week else now.date()
        c.date_from = datetime.combine(start, time.min, now.tzinfo)
        c.date_to = datetime.combine(start + timedelta(days=6), time.max, now.tzinfo)
    if "на двоих" in s or "вдвоем" in s:
        c.party = 2
    party = re.search(r"на\s+(\d{1,2})\s+(?:человек|персон)", s)
    if party:
        c.party = max(1, int(party[1]))
    budget = _BUDGET_RE.search(s)
    if budget:
        amount = budget["amount"]
        c.budget = _number(amount) if amount else 1000 * _number(budget["count"] or "1")
    if "бесплат" in s:
        c.is_free = True
    if "можно платные" in s:
        c.is_free = None
    age = _AGE_WITH_CHILD.search(s) or _AGE_RE.search(s)
    if age:
        c.age = int(_number(age["age"]))
    elif re.search(r"ребен|дет[ья]|для детей", s) and c.age is None:
        c.question = "Сколько лет ребёнку?"
    end = re.search(r"(?:не позже|не позднее|законч\w*\s+до)\s*(\d{1,2}):(\d{2})", s)
    if end:
        if int(end[1]) < 24 and int(end[2]) < 60:
            c.end_hour, c.end_minute = int(end[1]), int(end[2])
        else:
            c.question = "До какого времени должно закончиться мероприятие (ЧЧ:ММ)?"
    after = re.search(r"(?<!не )\bпосле\s+(\d{1,2}):(\d{2})", s)
    if after:
        hour, minute = int(after[1]), int(after[2])
        if hour < 24 and minute < 60:
            c.start_after = time(hour, minute)
        else:
            c.question = "После какого времени искать мероприятие (ЧЧ:ММ)?"
    dur = re.search(r"(?:не дольше|длительность до|длительностью до)\s*(\d+)\s*(мин|час)", s)
    if dur:
        c.duration_max = int(dur[1]) * (60 if dur[2] == "час" else 1)
    if "маршрут" in s or "выходной день" in s or "план на день" in s:
        c.route = True
    span = re.search(r"на\s*(\d+)\s*час", s)
    if span:
        c.span_min = int(span[1]) * 60
    if "дешевле" in s or "подешевле" in s:
        c.cheaper = True
        if previous:
            ceiling = max(e.price_max for e in previous)
            c.budget = min(c.budget if c.budget is not None else float("inf"), max(0, ceiling - 1) * c.party)
    if "а еще" in s or "другие варианты" in s:
        c.exclude.update(e.id for e in previous)
    elif day or budget or c.city != old.city or c.category != old.category:
        c.exclude.clear()
    if "ближе" in s or "ехать не больше" in s:
        c.question = "Откуда планируете ехать (адрес или координаты)?"
    if "рядом с" in s:
        c.question = "Для точной оценки дороги подключите карты; пока подобрать по городу?"
    for pattern, keyword in (
        (r"\bджаз", "джаз"), (r"\bбалет", "балет"),
        (r"\bмастер[-\s]класс", "мастер-класс"),
        (r"\bкукольн", "кукольный театр"), (r"\bсказ(?:к|оч)", "сказка"),
        (r"\bкраевед", "краеведение"), (r"\bрок\b", "рок"),
        (r"\bнародн\w*\s+музык", "народная музыка"),
    ):
        if re.search(pattern, s):
            c.text = keyword
            break
    quoted = re.search(r'[«"]([^»"]{2,120})[»"]', message)
    if quoted and not ("подпис" in s or "отзыв" in s):
        c.text = quoted[1]
    return c
