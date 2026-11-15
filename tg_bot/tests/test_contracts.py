"""Cross-layer contracts that must remain stable when merging this package."""

import json
from pathlib import Path
from string import Formatter

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from tg_bot.locales import load_locale
from tg_bot.models import AuditLog, Database, Subscription, UserSettings
from tg_bot.models.schemas import EventInput, SearchFilters
from tg_bot.repositories import SqlCatalogRepository
from tg_bot.services import ImporterService


def test_locale_key_and_placeholder_parity():
    dictionaries = [load_locale(lang) for lang in ("ru", "ba", "en")]
    assert len(dictionaries[0]) > 250
    assert all(set(dictionary) == set(dictionaries[0]) for dictionary in dictionaries)
    for key in dictionaries[0]:
        placeholders = [
            {field for _, field, _, _ in Formatter().parse(dictionary[key]) if field}
            for dictionary in dictionaries
        ]
        assert all(fields == placeholders[0] for fields in placeholders), key


def test_explicit_price_and_shared_identity_schema():
    row = json.loads((Path(__file__).parents[1] / "data" / "sample_events.json").read_text(encoding="utf-8"))[0]
    row.pop("price_min")
    with pytest.raises(ValidationError):
        EventInput.model_validate(row)
    assert "tg_user_id" in UserSettings.__table__.c
    assert "tg_user_id" in Subscription.__table__.c
