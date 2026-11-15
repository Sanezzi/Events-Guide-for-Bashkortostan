"""Import structured events from organizer URLs into the moderation queue."""

import argparse
import asyncio
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

from app.catalog import Catalog, SOURCE_CODES
from app.db_config import database_url
from contour.parser import event_page_links, fetch_text, parse_event_page, source_link
from tg_bot.models import Database


def failure_reason(exc):
    if isinstance(exc, HTTPError):
        return f"HTTP {exc.code}"
    reason = exc.reason if isinstance(exc, URLError) else exc
    if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
        return "timeout"
    return type(reason).__name__
