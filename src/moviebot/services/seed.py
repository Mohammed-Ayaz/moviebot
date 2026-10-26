"""SeedService: the one-time import of watchlist_seed.json (FR-15), and matching it on TMDB.

scripts/import_seed.py reads the files and prints what happened; the rules live here. Every
insert leaves existing rows alone, so importing again adds nothing and never undoes an edit.
"""

import logging
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from moviebot.db.blocklist import BlocklistRepository
from moviebot.db.categories import CategoryRepository
from moviebot.db.films import FilmRepository
from moviebot.models import (
    Category,
    Film,
    InvalidSeed,
    NewFilm,
    Seed,
    SeedBlock,
    SeedFilm,
    SeedReport,
    TmdbMatches,
    TmdbMovie,
)
from moviebot.services.watchlist import MAX_TITLE, MAX_YEAR, MIN_YEAR, titles_match
from moviebot.tmdb.client import TmdbApi, TmdbError

log = logging.getLogger(__name__)

MAX_WHY_WATCH = 1000  # FR-20
SIDES = ("bad", "good", "both")
GENRES = ("masala", "drama", "horror")
CATEGORY_KEY = re.compile(r"[a-z0-9]+")  # keys travel in button ids, which are split at colons
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class SeedService:
    """Imports the seed file and finds its films on TMDB. Never imports discord."""

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

    async def import_seed(self, seed: Seed) -> SeedReport:
        """Add the seed's categories, films and do-not-watch entries, leaving existing ones alone.

        A film already on the list, by slug, TMDB id, or title and year, is left out. Films
        marked watched get watched_at set to now, and each film's note goes into why_watch,
        because an AI wrote it (FR-15).
        """
        now = self._timestamp()
        categories_added = films_added = blocked_added = 0
        for category in seed.categories:
            if await self._categories.add(category):
                categories_added += 1
        for film in seed.films:
            new = NewFilm(
                slug=film.slug,
                title=film.title,
                year=film.year,
                category_key=film.category_key,
                side=film.side,
                genre=film.genre,
                is_indian=film.is_indian,
                grade=film.grade,
                why_watch=film.why_watch,
                watched_at=now if film.watched else None,
            )
            if await self._films.add_if_new(new) is not None:
                films_added += 1
        for block in seed.blocklist:
            if await self._blocklist.add(block.title, block.year, block.reason):
                blocked_added += 1
        return SeedReport(
            categories_added=categories_added,
            films_added=films_added,
            films_skipped=len(seed.films) - films_added,
            blocked_added=blocked_added,
        )

    async def match_tmdb(self, seed: Seed) -> TmdbMatches:
        """Find each seed film that has no TMDB id yet on TMDB, and store its poster and runtime.

        Takes the first result whose title matches, ignoring case and punctuation, and whose year
        is within 1. It searches with the year first, then without it, because TMDB's year can be
        one off. If TMDB stops answering, it stops; running it again carries on from there.
        """
        progress = _Progress()
        for seed_film in seed.films:
            film = await self._films.get_by_slug(seed_film.slug)
            if film is None or film.tmdb_id is not None:
                continue
            try:
                movie = await self._first_match(film.title, film.year)
            except TmdbError as error:
                log.warning("TMDB stopped answering: %s", error)
                return progress.report(stopped=True)
            if movie is None:
                progress.unmatched.append(film)
            else:
                await self._store(film, movie, progress)
        return progress.report()

    async def apply_fixes(self, fixes: list[tuple[str, int]]) -> TmdbMatches:
        """--map: give each slug's film the TMDB film named for it, replacing any earlier match."""
        progress = _Progress()
        for slug, tmdb_id in fixes:
            film = await self._films.get_by_slug(slug)
            if film is None:
                progress.unknown_slugs.append(slug)
                continue
            try:
                movie = await self._tmdb.details(tmdb_id)
            except TmdbError as error:
                log.warning("No TMDB film %d for %s: %s", tmdb_id, slug, error)
                progress.unmatched.append(film)
                continue
            await self._store(film, movie, progress)
        return progress.report()

    async def _first_match(self, title: str, year: int | None) -> TmdbMovie | None:
        """The first TMDB film with this title and a year within 1, with its details."""
        for search_year in (year, None) if year is not None else (None,):
            for movie in await self._tmdb.search(title, search_year):
                if titles_match(title, movie.title) and _near(movie.year, year):
                    return await self._tmdb.details(movie.id)
        return None

    async def _store(self, film: Film, movie: TmdbMovie, progress: "_Progress") -> None:
        """Save the TMDB film's id, poster and runtime on the film, unless another film has it."""
        holder = await self._films.get_by_tmdb_id(movie.id)
        if holder is not None and holder.id != film.id:
            progress.taken.append((film, holder))
            return
        updated = await self._films.set_tmdb(
            film.id,
            tmdb_id=movie.id,
            poster_path=movie.poster_path,
            runtime_min=movie.runtime_min,
            synced_at=self._timestamp(),
        )
        if updated is not None:
            progress.matched.append(updated)

    def _timestamp(self) -> str:
        """Now, in the ISO 8601 UTC format the database uses."""
        return self._clock().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class _Progress:
    """A TmdbMatches while it's being filled in."""

    matched: list[Film] = field(default_factory=list)
    unmatched: list[Film] = field(default_factory=list)
    taken: list[tuple[Film, Film]] = field(default_factory=list)
    unknown_slugs: list[str] = field(default_factory=list)

    def report(self, *, stopped: bool = False) -> TmdbMatches:
        return TmdbMatches(
            matched=tuple(self.matched),
            unmatched=tuple(self.unmatched),
            taken=tuple(self.taken),
            unknown_slugs=tuple(self.unknown_slugs),
            stopped=stopped,
        )


def parse_seed(data: object) -> Seed:
    """Check a decoded seed file and turn it into a Seed. Raises InvalidSeed naming the problem."""
    top = _object(data, "The seed file")
    categories = tuple(
        _category(item, f"categories[{number}]")
        for number, item in enumerate(_list(top, "categories"))
    )
    _no_repeats((category.key for category in categories), "category key")
    keys = {category.key for category in categories}
    films = tuple(
        _film(item, f"films[{number}]", keys) for number, item in enumerate(_list(top, "films"))
    )
    _no_repeats((film.slug for film in films), "film id")
    blocks = tuple(
        _block(item, f"{name}[{number}]")
        for name in ("didnt_land", "do_not_watch")
        for number, item in enumerate(_list(top, name, required=False))
    )
    return Seed(categories=categories, films=films, blocklist=blocks)


def parse_fixes(text: str) -> list[tuple[str, int]]:
    """Read --map's file: a slug and a TMDB id on each line, like heropanti-2014,280391.

    A semicolon or a tab works as the separator too, because spreadsheet apps in some countries
    save CSV files that way. Blank lines and a 'slug,tmdb_id' header line are skipped.
    """
    fixes: list[tuple[str, int]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        cells = [cell.strip().strip('"').strip() for cell in re.split(r"[,;\t]", line)]
        if not any(cells) or (number == 1 and cells == ["slug", "tmdb_id"]):
            continue
        if len(cells) != 2 or not cells[0] or not (cells[1].isascii() and cells[1].isdigit()):
            raise InvalidSeed(f"Line {number} should look like heropanti-2014,280391.")
        fixes.append((cells[0], int(cells[1])))
    return fixes


def _category(item: object, where: str) -> Category:
    entry = _object(item, where)
    key = _text(entry, "key", where, limit=30)
    if not CATEGORY_KEY.fullmatch(key):
        raise InvalidSeed(f"{where}: key must be lower-case letters and digits.")
    number = entry.get("number")
    if not _is_int(number):
        raise InvalidSeed(f"{where}: number must be a whole number.")
    side = _choice(entry, "side", where, SIDES)
    if side is None:
        raise InvalidSeed(f"{where}: side is missing.")
    return Category(
        key=key,
        name=_text(entry, "name", where, limit=100),
        position=number,
        side=side,
        blurb=_maybe_text(entry, "blurb", where),
    )


def _film(item: object, where: str, categories: set[str]) -> SeedFilm:
    entry = _object(item, where)
    slug = _text(entry, "id", where, limit=MAX_TITLE + 10)
    if not SLUG.fullmatch(slug):
        raise InvalidSeed(f"{where}: id must be lower-case letters, digits and hyphens.")
    category = _maybe_text(entry, "category", where)
    if category is not None and category not in categories:
        raise InvalidSeed(f"{where}: category \"{category}\" isn't one of the file's categories.")
    return SeedFilm(
        slug=slug,
        title=_text(entry, "title", where, limit=MAX_TITLE),
        year=_year(entry, where),
        category_key=category,
        side=_choice(entry, "side", where, SIDES),
        genre=_choice(entry, "genre", where, GENRES),
        is_indian=_flag(entry, "indian", where, default=True),
        grade=_maybe_text(entry, "grade", where, limit=20),
        why_watch=_maybe_text(entry, "note", where, limit=MAX_WHY_WATCH),
        watched=_flag(entry, "watched", where, default=False),
    )


def _block(item: object, where: str) -> SeedBlock:
    entry = _object(item, where)
    return SeedBlock(
        title=_text(entry, "title", where, limit=MAX_TITLE),
        year=_year(entry, where),
        reason=_maybe_text(entry, "note", where, limit=MAX_WHY_WATCH),
    )


def _object(value: object, where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise InvalidSeed(f"{where} must be a JSON object.")
    return value


def _list(top: Mapping[str, Any], name: str, *, required: bool = True) -> list[Any]:
    value = top.get(name)
    if value is None and not required:
        return []
    if not isinstance(value, list):
        raise InvalidSeed(f'"{name}" must be a list.')
    return value


def _text(entry: Mapping[str, Any], name: str, where: str, *, limit: int) -> str:
    value = _maybe_text(entry, name, where, limit=limit)
    if value is None:
        raise InvalidSeed(f"{where}: {name} is missing.")
    return value


def _maybe_text(
    entry: Mapping[str, Any], name: str, where: str, *, limit: int | None = None
) -> str | None:
    value = entry.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidSeed(f"{where}: {name} must be text.")
    value = value.strip()
    if limit is not None and len(value) > limit:
        raise InvalidSeed(f"{where}: {name} can be at most {limit} characters.")
    return value or None


def _year(entry: Mapping[str, Any], where: str) -> int | None:
    year = entry.get("year")
    if year is not None and not (_is_int(year) and MIN_YEAR <= year <= MAX_YEAR):
        raise InvalidSeed(f"{where}: year must be a whole number from {MIN_YEAR} to {MAX_YEAR}.")
    return year


def _choice(
    entry: Mapping[str, Any], name: str, where: str, allowed: tuple[str, ...]
) -> str | None:
    value = entry.get(name)
    if value is not None and value not in allowed:
        raise InvalidSeed(f"{where}: {name} must be one of {', '.join(allowed)}.")
    return value


def _flag(entry: Mapping[str, Any], name: str, where: str, *, default: bool) -> bool:
    value = entry.get(name)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise InvalidSeed(f"{where}: {name} must be true or false.")
    return value


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _no_repeats(values: Iterable[str], what: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise InvalidSeed(f'The {what} "{value}" appears twice.')
        seen.add(value)


def _near(found: int | None, wanted: int | None) -> bool:
    """Whether TMDB's year is within 1 of the wanted one. Any year will do if none is wanted."""
    return wanted is None or (found is not None and abs(found - wanted) <= 1)
