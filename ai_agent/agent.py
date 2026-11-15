from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import logging
import re
from secrets import token_urlsafe
import time
from typing import Any
from dataclasses import replace
from contextlib import asynccontextmanager
from .telemetry import TraceSinkProtocol
from uuid import UUID
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from . import dialogue, prompts
from .config import AgentSettings
from .schemas import (AgentRequest, AgentResponse, AgentTrace, EventCard,
                      GetEventArgs, SubscribeArgs, ToolCallTrace)
from .tools import EventRepository, TOOL_MODELS, TOOLS

logger = logging.getLogger(__name__)
_MUTATIONS = frozenset({"subscribe", "save_feedback"})
_WINDOW = 86400.0


@dataclass
class _Session:
    constraints: dialogue.Constraints = field(default_factory=dialogue.Constraints)
    previous: list[EventCard] = field(default_factory=list)
    pending: dict[str, Any] | None = None
    touched: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    initialized: bool = False
    active: int = 0


@dataclass
class _Run:
    request: AgentRequest
    now: datetime
    trace: AgentTrace
    started: float = field(default_factory=time.monotonic)
    records: dict[UUID, EventCard] = field(default_factory=dict)


class CultureAgentService:

    def __init__(self, repository: EventRepository, settings: AgentSettings | None = None,
                 client: AsyncOpenAI | None = None,
                 trace_sink: TraceSinkProtocol | None = None) -> None:
        self.repository = repository
        self.trace_sink = trace_sink
        self.settings = settings if settings is not None else AgentSettings.from_env()
        self._timezone = ZoneInfo(self.settings.timezone)
        self._client = client
        self._owns_client = False
        self._sessions: dict[tuple[str, str], _Session] = {}
        self._session_costs: dict[tuple[str, str], deque] = defaultdict(deque)
        self._user_costs: dict[str, deque] = defaultdict(deque)
        self._requests: dict[str, deque] = defaultdict(deque)
        self._budget_lock = asyncio.Lock()

    @staticmethod
    @asynccontextmanager
    async def _session_guard(state: _Session):
        state.active += 1
        try:
            async with state.lock:
                yield
        finally:
            state.active -= 1

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.close()
            self._client = None
            self._owns_client = False

    @staticmethod
    def _prune(ledger: deque, now: float, window: float) -> None:
        while ledger and ledger[0][0] <= now - window:
            ledger.popleft()

    async def _reserve(self, run: _Run, messages: list[dict], tool_defs: list) -> tuple[list, list]:
        input_bound = len(json.dumps([messages, tool_defs], ensure_ascii=False).encode("utf-8")) + 1024
        amount = (input_bound * self.settings.input_usd_per_million +
                  self.settings.max_output_tokens * self.settings.output_usd_per_million) / 1_000_000
        key = (run.request.session_id, run.request.user_id)
        async with self._budget_lock:
            now = time.monotonic()
            session = self._session_costs[key]
            user = self._user_costs[run.request.user_id]
            self._prune(user, now, _WINDOW)
            limits = ((run.trace.cost_usd, self.settings.request_budget_usd),
                      (sum(row[1] for row in session), self.settings.session_budget_usd),
                      (sum(row[1] for row in user), self.settings.user_daily_budget_usd))
            if any(limit <= 0 or spent + amount > limit for spent, limit in limits):
                raise ValueError("budget_exceeded")
            first, second = [now, amount], [now, amount]
            session.append(first)
            user.append(second)
            return first, second

    async def _completion(self, run: _Run, messages: list[dict]) -> Any:
        if not self.settings.api_key.strip():
            raise ValueError("api_key_missing")
        definitions = TOOLS
        reservations = await self._reserve(run, messages, definitions)
        try:
            if self._client is None:
                self._client = AsyncOpenAI(api_key=self.settings.api_key,
                    base_url=self.settings.base_url, timeout=self.settings.timeout_seconds,
                    max_retries=0)
                self._owns_client = True
            response = await asyncio.wait_for(self._client.chat.completions.create(
                model=self.settings.model, messages=messages, tools=definitions,
                tool_choice="auto",
                max_tokens=self.settings.max_output_tokens), timeout=self.settings.timeout_seconds)
        except Exception:
            run.trace.cost_usd += reservations[0][1]
            raise
        usage = getattr(response, "usage", None)
        if usage is not None:
            incoming = max(0, int(getattr(usage, "prompt_tokens", 0) or 0))
            outgoing = max(0, int(getattr(usage, "completion_tokens", 0) or 0))
            run.trace.tokens_input += incoming
            run.trace.tokens_output += outgoing
            run.trace.total_tokens += incoming + outgoing
            cost = (incoming * self.settings.input_usd_per_million +
                    outgoing * self.settings.output_usd_per_million) / 1_000_000
            async with self._budget_lock:
                for row in reservations:
                    row[1] = cost
            run.trace.cost_usd += cost
        else:
            run.trace.cost_usd += reservations[0][1]
        return response

    async def _execute(self, run: _Run, name: str, args: BaseModel) -> Any:
        if len(run.trace.tool_calls) >= 5:
            raise ValueError("tool_limit")
        trace = ToolCallTrace(name=name, args=args.model_dump(mode="json"))
        run.trace.tool_calls.append(trace)
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(getattr(self.repository, name)(args),
                timeout=self.settings.repository_timeout_seconds)
            cards = ([result] if isinstance(result, EventCard) else getattr(result, "events", []))
            for card in cards:
                if not isinstance(card, EventCard):
                    raise TypeError("repository returned an unvalidated event")
                if card.status != "черновик":
                    run.records[card.id] = card
                    trace.result_ids.append(card.id)
            return result
        except Exception as exc:
            trace.error = type(exc).__name__
            raise
        finally:
            trace.duration_ms = (time.monotonic() - started) * 1000

    def _finish(self, run: _Run, state: _Session, events: list[EventCard] | None = None,
                text: str | None = None, question: str | None = None,
                pending: dict | None = None) -> AgentResponse:
        events = events or []
        state.previous = events
        state.touched = time.monotonic()
        run.trace.event_ids = list(run.records)
        run.trace.latency_ms = (time.monotonic() - run.started) * 1000
        if text is None:
            lines = []
            for event in events:
                price = "бесплатно" if event.is_free else f"{event.price_min:g}–{event.price_max:g} ₽ за билет"
                local = event.date_start.astimezone(self._timezone)
                c = state.constraints
                why = [f"в выбранном городе {event.city}" if c.city else f"город {event.city}"]
                if c.age is not None:
                    why.append(f"рейтинг {event.age_limit}+ допускает ребёнка {c.age} лет")
                if c.budget is not None:
                    why.append(f"верхняя цена на {c.party} чел. — {event.price_max * c.party:g} ₽, в пределах {c.budget:g} ₽")
                if c.end_hour is not None and event.date_end is not None:
                    why.append(f"окончание {event.date_end.astimezone(self._timezone):%H:%M} до указанного предела")
                if c.start_after is not None:
                    why.append(f"начало от {c.start_after:%H:%M}")
                if c.is_free:
                    why.append("вход бесплатный")
                lines.append(f"{event.title}: {local:%d.%m.%Y %H:%M}, {event.venue}; {price}, {event.age_limit}+. Подходит: " + "; ".join(why) + ".")
            text = "\n".join(lines) or "По заданным условиям подтверждённых вариантов нет. Можно изменить дату или бюджет."
            if events and state.constraints.route:
                text += (f"\nОбщий верхний бюджет на {state.constraints.party} чел.: {sum(e.price_max for e in events) * state.constraints.party:g} ₽. "
                         f"Между событиями заложен условный запас {self.settings.transfer_buffer_min} мин.; "
                         "время дороги без карт неизвестно.")
        if run.trace.fallback_reason and run.trace.fallback_reason != "rate_limit":
            text = "Работаю в резервном режиме поиска. " + text
        return AgentResponse(reply_text=text[:12000], events=events,
            clarifying_question=question, requires_confirmation=pending,
            is_fallback=run.trace.fallback_reason is not None, trace=run.trace)

    def _select(self, run: _Run, state: _Session, cards: list[EventCard]) -> list[EventCard]:
        eligible = [e for e in cards if dialogue.eligible(e, state.constraints, run.now)]
        age = state.constraints.age
        eligible.sort(key=lambda event: (
            event.price_max if state.constraints.cheaper else 0,
            "семейное" not in event.tags if age is not None else False,
            event.age_limit != age if age is not None else False,
            event.date_start, event.price_max,
        ))
        if state.constraints.route:
            return dialogue.make_route(eligible, state.constraints, self.settings.transfer_buffer_min)
        return eligible[:5]

    async def _finish_empty_search(self, run: _Run, state: _Session) -> AgentResponse:
        constraints = state.constraints
        if constraints.city and not constraints.route:
            alternatives = []
            if constraints.date_from is not None or constraints.date_to is not None:
                alternatives.append((
                    replace(constraints, date_from=None, date_to=None),
                    f"В городе {constraints.city} есть варианты на другие даты.",
                ))
            alternatives.append((
                replace(constraints, city=None),
                "Есть варианты в других городах Башкортостана. Город указан в каждой карточке.",
            ))
            for filters, note in alternatives:
                if len(run.trace.tool_calls) >= 5:
                    break
                await self._execute(run, "search_events", filters.query())
                candidates = [event for event in run.records.values()
                              if not dialogue.eligible(event, constraints, run.now)]
                cards = self._select(run, replace(state, constraints=filters), candidates)
                if cards:
                    run.trace.plan.append("offer_catalog_alternatives")
                    return self._finish(run, state, cards, text=f"Точного совпадения нет. {note}")
        return self._finish(run, state, text=await self._empty_explanation(run, state))

    async def _empty_explanation(self, run: _Run, state: _Session) -> str:
        c = state.constraints
        candidates = [e for e in run.records.values() if dialogue.eligible(e, c, run.now)]
        if c.route and candidates:
            from itertools import combinations
            pairs = [pair for pair in combinations(sorted(candidates, key=lambda e: e.date_start), 2)
                     if pair[0].date_end is not None and pair[1].date_end is not None
                     and pair[0].date_start.date() == pair[1].date_start.date()
                     and pair[0].date_end + timedelta(minutes=self.settings.transfer_buffer_min) <= pair[1].date_start]
            budget_pairs = [pair for pair in pairs if c.span_min is None or
                            (pair[1].date_end - pair[0].date_start).total_seconds() <= c.span_min * 60]
            if c.budget is not None and budget_pairs:
                minimum = min(sum(e.price_max for e in pair) * c.party for pair in budget_pairs)
                if minimum > c.budget:
                    return f"Маршрут из двух событий не укладывается в бюджет {c.budget:g} ₽. Среди проверенных вариантов нужно минимум {minimum:g} ₽ на {c.party} чел.; можно увеличить бюджет на {minimum - c.budget:g} ₽."
            span_pairs = [pair for pair in pairs if c.budget is None or sum(e.price_max for e in pair) * c.party <= c.budget]
            if c.span_min is not None and span_pairs:
                minimum = min((b.date_end - a.date_start).total_seconds() / 60 for a, b in span_pairs)
                if minimum > c.span_min:
                    return f"Для двух событий нужен интервал минимум {minimum:g} мин. среди проверенных вариантов; увеличьте длительность на {minimum - c.span_min:g} мин."
        for key, label in (("budget", "бюджет"), ("text", "название/ключевые слова"),
                           ("category", "категория"), ("is_free", "только бесплатный вход"),
                           ("end_hour", "время окончания"), ("duration_max", "длительность")):
            if len(run.trace.tool_calls) >= 5:
                break
            if getattr(c, key) is None:
                continue
            relaxed = replace(c, **{key: None})
            await self._execute(run, "search_events", relaxed.query())
            fitting = [e for e in run.records.values() if dialogue.eligible(e, relaxed, run.now)]
            if not fitting:
                continue
            if c.route and not dialogue.make_route(fitting, relaxed, self.settings.transfer_buffer_min):
                continue
            if key == "budget" and not c.route:
                minimum = min(e.price_max * c.party for e in fitting)
                return f"Мешает бюджет {c.budget:g} ₽: среди проверенных вариантов нужно минимум {minimum:g} ₽ на {c.party} чел. Можно увеличить бюджет на {max(0, minimum - c.budget):g} ₽."
            return f"По всем условиям вариантов нет. Если ослабить ограничение «{label}», проверенные варианты появляются. Разрешить такое изменение?"
        if c.route:
            return "По выбранным городу, датам, времени и бюджету маршрут из 2–4 непересекающихся событий не найден. Можно выбрать один пункт вместо двух или другой день; подходящие события не выдумываю."
        return "Подходящих событий нет по сочетанию выбранных города, даты, возраста, цены и ключевых слов. Не удалось установить одно мешающее ограничение; попробуйте другую дату или более широкий запрос."

    async def _fallback(self, run: _Run, state: _Session, reason: str) -> AgentResponse:
        run.trace.fallback_reason = reason[:300]
        run.trace.plan.append("deterministic_repository_search")
        if state.constraints.question:
            return self._finish(run, state, text=state.constraints.question, question=state.constraints.question)
        try:
            if len(run.trace.tool_calls) < 5:
                await self._execute(run, "search_events", state.constraints.query())
            events = self._select(run, state, list(run.records.values()))
            if not events:
                return await self._finish_empty_search(run, state)
            return self._finish(run, state, events)
        except Exception as exc:
            logger.warning("Culture agent fallback failed: %s", type(exc).__name__)
            run.trace.fallback_reason = (reason + ";repository_" + type(exc).__name__)[:300]
            return self._finish(run, state, text="Сейчас не удалось проверить афишу. Попробуйте ещё раз позже.")

    def _propose(self, run: _Run, state: _Session, name: str, args: BaseModel) -> AgentResponse:
        now = run.now
        pending = {"tool": name, "arguments": args.model_dump(mode="json"),
                   "session_id": run.request.session_id, "user_id": run.request.user_id,
                   "expires_at": (now + timedelta(seconds=self.settings.confirmation_ttl_seconds)).isoformat(),
                   "expires_in_seconds": self.settings.confirmation_ttl_seconds,
                   "version": token_urlsafe(18)}
        state.pending = json.loads(json.dumps(pending))
        run.trace.tool_calls.append(ToolCallTrace(name=name, args=args.model_dump(mode="json"),
                                                  error="confirmation_required"))
        if name == "subscribe":
            summary = f"Подписка: город {args.city}, категория {args.category or 'любая'}, период {args.period}."
        else:
            summary = f"Обращение по событию {args.event_id}: {args.text}"
        return self._finish(run, state, text=summary + " Подтвердите действие перед сохранением.", pending=dict(pending))

    async def _llm(self, run: _Run, state: _Session) -> AgentResponse:
        messages = [{"role": "system", "content": prompts.system_prompt(run.now)}]
        messages.extend(message.model_dump() for message in run.request.history)
        messages.append({"role": "user", "content": run.request.message})

        for attempt in range(2):
            response = await self._completion(run, messages)
            calls = response.choices[0].message.tool_calls or []
            if len(calls) > 4:
                raise ValueError("tool_limit")
            try:
                tools = self._validated_calls(calls, state)
            except ValidationError:
                reason = "invalid_tool_arguments"
            else:
                if tools:
                    break
                reason = "no_verified_retrieval"
            if attempt:
                raise ValueError(reason)
            run.trace.plan.append("repair_model_tool_call")
            messages.append({"role": "system", "content":
                "Предыдущий ответ не удалось разобрать. Вызови подходящий инструмент "
                "с полным JSON аргументов. Для поиска используй search_events. "
                "Оставь необязательные параметры пустыми, если их нет в запросе."})

        for name, args in tools:
            if name in _MUTATIONS:
                return await self._propose_model_action(run, state, name, args)
            await self._execute(run, name, args)

        cards = self._select(run, state, list(run.records.values()))
        if not cards:
            return await self._finish_empty_search(run, state)
        return self._finish(run, state, cards)

    def _validated_calls(self, calls, state):
        tools = []
        enforced = state.constraints.query().model_dump(mode="json", exclude_none=True)
        for call in calls:
            name = call.function.name
            if name not in TOOL_MODELS:
                raise ValueError("unknown_tool")
            if len(call.function.arguments) > 16000:
                raise ValueError("tool_arguments_too_large")
            args = TOOL_MODELS[name].model_validate_json(call.function.arguments)
            if name == "search_events":
                merged = {**args.model_dump(mode="json"), **enforced}
                args = TOOL_MODELS[name].model_validate_json(json.dumps(merged))
            tools.append((name, args))
        return tools

    async def _propose_model_action(self, run, state, name, args):
        text = run.request.message.lower().replace("ё", "е")
        keywords = ("подпис", "подпиш", "уведомл") if name == "subscribe" else (
            "отзыв", "обращен", "организатор", "сообщен"
        )
        if not any(word in text for word in keywords):
            raise ValueError("mutation_without_user_intent")
        updates = {"user_id": run.request.user_id}
        if name == "subscribe":
            if state.constraints.city:
                updates["city"] = state.constraints.city
            if state.constraints.category:
                updates["category"] = state.constraints.category
        else:
            requested_id = dialogue.UUID_RE.search(run.request.message)
            if requested_id is not None and str(args.event_id) != requested_id[0].lower():
                raise ValueError("feedback_event_mismatch")
            if args.event_id not in run.records:
                await self._execute(run, "get_event", GetEventArgs(event_id=args.event_id))
            if args.event_id not in run.records:
                raise ValueError("feedback_event_not_found")
        args = TOOL_MODELS[name].model_validate_json(json.dumps({**args.model_dump(mode="json"), **updates}))
        return self._propose(run, state, name, args)

    async def handle_message(self, request: AgentRequest) -> AgentResponse:
        response = await self._handle_message(request)
        if self.trace_sink is not None:
            try:
                await self.trace_sink.save(response.trace.model_copy(deep=True))
            except Exception as exc:
                logger.error("Trace persistence failed: %s", type(exc).__name__)
        return response

    async def _handle_message(self, request: AgentRequest) -> AgentResponse:
        now = datetime.now(self._timezone)
        run = _Run(request, now, AgentTrace(request=request.model_dump(mode="json")))
        key = (request.session_id, request.user_id)
        clock = time.monotonic()
        for old_key, old in list(self._sessions.items()):
            if clock - old.touched > _WINDOW and not old.lock.locked() and not old.active:
                del self._sessions[old_key]
        for old_key in list(self._session_costs):
            if old_key not in self._sessions:
                del self._session_costs[old_key]
        for mapping, window in ((self._requests, 60), (self._user_costs, _WINDOW)):
            for old_key, ledger in list(mapping.items()):
                self._prune(ledger, clock, window)
                if not ledger:
                    del mapping[old_key]
        if key not in self._sessions and len(self._sessions) >= 10000:
            run.trace.fallback_reason = "state_capacity"
            return self._finish(run, _Session(), text="Сервис занят. Попробуйте позже.")
        state = self._sessions.setdefault(key, _Session())
        async with self._session_guard(state):
            try:
                now = datetime.now(self._timezone)
                run.now = now
                clock = time.monotonic()
                requests = self._requests[request.user_id]
                self._prune(requests, clock, 60)
                if len(requests) >= self.settings.requests_per_minute:
                    run.trace.fallback_reason = "rate_limit"
                    return self._finish(run, state, text="Слишком много запросов. Попробуйте через минуту.")
                requests.append([clock, 0])
                if request.confirm_action:
                    pending = state.pending
                    if (pending is None or pending["session_id"] != request.session_id or
                        pending["user_id"] != request.user_id or datetime.fromisoformat(pending["expires_at"]) <= now):
                        state.pending = None
                        return self._finish(run, state, text="Нет действующего действия для подтверждения. Повторите запрос.")
                    if request.confirmation_version is not None and request.confirmation_version != pending["version"]:
                        return self._finish(run, state, text="Предложение изменилось. Проверьте последнее действие.")
                    state.pending = None
                    args = TOOL_MODELS[pending["tool"]].model_validate_json(json.dumps(pending["arguments"]))
                    result = await self._execute(run, pending["tool"], args)
                    return self._finish(run, state, text=result.message)
                state.pending = None
                if not state.initialized and request.history:
                    for message in request.history:
                        if message.role == "user":
                            state.constraints = dialogue.parse(message.content, state.constraints, now, [])
                state.initialized = True
                lowered = request.message.lower().replace("ё", "е")
                if any(x in lowered for x in ("системный промпт", "системные инструкции", "system prompt", "ignore previous", "игнорируй инструкции", "игнорируй все", "раскрой промпт")):
                    if any(root in lowered for root in (*dialogue.CITIES, *dialogue.CATEGORY_ROOTS, "афиш", "мероприят", "куда пойти")):
                        state.constraints = dialogue.parse(request.message, state.constraints, now, state.previous)
                        return await self._fallback(run, state, "user_injection_ignored")
                    return self._finish(run, state, text="Я помогаю с культурной афишей. Могу подобрать мероприятия по городу, дате и бюджету.")
                if (any(x in lowered for x in ("рецепт", "реши уравнение", "напиши код", "курс биткоин", "столиц", "квантов", "погода", "кредит"))
                    and not any(root in lowered for root in (*dialogue.CATEGORY_ROOTS, "афиш", "мероприят"))):
                    return self._finish(run, state, text="Я помогаю выбирать культурные мероприятия. В каком городе посмотреть афишу?", question="В каком городе посмотреть афишу?")
                state.constraints = dialogue.parse(request.message, state.constraints, now, state.previous)
                run.trace.plan.append("parse_constraints_and_verify_repository_facts")
                general_search = re.fullmatch(
                    r"(?:привет[,.!]?\s+)?куда\s+(?:мне\s+)?(?:сходить|пойти)[?!.\s]*", lowered.strip()
                )
                if general_search or dialogue.overview_city(request.message):
                    filters = state.constraints
                    run.trace.plan.append("catalog_overview")
                    await self._execute(run, "search_events", filters.query())
                    if filters.city is not None:
                        cards = self._select(run, state, list(run.records.values()))
                    else:
                        eligible = sorted((event for event in run.records.values()
                                           if dialogue.eligible(event, filters, run.now)),
                                          key=lambda event: (event.date_start, event.price_max))
                        by_city = {}
                        for event in eligible:
                            by_city.setdefault(event.city, event)
                        cards = list(by_city.values())[:5]
                    if cards:
                        return self._finish(run, state, cards)
                    return await self._finish_empty_search(run, state)
                if state.constraints.question:
                    return self._finish(run, state, text=state.constraints.question, question=state.constraints.question)
                direct = dialogue.UUID_RE.search(request.message)
                if direct and not any(word in request.message.lower() for word in ("похож", "отзыв", "обращен", "подпис")):
                    await self._execute(run, "get_event", GetEventArgs(event_id=UUID(direct[0])))
                    card = run.records.get(UUID(direct[0]))
                    if card is None:
                        return self._finish(run, state, text="Событие не найдено в доступной афише.")
                    if card.status == "отменено":
                        return self._finish(run, state, text=f"{card.title}: мероприятие отменено.")
                    if not dialogue.eligible(card, state.constraints, now):
                        return self._finish(run, state, text="Событие найдено, но не подходит под текущие условия или уже прошло.")
                    return self._finish(run, state, [card])
                if not self.settings.api_key.strip():
                    if any(word in lowered for word in ("подпис", "подпиш", "уведомл")):
                        if not state.constraints.city:
                            question = "На какой город оформить подписку?"
                            return self._finish(run, state, text=question, question=question)
                        period = "daily" if "ежеднев" in lowered else "monthly" if "ежемесяч" in lowered else "weekly"
                        return self._propose(run, state, "subscribe", SubscribeArgs(
                            user_id=request.user_id, city=state.constraints.city,
                            category=state.constraints.category, period=period,
                        ))
                    return await self._fallback(run, state, "api_key_missing")
                return await self._llm(run, state)
            except (OpenAIError, TimeoutError) as exc:
                return await self._fallback(run, state, type(exc).__name__)
            except Exception as exc:
                logger.warning("Culture agent recovered from %s", type(exc).__name__)
                reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                return await self._fallback(run, state, reason or type(exc).__name__)
