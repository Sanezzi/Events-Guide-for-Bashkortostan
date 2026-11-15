from __future__ import annotations

import asyncio
from typing import Protocol, runtime_checkable

from tg_bot.models.schemas import AgentReply, SearchFilters, SearchResult
from tg_bot.repositories import CatalogRepositoryProtocol


@runtime_checkable
class AgentBridgeProtocol(Protocol):
    async def ask(
        self, *, user_id: str, session_id: str, text: str, history: list
    ) -> AgentReply | None: ...


class BotService:
    def __init__(
        self,
        repo: CatalogRepositoryProtocol,
        agent: AgentBridgeProtocol | None = None,
        *,
        timeout: float = 8.0,
    ):
        self.repo = repo
        self.agent = agent
        self.timeout = timeout

    async def search(self, filters: SearchFilters) -> SearchResult:
        return await self.repo.search(filters)

    async def ask(
        self, user_id: str, session_id: str, text: str, history: list
    ) -> AgentReply | None:
        if self.agent is None:
            return None
        try:
            async with asyncio.timeout(self.timeout):
                reply = await self.agent.ask(
                    user_id=user_id, session_id=session_id, text=text, history=history
                )
                if reply is None:
                    return None
                reply = AgentReply.model_validate(reply)
                for event_id in reply.event_ids:
                    event = await self.repo.get_event(event_id)
                    if event is None or event.status != "опубликовано":
                        return None
                return reply
        except Exception:
            return None
