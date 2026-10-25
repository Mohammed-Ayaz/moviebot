"""PickerService: the suggestion algorithm (FR-7, FR-10) and "We're watching this" (FR-9)."""

import random
from datetime import UTC, datetime

import pytest

from moviebot.db.categories import CategoryRepository
from moviebot.db.database import Database
from moviebot.db.films import FilmRepository
from moviebot.db.suggestions import SuggestionRepository
from moviebot.models import (
    AlreadyWatched,
    Category,
    Film,
    FilmNotFound,
    NewFilm,
    NothingToSuggest,
    SuggestFilters,
    UnknownCategory,
)
from moviebot.services.picker import PickerService

WATCHED_AT = "2026-10-20T10:00:00Z"
PLACE = Category(key="place", name="Place as a character", position=11, side="good")


async def add_film(
    films: FilmRepository,
    title: str,
    *,
    side: str | None = None,
    genre: str | None = None,
    category_key: str | None = None,
    watched_at: str | None = None,
) -> Film:
    return await films.add(
        NewFilm(
            slug=title.lower().replace(" ", "-"),
            title=title,
            year=2000,
            side=side,
            genre=genre,
            category_key=category_key,
            watched_at=watched_at,
        )
    )


async def picks(
    picker: PickerService, count: int, filters: SuggestFilters | None = None
) -> set[str]:
    """The titles of `count` suggestions in a row."""
    return {
        (await picker.suggest(requested_by=1, filters=filters)).film.title for _ in range(count)
    }


async def test_suggest_never_picks_watched(picker: PickerService, films: FilmRepository) -> None:
    await add_film(films, "Unwatched")
    for number in range(5):
        await add_film(films, f"Watched {number}", watched_at=WATCHED_AT)

    assert await picks(picker, 20) == {"Unwatched"}


async def test_suggest_skips_last_10_suggestions(
    picker: PickerService, films: FilmRepository, suggestions: SuggestionRepository
) -> None:
    pool = [await add_film(films, f"Film {number}") for number in range(12)]
    for film in pool[:10]:
        await suggestions.add(film.id, requested_by=1)

    suggestion = await picker.suggest(requested_by=1)

    assert suggestion.film.title in {"Film 10", "Film 11"}


async def test_suggest_falls_back_when_pool_is_small(
    picker: PickerService, films: FilmRepository, suggestions: SuggestionRepository
) -> None:
    first = await add_film(films, "First")
    second = await add_film(films, "Second")
    for film in (first, second):
        await suggestions.add(film.id, requested_by=1)

    # Both films are in the last 10 suggestions, so that rule is dropped,
    # but Another still leaves out the film it is re-rolling away from.
    suggestion = await picker.suggest(requested_by=1, leave_out=first.id)

    assert suggestion.film.title == "Second"


async def test_another_shows_the_same_film_only_when_it_is_the_only_one(
    picker: PickerService, films: FilmRepository
) -> None:
    only = await add_film(films, "Only")

    suggestion = await picker.suggest(requested_by=1, leave_out=only.id)

    assert suggestion.film.title == "Only"


async def test_suggest_respects_filters(
    picker: PickerService, films: FilmRepository, categories: CategoryRepository, launch: Category
) -> None:
    await categories.add(PLACE)
    await add_film(films, "Hate", side="bad", genre="masala")
    await add_film(films, "Good", side="good", genre="drama")
    await add_film(films, "Both", side="both", genre="masala")
    await add_film(films, "Launched", category_key="launch")  # no side: "bad" from its category
    await add_film(films, "Placed", category_key="place")  # no side: "good" from its category
    await add_film(films, "Plain")  # no side and no category

    assert await picks(picker, 40, SuggestFilters(side="bad")) == {"Hate", "Both", "Launched"}
    assert await picks(picker, 40, SuggestFilters(side="good")) == {"Good", "Both", "Placed"}
    assert await picks(picker, 40, SuggestFilters(genre="masala")) == {"Hate", "Both"}
    assert await picks(picker, 40, SuggestFilters(category_key="launch")) == {"Launched"}
    assert await picks(picker, 40, SuggestFilters(genre="masala", side="good")) == {"Both"}
    assert await picks(picker, 60) == {"Hate", "Good", "Both", "Launched", "Placed", "Plain"}


async def test_suggestion_carries_its_category_and_filters(
    picker: PickerService, films: FilmRepository, launch: Category
) -> None:
    await add_film(films, "Launched", category_key="launch")

    suggestion = await picker.suggest(requested_by=1, filters=SuggestFilters(side="bad"))

    assert suggestion.category == launch
    assert suggestion.filters == SuggestFilters(side="bad")


async def test_unknown_category_is_refused(picker: PickerService) -> None:
    with pytest.raises(UnknownCategory):
        await picker.suggest(requested_by=1, filters=SuggestFilters(category_key="nope"))


async def test_another_never_shows_the_same_film_twice_in_a_row(
    picker: PickerService, films: FilmRepository
) -> None:
    for number in range(3):
        await add_film(films, f"Film {number}")

    current = await picker.suggest(requested_by=1)
    for _ in range(30):
        following = await picker.suggest(requested_by=1, leave_out=current.film.id)
        assert following.film.id != current.film.id
        current = following


@pytest.mark.parametrize("seed", range(5))
async def test_twenty_clicks_of_another_never_repeat_a_film_within_ten(
    seed: int,
    films: FilmRepository,
    categories: CategoryRepository,
    suggestions: SuggestionRepository,
) -> None:
    for number in range(25):
        await add_film(films, f"Film {number}")
    picker = PickerService(
        films,
        categories,
        suggestions,
        rng=random.Random(seed),  # noqa: S311 (picking films, not secrets)
        clock=lambda: datetime(2026, 10, 21, 18, 0, tzinfo=UTC),
    )

    current = await picker.suggest(requested_by=1)
    shown = [current.film.id]
    for _ in range(20):
        current = await picker.suggest(requested_by=1, leave_out=current.film.id)
        shown.append(current.film.id)

    for start in range(len(shown) - 10):
        window = shown[start : start + 11]  # a film and the 10 clicks after it
        assert len(set(window)) == len(window)


async def test_nothing_to_suggest(picker: PickerService, films: FilmRepository) -> None:
    with pytest.raises(NothingToSuggest, match="Add some films with /add"):
        await picker.suggest(requested_by=1)

    await add_film(films, "Hate", side="bad")

    with pytest.raises(NothingToSuggest, match="match those filters"):
        await picker.suggest(requested_by=1, filters=SuggestFilters(side="good"))


async def test_each_suggestion_is_recorded(
    picker: PickerService, films: FilmRepository, suggestions: SuggestionRepository
) -> None:
    film = await add_film(films, "Film")

    await picker.suggest(requested_by=42)

    assert await suggestions.recent_film_ids(10) == [film.id]


async def test_watch_marks_the_film_watched_and_the_suggestion_chosen(
    picker: PickerService, films: FilmRepository, db: Database
) -> None:
    film = await add_film(films, "Film")
    await picker.suggest(requested_by=1)

    watched = await picker.watch(film.id)

    assert watched.watched_at == "2026-10-21T18:00:00Z"
    stored = await films.get(film.id)
    assert stored is not None
    assert stored.watched_at == "2026-10-21T18:00:00Z"
    rows = await db.conn.execute_fetchall("SELECT chosen FROM suggestions")
    assert [row[0] for row in rows] == [1]


async def test_watch_refuses_a_watched_or_removed_film(
    picker: PickerService, films: FilmRepository
) -> None:
    film = await add_film(films, "Seen", watched_at=WATCHED_AT)

    with pytest.raises(AlreadyWatched, match="already marked as watched"):
        await picker.watch(film.id)
    with pytest.raises(FilmNotFound):
        await picker.watch(9999)
