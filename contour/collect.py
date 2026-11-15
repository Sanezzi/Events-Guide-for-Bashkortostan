import argparse
import asyncio
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

from app.catalog import Catalog, SOURCE_CODES
from app.db_config import database_url
from contour.parser import event_page_links, fetch_text, parse_event_page, source_link
from tg_bot.models import Database

CLI_DESCRIPTION = 'Import structured events from organizer URLs into the moderation queue.'


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=CLI_DESCRIPTION)
    parser.add_argument("urls", nargs="*", help="Organizer event or listing URLs")
    parser.add_argument("--configured", action="store_true", help="Read URLs from contour/data/sources.json")
    parser.add_argument("--preview", action="store_true", help="Scan sources without importing")
    args = parser.parse_args()
    if args.configured:
        registry = Path(__file__).with_name("data") / "sources.json"
        sources = json.loads(registry.read_text(encoding="utf-8"))
        args.urls.extend(item["url"] for item in sources if item.get("url"))
    if not args.urls:
        parser.error("supply at least one URL or use --configured")
    raise SystemExit(asyncio.run(collect(args.urls, preview=args.preview)))
