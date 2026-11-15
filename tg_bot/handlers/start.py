"""Entry commands and shared safe Telegram response helpers."""

from __future__ import annotations

import asyncio
import logging
from html import escape
from uuid import UUID

from aiogram import F, Router
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from tg_bot.keyboards.inline import back_keyboard, language_keyboard, menu_keyboard
from tg_bot.locales import t
from tg_bot.backend_client import repository

logger = logging.getLogger(__name__)


def html(value: object) -> str:
    return escape(str(value), quote=True)


async def language(database, user_id: int) -> str:
    async with repository(database) as repo:
        value = await repo.get_lang(str(user_id))
    return value if value in {"ru", "ba", "en"} else "ru"


async def answer_callback(query: CallbackQuery, text: str | None = None) -> None:
    try:
        await query.answer(text=text)
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError):
        # Expired callbacks are normal; never log update bodies or user identifiers.
        return
