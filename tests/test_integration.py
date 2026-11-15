from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import pytest
import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Chat, Message, Update, User
from fastapi.testclient import TestClient

from app.main import app
from tg_bot.backend_client import BackendClient
from tg_bot.config import Settings
from tg_bot.handlers import create_router
from tg_bot.tests.test_bot import CaptureSession


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'catalog.db'}")
    monkeypatch.setenv("SEED_CONFIRMED_EVENTS", "0")
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin")
    monkeypatch.setenv("INTERNAL_API_TOKEN", "test-bot")
    monkeypatch.setenv("SESSION_SECRET", "test-session-identity")
    monkeypatch.setenv("LLM_API_KEY", "")
    with TestClient(app) as client:
        yield client


def test_broad_request_lists_events_across_bashkortostan(client):
    rows = [
        dict(title="Концерт", city=city, age_limit=6, category="концерт", venue="Зал",
             address="Адрес", description="Событие", price_min=100,
             date_start=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
             source_url=f"https://example.invalid/{i}")
        for i, city in enumerate(("Уфа", "Стерлитамак"))
    ]
    uploaded = client.post("/api/v1/admin/import", headers={"X-Admin-Token": "test-admin"},
                           files={"file": ("events.json", json.dumps(rows))})
    assert uploaded.json()["added"] == 2
    for text in ("Куда сходить?", "Куда пойти"):
        response = client.post("/api/chat", json={"session_id": "broad", "message": text})
        assert response.status_code == 200
        data = response.json()
        assert not data["clarifying_question"]
        assert not data["is_fallback"]
        assert {event["city"] for event in data["events"]} == {"Уфа", "Стерлитамак"}


def test_organizer_proposals_require_moderation_and_resist_duplicates(client):
    card = dict(title="Предложение организатора", category="спектакль", city="Уфа",
                address="Улица 1", venue="Сцена", description="Описание",
                date_start=(datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                age_limit=6, price_min=150, source_url="https://organizer.example/event")
    endpoint = "/api/v1/event-submissions"
    assert client.post(endpoint, json={"event": card, "website": "spam"}).status_code == 422
    assert client.post(endpoint, json={"event": {**card, "source_url": "javascript:bad"}}).status_code == 422
    response = client.post(endpoint, json={"event": card})
    assert response.status_code == 201
    event_id = response.json()["id"]
    assert client.get(f"/api/v1/events/{event_id}").status_code == 404
    assert client.post(endpoint, json={"event": card}).status_code == 409
    headers = {"X-Admin-Token": "test-admin"}
    response = client.get("/api/v1/admin/events?status=черновик", headers=headers)
    assert [event["id"] for event in response.json()] == [event_id]
    assert client.patch(f"/api/v1/admin/events/{event_id}/status", headers=headers,
                        json={"status": "опубликовано"}).status_code == 200
    assert client.post("/api/v1/feedback", json={"event_id": event_id, "text": "Новое время"}).status_code == 200
