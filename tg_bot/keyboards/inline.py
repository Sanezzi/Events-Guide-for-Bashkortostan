"""Localized Telegram inline keyboards; callback payloads contain IDs only."""

from __future__ import annotations

from typing import get_args
from urllib.parse import urlparse

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from tg_bot.locales import t
from tg_bot.models.schemas import Category

CATEGORY_KEYS = {
    "концерт": "concert",
    "спектакль": "theatre",
    "выставка": "exhibition",
    "фестиваль": "festival",
    "кино": "cinema",
    "экскурсия": "excursion",
    "другое": "other",
}


def category_label(value: str, lang: str) -> str:
    return t(CATEGORY_KEYS.get(value, value), lang)


def categories_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=category_label(value, lang), callback_data=f"category:{index}")]
        for index, value in enumerate(get_args(Category))
    ]
    rows.append([button("bot.any", lang, "category:all")])
    rows.append(back_row(lang, "filters"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def button(key: str, lang: str, data: str) -> InlineKeyboardButton:
    if len(data.encode("utf-8")) > 64:
        raise ValueError("callback payload exceeds Telegram limit")
    return InlineKeyboardButton(text=t(key, lang), callback_data=data)


def back_row(lang: str, callback: str = "menu") -> list[InlineKeyboardButton]:
    return [button("bot.back", lang, callback)]


def back_keyboard(lang: str, callback: str = "menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[back_row(lang, callback)])


def https_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value)
        return (
            value if parsed.scheme == "https" and parsed.hostname and not parsed.username else None
        )
    except ValueError:
        return None


def external_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value)
        return (
            value
            if parsed.scheme in {"https", "http"} and parsed.hostname and not parsed.username
            else None
        )
    except ValueError:
        return None


def menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [button("bot.agent", lang, "agent")],
        [button("bot.catalog", lang, "catalog"), button("bot.subscriptions", lang, "subscriptions")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def language_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
                InlineKeyboardButton(text="🟢 Башҡортса", callback_data="lang:ba"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
            ],
            back_row(lang),
        ]
    )


def filters_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                button("bot.query", lang, "filter:q"),
                button("bot.city", lang, "filter:city"),
                button("bot.category", lang, "filter:category"),
            ],
            [
                button("bot.today", lang, "period:today"),
                button("bot.tomorrow", lang, "period:tomorrow"),
            ],
            [
                button("bot.weekend", lang, "period:weekend"),
                button("bot.week", lang, "period:week"),
            ],
            [
                button("bot.date", lang, "filter:date"),
                button("bot.max_price", lang, "filter:max_price"),
            ],
            [
                button("bot.free", lang, "toggle:free"),
                button("bot.bashkir", lang, "toggle:bashkir"),
            ],
            [button("bot.reset_filters", lang, "filters:reset")],
            back_row(lang, "results"),
        ]
    )


def results_keyboard(
    lang: str, items: list, page: int, total: int, page_size: int
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=str(event.title)[:80], callback_data=f"event:{event.id}")]
        for event in items
    ]
    navigation = []
    if page > 1:
        navigation.append(InlineKeyboardButton(text=f"‹ {page - 1}", callback_data=f"page:{page - 1}"))
    if page * page_size < total:
        navigation.append(InlineKeyboardButton(text=f"{page + 1} ›", callback_data=f"page:{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append(
        [button("bot.filters", lang, "filters"), button("bot.subscribe", lang, "subscribe:filters")]
    )
    rows.append(back_row(lang))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def event_keyboard(lang: str, event: object, *, screen: str, back: str) -> InlineKeyboardMarkup:
    rows = []
    links = []
    for key, field in (("bot.source", "source_url"), ("bot.tickets", "org_link")):
        url = external_url(getattr(event, field, None))
        if url and not any(link.url == url for link in links):
            links.append(InlineKeyboardButton(text=t(key, lang), url=url))
    if links:
        rows.append(links)
    rows.append([button("bot.subscribe", lang, f"subscribe:{screen}:{event.id}")])
    rows.append(back_row(lang, back))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subscriptions_keyboard(
    lang: str, subscriptions: list, page: int = 1, total: int | None = None, page_size: int = 10
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{t('bot.unsubscribe', lang)} #{sub.id}",
                callback_data=f"unsubscribe:{sub.id}",
            )
        ]
        for sub in subscriptions
    ]
    navigation = []
    if page > 1:
        navigation.append(InlineKeyboardButton(text=f"‹ {page - 1}", callback_data=f"subpage:{page - 1}"))
    if total is not None and page * page_size < total:
        navigation.append(InlineKeyboardButton(text=f"{page + 1} ›", callback_data=f"subpage:{page + 1}"))
    if navigation:
        rows.append(navigation)
    if subscriptions:
        rows.append([button("bot.remove_all", lang, "unsubscribe:all")])
    rows.append(back_row(lang))
    return InlineKeyboardMarkup(inline_keyboard=rows)
