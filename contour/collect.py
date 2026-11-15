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


async def scan_source(url, semaphore=None):
    if not source_link(url, url):
        return [], 0, [{"url": url, "error": "invalid_url"}]
    semaphore = semaphore or asyncio.Semaphore(6)

    async def read_page(page_url):
        async with semaphore:
            try:
                return await asyncio.to_thread(fetch_text, page_url), None
            except (URLError, OSError, ValueError) as exc:
                return None, {"url": page_url, "error": failure_reason(exc)}

    raw, failure = await read_page(url)
    if failure:
        return [], 1, [failure]
    events = parse_event_page(raw, url)
    children = event_page_links(raw, url)
    errors = []
    child_pages = await asyncio.gather(*(read_page(child) for child in children))
    for child, (page, failure) in zip(children, child_pages):
        if failure:
            errors.append(failure)
        else:
            events.extend(parse_event_page(page, child))
    return list({row["id"]: row for row in events}.values()), 1 + len(children), errors


async def collect(urls, *, preview=False):
    database = None if preview else Database(database_url())
    catalog = Catalog(database) if database is not None else None
    failed = False
    semaphore = asyncio.Semaphore(6)
    sources = list(dict.fromkeys(urls))
    try:
        scans = await asyncio.gather(*(scan_source(url, semaphore) for url in sources))
        for url, (events, pages, errors) in zip(sources, scans):
            result = {"source": url, "pages_attempted": pages, "found": len(events), "fetch_errors": errors}
            if catalog is not None and events:
                for row in events:
                    row["source_type"] = SOURCE_CODES[row["source_type"]]
                    for field in ("created_at", "updated_at", "source_hash", "dedup_key"):
                        row.pop(field, None)
                report = await catalog.import_file(json.dumps(events, ensure_ascii=False).encode(),
                                                   "source.json", "organizer-page", preserve_reviewed=True)
                result["import"] = report.model_dump()
                failed = failed or bool(report.rejected)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            failed = failed or bool(errors)
    finally:
        if database is not None:
            await database.close()
    return int(failed)
