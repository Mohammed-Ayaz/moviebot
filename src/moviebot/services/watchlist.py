"""WatchlistService: the rules for adding, listing and changing films.

It covers FR-2 to FR-5, FR-11 to FR-13, and the do-not-watch check on adding (FR-17).
"""

import logging
import math
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from moviebot.db.blocklist import BlocklistRepository
from moviebot.db.categories import CategoryRepository
from moviebot.db.films import FilmRepository
from moviebot.models import (
    AddedFilm,
    AlreadyWatched,
    AmbiguousFilm,
    Blocklisted,
    BlocklistEntry,
    Category,
    DuplicateFilm,
    Film,
    FilmInfo,
    FilmNotFound,
    FilmPage,
    InvalidFilm,
    NewFilm,
    NotWatched,
    Show,
    TmdbMovie,
    TmdbResult,
    TmdbUnavailable,
    UnknownCategory,
    UnknownFilm,
)
from moviebot.tmdb.client import TmdbApi, TmdbError

log = logging.getLogger(__name__)

PAGE_SIZE = 10
MAX_TITLE = 200
MAX_NOTE = 500
MIN_YEAR = 1888  # the oldest surviving film
MAX_YEAR = 2100
MIN_SEARCH = 2  # characters typed before /add's suggestions search TMDB
REFRESH_AFTER = timedelta(days=150)  # about 5 months: TMDB's terms allow keeping its data for 6
REFRESH_BATCH = 50  # films refreshed per daily run at most, to stay gentle with TMDB
REFRESH_GIVE_UP = 3  # failures in one run that mean TMDB isn't answering: try again tomorrow


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
        blocklist: BlocklistRepository,
        tmdb: TmdbApi,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._films = films
        self._categories = categories
        self._blocklist = blocklist
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
        confirmed: bool = False,
    ) -> AddedFilm:
        """Add the film picked from TMDB's suggestions, with TMDB's title, year, poster, runtime.

        Raises DuplicateFilm before asking TMDB if the film is already listed, and
        TmdbUnavailable if TMDB doesn't answer. A film on the do-not-watch list raises
        Blocklisted unless confirmed is True (FR-17).
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
            confirmed=confirmed,
        )

    async def add_film(
        self,
        *,
        title: str,
        year: int | None = None,
        category_key: str | None = None,
        note: str | None = None,
        added_by: int | None = None,
        confirmed: bool = False,
    ) -> AddedFilm:
        """Add a typed title (FR-2), searching TMDB for it once.

        A single exact match on TMDB is used as if it were picked. Otherwise the film is saved as
        typed, and AddedFilm.tmdb says why. Raises InvalidFilm, UnknownCategory or DuplicateFilm,
        and Blocklisted for a film on the do-not-watch list unless confirmed is True (FR-17).
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
            confirmed=confirmed,
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

    async def category(self, key: str | None) -> Category | None:
        """The category with this key, or None for no key. Raises UnknownCategory."""
        return await self._category(key)

    async def search_films(
        self, text: str, *, watched: bool | None = None, limit: int = 25
    ) -> list[Film]:
        """Films whose title contains the text, ignoring case and punctuation, sorted by title.

        This feeds the film options' suggestions: watched=False for unwatched films only, True
        for watched ones. The list is a few hundred films, so the matching happens here.
        """
        wanted = _plain(text)
        films = await self._films.list_all(watched=watched)
        return [film for film in films if wanted in _plain(film.title)][:limit]

    async def get_film(self, film_id: int) -> Film:
        """The film with this id. Raises FilmNotFound."""
        film = await self._films.get(film_id)
        if film is None:
            raise FilmNotFound
        return film

    async def film_named(self, title: str, *, watched: bool | None = None) -> Film:
        """The one film with this title, ignoring case and punctuation, for a name typed in full.

        Looks among the watched or unwatched films first, if asked to, and then among all films.
        Raises UnknownFilm when no film has the title, and AmbiguousFilm when several do.
        """
        films = await self._films.list_all(watched=watched)
        matches = [film for film in films if titles_match(title, film.title)]
        if not matches and watched is not None:
            everything = await self._films.list_all()
            matches = [film for film in everything if titles_match(title, film.title)]
        if not matches:
            raise UnknownFilm(title.strip())
        if len(matches) > 1:
            raise AmbiguousFilm(title.strip())
        return matches[0]

    async def remove_film(self, film_id: int) -> Film:
        """Delete a film, with its suggestion history (FR-11). Returns the film that was removed."""
        film = await self.get_film(film_id)
        if not await self._films.delete(film_id):
            raise FilmNotFound
        return film

    async def edit_film(
        self, film_id: int, *, note: str | None, category_key: str | None = None
    ) -> FilmInfo:
        """Set a film's note, and its category if one is given (FR-12). An empty note clears it.

        Raises FilmNotFound, InvalidFilm or UnknownCategory.
        """
        note = _clean_note(note)
        film = await self.get_film(film_id)
        category = await self._category(category_key or film.category_key)
        updated = await self._films.update(
            film_id, note=note, category_key=category.key if category else None
        )
        if updated is None:
            raise FilmNotFound
        return FilmInfo(film=updated, category=category)

    async def mark_watched(self, film_id: int) -> Film:
        """/watched (FR-13): mark the film watched now. Raises FilmNotFound or AlreadyWatched."""
        film = await self.get_film(film_id)
        watched = await self._films.mark_watched(film_id, self._timestamp())
        if watched is None:
            raise AlreadyWatched(film)
        return watched

    async def unwatch(self, film_id: int) -> Film:
        """/unwatch (FR-13): back on the unwatched list. Raises FilmNotFound or NotWatched."""
        film = await self.get_film(film_id)
        unwatched = await self._films.mark_unwatched(film_id)
        if unwatched is None:
            raise NotWatched(film)
        return unwatched

    async def refresh_tmdb(self, *, limit: int = REFRESH_BATCH) -> int:
        """Fetch TMDB's poster and runtime again for films last fetched over 5 months ago.

        TMDB's terms allow keeping its data for up to six months. A film TMDB can't give right
        now is skipped and tried again on the next run. Returns how many films were refreshed.
        """
        cutoff = (self._clock() - REFRESH_AFTER).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        refreshed = failures = 0
        for film in await self._films.needing_refresh(synced_before=cutoff, limit=limit):
            if film.tmdb_id is None:  # the query leaves these out; this tells the type checker
                continue
            try:
                movie = await self._tmdb.details(film.tmdb_id)
            except TmdbError as error:
                log.warning("Couldn't refresh %s from TMDB: %s", film.label, error)
                failures += 1
                if failures == REFRESH_GIVE_UP:
                    break
                continue
            await self._films.set_tmdb(
                film.id,
                tmdb_id=film.tmdb_id,
                poster_path=movie.poster_path,
                runtime_min=movie.runtime_min,
                synced_at=self._timestamp(),
            )
            refreshed += 1
        return refreshed

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
        confirmed: bool,
    ) -> AddedFilm:
        """Shared by every way of adding: the title and year rules, the checks, and the slug.

        Duplicates are refused first (FR-4), then the do-not-watch list unless confirmed (FR-17).
        """
        title = _clean_title(title)
        year = _check_year(year)
        tmdb_id = movie.id if movie else None
        existing = await self._films.find_duplicate(title=title, year=year, tmdb_id=tmdb_id)
        if existing is not None:
            raise DuplicateFilm(existing)
        if not confirmed:
            entry = await self._blocked(title, year)
            if entry is not None:
                raise Blocklisted(entry)
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

    async def _blocked(self, title: str, year: int | None) -> BlocklistEntry | None:
        """The do-not-watch entry for this film, if there is one.

        Titles match ignoring case and punctuation, and the years must be equal unless the film
        or the entry has no year. The list is a dozen or so entries, so matching happens here.
        """
        for entry in await self._blocklist.list_all():
            same_year = year is None or entry.year is None or entry.year == year
            if same_year and titles_match(title, entry.title):
                return entry
        return None

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
