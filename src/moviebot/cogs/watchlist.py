"""The watchlist commands: read the options, call WatchlistService, draw the replies.

Rules the service enforces come back as DomainErrors, which MovieTree shows privately.
"""

import asyncio
import re
from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from moviebot.models import AddedFilm, Film, Show
from moviebot.services.watchlist import MAX_NOTE, MAX_TITLE, MAX_YEAR, MIN_YEAR, WatchlistService
from moviebot.ui.choices import category_choices, film_choices, tmdb_choices
from moviebot.ui.embeds import film_card, list_embed
from moviebot.ui.modals import EditFilmModal
from moviebot.ui.views import ConfirmRemoveView, ListView, suggest_view

TMDB_PICK = re.compile(r"tmdb:(\d+)")  # the value of a TMDB suggestion picked from the list
FILM_PICK = re.compile(r"film:(\d+)")  # the value of a film picked from the list
SUGGEST_SECONDS = 1.8  # Discord waits 3 seconds for suggestions; leave time to send them
SHOW_CHOICES = [
    app_commands.Choice(name="Unwatched", value="unwatched"),
    app_commands.Choice(name="Watched", value="watched"),
    app_commands.Choice(name="All", value="all"),
]


class WatchlistCog(commands.Cog):
    """/add, /list, /remove, /edit, /watched and /unwatch."""

    def __init__(self, watchlist: WatchlistService) -> None:
        self.watchlist = watchlist

    @app_commands.command(name="add", description="Add a film to the watchlist.")
    @app_commands.describe(
        title="Type part of the name, then pick the film from the list",
        year="The year it came out, if you know it",
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
        """FR-2 and FR-5: save the film, confirm privately, then post its card publicly.

        TMDB can take a few seconds, so the reply is deferred privately first. Errors raised
        after that still reach the user privately, through MovieTree.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        pick = TMDB_PICK.fullmatch(title)
        if pick is not None:
            added = await self.watchlist.add_from_tmdb(
                int(pick[1]), category_key=category, note=note, added_by=interaction.user.id
            )
        else:
            added = await self.watchlist.add_film(
                title=title,
                year=year,
                category_key=category,
                note=note,
                added_by=interaction.user.id,
            )
        await interaction.followup.send(_confirmation(added), ephemeral=True)
        await interaction.followup.send(embed=film_card(added.film, added.category))

    @add.autocomplete("title")
    async def add_title(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """TMDB suggestions as 'Title (Year)' while the user types (FR-5)."""
        try:
            async with asyncio.timeout(SUGGEST_SECONDS):
                movies = await self.watchlist.search_tmdb(current)
        except TimeoutError:
            return []
        return tmdb_choices(movies)

    @add.autocomplete("category")
    async def add_category(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return category_choices(await self.watchlist.list_categories(), current)

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
        """FR-3: post the first page, with Suggest, plus Previous and Next if there are more."""
        page = await self.watchlist.list_films(
            show=cast(Show, show.value) if show else "unwatched", category_key=category
        )
        if page.page_count > 1:
            view = ListView(self.watchlist, page)
            await interaction.response.send_message(embed=list_embed(page), view=view)
            view.message = await interaction.original_response()
        elif page.total:
            await interaction.response.send_message(embed=list_embed(page), view=suggest_view())
        else:
            await interaction.response.send_message(embed=list_embed(page))

    @list_films.autocomplete("category")
    async def list_category(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return category_choices(await self.watchlist.list_categories(), current)

    @app_commands.command(name="remove", description="Remove a film from the watchlist.")
    @app_commands.describe(film="Start typing, then pick the film from the list")
    async def remove(self, interaction: discord.Interaction, film: str) -> None:
        """FR-11: ask privately. Confirm removes the film and says so publicly."""
        chosen = await self._film(film)
        view = ConfirmRemoveView(self.watchlist, chosen, user_id=interaction.user.id)
        label = discord.utils.escape_markdown(chosen.label)
        await interaction.response.send_message(
            f"Remove {label} from the list? This can't be undone.", view=view, ephemeral=True
        )
        view.interaction = interaction

    @remove.autocomplete("film")
    async def remove_suggestions(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return film_choices(await self.watchlist.search_films(current))

    @app_commands.command(name="edit", description="Change a film's note or category.")
    @app_commands.describe(
        film="Start typing, then pick the film from the list",
        category="Move the film to this category",
    )
    async def edit(
        self, interaction: discord.Interaction, film: str, category: str | None = None
    ) -> None:
        """FR-12: open the pop-up with the note filled in. Saving also sets the category."""
        chosen = await self._film(film)
        await self.watchlist.category(category)  # refuse an unknown category before the pop-up
        await interaction.response.send_modal(
            EditFilmModal(self.watchlist, chosen, category_key=category)
        )

    @edit.autocomplete("film")
    async def edit_suggestions(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return film_choices(await self.watchlist.search_films(current))

    @edit.autocomplete("category")
    async def edit_category(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return category_choices(await self.watchlist.list_categories(), current)

    @app_commands.command(name="watched", description="Mark a film as watched.")
    @app_commands.describe(film="Start typing, then pick the film from the list")
    async def watched(self, interaction: discord.Interaction, film: str) -> None:
        """FR-13: mark the film watched, and say so publicly."""
        chosen = await self._film(film, watched=False)
        updated = await self.watchlist.mark_watched(chosen.id)
        label = discord.utils.escape_markdown(updated.label)
        await interaction.response.send_message(f"Marked {label} as watched.")

    @watched.autocomplete("film")
    async def watched_suggestions(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return film_choices(await self.watchlist.search_films(current, watched=False))

    @app_commands.command(
        name="unwatch", description="Put a watched film back on the unwatched list."
    )
    @app_commands.describe(film="Start typing, then pick the film from the list")
    async def unwatch(self, interaction: discord.Interaction, film: str) -> None:
        """FR-13: undo /watched, privately."""
        chosen = await self._film(film, watched=True)
        updated = await self.watchlist.unwatch(chosen.id)
        label = discord.utils.escape_markdown(updated.label)
        await interaction.response.send_message(
            f"{label} is back on the unwatched list.", ephemeral=True
        )

    @unwatch.autocomplete("film")
    async def unwatch_suggestions(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return film_choices(await self.watchlist.search_films(current, watched=True))

    async def _film(self, value: str, *, watched: bool | None = None) -> Film:
        """The film picked from the suggestions, or else the one film with exactly that title."""
        pick = FILM_PICK.fullmatch(value)
        if pick is not None:
            return await self.watchlist.get_film(int(pick[1]))
        return await self.watchlist.film_named(value, watched=watched)


def _confirmation(added: AddedFilm) -> str:
    """The private reply to /add: what was added, and anything the adder should know."""
    lines = [f"Added {discord.utils.escape_markdown(added.film.label)}."]
    if added.tmdb == "not_found":
        lines.append("It's saved without a poster. Next time, pick the film from the list.")
    elif added.tmdb == "unavailable":
        lines.append("TMDB isn't answering, so it's saved without a poster.")
    if added.same_title is not None:
        same = discord.utils.escape_markdown(added.same_title.label)
        lines.append(f"Heads up: {same} is already on the list, so this may be a duplicate.")
    return "\n".join(lines)
