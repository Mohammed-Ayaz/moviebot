"""Entry point: `python -m moviebot` loads the settings, sets up logging and runs the bot."""

import asyncio
import logging
import sys

import discord

from moviebot.bot import MovieBot
from moviebot.config import ConfigError, Settings, load_settings

log = logging.getLogger(__name__)


async def main(settings: Settings) -> None:
    """Create the bot and run it until it stops."""
    async with MovieBot(settings) as bot:
        await bot.start(settings.discord_token)


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
