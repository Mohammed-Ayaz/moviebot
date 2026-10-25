"""/suggest: pick tonight's film, optionally narrowed by category, genre and side (FR-7 to FR-10).

The card's buttons live in ui/buttons.py.
"""

import discord
from discord import app_commands
from discord.ext import commands

from moviebot.models import SuggestFilters
from moviebot.services.picker import PickerService
from moviebot.services.watchlist import WatchlistService
from moviebot.ui.buttons import card_view
from moviebot.ui.choices import category_choices
from moviebot.ui.embeds import suggestion_card

GENRE_CHOICES = [
    app_commands.Choice(name="Masala", value="masala"),
    app_commands.Choice(name="Drama", value="drama"),
    app_commands.Choice(name="Horror", value="horror"),
]
SIDE_CHOICES = [
    app_commands.Choice(name="Hate-watch", value="bad"),
    app_commands.Choice(name="Actually good", value="good"),
]


class SuggestCog(commands.Cog):
    """/suggest."""

    def __init__(self, picker: PickerService, watchlist: WatchlistService) -> None:
        self.picker = picker
        self.watchlist = watchlist  # for the category suggestions

    @app_commands.command(name="suggest", description="Pick a random unwatched film for tonight.")
    @app_commands.describe(
        category="Only films in this category",
        genre="Only films of this genre",
        side="A hate-watch, or something actually good",
    )
    @app_commands.choices(genre=GENRE_CHOICES, side=SIDE_CHOICES)
    @app_commands.checks.cooldown(1, 3.0)
    async def suggest(
        self,
        interaction: discord.Interaction,
        category: str | None = None,
        genre: app_commands.Choice[str] | None = None,
        side: app_commands.Choice[str] | None = None,
    ) -> None:
        """FR-7 and FR-8: post a suggestion card with Another and We're watching this."""
        filters = SuggestFilters(
            category_key=category or None,
            genre=genre.value if genre else None,
            side=side.value if side else None,
        )
        suggestion = await self.picker.suggest(requested_by=interaction.user.id, filters=filters)
        await interaction.response.send_message(
            embed=suggestion_card(suggestion), view=card_view(suggestion)
        )

    @suggest.autocomplete("category")
    async def suggest_category(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return category_choices(await self.watchlist.list_categories(), current)
