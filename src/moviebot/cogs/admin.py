"""Admin and health commands: /ping and /about for everyone, and the owner-only sync."""

import asyncio
import io
import logging
from importlib import resources

import discord
from discord import app_commands
from discord.ext import commands

from moviebot.ui.embeds import LOGO_FILENAME, about_embed

log = logging.getLogger(__name__)

TMDB_LOGO = resources.files("moviebot") / "assets" / LOGO_FILENAME


class AdminCog(commands.Cog):
    """/ping, /about, and the bot's one text command: `@MovieBot sync`."""

    def __init__(self, bot: commands.Bot, *, guild_id: int) -> None:
        self.bot = bot
        self.guild = discord.Object(id=guild_id)

    @app_commands.command(name="ping", description="Check that the bot is alive.")
    async def ping(self, interaction: discord.Interaction) -> None:
        """FR-1: reply privately with the bot's latency in milliseconds."""
        latency_ms = self.bot.latency * 1000
        await interaction.response.send_message(f"Pong! {latency_ms:.0f} ms", ephemeral=True)

    @app_commands.command(
        name="about", description="What this bot is, and where its film data comes from."
    )
    async def about(self, interaction: discord.Interaction) -> None:
        """FR-6: private credits, with TMDB's required notice and logo (NFR-8)."""
        try:
            logo = await asyncio.to_thread(TMDB_LOGO.read_bytes)
        except FileNotFoundError:
            log.warning("The TMDB logo is missing: %s", TMDB_LOGO)
            await interaction.response.send_message(
                embed=about_embed(with_logo=False), ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=about_embed(with_logo=True),
            file=discord.File(io.BytesIO(logo), filename=LOGO_FILENAME),
            ephemeral=True,
        )

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
