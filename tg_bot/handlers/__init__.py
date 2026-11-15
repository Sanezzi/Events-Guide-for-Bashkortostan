"""Build a fresh aiogram router with application dependencies supplied by DI."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent, Message

from tg_bot.handlers import admin_import, search, start, subscriptions
from tg_bot.keyboards.inline import back_keyboard
from tg_bot.locales import t

logger = logging.getLogger(__name__)


def create_router() -> Router:
    router = Router(name="culture_bot")
    router.include_routers(
        start.create_router(),
        subscriptions.create_router(),
        admin_import.create_router(),
        search.create_router(),
    )

    @router.errors()
    async def handle_error(event: ErrorEvent, database=None):
        # Never include exception messages, update contents, identities or tokens.
        logger.error(
            "bot_handler_error",
            extra={"event": "bot_handler_error", "error_type": type(event.exception).__name__},
        )
        update = event.update
        query = update.callback_query
        message = query.message if query else update.message
        user = (
            query.from_user
            if query
            else (message.from_user if isinstance(message, Message) else None)
        )
        if query:
            await start.answer_callback(query)
        lang = "ru"
        if database is not None and user is not None:
            try:
                lang = await start.language(database, user.id)
            except Exception as exc:
                logger.warning(
                    "language_lookup_failed",
                    extra={"event": "language_lookup_failed", "error_type": type(exc).__name__},
                )
        if isinstance(message, Message):
            try:
                await start.respond(message, start.html(t("bot.error", lang)), back_keyboard(lang))
            except TelegramAPIError as exc:
                logger.warning(
                    "telegram_reply_failed",
                    extra={"event": "telegram_reply_failed", "error_type": type(exc).__name__},
                )
        return True

    return router
