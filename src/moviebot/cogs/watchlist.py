"""/add and /list: read the options, call WatchlistService, draw the reply.

Rules the service enforces come back as DomainErrors, which MovieTree shows privately.
"""

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from moviebot.models import Show
from moviebot.services.watchlist import MAX_NOTE, MAX_TITLE, MAX_YEAR, MIN_YEAR, WatchlistService
from moviebot.ui.embeds import film_card, list_embed
from moviebot.ui.views import ListView

SHOW_CHOICES = [
    app_commands.Choice(name="Unwatched", value="unwatched"),
    app_commands.Choice(name="Watched", value="watched"),
    app_commands.Choice(name="All", value="all"),
]


class WatchlistCog(commands.Cog):
    """/add and /list."""

    def __init__(self, watchlist: WatchlistService) -> None:
        self.watchlist = watchlist

    @app_commands.command(name="add", description="Add a film to the watchlist.")
    @app_commands.describe(
        title="The film's title",
        year="The year it came out",
        category="Which category it belongs in",
        note="Why it's worth watching, up to 500 characters",
    )
    @app_commands.checks.cooldown(1, 3.0)
    async def add(
        self,
        interaction: discord.Interaction,
        title: app_commands.Range[str, 1, MAX_TITLE],
        year: app_commands.Range[int, MIN_YEAR, MAX_YEAR] | None = None,
        category: str | None = None,
        note: app_commands.Range[str, 1, MAX_NOTE] | None = None,
    ) -> None:
        """FR-2: save the film and post its card. A duplicate is refused privately (FR-4)."""
        added = await self.watchlist.add_film(
            title=title, year=year, category_key=category, note=note, added_by=interaction.user.id
        )
        await interaction.response.send_message(embed=film_card(added.film, added.category))
        if added.same_title is not None:
            await interaction.followup.send(
                f"Heads up: {added.same_title.label} is already on the list, "
                "so this one may be a duplicate.",
                ephemeral=True,
            )

    @add.autocomplete("category")
    async def add_category(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._category_choices(current)

    @app_commands.command(name="list", description="Show the watchlist, 10 films a page.")
    @app_commands.describe(
        show="Unwatched films (the default), watched films, or all of them",
        category="Only films in this category",
    )
    @app_commands.choices(show=SHOW_CHOICES)
    async def list_films(
        self,
        interaction: discord.Interaction,
        show: app_commands.Choice[str] | None = None,
        category: str | None = None,
    ) -> None:
        """FR-3: post the first page, with Previous and Next when there's more than one."""
        page = await self.watchlist.list_films(
            show=cast(Show, show.value) if show else "unwatched", category_key=category
        )
        if page.page_count == 1:
            await interaction.response.send_message(embed=list_embed(page))
            return
        view = ListView(self.watchlist, page)
        await interaction.response.send_message(embed=list_embed(page), view=view)
        view.message = await interaction.original_response()

    @list_films.autocomplete("category")
    async def list_category(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._category_choices(current)

    async def _category_choices(self, current: str) -> list[app_commands.Choice[str]]:
        """Up to 25 categories whose name or key contains what has been typed so far."""
        typed = current.lower()
        return [
            app_commands.Choice(name=category.name, value=category.key)
            for category in await self.watchlist.list_categories()
            if typed in category.name.lower() or typed in category.key
        ][:25]
