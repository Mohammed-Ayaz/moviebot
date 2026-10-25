"""Entry point: `python -m moviebot` loads the settings, sets up logging and runs the bot."""

import asyncio
import logging
import random
import sys
from datetime import UTC, datetime
from functools import partial

import aiohttp
import discord

from moviebot.bot import MovieBot
from moviebot.config import ConfigError, Settings, load_settings
from moviebot.db.categories import CategoryRepository
from moviebot.db.database import open_database
from moviebot.db.films import FilmRepository
from moviebot.db.suggestions import SuggestionRepository
from moviebot.services.picker import PickerService
from moviebot.services.watchlist import WatchlistService
from moviebot.tmdb.client import TmdbClient

log = logging.getLogger(__name__)


async def main(settings: Settings) -> None:
    """Open the database, build the services, and run the bot until it stops."""
    db = await open_database(settings.database_path)
    try:
        async with aiohttp.ClientSession() as session:  # the one session for every TMDB call
            films, categories = FilmRepository(db), CategoryRepository(db)
            clock = partial(datetime.now, UTC)
            tmdb = TmdbClient(session, settings.tmdb_read_token)
            watchlist = WatchlistService(films, categories, tmdb, clock=clock)
            # Picking films needs no cryptographic randomness, hence the noqa for ruff's S311.
            rng = random.Random()  # noqa: S311
            picker = PickerService(
                films, categories, SuggestionRepository(db), rng=rng, clock=clock
            )
            async with MovieBot(settings, watchlist=watchlist, picker=picker) as bot:
                await bot.start(settings.discord_token)
    finally:
        await db.close()


def run() -> None:
    """Load the settings and set up logging before the event loop starts, then run main()."""
    try:
        settings = load_settings()
    except ConfigError as error:
        problems = "\n".join(f"  - {problem}" for problem in error.problems)
        sys.exit(f"Can't start. Fix these in .env (see .env.example):\n{problems}")
    discord.utils.setup_logging(level=logging.getLevelNamesMapping()[settings.log_level])
    try:
        asyncio.run(main(settings))
    except KeyboardInterrupt:
        log.info("Stopped with Ctrl+C")


if __name__ == "__main__":
    run()
