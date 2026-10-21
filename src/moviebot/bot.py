"""The Discord side of the bot: the Bot subclass, its slash command tree and the error handlers.

Like cogs/ and ui/, this is the bot layer, so it may import discord.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from moviebot.cogs.admin import AdminCog
from moviebot.config import Settings

log = logging.getLogger(__name__)

ERROR_REPLY = "Something went wrong."


class MovieTree(app_commands.CommandTree):
    """The slash command tree. Its on_error is the one error handler for every slash command."""

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError, /
    ) -> None:
        """Log the traceback and tell the user privately. Never raises."""
        name = interaction.command.qualified_name if interaction.command else "unknown"
        log.error("Error in /%s", name, exc_info=error)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(ERROR_REPLY, ephemeral=True)
            else:
                await interaction.response.send_message(ERROR_REPLY, ephemeral=True)
        except discord.HTTPException:
            log.warning("Couldn't tell the user about the error in /%s", name, exc_info=True)


class MovieBot(commands.Bot):
    """Movie Night Bot: slash commands and buttons, plus the owner's `@MovieBot sync`."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            help_command=None,  # so `@MovieBot sync` stays the only text command
            tree_cls=MovieTree,
            intents=discord.Intents.default(),  # no privileged intents
            allowed_mentions=discord.AllowedMentions.none(),  # nothing the bot posts pings anyone
        )
        self.settings = settings

    async def setup_hook(self) -> None:
        """Add the cogs. Never sync here: slash commands sync only on `@MovieBot sync`."""
        await self.add_cog(AdminCog(self, guild_id=self.settings.guild_id))

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
