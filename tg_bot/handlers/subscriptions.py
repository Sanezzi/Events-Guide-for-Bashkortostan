from __future__ import annotations

from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from tg_bot.handlers.start import answer_callback, html, language, respond
from tg_bot.keyboards.inline import back_keyboard, category_label, subscriptions_keyboard
from tg_bot.locales import t
from tg_bot.backend_client import repository


async def show_subscriptions(target, database, *, edit=False, page=1, removed=None):
    lang = await language(database, target.from_user.id)
    async with repository(database) as repo:
        subscriptions = await repo.list_subscriptions(
            str(target.from_user.id)
        )
    total = len(subscriptions)
    page = max(1, min(page, max(1, (total + 9) // 10)))
    selected = subscriptions[(page - 1) * 10 : page * 10]
    lines = [t("bot.subscriptions", lang) if subscriptions else t("bot.no_subscriptions", lang)]
    if removed is not None:
        lines.insert(0, t("bot.removed", lang, count=removed))
    for subscription in selected:
        lines.append(
            t(
                "bot.subscription_item",
                lang,
                id=subscription.id,
                city=subscription.city or t("bot.any", lang),
                category=category_label(subscription.category, lang)
                if subscription.category
                else t("bot.any", lang),
            )
        )
    await respond(
        target,
        html("\n".join(lines)),
        subscriptions_keyboard(lang, selected, page, total),
        edit=edit,
    )


def create_router() -> Router:
    router = Router(name="subscriptions")

    @router.message(Command("subscriptions"))
    async def list_command(message: Message, state: FSMContext, database):
        await state.set_state(None)
        await show_subscriptions(message, database)

    @router.callback_query(F.data == "subscriptions")
    async def list_callback(query: CallbackQuery, state: FSMContext, database):
        await answer_callback(query)
        await state.set_state(None)
        await show_subscriptions(query, database, edit=True)

    @router.callback_query(F.data.startswith("subpage:"))
    async def subscription_page(query: CallbackQuery, database):
        await answer_callback(query)
        try:
            page = int(query.data.split(":", 1)[1])
        except ValueError:
            return
        await show_subscriptions(query, database, edit=True, page=page)

    @router.callback_query(F.data.startswith("subscribe:"))
    async def subscribe(query: CallbackQuery, state: FSMContext, database):
        await answer_callback(query)
        lang = await language(database, query.from_user.id)
        argument = query.data.split(":", 1)[1]
        screen, separator, identifier = argument.partition(":")
        back = "results"
        async with repository(database) as repo:
            if argument == "filters":
                data = await state.get_data()
                values = data.get("filters", {})
                city, category = values.get("city"), values.get("category")
            else:
                try:
                    event = await repo.get_event(UUID(identifier if separator else argument))
                except ValueError:
                    event = None
                if event is None:
                    await respond(query, html(t("bot.not_found", lang)), back_keyboard(lang, back), edit=True)
                    return
                if not separator or screen not in {"event", "open-event", "agent-event", "agent-summary"}:
                    screen = "event"
                back = f"{screen}:{event.id}"
                city, category = event.city, event.category
            await repo.subscribe(str(query.from_user.id), city, category)
        await respond(query, html(t("bot.subscribed", lang)), back_keyboard(lang, back), edit=True)

    @router.callback_query(F.data.startswith("unsubscribe:"))
    async def unsubscribe_callback(query: CallbackQuery, database):
        await answer_callback(query)
        argument = query.data.split(":", 1)[1]
        try:
            subscription_id = None if argument == "all" else int(argument)
            if subscription_id is not None and subscription_id <= 0:
                return
        except ValueError:
            return
        async with repository(database) as repo:
            count = await repo.unsubscribe(
                str(query.from_user.id), subscription_id
            )
        await show_subscriptions(query, database, edit=True, removed=count)

    @router.message(Command("unsubscribe"))
    async def unsubscribe_command(
        message: Message, command: CommandObject, state: FSMContext, database
    ):
        await state.set_state(None)
        argument = (command.args or "all").strip() or "all"
        if argument:
            try:
                subscription_id = None if argument.lower() == "all" else int(argument)
                if subscription_id is not None and subscription_id <= 0:
                    raise ValueError
            except ValueError:
                await show_subscriptions(message, database)
                return
            async with repository(database) as repo:
                count = await repo.unsubscribe(
                    str(message.from_user.id), subscription_id
                )
        await show_subscriptions(message, database, removed=count)

    return router
