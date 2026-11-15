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
