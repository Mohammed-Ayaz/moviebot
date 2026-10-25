"""The persistent buttons: Suggest, Another and We're watching this (FR-7 to FR-9).

They are DynamicItems that setup_hook registers, so buttons on old messages keep working after a
restart: everything a click needs is in the button's custom_id. discord.py only logs errors that
these buttons raise, so each one reports its own errors to the user privately.
"""

import re
from typing import Protocol, Self, cast

import discord
from discord import app_commands

from moviebot.models import SuggestFilters, Suggestion
from moviebot.services.picker import PickerService
from moviebot.ui.embeds import suggestion_card
from moviebot.ui.errors import report_error

SUGGEST_ID = "mb:suggest"
SUGGEST_TEMPLATE = r"mb:suggest"
ANOTHER_TEMPLATE = (
    r"mb:another:(?P<film_id>\d+)(?::(?P<category>[^:]*):(?P<genre>[a-z]*):(?P<side>[a-z]*))?"
)
WATCH_TEMPLATE = r"mb:watch:(?P<film_id>\d+)"


class PickerHost(Protocol):
    """The bot, as the buttons see it: something that has a picker."""

    picker: PickerService


class ButtonCooldown:
    """A limit on clicks per person, like the slash command cooldown but for buttons."""

    def __init__(self, rate: int, per: float) -> None:
        self._rate = rate
        self._per = per
        self._buckets: dict[int, app_commands.Cooldown] = {}

    def check(self, user_id: int) -> None:
        """Raise CommandOnCooldown if this person has clicked too often."""
        bucket = self._buckets.setdefault(user_id, app_commands.Cooldown(self._rate, self._per))
        retry_after = bucket.update_rate_limit()
        if retry_after is not None:
            raise app_commands.CommandOnCooldown(bucket, retry_after)


PICKER_COOLDOWN = ButtonCooldown(1, 3.0)  # Suggest and Another: one click per 3 seconds each


def another_id(film_id: int, filters: SuggestFilters) -> str:
    """Another's custom_id: 'mb:another:42', or with filters 'mb:another:42::masala:good'."""
    if not filters.active:
        return f"mb:another:{film_id}"
    category, genre, side = filters.category_key or "", filters.genre or "", filters.side or ""
    return f"mb:another:{film_id}:{category}:{genre}:{side}"


def filters_from(match: re.Match[str]) -> SuggestFilters:
    """The filters stored in a matched Another custom_id."""
    return SuggestFilters(
        category_key=match["category"] or None,
        genre=match["genre"] or None,
        side=match["side"] or None,
    )


def card_view(suggestion: Suggestion) -> discord.ui.View:
    """The buttons under a suggestion card. No timeout: setup_hook keeps them working."""
    view = discord.ui.View(timeout=None)
    view.add_item(AnotherButton(suggestion.film.id, suggestion.filters))
    view.add_item(WatchButton(suggestion.film.id))
    return view


class SuggestButton(discord.ui.DynamicItem[discord.ui.Button], template=SUGGEST_TEMPLATE):
    """Suggest: the same as /suggest with no filters. Posts a new suggestion card."""

    def __init__(self) -> None:
        super().__init__(
            discord.ui.Button(
                label="Suggest", style=discord.ButtonStyle.primary, custom_id=SUGGEST_ID
            )
        )

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Item, match: re.Match[str], /
    ) -> Self:
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            PICKER_COOLDOWN.check(interaction.user.id)
            suggestion = await _picker(interaction).suggest(requested_by=interaction.user.id)
            await interaction.response.send_message(
                embed=suggestion_card(suggestion), view=card_view(suggestion)
            )
        except Exception as error:  # discord.py would only log it
            await report_error(interaction, error)


class AnotherButton(discord.ui.DynamicItem[discord.ui.Button], template=ANOTHER_TEMPLATE):
    """Another: pick again with the same filters, leaving out this film, and update the card."""

    def __init__(self, film_id: int, filters: SuggestFilters) -> None:
        super().__init__(
            discord.ui.Button(
                label="Another",
                style=discord.ButtonStyle.secondary,
                custom_id=another_id(film_id, filters),
            )
        )
        self.film_id = film_id
        self.filters = filters

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Item, match: re.Match[str], /
    ) -> Self:
        return cls(int(match["film_id"]), filters_from(match))

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            PICKER_COOLDOWN.check(interaction.user.id)
            suggestion = await _picker(interaction).suggest(
                requested_by=interaction.user.id, filters=self.filters, leave_out=self.film_id
            )
            await interaction.response.edit_message(
                embed=suggestion_card(suggestion), view=card_view(suggestion)
            )
        except Exception as error:  # discord.py would only log it
            await report_error(interaction, error)


class WatchButton(discord.ui.DynamicItem[discord.ui.Button], template=WATCH_TEMPLATE):
    """We're watching this: mark the film watched, grey out the card, post tonight's pick."""

    def __init__(self, film_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="We're watching this",
                style=discord.ButtonStyle.success,
                custom_id=f"mb:watch:{film_id}",
            )
        )
        self.film_id = film_id

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Item, match: re.Match[str], /
    ) -> Self:
        return cls(int(match["film_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            film = await _picker(interaction).watch(self.film_id)
            greyed = _greyed_out(interaction.message)
            await interaction.response.edit_message(view=greyed)
            if greyed is not None:
                greyed.stop()  # nothing on it can be clicked, so stop listening
            await interaction.followup.send(f"Tonight: {discord.utils.escape_markdown(film.label)}")
        except Exception as error:  # discord.py would only log it
            await report_error(interaction, error)


def _picker(interaction: discord.Interaction) -> PickerService:
    return cast(PickerHost, interaction.client).picker


def _greyed_out(message: discord.Message | None) -> discord.ui.View | None:
    """The message's buttons, all disabled, to show the film has been chosen."""
    if message is None:
        return None
    view = discord.ui.View.from_message(message, timeout=None)
    for item in view.children:
        if isinstance(item, discord.ui.Button):
            item.disabled = True
    return view
