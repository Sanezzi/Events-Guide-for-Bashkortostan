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


async def show_event(target, database, event_id: UUID, settings=None, *, screen="open-event", edit=False):
    lang = await language(database, target.from_user.id)
    async with repository(database) as repo:
        event = await repo.get_event(event_id)
    if event is None:
        back = {"event": "results", "agent-event": "agent", "agent-summary": "agent"}.get(screen, "menu")
        await respond(target, html(t("bot.not_found", lang)), back_keyboard(lang, back), edit=edit)
        return
    await render_event(target, event, lang, settings, screen=screen, edit=edit)


async def agent_search(
    message: Message, state: FSMContext, database, agent, text: str, settings=None
) -> bool:
    if agent is None:
        return False
    data = await state.get_data()
    history = data.get("history", [])[-12:]
    try:
        async with repository(database) as repo:
            service = BotService(repo, agent, timeout=30)
            reply = await asyncio.wait_for(
                service.ask(str(message.from_user.id), str(message.chat.id), text, history),
                timeout=30,
            )
    except Exception:
        # A model failure must never disable deterministic catalog search.
        return False
    if reply is None:
        return False
    lang = await language(database, message.from_user.id)
    await state.update_data(
        history=(
            history
            + [{"role": "user", "content": text}, {"role": "assistant", "content": str(reply.text)}]
        )[-12:],
        agent_confirmation=reply.confirmation_version,
    )
    if reply.text and (not reply.event_ids or "Точного совпадения нет" in reply.text):
        await send_long(message, str(reply.text), back_keyboard(lang, "agent"))
    elif reply.is_fallback:
        await message.answer("Работаю в резервном режиме поиска.", reply_markup=back_keyboard(lang, "agent"))
    if reply.confirmation_version:
        await message.answer("Сохранить действие?", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Подтвердить", callback_data=f"confirm:{reply.confirmation_version}"),
        ], back_row(lang, "agent")]))
    if reply.clarification and reply.clarification != reply.text:
        await send_long(message, str(reply.clarification), back_keyboard(lang, "agent"))
        return True
    valid = []
    async with repository(database) as repo:
        for identifier in reply.event_ids[:5]:
            try:
                event = await repo.get_event(UUID(str(identifier)))
            except (TypeError, ValueError):
                continue
            status = getattr(event, "status", "") if event else ""
            if event and getattr(status, "value", status) not in {
                "cancelled",
                "отменено",
                "draft",
                "черновик",
            }:
                valid.append(event)
    if valid:
        for event in valid:
            await render_event(message, event, lang, settings, screen="agent-summary")
        return True
    return bool(reply.text)


def create_router() -> Router:
    router = Router(name="search")

    async def show_assistant(target, state: FSMContext, database, *, edit=False):
        await state.set_state(AgentFlow.query)
        await state.update_data(agent_confirmation=None)
        lang = await language(database, target.from_user.id)
        prompt = f"<b>{html(t('bot.agent', lang))}</b>\n\n{html(t('bot.agent_prompt', lang))}"
        await respond(target, prompt, back_keyboard(lang), edit=edit)

    @router.message(Command("ai"))
    async def assistant_command(message: Message, state: FSMContext, database):
        await show_assistant(message, state, database)

    @router.callback_query(F.data == "agent")
    async def assistant(query: CallbackQuery, state: FSMContext, database):
        await answer_callback(query)
        await show_assistant(query, state, database, edit=True)

    @router.message(Command("search", "catalog"))
    async def catalog_command(
        message: Message, state: FSMContext, database, agent=None, settings=None
    ):
        await state.set_state(None)
        await state.update_data(filters={}, history=[])
        await search_results(message, state, database, agent, settings=settings)

    @router.callback_query(F.data == "catalog")
    async def catalog(query: CallbackQuery, state: FSMContext, database, agent=None, settings=None):
        await answer_callback(query)
        await state.set_state(None)
        await state.update_data(filters={}, history=[])
        await search_results(query, state, database, agent, edit=True, settings=settings)

    @router.callback_query(F.data.in_({"filters", "filters:reset"}))
    async def filters(query: CallbackQuery, state: FSMContext, database):
        await answer_callback(query)
        await state.set_state(None)
        if query.data == "filters:reset":
            await state.update_data(filters={}, history=[])
        lang = await language(database, query.from_user.id)
        data = await state.get_data()
        await respond(
            query,
            html(filter_summary(data.get("filters", {}), lang)),
            filters_keyboard(lang),
            edit=True,
        )

    @router.callback_query(F.data.startswith("filter:"))
    async def choose_filter(query: CallbackQuery, state: FSMContext, database):
        await answer_callback(query)
        field = query.data.split(":", 1)[1]
        if field not in FILTER_KEYS:
            return
        if field == "category":
            await state.set_state(None)
            lang = await language(database, query.from_user.id)
            await respond(query, html(t("bot.category", lang)), categories_keyboard(lang), edit=True)
            return
        await state.set_state(SearchFlow.value)
        await state.update_data(field=field)
        lang = await language(database, query.from_user.id)
        prompt = t("bot.enter_value", lang) + "\n" + t(FILTER_KEYS[field], lang)
        if field == "date":
            prompt += " · DD.MM.YYYY"
        await respond(query, html(prompt), back_keyboard(lang, "filters"), edit=True)

    @router.callback_query(F.data.startswith("category:"))
    async def category(
        query: CallbackQuery, state: FSMContext, database, agent=None, settings=None
    ):
        await answer_callback(query)
        argument = query.data.split(":", 1)[1]
        try:
            options = get_args(Category)
            if argument == "all":
                value = None
            else:
                index = int(argument)
                if not 0 <= index < len(options):
                    return
                value = options[index]
        except (ValueError, IndexError):
            return
        data = await state.get_data()
        await state.set_state(None)
        await state.update_data(filters={**data.get("filters", {}), "category": value, "page": 1})
        await search_results(query, state, database, agent, edit=True, settings=settings)

    @router.message(SearchFlow.value, F.text, ~F.text.startswith("/"))
    async def filter_value(
        message: Message, state: FSMContext, database, agent=None, settings=None
    ):
        data = await state.get_data()
        field = data.get("field")
        lang = await language(database, message.from_user.id)
        if field not in FILTER_KEYS:
            await state.set_state(None)
            await respond(message, html(t("bot.expired", lang)), back_keyboard(lang, "filters"))
            return
        raw = message.text.strip()
        value = raw[: 150 if field == "city" else 250] if raw else None
        if field == "date":
            try:
                try:
                    value = datetime.strptime(raw, "%d.%m.%Y").date().isoformat()
                except ValueError:
                    value = datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
            except ValueError:
                await respond(message, html(t("bot.invalid_date", lang)), back_keyboard(lang, "filters"))
                return
        elif field == "max_price":
            try:
                amount = Decimal(raw.replace(",", "."))
                if not amount.is_finite() or amount < 0 or amount > Decimal("100000000"):
                    raise InvalidOperation
                value = str(amount)
            except InvalidOperation:
                await respond(message, html(t("bot.invalid_price", lang)), back_keyboard(lang, "filters"))
                return
        values = {**data.get("filters", {}), field: value, "page": 1}
        if field == "date":
            values.pop("period", None)
        if field == "max_price":
            values.pop("is_free", None)
        try:
            SearchFilters(**values)
        except ValidationError:
            await respond(message, html(t("bot.invalid_category", lang)), back_keyboard(lang, "filters"))
            return
        await state.set_state(None)
        await state.update_data(filters=values, field=None)
        await search_results(message, state, database, agent, settings=settings)

    @router.callback_query(F.data.startswith("period:"))
    async def period(query: CallbackQuery, state: FSMContext, database, agent=None, settings=None):
        await answer_callback(query)
        value = query.data.split(":", 1)[1]
        if value not in {"today", "tomorrow", "weekend", "week"}:
            return
        data = await state.get_data()
        values = {**data.get("filters", {}), "period": value, "page": 1}
        values.pop("date", None)
        await state.set_state(None)
        await state.update_data(filters=values)
        await search_results(query, state, database, agent, edit=True, settings=settings)

    @router.callback_query(F.data.startswith("toggle:"))
    async def toggle(query: CallbackQuery, state: FSMContext, database, agent=None, settings=None):
        await answer_callback(query)
        mode = query.data.split(":", 1)[1]
        data = await state.get_data()
        values = dict(data.get("filters", {}))
        if mode == "free":
            values["is_free"] = None if values.get("is_free") else True
            if values["is_free"]:
                values.pop("max_price", None)
        elif mode == "bashkir":
            values["language"] = None if values.get("language") else "ba"
        else:
            return
        values["page"] = 1
        await state.set_state(None)
        await state.update_data(filters=values)
        await search_results(query, state, database, agent, edit=True, settings=settings)

    @router.callback_query(F.data == "results")
    async def results(query: CallbackQuery, state: FSMContext, database, agent=None, settings=None):
        await answer_callback(query)
        await state.set_state(None)
        await search_results(query, state, database, agent, edit=True, settings=settings)

    @router.callback_query(F.data.startswith("page:"))
    async def page(query: CallbackQuery, state: FSMContext, database, agent=None, settings=None):
        await answer_callback(query)
        try:
            number = int(query.data.split(":", 1)[1])
            if not 1 <= number <= 100000:
                return
        except ValueError:
            return
        data = await state.get_data()
        await state.set_state(None)
        await state.update_data(filters={**data.get("filters", {}), "page": number})
        await search_results(query, state, database, agent, edit=True, settings=settings)

    @router.callback_query(F.data.startswith(("event:", "open-event:", "agent-event:", "agent-summary:")))
    async def event(query: CallbackQuery, state: FSMContext, database, settings=None):
        await answer_callback(query)
        await state.set_state(None)
        screen, identifier = query.data.split(":", 1)
        try:
            event_id = UUID(identifier)
        except ValueError:
            lang = await language(database, query.from_user.id)
            await respond(query, html(t("bot.not_found", lang)), back_keyboard(lang), edit=True)
            return
        await show_event(query, database, event_id, settings, screen=screen, edit=True)

    @router.callback_query(F.data.startswith("confirm:"))
    async def confirm_agent(query: CallbackQuery, state: FSMContext, database, agent=None):
        await answer_callback(query)
        if agent is None or query.message is None:
            return
        lang = await language(database, query.from_user.id)
        version = query.data.split(":", 1)[1]
        if (await state.get_data()).get("agent_confirmation") != version:
            await respond(query, html(t("bot.expired", lang)), back_keyboard(lang, "agent"), edit=True)
            return
        await state.update_data(agent_confirmation=None)
        reply = await agent.ask(user_id=str(query.from_user.id),
                                session_id=str(query.message.chat.id), text="Подтверждаю",
                                history=[], confirmation_version=version)
        await respond(query, html(reply.text), back_keyboard(lang, "agent"), edit=True)
