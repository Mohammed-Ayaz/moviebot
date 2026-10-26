"""The Discord side of the bot: the Bot subclass, its slash command tree, the error handlers,
and the daily background tasks.

Like cogs/ and ui/, this is the bot layer, so it may import discord.
"""

import io
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from moviebot.cogs.admin import AdminCog
from moviebot.cogs.suggest import SuggestCog
from moviebot.cogs.watchlist import WatchlistCog
from moviebot.config import Settings
from moviebot.services.backup import BackupService
from moviebot.services.picker import PickerService
from moviebot.services.watchlist import WatchlistService
from moviebot.ui.buttons import AnotherButton, SuggestButton, WatchButton
from moviebot.ui.errors import report_error

log = logging.getLogger(__name__)

BACKUP_NOTE = (
    "Weekly backup of the watchlist. To restore it, stop the bot, replace data/moviebot.db with "
    "this file, and start the bot again."
)


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
        self,
        settings: Settings,
        *,
        watchlist: WatchlistService,
        picker: PickerService,
        backup: BackupService,
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
        self.backup = backup

    async def setup_hook(self) -> None:
        """Add the cogs and the persistent buttons. Never sync here: only `@MovieBot sync` does."""
        await self.add_cog(
            AdminCog(
                self,
                guild_id=self.settings.guild_id,
                backup=self.backup,
                admin_role_id=self.settings.admin_role_id,
            )
        )
        await self.add_cog(WatchlistCog(self.watchlist))
        await self.add_cog(SuggestCog(self.picker, self.watchlist))
        self.add_dynamic_items(SuggestButton, AnotherButton, WatchButton)
        if self.settings.backup_channel_id is None:
            log.warning("Weekly backups are off: put the backup channel's ID in BACKUP_CHANNEL_ID.")
        else:
            self.daily_backup.start()
        self.daily_tmdb_refresh.start()

    async def close(self) -> None:
        """Stop the background tasks, then disconnect."""
        self.daily_backup.cancel()
        self.daily_tmdb_refresh.cancel()
        await super().close()

    @tasks.loop(hours=24)
    async def daily_backup(self) -> None:
        """FR-16: right after startup, then once a day, post a backup if a week has passed.

        Nothing here raises: a failure is logged, and the next day's run tries again.
        """
        try:
            await self._post_backup()
        except Exception:
            log.exception("The weekly backup failed. The bot tries again tomorrow.")

    @tasks.loop(hours=24)
    async def daily_tmdb_refresh(self) -> None:
        """Right after startup, then once a day, refresh TMDB details over 5 months old."""
        try:
            refreshed = await self.watchlist.refresh_tmdb()
        except Exception:
            log.exception("The TMDB refresh failed. The bot tries again tomorrow.")
            return
        if refreshed:
            log.info("Refreshed the TMDB details of %d film(s)", refreshed)

    @daily_backup.before_loop
    @daily_tmdb_refresh.before_loop
    async def _until_ready(self) -> None:
        await self.wait_until_ready()

    async def _post_backup(self) -> None:
        """Post a copy of the database to BACKUP_CHANNEL_ID if one is due, and remember it."""
        channel_id = self.settings.backup_channel_id
        if channel_id is None or not await self.backup.backup_due():
            return
        copy = await self.backup.make_backup(self.settings.database_path.parent)
        try:
            channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
            if not isinstance(channel, discord.abc.Messageable):
                log.error(
                    "The weekly backup couldn't be posted: BACKUP_CHANNEL_ID isn't a text channel."
                )
                return
            file = discord.File(io.BytesIO(copy.content), filename=copy.filename)
            await channel.send(BACKUP_NOTE, file=file)
        except discord.NotFound:
            log.error(
                "The weekly backup couldn't be posted: the bot can't find a channel with the ID "
                "in BACKUP_CHANNEL_ID. In the bot's server, right-click the backup channel, "
                "choose Copy Channel ID, and put that number in .env."
            )
            return
        except discord.HTTPException as error:
            log.error(
                "The weekly backup couldn't be posted (%s). Check that the bot can see the "
                "BACKUP_CHANNEL_ID channel, and send messages and attach files there.",
                error,
            )
            return
        await self.backup.backup_posted(copy)
        log.info("Posted the weekly backup: %s", copy.filename)

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
