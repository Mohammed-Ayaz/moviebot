"""The Discord side of the bot: the Bot subclass, its slash command tree and the error handlers.

Like cogs/ and ui/, this is the bot layer, so it may import discord.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from moviebot.cogs.admin import AdminCog
from moviebot.cogs.suggest import SuggestCog
from moviebot.cogs.watchlist import WatchlistCog
from moviebot.config import Settings
from moviebot.services.picker import PickerService
from moviebot.services.watchlist import WatchlistService
from moviebot.ui.buttons import AnotherButton, SuggestButton, WatchButton
from moviebot.ui.errors import report_error

log = logging.getLogger(__name__)


class MovieTree(app_commands.CommandTree):
    """The slash command tree. Its on_error is the one error handler for every slash command."""

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError, /
    ) -> None:
        """Reply privately with the broken rule, the cooldown, or "Something went wrong."."""
        await report_error(interaction, error)


class MovieBot(commands.Bot):
    """Movie Night Bot: slash commands and buttons, plus the owner's `@MovieBot sync`."""

    def __init__(
        self, settings: Settings, *, watchlist: WatchlistService, picker: PickerService
    ) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            help_command=None,  # so `@MovieBot sync` stays the only text command
            tree_cls=MovieTree,
            intents=discord.Intents.default(),  # no privileged intents
            allowed_mentions=discord.AllowedMentions.none(),  # nothing the bot posts pings anyone
        )
        self.settings = settings
        self.watchlist = watchlist
        self.picker = picker  # the persistent buttons reach it through interaction.client

    async def setup_hook(self) -> None:
        """Add the cogs and the persistent buttons. Never sync here: only `@MovieBot sync` does."""
        await self.add_cog(AdminCog(self, guild_id=self.settings.guild_id))
        await self.add_cog(WatchlistCog(self.watchlist))
        await self.add_cog(SuggestCog(self.picker, self.watchlist))
        self.add_dynamic_items(SuggestButton, AnotherButton, WatchButton)

    async def on_ready(self) -> None:
        """Log the login, and warn if the bot isn't in the GUILD_ID server."""
        log.info("Logged in as %s", self.user)
        if self.get_guild(self.settings.guild_id) is None:
            log.warning("The bot isn't in the GUILD_ID server: invite it there, or fix GUILD_ID.")

    async def on_command_error(
        self, context: commands.Context[commands.Bot], exception: commands.CommandError, /
    ) -> None:
        """Handle text command errors. By default discord.py logs every stray mention."""
        if isinstance(exception, commands.CommandNotFound):
            return  # a mention that isn't a command, such as "@MovieBot hi"
        if isinstance(exception, commands.CheckFailure):
            log.info("%s can't use %s: %s", context.author, context.command, exception)
            return
        log.error("Error in text command %s", context.command, exc_info=exception)
