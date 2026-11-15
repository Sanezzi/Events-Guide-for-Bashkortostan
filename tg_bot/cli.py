"""Catalog administration: python -m tg_bot.cli import PATH / seed / init-db."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from tg_bot.models import Database
from tg_bot.services import ImporterService


async def run(args: argparse.Namespace) -> int:
    from tg_bot.config import get_settings

    settings = get_settings()
    database = Database(args.database_url or settings.database_url)
    try:
        await database.create_tables()
        if args.command == "init-db":
            print(json.dumps({"status": "initialized"}))
            return 0
        path = (
            Path(__file__).parent / "data" / "sample_events.json"
            if args.command == "seed"
            else Path(args.path)
        )
        async with database.sessions() as session:
            report = await ImporterService(session).import_bytes(
                path.read_bytes(), path.name, actor="cli"
            )
        print(report.model_dump_json(indent=2))
        return 1 if report.rejected else 0
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validated CSV/JSON catalog import; seed contains fictional DEMO events only"
    )
    parser.add_argument("--database-url", help="Override configured database URL")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="Create database tables")
    commands.add_parser("seed", help="Import 15 explicitly fictional DEMO events")
    importer = commands.add_parser("import", help="Import UTF-8 CSV or JSON")
    importer.add_argument("path")
    args = parser.parse_args()
    try:
        status = asyncio.run(run(args))
    except (OSError, ValueError):
        parser.exit(2, "Cannot read import file or initialize database configuration.\n")
    raise SystemExit(status)


if __name__ == "__main__":
    main()
