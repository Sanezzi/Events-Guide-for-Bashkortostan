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


async def run() -> None:
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required in the environment or .env")
    database = (BackendClient(settings.backend_url, settings.internal_api_token)
                if settings.backend_url else Database(settings.database_url))
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    agent = database if isinstance(database, BackendClient) else None
    dispatcher = Dispatcher(
        storage=MemoryStorage(),
        events_isolation=SimpleEventIsolation(),
        database=database,
        settings=settings,
        agent=agent,
    )
    dispatcher.update.outer_middleware(TraceMiddleware())
    dispatcher.include_router(create_router())
    notifier = None
    try:
        if isinstance(database, Database):
            await database.create_tables()
        if settings.seed_sample and isinstance(database, Database):
            sample = Path(__file__).parent / "data" / "sample_events.json"
            async with database.sessions() as session:
                report = await ImporterService(session).import_bytes(
                    sample.read_bytes(), sample.name, actor="seed"
                )
                if report.rejected:
                    raise RuntimeError("Sample import failed")
            logger.info("demo_catalog_ready", extra={"event": "demo_catalog_ready"})
        await bot.delete_webhook(drop_pending_updates=False)
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Главное меню / Төп меню / Menu"),
                BotCommand(command="ai", description="ИИ-помощник / ЯИ ярҙамсыһы / AI assistant"),
                BotCommand(
                    command="search", description="Поиск событий / Сараларҙы эҙләү / Search"
                ),
                BotCommand(
                    command="subscriptions", description="Мои подписки / Яҙылыуҙар / Subscriptions"
                ),
                BotCommand(
                    command="unsubscribe",
                    description="Удалить подписки / Яҙылыуҙы бөтөрөү / Unsubscribe",
                ),
                BotCommand(command="help", description="Помощь / Ярҙәм / Help"),
                BotCommand(command="cancel", description="Отмена / Баш тартыу / Cancel"),
            ]
        )
        logger.info("bot_ready", extra={"event": "bot_ready"})
        if agent is not None:
            notifier = asyncio.create_task(send_notifications(bot, agent))
        await dispatcher.start_polling(
            bot, close_bot_session=False, allowed_updates=dispatcher.resolve_used_update_types()
        )
    finally:
        if notifier:
            notifier.cancel()
            with suppress(asyncio.CancelledError):
                await notifier
        await dispatcher.storage.close()
        await dispatcher.fsm.events_isolation.close()
        await bot.session.close()
        await database.close()


async def send_notifications(bot, backend):
    while True:
        try:
            pending = await backend.request("GET", "notifications")
            for digest in pending:
                user_id = digest["user_id"]
                try:
                    me = await bot.me()
                    lines = [f'<a href="https://t.me/{me.username}?start=event_{event["id"]}">{escape(event["title"])}</a>'
                             for event in digest["events"]]
                    await bot.send_message(
                        int(user_id), "Новые события по подписке:\n" + "\n".join(lines),
                        reply_markup=back_keyboard(await backend.get_lang(str(user_id))),
                    )
                except TelegramForbiddenError:
                    await backend.unsubscribe(user_id, digest["id"])
                    continue
                await backend.request("POST", "notifications/delivered", json={
                    "user_id": user_id, "subscription_id": digest["id"], "through": digest["through"]})
        except Exception as exc:
            logger.warning("notification_cycle_failed", extra={"error_type": type(exc).__name__})
        await asyncio.sleep(300)


def main() -> None:
    configure_logging()
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("shutdown", extra={"event": "shutdown"})
    except Exception as exc:
        logger.error(
            "startup_failed", extra={"event": "startup_failed", "error_type": type(exc).__name__}
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
