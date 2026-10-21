"""WatchlistService: the rules for adding films and listing them (FR-2 to FR-4)."""

import math
import re

from moviebot.db.categories import CategoryRepository
from moviebot.db.films import FilmRepository
from moviebot.models import (
    AddedFilm,
    Category,
    DuplicateFilm,
    FilmPage,
    InvalidFilm,
    NewFilm,
    Show,
    UnknownCategory,
)

PAGE_SIZE = 10
MAX_TITLE = 200
MAX_NOTE = 500
MIN_YEAR = 1888  # the oldest surviving film
MAX_YEAR = 2100


def make_slug(title: str, year: int | None) -> str:
    """A film's permanent key, made like the seed file's ids: 'Ra.One', 2011 -> 'ra-one-2011'.

    Lower-case the title, turn each run of characters other than a-z and 0-9 into one hyphen,
    then add the year. A title with no a-z or 0-9 at all becomes 'film'.
    """
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "film"
    return base if year is None else f"{base}-{year}"


class WatchlistService:
    """Adds and lists films. Uses only the repositories, and never imports discord."""

    def __init__(self, films: FilmRepository, categories: CategoryRepository) -> None:
        self._films = films
        self._categories = categories

    async def add_film(
        self,
        *,
        title: str,
        year: int | None = None,
        category_key: str | None = None,
        note: str | None = None,
        added_by: int | None = None,
        tmdb_id: int | None = None,
    ) -> AddedFilm:
        """Add a film (FR-2) unless it's already on the list (FR-4).

        Raises InvalidFilm, UnknownCategory or DuplicateFilm. A film added without a year comes
        back with same_title set when a film with the same title is already listed.
        """
        title = title.strip()
        note = (note or "").strip() or None
        if not 1 <= len(title) <= MAX_TITLE:
            raise InvalidFilm(f"The title must be 1 to {MAX_TITLE} characters.")
        if note is not None and len(note) > MAX_NOTE:
            raise InvalidFilm(f"The note can be at most {MAX_NOTE} characters.")
        if year is not None and not MIN_YEAR <= year <= MAX_YEAR:
            raise InvalidFilm(f"The year must be between {MIN_YEAR} and {MAX_YEAR}.")
        category = await self._category(category_key)

        existing = await self._films.find_duplicate(title=title, year=year, tmdb_id=tmdb_id)
        if existing is not None:
            raise DuplicateFilm(existing)
        same_title = await self._films.find_by_title(title) if year is None else None

        film = await self._films.add(
            NewFilm(
                slug=await self._free_slug(make_slug(title, year)),
                title=title,
                year=year,
                tmdb_id=tmdb_id,
                category_key=category.key if category else None,
                note=note,
                added_by=added_by,
            )
        )
        return AddedFilm(film=film, category=category, same_title=same_title)

    async def list_films(
        self, *, show: Show = "unwatched", category_key: str | None = None, page: int = 1
    ) -> FilmPage:
        """One page of the list (FR-3): unwatched films by default, 10 a page, sorted by title.

        A page number past either end gives the nearest page that exists.
        """
        category = await self._category(category_key)
        key = category.key if category else None
        total = await self._films.count(show=show, category_key=key)
        page_count = max(1, math.ceil(total / PAGE_SIZE))
        page = min(max(page, 1), page_count)
        films = await self._films.list_page(
            show=show, category_key=key, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE
        )
        names = {each.key: each.name for each in await self._categories.list_all()}
        return FilmPage(
            films=tuple(films),
            page=page,
            page_count=page_count,
            per_page=PAGE_SIZE,
            total=total,
            show=show,
            category=category,
            category_names=names,
        )

    async def list_categories(self) -> list[Category]:
        """Every category, in display order."""
        return await self._categories.list_all()

    async def _category(self, key: str | None) -> Category | None:
        """The category with this key: None when no key is given, UnknownCategory if missing."""
        if key is None or not key.strip():
            return None
        category = await self._categories.get(key.strip())
        if category is None:
            raise UnknownCategory(key.strip())
        return category

    async def _free_slug(self, base: str) -> str:
        """base, or else base-2, base-3 and so on: the first that no film uses yet."""
        slug, number = base, 1
        while await self._films.slug_taken(slug):
            number += 1
            slug = f"{base}-{number}"
        return slug
