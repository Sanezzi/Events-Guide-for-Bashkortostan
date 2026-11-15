"""Shared flat translations for the bot and Telegram WebApp."""

import json
from functools import lru_cache
from pathlib import Path

SUPPORTED_LANGUAGES = ("ru", "ba", "en")


@lru_cache(maxsize=3)
def load_locale(lang: str = "ru") -> dict[str, str]:
    """Load a supported locale, falling back to Russian for unknown languages."""
    language = lang if lang in SUPPORTED_LANGUAGES else "ru"
    with Path(__file__).with_name(f"{language}.json").open(encoding="utf-8") as stream:
        return json.load(stream)


class _SafeValues(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def t(key: str, lang: str = "ru", **kwargs) -> str:
    """Translate a flat key and interpolate named values without losing unknown fields."""
    value = load_locale(lang).get(key, load_locale("ru").get(key, key))
    return value.format_map(_SafeValues(kwargs)) if kwargs else value
