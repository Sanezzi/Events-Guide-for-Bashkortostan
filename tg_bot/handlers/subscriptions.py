"""User-owned city/category subscriptions."""

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
