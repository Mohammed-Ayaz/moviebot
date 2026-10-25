"""Views: the buttons under a /list message."""

import logging

import discord

from moviebot.models import FilmPage
from moviebot.services.watchlist import WatchlistService
from moviebot.ui.buttons import SUGGEST_ID, SuggestButton
from moviebot.ui.embeds import list_embed
from moviebot.ui.errors import report_error

log = logging.getLogger(__name__)

LIST_TIMEOUT = 600  # seconds: the buttons stop working after 10 minutes


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
