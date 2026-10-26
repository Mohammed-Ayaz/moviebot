"""Import watchlist_seed.json into the bot's database (FR-15).

Run it from the repo folder, with the bot stopped:

    uv run python scripts/import_seed.py watchlist_seed.json
    uv run python scripts/import_seed.py watchlist_seed.json --match-tmdb
    uv run python scripts/import_seed.py watchlist_seed.json --map fixes.csv

It writes to DATABASE_PATH from .env. Importing again adds nothing and never undoes an edit, so
it's safe to repeat. --match-tmdb finds posters and runtimes for films that have none yet, and
--map takes a file of lines like heropanti-2014,280391 for films TMDB couldn't match.
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

import aiohttp

from moviebot.config import ConfigError, Settings, load_settings
from moviebot.db.blocklist import BlocklistRepository
from moviebot.db.categories import CategoryRepository
from moviebot.db.database import open_database
from moviebot.db.films import FilmRepository
from moviebot.models import InvalidSeed, Seed, TmdbMatches
from moviebot.services.seed import SeedService, parse_fixes, parse_seed
from moviebot.tmdb.client import TmdbClient

log = logging.getLogger("import_seed")


def main(argv: list[str] | None = None) -> int:
    """Check the settings and the files, then import. Returns the exit code: 0 when it worked."""
    args = _arguments(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        settings = load_settings()
    except ConfigError as error:
        log.error("Can't start. Fix these in .env (see .env.example):")
        for problem in error.problems:
            log.error("  - %s", problem)
        return 1
    try:
        seed = parse_seed(json.loads(args.seed.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError, InvalidSeed) as error:
        log.error("Can't import %s: %s", args.seed, _reason(error))
        return 1
    try:
        fixes = parse_fixes(args.map.read_text(encoding="utf-8-sig")) if args.map else []
    except (OSError, ValueError, InvalidSeed) as error:
        log.error("Can't use %s: %s", args.map, _reason(error))
        return 1
    asyncio.run(_import(settings, seed, match_tmdb=args.match_tmdb, fixes=fixes))
    return 0


async def _import(
    settings: Settings, seed: Seed, *, match_tmdb: bool, fixes: list[tuple[str, int]]
) -> None:
    db = await open_database(settings.database_path)
    try:
        async with aiohttp.ClientSession() as session:
            service = SeedService(
                FilmRepository(db),
                CategoryRepository(db),
                BlocklistRepository(db),
                TmdbClient(session, settings.tmdb_read_token),
                clock=partial(datetime.now, UTC),
            )
            report = await service.import_seed(seed)
            log.info(
                "Imported into %s: %d categories added, %d films added, %d already on the "
                "list, %d do-not-watch entries added.",
                settings.database_path,
                report.categories_added,
                report.films_added,
                report.films_skipped,
                report.blocked_added,
            )
            if match_tmdb:
                log.info("Looking the films up on TMDB. This can take a couple of minutes...")
                _show(await service.match_tmdb(seed))
            if fixes:
                _show(await service.apply_fixes(fixes))
    finally:
        await db.close()


def _show(matches: TmdbMatches) -> None:
    """Say what matching on TMDB did, and what's left to fix by hand."""
    log.info("Matched %d film(s) on TMDB.", len(matches.matched))
    for film, holder in matches.taken:
        log.info("  %s: that TMDB film already belongs to %s.", film.label, holder.label)
    for slug in matches.unknown_slugs:
        log.info("  No film has the slug %s.", slug)
    if matches.unmatched:
        log.info(
            "%d film(s) have no TMDB match. They still work, just without a poster. To fix "
            "them, write lines like heropanti-2014,280391 into fixes.csv (the slug, then the "
            "number in the film's themoviedb.org address) and run this again with "
            "--map fixes.csv:",
            len(matches.unmatched),
        )
        for film in matches.unmatched:
            log.info("  %s  (%s)", film.slug, film.label)
    if matches.stopped:
        log.warning("TMDB stopped answering, so some films weren't tried. Run this again later.")


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import the seed file into the bot's database.")
    parser.add_argument("seed", type=Path, help="the seed file, such as watchlist_seed.json")
    parser.add_argument(
        "--match-tmdb", action="store_true", help="look up films without a poster on TMDB"
    )
    parser.add_argument(
        "--map",
        type=Path,
        metavar="FIXES_CSV",
        help="a file of slug,tmdb_id lines for films TMDB couldn't match",
    )
    return parser.parse_args(argv)


def _reason(error: Exception) -> str:
    if isinstance(error, OSError):
        return error.strerror or str(error)
    return str(error)


if __name__ == "__main__":
    sys.exit(main())
