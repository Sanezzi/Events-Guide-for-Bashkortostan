import json
from datetime import datetime, timedelta

import pytest

from contour import collect
from contour.parser import TZ, event_page_links, parse_event_page


def test_parser_extracts_event_metadata_and_resolves_links():
    now = datetime(2026, 11, 14, tzinfo=TZ)
    item = {
        "@type": "TheaterEvent", "name": "Детский спектакль 6+",
        "startDate": (now + timedelta(days=2)).isoformat(),
        "description": "<p>Кукольная сказка для всей семьи.</p>",
        "url": "/afisha/skazka",
        "location": {"name": "Театр", "address": {
            "addressLocality": "Стерлитамак", "streetAddress": "ул. Ленина, 1"}},
        "offers": [{"price": "300", "priceCurrency": "RUB", "url": "/tickets/skazka"}],
    }
    page = f'<script type="application/ld+json">{json.dumps(item)}</script>'
    result = parse_event_page(page, "https://theatre.example/afisha", now=now)
    event, = result
    assert event["age_limit"] == 6 and event["status"] == "черновик"
    assert {"6+", "семейное", "кукольный театр"} <= set(event["tags"])
    assert event["source_url"] == "https://theatre.example/afisha/skazka"
    assert event["org_link"] == "https://theatre.example/tickets/skazka"
    item["startDate"] = (now + timedelta(days=2, microseconds=987)).isoformat()
    repeated = f'<script type="application/ld+json">{json.dumps(item)}</script>'
    assert parse_event_page(repeated, "https://theatre.example/afisha", now=now)[0]["id"] == event["id"]
    item["eventStatus"] = "https://schema.org/EventCancelled"
    cancelled = f'<script type="application/ld+json">{json.dumps(item)}</script>'
    assert parse_event_page(cancelled, "https://theatre.example/afisha", now=now) == []


def test_listing_discovers_local_event_pages_only():
    raw = """<a href="/afisha/skazka">Сказка</a>
             <a href="https://[bad/afisha/broken">Сломанная ссылка</a>
             <a href="https://elsewhere.example/afisha/show">Другой сайт</a>
             <a href="/about">О театре</a>"""
    assert event_page_links(raw, "https://theatre.example/afisha") == [
        "https://theatre.example/afisha/skazka"
    ]
