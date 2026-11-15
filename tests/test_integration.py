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


def test_venue_dictionary_and_combined_catalog_filters(client):
    now = datetime.now(timezone.utc)
    rows = [
        dict(title=title, city=city, venue=venue, age_limit=age, category="концерт",
             address="Адрес", description="Проверка", price_min=price,
             date_start=(now + timedelta(days=days)).isoformat(),
             status=status, source_url=f"https://example.invalid/{i}")
        for i, (title, city, venue, age, price, days, status) in enumerate([
            ("Концерт А", "Уфа", "Зал А", 6, 100, 2, "опубликовано"),
            ("Концерт Б", "Уфа", "Зал А", 0, 200, 2, "опубликовано"),
            ("Концерт В", "Уфа", "Зал Б", 12, 300, 3, "опубликовано"),
            ("Концерт Г", "Стерлитамак", "Зал В", 0, 0, 2, "опубликовано"),
            ("Концерт Д", "Уфа", "Архив", 0, 0, -2, "опубликовано"),
            ("Концерт Е", "Уфа", "Черновик", 0, 0, 2, "черновик"),
            ("Концерт Ж", "Уфа", "Отмена", 0, 0, 2, "отменено"),
        ])
    ]
    result = client.post("/api/v1/admin/import", headers={"X-Admin-Token": "test-admin"},
                         files={"file": ("events.json", json.dumps(rows))})
    assert result.json()["added"] == 7
    assert client.get("/api/v1/venues").json() == {"venues": ["Зал А", "Зал Б", "Зал В"]}
    assert client.get("/api/v1/venues", params={"city": "уфа"}).json() == {"venues": ["Зал А", "Зал Б"]}
    assert client.get("/api/v1/venues", params={"city": "Салават"}).json() == {"venues": []}
    params = dict(city="Уфа", venue="Зал А", category="концерт", text="Концерт",
                  age_limit=6, price_max=200, date_to=(now + timedelta(days=2, hours=1)).isoformat(),
                  sort="price_max_desc", limit=1)
    first = client.get("/api/v1/events", params=params).json()
    second = client.get("/api/v1/events", params={**params, "offset": 1}).json()
    assert first["total"] == second["total"] == 2
    assert [first["events"][0]["title"], second["events"][0]["title"]] == ["Концерт Б", "Концерт А"]
    free = client.get("/api/v1/events", params={"is_free": True}).json()["events"]
    assert [row["title"] for row in free] == ["Концерт Г"]


def test_family_search_offers_alternative_cities_without_relaxing_age(client):
    start = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    rows = [
        dict(title="Спектакль", city=city, age_limit=age, category="спектакль",
             venue="Зал", address="Адрес", description="Событие",
             price_min=100, date_start=start, source_url=f"https://example.invalid/{i}")
        for i, (city, age) in enumerate([("Стерлитамак", 16), ("Уфа", 6), ("Бирск", 12)])
    ]
    uploaded = client.post("/api/v1/admin/import", headers={"X-Admin-Token": "test-admin"},
                           files={"file": ("events.json", json.dumps(rows))})
    assert uploaded.json()["added"] == 3
    result = client.post("/api/chat", json={"session_id": "family",
        "message": "Привет, куда сходить в Стерлитамаке с ребёнком 6 лет?"}).json()
    assert "в других городах" in result["reply_text"]
    assert [(e["city"], e["age_limit"]) for e in result["events"]] == [("Уфа", 6)]


def test_new_city_overview_drops_previous_category(client):
    event = dict(title="Концерт в Уфе", city="Уфа", category="концерт", venue="Зал",
                 address="Адрес", description="Событие", price_min=100, age_limit=6,
                 date_start=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                 source_url="https://example.invalid/ufa")
    uploaded = client.post("/api/v1/admin/import", headers={"X-Admin-Token": "test-admin"},
                           files={"file": ("events.json", json.dumps([event]))})
    assert uploaded.json()["added"] == 1
    session = {"session_id": "switch-city"}
    first = client.post("/api/chat", json={**session, "message": "Какие экскурсии есть в Стерлитамаке?"})
    assert first.status_code == 200 and not first.json()["events"]
    next_city = client.post("/api/chat", json={**session, "message": "Куда сходить в Уфе?"})
    assert next_city.status_code == 200
    assert [row["title"] for row in next_city.json()["events"]] == [event["title"]]
