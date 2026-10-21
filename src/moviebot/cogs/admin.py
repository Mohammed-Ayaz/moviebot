"""Admin and health commands: /ping for everyone, and the owner-only `@MovieBot sync`."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)


class AdminCog(commands.Cog):
    """/ping, and the bot's one text command: `@MovieBot sync`."""

    def __init__(self, bot: commands.Bot, *, guild_id: int) -> None:
        self.bot = bot
        self.guild = discord.Object(id=guild_id)

    @app_commands.command(name="ping", description="Check that the bot is alive.")
    async def ping(self, interaction: discord.Interaction) -> None:
        """FR-1: reply privately with the bot's latency in milliseconds."""
        latency_ms = self.bot.latency * 1000
        await interaction.response.send_message(f"Pong! {latency_ms:.0f} ms", ephemeral=True)

    @commands.command(name="sync")
    @commands.is_owner()
    async def sync(self, ctx: commands.Context[commands.Bot]) -> None:
        """Copy the slash commands to the GUILD_ID server and register them there. Owner only."""
        self.bot.tree.copy_global_to(guild=self.guild)
        try:
            synced = await self.bot.tree.sync(guild=self.guild)
        except discord.HTTPException:
            log.exception("Syncing the slash commands failed")
            await ctx.reply("Sync failed. The bot's log has the details.")
            return
        log.info("Synced %d slash command(s)", len(synced))
        await ctx.reply(f"Synced {len(synced)} slash command(s) to the server.")
