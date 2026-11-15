"""Bounded asynchronous orchestration with repository-grounded answers.

Ledgers and confirmation state are process-local. Multi-worker deployments should
replace them with a shared transactional store before offering durable quotas.
"""
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
    """An injectable async service; constructing it never performs network I/O."""

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
        # UTF-8 bytes bound text token count conservatively; include protocol overhead.
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
        # A blank key disables even an injected client, making offline mode explicit.
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
            # Unknown provider usage after a timeout is charged at the reserved bound.
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
