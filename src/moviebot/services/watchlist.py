"""WatchlistService: the rules for adding films and listing them (FR-2 to FR-5)."""

import logging
import math
import re
from collections.abc import Callable
from datetime import UTC, datetime

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
    TmdbMovie,
    TmdbResult,
    TmdbUnavailable,
    UnknownCategory,
)
from moviebot.tmdb.client import TmdbApi, TmdbError

log = logging.getLogger(__name__)

PAGE_SIZE = 10
MAX_TITLE = 200
MAX_NOTE = 500
MIN_YEAR = 1888  # the oldest surviving film
MAX_YEAR = 2100
MIN_SEARCH = 2  # characters typed before /add's suggestions search TMDB


def make_slug(title: str, year: int | None) -> str:
    """A film's permanent key, made like the seed file's ids: 'Ra.One', 2011 -> 'ra-one-2011'.

    Lower-case the title, turn each run of characters other than a-z and 0-9 into one hyphen,
    then add the year. A title with no a-z or 0-9 at all becomes 'film'.
    """
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "film"
    return base if year is None else f"{base}-{year}"


def titles_match(typed: str, other: str) -> bool:
    """Whether two titles are the same once case and punctuation are ignored: 'ra one', 'Ra.One'."""
    plain = _plain(typed)
    return plain != "" and plain == _plain(other)


class WatchlistService:
    """Adds and lists films. Uses the repositories and the TMDB client; never imports discord."""

    def __init__(
        self,
        films: FilmRepository,
        categories: CategoryRepository,
        tmdb: TmdbApi,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._films = films
        self._categories = categories
        self._tmdb = tmdb
        self._clock = clock

    async def search_tmdb(self, query: str) -> list[TmdbMovie]:
        """TMDB films for /add's suggestions (FR-5): none under 2 characters, or if TMDB fails."""
        query = query.strip()
        if len(query) < MIN_SEARCH:
            return []
        try:
            return await self._tmdb.search(query)
        except TmdbError as error:
            log.warning("TMDB search failed: %s", error)
            return []

    async def add_from_tmdb(
        self,
        tmdb_id: int,
        *,
        category_key: str | None = None,
        note: str | None = None,
        added_by: int | None = None,
    ) -> AddedFilm:
        """Add the film picked from TMDB's suggestions, with TMDB's title, year, poster, runtime.

        Raises DuplicateFilm before asking TMDB if the film is already listed, and
        TmdbUnavailable if TMDB doesn't answer.
        """
        note = _clean_note(note)
        category = await self._category(category_key)
        existing = await self._films.get_by_tmdb_id(tmdb_id)
        if existing is not None:
            raise DuplicateFilm(existing)
        try:
            movie = await self._tmdb.details(tmdb_id)
        except TmdbError as error:
            log.warning("TMDB details failed: %s", error)
            raise TmdbUnavailable from error
        return await self._add(
            title=movie.title,
            year=movie.year,
            movie=movie,
            category=category,
            note=note,
            added_by=added_by,
            tmdb="found",
        )

    async def add_film(
        self,
        *,
        title: str,
        year: int | None = None,
        category_key: str | None = None,
        note: str | None = None,
        added_by: int | None = None,
    ) -> AddedFilm:
        """Add a typed title (FR-2), searching TMDB for it once.

        A single exact match on TMDB is used as if it were picked. Otherwise the film is saved as
        typed, and AddedFilm.tmdb says why. Raises InvalidFilm, UnknownCategory or DuplicateFilm.
        """
        title = _clean_title(title)
        year = _check_year(year)
        note = _clean_note(note)
        category = await self._category(category_key)
        tmdb: TmdbResult
        try:
            movie = await self._match_on_tmdb(title, year)
        except TmdbError as error:
            log.warning("TMDB lookup failed: %s", error)
            movie, tmdb = None, "unavailable"
        else:
            tmdb = "not_found" if movie is None else "found"
        return await self._add(
            title=movie.title if movie else title,
            year=movie.year if movie else year,
            movie=movie,
            category=category,
            note=note,
            added_by=added_by,
            tmdb=tmdb,
        )

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

    async def _match_on_tmdb(self, title: str, year: int | None) -> TmdbMovie | None:
        """The one TMDB film with this title, and a year within 1 of the given year if any.

        Returns it with its details, or None when TMDB has no such film or more than one.
        """
        matches = [
            movie
            for movie in await self._tmdb.search(title)
            if titles_match(title, movie.title)
            and (year is None or (movie.year is not None and abs(movie.year - year) <= 1))
        ]
        if len(matches) != 1:
            return None
        return await self._tmdb.details(matches[0].id)

    async def _add(
        self,
        *,
        title: str,
        year: int | None,
        movie: TmdbMovie | None,
        category: Category | None,
        note: str | None,
        added_by: int | None,
        tmdb: TmdbResult,
    ) -> AddedFilm:
        """Shared by every way of adding: title and year rules, duplicates (FR-4), the slug."""
        title = _clean_title(title)
        year = _check_year(year)
        tmdb_id = movie.id if movie else None
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
                poster_path=movie.poster_path if movie else None,
                runtime_min=movie.runtime_min if movie else None,
                tmdb_synced_at=self._timestamp() if movie else None,
            )
        )
        return AddedFilm(film=film, category=category, same_title=same_title, tmdb=tmdb)

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

    def _timestamp(self) -> str:
        """Now, in the ISO 8601 UTC format the database uses."""
        return self._clock().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_title(title: str) -> str:
    title = title.strip()
    if not 1 <= len(title) <= MAX_TITLE:
        raise InvalidFilm(f"The title must be 1 to {MAX_TITLE} characters.")
    return title


def _clean_note(note: str | None) -> str | None:
    note = (note or "").strip() or None
    if note is not None and len(note) > MAX_NOTE:
        raise InvalidFilm(f"The note can be at most {MAX_NOTE} characters.")
    return note


def _check_year(year: int | None) -> int | None:
    if year is not None and not MIN_YEAR <= year <= MAX_YEAR:
        raise InvalidFilm(f"The year must be between {MIN_YEAR} and {MAX_YEAR}.")
    return year


def _plain(title: str) -> str:
    """A title in lower case with each run of punctuation and spaces turned into one space."""
    return re.sub(r"[\W_]+", " ", title.casefold()).strip()
