"""Modals: the /edit pop-up form."""

import discord

from moviebot.models import Film
from moviebot.services.watchlist import MAX_NOTE, WatchlistService
from moviebot.ui.choices import shorten
from moviebot.ui.embeds import film_card
from moviebot.ui.errors import report_error

MAX_MODAL_TITLE = 45  # Discord's limit for a pop-up's title
EDIT_TIMEOUT = 900  # seconds: a pop-up closed without saving is forgotten after 15 minutes


class EditFilmModal(discord.ui.Modal):
    """/edit's pop-up (FR-12): the film's note, filled in so it can be changed."""

    def __init__(
        self, watchlist: WatchlistService, film: Film, *, category_key: str | None
    ) -> None:
        super().__init__(title=shorten(f"Edit {film.label}", MAX_MODAL_TITLE), timeout=EDIT_TIMEOUT)
        self.watchlist = watchlist
        self.film_id = film.id
        self.category_key = category_key
        self.note = discord.ui.TextInput(
            label="Note",
            style=discord.TextStyle.paragraph,
            placeholder="Why it's worth watching. Leave it empty to clear the note.",
            default=film.note,
            required=False,
            max_length=MAX_NOTE,
        )
        self.add_item(self.note)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Save the note, and the category if /edit was given one, then show the card."""
        info = await self.watchlist.edit_film(
            self.film_id, note=self.note.value, category_key=self.category_key
        )
        await interaction.response.send_message(
            "Saved.", embed=film_card(info.film, info.category), ephemeral=True
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception, /) -> None:
        """Report a failed save the same way as a failed command."""
        await report_error(interaction, error)
