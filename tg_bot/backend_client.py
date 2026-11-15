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

    async def search(self, filters: SearchFilters):
        return SearchResult.model_validate(await self.request("POST", "search",
            json=filters.model_dump(mode="json", exclude_none=True)))

    async def get_event(self, event_id: UUID):
        result = await self.request("GET", f"events/{event_id}")
        return EventOut.model_validate(result) if result else None

    async def get_lang(self, user_id):
        return await self.request("POST", "language", json={"user_id": user_id})

    async def set_lang(self, user_id, lang):
        await self.request("PUT", "language", json={"user_id": user_id, "lang": lang})

    async def subscribe(self, user_id, city=None, category=None):
        row = await self.request("POST", "subscriptions", json={
            "user_id": user_id, "city": city, "category": category})
        return SimpleNamespace(**row)

    async def list_subscriptions(self, user_id):
        rows = await self.request("POST", "subscriptions/list", json={"user_id": user_id})
        return [SimpleNamespace(**row) for row in rows]

    async def unsubscribe(self, user_id, subscription_id=None):
        return await self.request("POST", "subscriptions/delete", json={
            "user_id": user_id, "subscription_id": subscription_id})

    async def import_bytes(self, data, filename, *, actor):
        return ImportReport.model_validate(await self.request("POST", "import", content=data,
            params={"filename": filename, "actor": actor}))
