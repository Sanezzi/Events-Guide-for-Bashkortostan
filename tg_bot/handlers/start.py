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


async def respond(
    target: Message | CallbackQuery, text: str, reply_markup=None, *, edit: bool = False
) -> None:
    message = target.message if isinstance(target, CallbackQuery) else target
    if not isinstance(message, Message):
        return
    kwargs = dict(parse_mode="HTML", link_preview_options={"is_disabled": True})
    if edit:
        try:
            await message.edit_text(text, reply_markup=reply_markup, **kwargs)
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return
        except TelegramForbiddenError:
            return
    try:
        await message.answer(text, reply_markup=reply_markup, **kwargs)
    except TelegramRetryAfter as exc:
        if exc.retry_after > 30:
            raise
        await asyncio.sleep(exc.retry_after)
        await message.answer(text, reply_markup=reply_markup, **kwargs)


async def send_long(target: Message | CallbackQuery, text: str, reply_markup=None) -> None:
    # Split raw text BEFORE escaping so HTML entities/tags cannot be truncated.
    chunks = []
    remaining = text
    while remaining:
        # Respect both escaped payload size and Telegram UTF-16 text limits.
        low, high = 1, min(len(remaining), 3900)
        while low < high:
            middle = (low + high + 1) // 2
            prefix = remaining[:middle]
            if len(html(prefix)) <= 3900 and len(prefix.encode("utf-16-le")) // 2 <= 3900:
                low = middle
            else:
                high = middle - 1
        size = low
        if size < len(remaining):
            boundary = remaining.rfind("\n", 0, size)
            if boundary > size // 2:
                size = boundary + 1
        chunks.append(remaining[:size])
        remaining = remaining[size:]
    for index, chunk in enumerate(chunks or [""]):
        await respond(
            target, html(chunk), reply_markup=reply_markup if index == len(chunks) - 1 else None
        )


async def show_menu(target, database, *, edit=False) -> None:
    lang = await language(database, target.from_user.id)
    text = t("bot.welcome", lang)
    await respond(target, html(text), menu_keyboard(lang), edit=edit)


def create_router() -> Router:
    router = Router(name="start")

    @router.message(CommandStart())
    async def start(
        message: Message, command: CommandObject, state: FSMContext, database, settings
    ):
        await state.clear()
        payload = command.args or ""
        if payload.startswith("event_") or len(payload) == 36:
            from tg_bot.handlers.search import show_event

            try:
                event_id = UUID(payload.removeprefix("event_"))
            except ValueError:
                lang = await language(database, message.from_user.id)
                await respond(message, html(t("bot.not_found", lang)), back_keyboard(lang))
                return
            await show_event(message, database, event_id, settings)
            return
        await show_menu(message, database)

    @router.message(Command("help"))
    async def help_command(message: Message, database):
        lang = await language(database, message.from_user.id)
        await respond(message, html(t("bot.help", lang)), back_keyboard(lang))

    @router.message(Command("cancel"))
    async def cancel(message: Message, state: FSMContext, database):
        await state.clear()
        lang = await language(database, message.from_user.id)
        await respond(
            message, html(t("bot.cancelled", lang)), back_keyboard(lang)
        )

    @router.callback_query(F.data == "menu")
    async def menu(query: CallbackQuery, state: FSMContext, database):
        await answer_callback(query)
        await state.set_state(None)
        await state.update_data(agent_confirmation=None)
        await show_menu(query, database, edit=True)
