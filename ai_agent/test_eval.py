"""Offline executable controls: python -m ai_agent.test_eval [--report PATH].

Uses the real OpenAI SDK with an HTTP mock, never a provider or an environment key.
The fixed service clock is a test-only patch, not a production clock API.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
from datetime import datetime
import importlib
import json
from pathlib import Path
import socket
import sys
from typing import Any
from unittest.mock import patch
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from openai import AsyncOpenAI

from .agent import CultureAgentService
from .config import AgentSettings
from .schemas import AgentRequest, AgentResponse
from .tools import MockEventRepository
from .prompts import PROMPT_VERSION

NOW = datetime(2030, 1, 4, 9, tzinfo=ZoneInfo("Asia/Yekaterinburg"))
SATURDAY = "2030-01-05"


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


def check(condition: bool, explanation: str) -> None:
    # Unlike assert, these checks remain active under python -O.
    if not condition:
        raise AssertionError(explanation)


def tool(name: str, arguments: dict[str, Any], count: int = 1) -> dict:
    return {"tool_calls": [
        {"id": f"call_{i}", "type": "function", "function": {
            "name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}
        for i in range(count)
    ], "content": None}


def final(*ids: UUID) -> dict:
    return {"content": json.dumps({"event_ids": [str(i) for i in ids]})}


class ScriptedProvider:
    """A real SDK client with an in-process HTTP transport and strict script."""
    def __init__(self, steps: list[dict | int | str]):
        self.steps = list(steps)
        self.requests: list[dict] = []
        self.http = httpx.AsyncClient(transport=httpx.MockTransport(self._respond))
        self.client = AsyncOpenAI(api_key="offline-placeholder-not-a-secret",
            base_url="https://offline.invalid/v1", http_client=self.http, max_retries=0)

    def _respond(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        self.requests.append(payload)
        check(bool(self.steps), "Unexpected SDK request after script exhausted")
        step = self.steps.pop(0)
        if step == "timeout":
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        if step == "network":
            raise httpx.ConnectError("synthetic network failure", request=request)
        if isinstance(step, int):
            return httpx.Response(step, json={"error": {"message": "synthetic failure",
                "type": "server_error", "code": "synthetic"}})
        return httpx.Response(200, json={"id": "chatcmpl-offline", "object": "chat.completion",
            "created": 0, "model": "offline-script", "choices": [{"index": 0,
                "message": {"role": "assistant", **step},
                "finish_reason": "tool_calls" if step.get("tool_calls") else "stop"}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40}})
