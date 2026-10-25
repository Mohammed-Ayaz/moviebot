"""The persistent buttons: everything a click needs after a restart is in the custom_id."""

import re
from typing import Any, cast

import pytest
from discord import app_commands

from moviebot.models import SuggestFilters
from moviebot.ui.buttons import (
    ANOTHER_TEMPLATE,
    WATCH_TEMPLATE,
    AnotherButton,
    ButtonCooldown,
    WatchButton,
    another_id,
    filters_from,
)


@pytest.mark.parametrize(
    ("film_id", "filters", "custom_id"),
    [
        (42, SuggestFilters(), "mb:another:42"),
        (42, SuggestFilters(side="good"), "mb:another:42:::good"),
        (7, SuggestFilters(genre="masala", side="good"), "mb:another:7::masala:good"),
        (
            7,
            SuggestFilters(category_key="launch", genre="drama", side="bad"),
            "mb:another:7:launch:drama:bad",
        ),
    ],
)
def test_another_ids_carry_the_film_and_the_filters(
    film_id: int, filters: SuggestFilters, custom_id: str
) -> None:
    assert another_id(film_id, filters) == custom_id
    match = re.fullmatch(ANOTHER_TEMPLATE, custom_id)
    assert match is not None
    assert int(match["film_id"]) == film_id
    assert filters_from(match) == filters


def test_the_longest_id_fits_discords_100_character_limit() -> None:
    filters = SuggestFilters(category_key="goodhorror", genre="masala", side="good")

    assert len(another_id(10**18, filters)) <= 100


async def test_buttons_are_rebuilt_from_their_ids_after_a_restart() -> None:
    another_match = re.fullmatch(ANOTHER_TEMPLATE, "mb:another:7:launch::bad")
    watch_match = re.fullmatch(WATCH_TEMPLATE, "mb:watch:7")
    assert another_match is not None
    assert watch_match is not None

    another = await AnotherButton.from_custom_id(cast(Any, None), cast(Any, None), another_match)
    watch = await WatchButton.from_custom_id(cast(Any, None), cast(Any, None), watch_match)

    assert (another.film_id, another.filters) == (
        7,
        SuggestFilters(category_key="launch", side="bad"),
    )
    assert another.item.custom_id == "mb:another:7:launch::bad"
    assert (watch.film_id, watch.item.custom_id) == (7, "mb:watch:7")


def test_button_cooldown_is_per_person() -> None:
    cooldown = ButtonCooldown(1, 3.0)

    cooldown.check(1)
    cooldown.check(2)  # someone else isn't slowed down

    with pytest.raises(app_commands.CommandOnCooldown):
        cooldown.check(1)
