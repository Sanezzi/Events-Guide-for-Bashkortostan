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


class LimitedBuffer(BytesIO):
    def write(self, data):
        if self.tell() + len(data) > MAX_IMPORT_BYTES:
            raise ValueError("import exceeds size limit")
        return super().write(data)


def create_router() -> Router:
    router = Router(name="admin_import")

    @router.message(Command("import"))
    async def request_import(message: Message, state: FSMContext, database, settings):
        lang = await language(database, message.from_user.id)
        if message.from_user.id not in settings.admin_ids:
            await respond(message, html(t("bot.import_denied", lang)), back_keyboard(lang))
            return
        await state.set_state(ImportFlow.document)
        await respond(message, html(t("bot.import_prompt", lang)), back_keyboard(lang))

    @router.message(F.document)
    async def import_document(message: Message, state: FSMContext, database, settings):
        lang = await language(database, message.from_user.id)
        if message.from_user.id not in settings.admin_ids:
            await respond(message, html(t("bot.import_denied", lang)), back_keyboard(lang))
            return
        document = message.document
        filename = PurePath(document.file_name or "").name
        if PurePath(filename).suffix.lower() not in {".csv", ".json"}:
            await respond(message, html(t("bot.import_file_type", lang)), back_keyboard(lang))
            return
        if document.file_size is not None and document.file_size > MAX_IMPORT_BYTES:
            await respond(message, html(t("bot.import_too_large", lang)), back_keyboard(lang))
            return
        buffer = LimitedBuffer()
        try:
            await message.bot.download(document.file_id, destination=buffer, timeout=30)
            data = buffer.getvalue()
        except ValueError:
            await respond(message, html(t("bot.import_too_large", lang)), back_keyboard(lang))
            return
        finally:
            buffer.close()
        if isinstance(database, BackendClient):
            report = await database.import_bytes(data, filename, actor=str(message.from_user.id))
        else:
            async with database.sessions() as session:
                report = await ImporterService(session).import_bytes(
                    data, filename, actor=f"telegram:{message.from_user.id}"
                )
        await state.set_state(None)
        await respond(
            message,
            html(
                t(
                    "bot.import_report",
                    lang,
                    added=report.added,
                    updated=report.updated,
                    rejected=report.rejected,
                    unchanged=report.unchanged,
                )
            ),
            back_keyboard(lang),
        )
        if report.errors:
            details = "\n".join(
                t(
                    "bot.import_row_error",
                    lang,
                    row=error.get("row", "?"),
                    reason=import_reason(error, lang),
                )
                for error in report.errors[:20]
            )
            await send_long(message, t("bot.import_errors", lang) + "\n" + details, back_keyboard(lang))

    @router.message(ImportFlow.document, ~F.text.startswith("/"))
    async def expect_document(message: Message, database):
        lang = await language(database, message.from_user.id)
        await respond(message, html(t("bot.import_prompt", lang)), back_keyboard(lang))

    return router
