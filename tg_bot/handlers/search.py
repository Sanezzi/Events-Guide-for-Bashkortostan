"""Catalog search, persistent filters, event cards and optional agent dialogue."""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import get_args
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from pydantic import ValidationError

from tg_bot.handlers.start import answer_callback, html, language, respond, send_long
from tg_bot.keyboards.inline import (
    back_keyboard,
    back_row,
    button,
    categories_keyboard,
    category_label,
    event_keyboard,
    filters_keyboard,
    results_keyboard,
)
from tg_bot.locales import t
from tg_bot.models.schemas import Category, SearchFilters
from tg_bot.backend_client import repository
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from tg_bot.services.bot_service import BotService


class SearchFlow(StatesGroup):
    value = State()


class AgentFlow(StatesGroup):
    query = State()


FILTER_KEYS = {
    "q": "bot.query",
    "city": "bot.city",
    "category": "bot.category",
    "date": "bot.date",
    "max_price": "bot.max_price",
}
