from datetime import datetime, timezone
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.methods import TelegramMethod
from aiogram.types import Chat, Message, Update, User

from tg_bot.config import Settings
from tg_bot.handlers import create_router
from tg_bot.locales import t
from tg_bot.models import Database
from tg_bot.repositories import SqlCatalogRepository
from tg_bot.services import ImporterService


class CaptureSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def close(self):
        self.calls.clear()

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout=None) -> Any:
        self.calls.append(method)
        if method.__api_method__ == "answerCallbackQuery":
            return True
        return Message(
            message_id=1000 + len(self.calls),
            date=datetime.now(timezone.utc),
            chat=Chat(id=42, type="private"),
            from_user=User(id=bot.id, is_bot=True, first_name="Bot"),
            text=getattr(method, "text", "") or "",
        )

    async def stream_content(
        self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True
    ):
        for chunk in ():
            yield chunk
        raise RuntimeError("Network disabled in dispatcher tests")


@pytest.mark.asyncio
async def test_start_language_search_deeplink_and_unsubscribe(tmp_path):
    import json

    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'bot.db'}")
    await db.create_tables()
    transport = CaptureSession()
    bot = Bot("123456:offline-test-token", session=transport)
    settings = Settings(
        bot_token="123456:offline-test-token",
        webapp_url="https://example.invalid/webapp",
        _env_file=None,
    )
    dp = Dispatcher(
        storage=MemoryStorage(),
        events_isolation=SimpleEventIsolation(),
        database=db,
        settings=settings,
        agent=None,
    )
    dp.include_router(create_router())
    update_id = 0

    async def message(text):
        nonlocal update_id
        update_id += 1
        msg = Message(
            message_id=update_id,
            date=datetime.now(timezone.utc),
            chat=Chat(id=42, type="private"),
            from_user=User(id=42, is_bot=False, first_name="Private test name"),
            text=text,
        )
        await dp.feed_update(bot, Update(update_id=update_id, message=msg))

    async def callback(data):
        nonlocal update_id
        update_id += 1
        await dp.feed_update(
            bot,
            Update.model_validate(
                {
                    "update_id": update_id,
                    "callback_query": {
                        "id": str(update_id),
                        "from": {"id": 42, "is_bot": False, "first_name": "Private test name"},
                        "chat_instance": "test",
                        "data": data,
                        "message": {
                            "message_id": 1,
                            "date": int(datetime.now().timestamp()),
                            "chat": {"id": 42, "type": "private"},
                            "from": {"id": 123456, "is_bot": True, "first_name": "Bot"},
                            "text": "menu",
                        },
                    },
                }
            ),
        )

    try:
        def callbacks():
            return [
                button.callback_data
                for row in transport.calls[-1].reply_markup.inline_keyboard
                for button in row
            ]

        await message("/start")
        sent = transport.calls[-1]
        assert "агрегатор" in sent.text
        assert all(
            button.web_app is None for row in sent.reply_markup.inline_keyboard for button in row
        )
        await callback("lang:ba")
        assert "languages" in callbacks()
        await callback("languages")
        assert "menu" in callbacks()
        await callback("menu")
        await callback("catalog")
        assert "menu" in callbacks()
        await callback("filters")
        assert "results" in callbacks()
        await callback("filter:category")
        assert "filters" in callbacks()
        await callback("filters")
        await callback("filter:date")
        assert callbacks() == ["filters"]
        await message("неверная дата")
        assert callbacks() == ["filters"]
        await callback("filters")
        await callback("results")
        await callback("subscribe:filters")
        assert callbacks() == ["results"]
        await callback("menu")
        await callback("subscriptions")
        assert "menu" in callbacks()
        async with db.sessions() as session:
            repo = SqlCatalogRepository(session)
            assert await repo.get_lang("42") == "ba"
            await repo.subscribe("42", "Уфа", "концерт")
            await repo.subscribe("43", "Уфа", "концерт")
            report = await ImporterService(session).import_bytes(
                json.dumps(
                    [
                        {
                            "id": "d0000000-0000-4000-8000-000000000015",
                            "title": "Cancelled <unsafe> concert",
                            "category": "концерт",
                            "date_start": "2099-01-01T18:00:00+05:00",
                            "city": "Уфа",
                            "venue": "Venue",
                            "address": "Address",
                            "description": "Description",
                            "price_min": 0,
                            "source_url": "https://example.invalid/event",
                            "status": "отменено",
                        }
                    ]
                ).encode(),
                "test.json",
            )
            assert report.added == 1
        await message("/start event_d0000000-0000-4000-8000-000000000015")
        card = "\n".join(getattr(call, "text", "") or "" for call in transport.calls[-3:])
        assert t("bot.event_cancelled", "ba") in card
        assert "&lt;unsafe&gt;" in card
        assert "menu" in callbacks()
        await message("/start d0000000-0000-4000-8000-000000000015")
        assert "&lt;unsafe&gt;" in transport.calls[-1].text
        await callback("event:d0000000-0000-4000-8000-000000000015")
        assert "results" in callbacks()
        await message("/unsubscribe")
        async with db.sessions() as session:
            repo = SqlCatalogRepository(session)
            assert await repo.list_subscriptions("42") == []
            assert len(await repo.list_subscriptions("43")) == 1
        await message("/help")
        assert "/cancel" in transport.calls[-1].text
        assert callbacks() == ["menu"]
        await callback("period:weekend")
        assert any(
            "results" in type(call).__name__.lower()
            or t("bot.results", "ba", total=0, page=1, pages=1) in str(getattr(call, "text", ""))
            for call in transport.calls
        )
    finally:
        await dp.storage.close()
        await dp.fsm.events_isolation.close()
        await bot.session.close()
        await db.close()
