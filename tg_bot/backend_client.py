from contextlib import asynccontextmanager
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from .models.schemas import AgentReply, EventOut, ImportReport, SearchFilters, SearchResult
from .repositories import SqlCatalogRepository

class BackendClient:
    def __init__(self, base_url: str, token: str):
        if urlsplit(base_url).scheme not in ("http", "https") or not token:
            raise ValueError("BACKEND_URL and INTERNAL_API_TOKEN are required")
        self.client = httpx.AsyncClient(base_url=base_url,
            headers={"X-Internal-Token": token}, timeout=15, trust_env=False)

    async def close(self):
        await self.client.aclose()

    async def request(self, method, path, **kwargs):
        response = await self.client.request(method, f"/internal/bot/{path}", **kwargs)
        response.raise_for_status()
        return response.json()
