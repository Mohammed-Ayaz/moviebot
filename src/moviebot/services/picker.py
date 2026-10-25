"""PickerService: the suggestion algorithm (FR-7, FR-10) and "We're watching this" (FR-9)."""

import random
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from moviebot.db.categories import CategoryRepository
from moviebot.db.films import FilmRepository
from moviebot.db.suggestions import SuggestionRepository
from moviebot.models import (
    AlreadyWatched,
    Category,
    Film,
    FilmNotFound,
    NothingToSuggest,
    SuggestFilters,
    Suggestion,
    UnknownCategory,
)

RECENT = 10  # films in this many of the latest suggestions are left out


class PickerService:
    """Picks tonight's film. Takes a random.Random and a clock, so tests can fix both."""

    def __init__(
        self,
        films: FilmRepository,
        categories: CategoryRepository,
        suggestions: SuggestionRepository,
        *,
        rng: random.Random,
        clock: Callable[[], datetime],
    ) -> None:
        self._films = films
        self._categories = categories
        self._suggestions = suggestions
        self._rng = rng
        self._clock = clock

    async def suggest(
        self,
        *,
        requested_by: int,
        filters: SuggestFilters | None = None,
        leave_out: int | None = None,
    ) -> Suggestion:
        """Pick a random film for tonight, in the spec's five steps.

        1. Take the unwatched films that match the filters.
        2. Leave out the films in the last 10 suggestions, and leave_out: the film that Another
           is re-rolling away from.
        3. If nothing is left, drop the last-10 rule but keep leaving out leave_out, unless it's
           the only film. If there's still nothing, raise NothingToSuggest.
        4. Choose one uniformly at random.
        5. Record the suggestion.
        """
        filters = filters or SuggestFilters()
        categories = {category.key: category for category in await self._categories.list_all()}
        if filters.category_key is not None and filters.category_key not in categories:
            raise UnknownCategory(filters.category_key)

        unwatched = await self._films.unwatched(
            category_key=filters.category_key, genre=filters.genre
        )
        pool = [
            film
            for film in unwatched
            if filters.side is None or _counts_for_side(film, filters.side, categories)
        ]
        recent = set(await self._suggestions.recent_film_ids(RECENT))
        candidates = (
            [film for film in pool if film.id not in recent and film.id != leave_out]
            or [film for film in pool if film.id != leave_out]
            or pool
        )
        if not candidates:
            raise NothingToSuggest(filtered=filters.active)

        film = self._rng.choice(candidates)
        await self._suggestions.add(film.id, requested_by)
        category = categories.get(film.category_key) if film.category_key else None
        return Suggestion(film=film, category=category, filters=filters)

    async def watch(self, film_id: int) -> Film:
        """ "We're watching this" (FR-9): mark the film watched and its suggestion chosen.

        Raises FilmNotFound or AlreadyWatched.
        """
        film = await self._films.get(film_id)
        if film is None:
            raise FilmNotFound
        watched_at = self._timestamp()
        if film.watched_at is not None or not await self._suggestions.choose(film_id, watched_at):
            raise AlreadyWatched(film)
        return replace(film, watched_at=watched_at)

    def _timestamp(self) -> str:
        """Now, in the ISO 8601 UTC format the database uses."""
        return self._clock().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _counts_for_side(film: Film, side: str, categories: dict[str, Category]) -> bool:
    """Whether a film counts for the side filter: its own side, or else its category's.

    A film on side "both" counts for either side.
    """
    own = film.side
    if own is None and film.category_key is not None and film.category_key in categories:
        own = categories[film.category_key].side
    return own in (side, "both")
