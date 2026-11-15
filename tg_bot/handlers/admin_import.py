"""Authorized document imports with bounded in-memory downloads."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import PurePath

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from tg_bot.handlers.start import html, language, respond, send_long
from tg_bot.keyboards.inline import back_keyboard
from tg_bot.locales import t
from tg_bot.services.importer import ImporterService
from tg_bot.backend_client import BackendClient

MAX_IMPORT_BYTES = 5 * 1024 * 1024


def import_reason(error: dict, lang: str) -> str:
    if error.get("code") == "invalid_file":
        return t("bot.import_invalid_file", lang)
    reason = t("bot.import_invalid_row", lang)
    field_keys = {
        "title": "bot.query",
        "category": "bot.category",
        "date_start": "bot.date",
        "date_end": "bot.date",
        "city": "bot.city",
        "address": "bot.address",
        "description": "bot.description",
        "price_min": "bot.price",
        "price_max": "bot.price",
        "age_limit": "bot.age",
        "language": "bot.event_language",
        "source_url": "bot.source",
        "org_link": "bot.tickets",
    }
    fields = []
    for part in str(error.get("message", "")).split("; "):
        match = re.fullmatch(r"([a-z_]+)(?:\.[\w]+)*: ([a-z_]+)", part)
        if match and match[1] in field_keys:
            label = t(field_keys[match[1]], lang)
            if label not in fields:
                fields.append(label)
    return reason + (": " + ", ".join(fields) if fields else "")


class ImportFlow(StatesGroup):
    document = State()
