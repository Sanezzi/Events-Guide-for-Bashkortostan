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
