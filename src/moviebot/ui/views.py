"""Views: the buttons under a /list message, and Confirm and Cancel for /remove."""

import logging

import discord

from moviebot.models import Film, FilmNotFound, FilmPage
from moviebot.services.watchlist import WatchlistService
from moviebot.ui.buttons import SUGGEST_ID, SuggestButton
from moviebot.ui.embeds import list_embed
from moviebot.ui.errors import report_error

log = logging.getLogger(__name__)

LIST_TIMEOUT = 600  # seconds: the buttons stop working after 10 minutes
CONFIRM_TIMEOUT = 600  # seconds: so do Confirm and Cancel


class ListView(discord.ui.View):
    """Previous, Next and Suggest for one /list message. Anyone may click them.

    Previous and Next stop working after 10 minutes, or when the bot restarts. Suggest is one of
    the persistent buttons, so it keeps working.
    """

    def __init__(self, watchlist: WatchlistService, page: FilmPage) -> None:
        super().__init__(timeout=LIST_TIMEOUT)
        self.watchlist = watchlist
        self.page = page
        self.message: discord.InteractionMessage | None = None
        # A plain button with the Suggest button's custom_id, so setup_hook's registration handles
        # its clicks. A real SuggestButton here would be unregistered by discord.py, for every
        # message, when this view expires.
        self.add_item(
            discord.ui.Button(
                label="Suggest", style=discord.ButtonStyle.primary, custom_id=SUGGEST_ID
            )
        )
        self._update_buttons()

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._show(interaction, self.page.page - 1)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._show(interaction, self.page.page + 1)

    async def on_timeout(self) -> None:
        """Grey out Previous and Next once they stop working. Suggest keeps working."""
        self.previous_page.disabled = True
        self.next_page.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                log.debug("Couldn't grey out the buttons on an old list", exc_info=True)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item, /
    ) -> None:
        """Report a failed click the same way as a failed command."""
        await report_error(interaction, error)

    async def _show(self, interaction: discord.Interaction, page_number: int) -> None:
        """Change the message to another page of the same list."""
        category = self.page.category.key if self.page.category else None
        self.page = await self.watchlist.list_films(
            show=self.page.show, category_key=category, page=page_number
        )
        self._update_buttons()
        await interaction.response.edit_message(embed=list_embed(self.page), view=self)

    def _update_buttons(self) -> None:
        self.previous_page.disabled = self.page.page <= 1
        self.next_page.disabled = self.page.page >= self.page.page_count


def suggest_view() -> discord.ui.View:
    """Just the Suggest button, for a /list that fits on one page."""
    view = discord.ui.View(timeout=None)
    view.add_item(SuggestButton())
    return view


class ConfirmRemoveView(discord.ui.View):
    """Confirm and Cancel under /remove's private question (FR-11).

    Confirm removes the film and says publicly who removed it, so nothing disappears silently.
    """

    def __init__(self, watchlist: WatchlistService, film: Film, *, user_id: int) -> None:
        super().__init__(timeout=CONFIRM_TIMEOUT)
        self.watchlist = watchlist
        self.film = film
        self.user_id = user_id
        self.interaction: discord.Interaction | None = None  # the /remove, set once it's answered

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the person who asked can answer. The question is private anyway."""
        return interaction.user.id == self.user_id

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        try:
            removed = await self.watchlist.remove_film(self.film.id)
        except FilmNotFound as error:  # someone else removed it first
            await interaction.response.edit_message(content=str(error), view=None)
            return
        label = discord.utils.escape_markdown(removed.label)
        await interaction.response.edit_message(content=f"Removed {label}.", view=None)
        await interaction.followup.send(
            f"{interaction.user.mention} removed {label} from the list."
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        label = discord.utils.escape_markdown(self.film.label)
        await interaction.response.edit_message(content=f"Kept {label}.", view=None)

    async def on_timeout(self) -> None:
        """Take the buttons away once they stop working."""
        if self.interaction is not None:
            try:
                await self.interaction.edit_original_response(
                    content="Nothing was removed: this question expired.", view=None
                )
            except discord.HTTPException:
                log.debug("Couldn't take the buttons off an old /remove question", exc_info=True)

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item, /
    ) -> None:
        """Report a failed click the same way as a failed command."""
        await report_error(interaction, error)
