"""Standalone Telegram polling bot: python -m tg_bot.main."""

import asyncio
import logging
from contextlib import suppress
from pathlib import Path

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.types import BotCommand, MenuButtonCommands
from aiogram.exceptions import TelegramForbiddenError
from html import escape

from tg_bot.config import get_settings
from tg_bot.backend_client import BackendClient
from tg_bot.handlers import create_router
from tg_bot.keyboards.inline import back_keyboard
from tg_bot.logging_config import configure_logging, new_request_id, request_id
from tg_bot.models import Database
from tg_bot.services import ImporterService

logger = logging.getLogger(__name__)


class TraceMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        marker = request_id.set(new_request_id())
        try:
            return await handler(event, data)
        finally:
            request_id.reset(marker)
