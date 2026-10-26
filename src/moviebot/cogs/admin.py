"""Admin and health commands: /ping and /about for everyone, /export for admins, and the
owner-only sync."""

import asyncio
import io
import logging
from functools import partial
from importlib import resources

import discord
from discord import app_commands
from discord.ext import commands

from moviebot.services.backup import BackupService
from moviebot.ui.embeds import LOGO_FILENAME, about_embed

log = logging.getLogger(__name__)

TMDB_LOGO = resources.files("moviebot") / "assets" / LOGO_FILENAME


class AdminCog(commands.Cog):
    """/ping, /about, /export, and the bot's one text command: `@MovieBot sync`."""

    def __init__(
        self,
        bot: commands.Bot,
        *,
        guild_id: int,
        backup: BackupService,
        admin_role_id: int | None,
    ) -> None:
        self.bot = bot
        self.guild = discord.Object(id=guild_id)
        self.backup = backup
        self.admin_role_id = admin_role_id

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

    @app_commands.command(
        name="export", description="Download the whole watchlist as a JSON file. Admins only."
    )
    @app_commands.default_permissions(manage_guild=True)
    async def export(self, interaction: discord.Interaction) -> None:
        """FR-14: send an admin the whole list privately, as one JSON file.

        Discord hides the command from members without Manage Server, and BackupService checks
        again, because hidden isn't the same as secure.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        export = await self.backup.export(
            is_admin=is_admin(interaction.user, self.admin_role_id),
            display_name=partial(_display_name, interaction.guild),
        )
        films = "film" if export.film_count == 1 else "films"
        await interaction.followup.send(
            f"Here's the whole list: {export.film_count} {films}.",
            file=discord.File(io.BytesIO(export.content), filename=export.filename),
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


def is_admin(user: discord.User | discord.Member, admin_role_id: int | None) -> bool:
    """Whether someone is an admin: they have Manage Server, or the ADMIN_ROLE_ID role."""
    permissions = getattr(user, "guild_permissions", None)
    if permissions is None:
        return False  # not a member of the server
    if permissions.manage_guild:
        return True
    roles = getattr(user, "roles", [])
    return admin_role_id is not None and any(role.id == admin_role_id for role in roles)


async def _display_name(guild: discord.Guild | None, user_id: int) -> str | None:
    """A member's name in the server, or None if they've left or can't be looked up.

    Fetching one member doesn't need the privileged Server Members intent.
    """
    if guild is None:
        return None
    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except discord.HTTPException:
            return None
    return member.display_name
