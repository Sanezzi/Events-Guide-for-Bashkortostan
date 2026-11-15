"""Catalog search, persistent filters, event cards and optional agent dialogue."""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import get_args
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from pydantic import ValidationError

from tg_bot.handlers.start import answer_callback, html, language, respond, send_long
from tg_bot.keyboards.inline import (
    back_keyboard,
    back_row,
    button,
    categories_keyboard,
    category_label,
    event_keyboard,
    filters_keyboard,
    results_keyboard,
)
from tg_bot.locales import t
from tg_bot.models.schemas import Category, SearchFilters
from tg_bot.backend_client import repository
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from tg_bot.services.bot_service import BotService


class SearchFlow(StatesGroup):
    value = State()


class AgentFlow(StatesGroup):
    query = State()


FILTER_KEYS = {
    "q": "bot.query",
    "city": "bot.city",
    "category": "bot.category",
    "date": "bot.date",
    "max_price": "bot.max_price",
}


def filter_summary(values: dict, lang: str) -> str:
    parts = []
    for field in ("q", "city", "category", "date", "max_price"):
        if values.get(field) is not None:
            value = category_label(values[field], lang) if field == "category" else values[field]
            parts.append(f"{t(FILTER_KEYS[field], lang)}: {value}")
    if values.get("period"):
        parts.append(t("bot." + values["period"], lang))
    if values.get("is_free"):
        parts.append(t("bot.free", lang))
    if values.get("language"):
        parts.append(t("bot.bashkir", lang))
    return t("bot.filter_summary", lang, filters=" · ".join(parts) or t("bot.any", lang))


def display_date(value, settings=None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        zone = ZoneInfo(getattr(settings, "timezone", "Asia/Yekaterinburg"))
        return value.astimezone(zone).strftime("%d.%m.%Y %H:%M %Z")
    return str(value)


async def search_results(
    target, state: FSMContext, database, agent=None, *, edit=False, settings=None
):
    lang = await language(database, target.from_user.id)
    data = await state.get_data()
    values = data.get("filters", {})
    filters = SearchFilters(**values)
    async with repository(database) as repo:
        result = await BotService(repo, agent).search(filters)
    # A stale page can become empty after catalog updates.
    if not result.items and result.total and filters.page > 1:
        values = {
            **values,
            "page": max(1, (result.total + filters.page_size - 1) // filters.page_size),
        }
        await state.update_data(filters=values)
        return await search_results(target, state, database, agent, edit=edit, settings=settings)
    pages = max(1, (result.total + result.page_size - 1) // result.page_size)
    text = t("bot.results", lang, total=result.total, page=result.page, pages=pages)
    text += "\n" + filter_summary(values, lang)
    if not result.items:
        text += "\n\n" + t("empty_" + (result.explanation or "combined"), lang)
    for index, event in enumerate(result.items, 1):
        date = getattr(event, "date_start", None)
        date_text = display_date(date, settings)
        demo = t("bot.demo", lang) + "\n" if getattr(event, "is_demo", False) else ""
        text += f"\n\n{index}. {demo}{str(event.title)[:180]}\n{event.city} · {date_text}"
    await respond(
        target,
        html(text),
        results_keyboard(lang, result.items, result.page, result.total, result.page_size),
        edit=edit,
    )


async def render_event(target, event, lang, settings=None, *, screen="open-event", edit=False):
    compact = screen == "agent-summary"
    status = getattr(event, "status", "")
    status = getattr(status, "value", status)
    lines = []
    if status in {"cancelled", "отменено"}:
        lines.append(f"⚠️ <b>{html(t('bot.event_cancelled', lang))}</b>")
    if getattr(event, "is_demo", False):
        lines.append(html(t("bot.demo", lang)))
    lines.append(f"🎟 <b>{html(event.title[:250])}</b>")
    date = getattr(event, "date_start", None)
    if date:
        lines.append(f"📅 {html(display_date(date, settings))}")
    ends = getattr(event, "date_end", None)
    if ends and not compact:
        lines.append("   ↳ " + html(display_date(ends, settings)))
    city = getattr(event, "city", "")
    venue = getattr(event, "venue", None) or getattr(event, "venue_name", None)
    lines.append("📍 " + html(" · ".join(str(value)[:150] for value in (city, venue) if value)))
    unknown = t("bot.unknown", lang)
    price = getattr(event, "price_min", None)
    upper = getattr(event, "price_max", None)
    if getattr(event, "is_free", False):
        price_text = t("bot.free", lang)
    elif price is not None:
        price_text = f"{price}–{upper}" if upper is not None and upper != price else str(price)
        price_text += " ₽"
    else:
        price_text = unknown
    age = getattr(event, "age_limit", None)
    if age is None:
        age = getattr(event, "age", None)
    category = category_label(getattr(event, "category", "other"), lang)
    age_text = f" · {age}+" if age is not None else ""
    lines.append(f"💳 <b>{html(price_text)}</b>{age_text} · {html(category)}")
    if not compact:
        if event.address:
            lines.append(html(event.address[:300]))
        if event.language:
            language_text = " / ".join(t(code, lang) for code in event.language.split("/"))
            lines.append(f"{html(t('bot.event_language', lang))}: {html(language_text)}")
        if event.description:
            description = event.description.strip()
            excerpt = description[:490] + "…" if len(description) > 490 else description
            lines.extend(("", html(excerpt)))
    back = {
        "event": "results",
        "agent-event": f"agent-summary:{event.id}",
        "agent-summary": "agent",
    }.get(screen, "menu")
    keyboard = event_keyboard(lang, event, screen=screen, back=back)
    if compact:
        keyboard.inline_keyboard.insert(0, [button("bot.details", lang, f"agent-event:{event.id}")])
    await respond(target, "\n".join(lines), keyboard, edit=edit)
