"""FilmRepository: all the SQL for the films table."""

from collections.abc import Iterable

import aiosqlite

from moviebot.db.database import Database
from moviebot.models import Film, NewFilm, Show

# For each /list "show" option: (include unwatched films, include watched films).
_SHOW = {"unwatched": (1, 0), "watched": (0, 1), "all": (1, 1)}


class FilmRepository:
    """Reads and writes films. Holds no business rules: WatchlistService decides what's allowed."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, film: NewFilm) -> Film:
        """Insert a film and return it with its id and added_at filled in."""
        async with self._db.transaction() as conn:
            rows = await conn.execute_fetchall(
                """
                INSERT INTO films (
                    slug, tmdb_id, title, year, category_key, side, genre, is_indian, grade,
                    note, why_watch, poster_path, runtime_min, tmdb_synced_at, added_by, watched_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING *
                """,
                _values(film),
            )
        added = _first(rows)
        if added is None:
            raise RuntimeError("INSERT ... RETURNING returned no row")
        return added

    async def add_if_new(self, film: NewFilm) -> Film | None:
        """Insert a film unless one with the same slug, TMDB id, or title and year is listed.

        Returns the new film, or None when it was left out. ON CONFLICT DO NOTHING is what makes
        the seed import safe to run twice: it never overwrites a film.
        """
        async with self._db.transaction() as conn:
            rows = await conn.execute_fetchall(
                """
                INSERT INTO films (
                    slug, tmdb_id, title, year, category_key, side, genre, is_indian, grade,
                    note, why_watch, poster_path, runtime_min, tmdb_synced_at, added_by, watched_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO NOTHING
                RETURNING *
                """,
                _values(film),
            )
        return _first(rows)

    async def get(self, film_id: int) -> Film | None:
        """The film with this id, if there is one."""
        rows = await self._db.conn.execute_fetchall("SELECT * FROM films WHERE id = ?", (film_id,))
        return _first(rows)

    async def get_by_slug(self, slug: str) -> Film | None:
        """The film with this slug, if there is one."""
        rows = await self._db.conn.execute_fetchall("SELECT * FROM films WHERE slug = ?", (slug,))
        return _first(rows)

    async def get_by_tmdb_id(self, tmdb_id: int) -> Film | None:
        """The film with this TMDB id, if there is one."""
        rows = await self._db.conn.execute_fetchall(
            "SELECT * FROM films WHERE tmdb_id = ?", (tmdb_id,)
        )
        return _first(rows)

    async def find_duplicate(
        self, *, title: str, year: int | None, tmdb_id: int | None
    ) -> Film | None:
        """A film with the same TMDB id, or with the same title (ignoring case) and year.

        A NULL year or TMDB id never matches anything, so films without a year are never
        duplicates of each other, just as the unique index allows.
        """
        rows = await self._db.conn.execute_fetchall(
            """
            SELECT * FROM films
            WHERE tmdb_id = ? OR (year = ? AND lower(title) = lower(?))
            ORDER BY id
            LIMIT 1
            """,
            (tmdb_id, year, title),
        )
        return _first(rows)

    async def find_by_title(self, title: str) -> Film | None:
        """The first film with this title, ignoring case, whatever its year."""
        rows = await self._db.conn.execute_fetchall(
            "SELECT * FROM films WHERE lower(title) = lower(?) ORDER BY id LIMIT 1", (title,)
        )
        return _first(rows)

    async def slug_taken(self, slug: str) -> bool:
        """Whether a film already uses this slug."""
        rows = await self._db.conn.execute_fetchall("SELECT 1 FROM films WHERE slug = ?", (slug,))
        return bool(list(rows))

    async def count(self, *, show: Show, category_key: str | None) -> int:
        """How many films match the /list filters."""
        unwatched, watched = _SHOW[show]
        rows = await self._db.conn.execute_fetchall(
            """
            SELECT count(*) FROM films
            WHERE ((? AND watched_at IS NULL) OR (? AND watched_at IS NOT NULL))
              AND (? IS NULL OR category_key = ?)
            """,
            (unwatched, watched, category_key, category_key),
        )
        return int(list(rows)[0][0])

    async def list_page(
        self, *, show: Show, category_key: str | None, limit: int, offset: int
    ) -> list[Film]:
        """One page of films matching the /list filters, sorted by title, then year."""
        unwatched, watched = _SHOW[show]
        rows = await self._db.conn.execute_fetchall(
            """
            SELECT * FROM films
            WHERE ((? AND watched_at IS NULL) OR (? AND watched_at IS NOT NULL))
              AND (? IS NULL OR category_key = ?)
            ORDER BY lower(title), year, id
            LIMIT ? OFFSET ?
            """,
            (unwatched, watched, category_key, category_key, limit, offset),
        )
        return [_film(row) for row in rows]

    async def unwatched(
        self, *, category_key: str | None = None, genre: str | None = None
    ) -> list[Film]:
        """Every unwatched film, optionally only one category or genre, in the order added."""
        rows = await self._db.conn.execute_fetchall(
            """
            SELECT * FROM films
            WHERE watched_at IS NULL
              AND (? IS NULL OR category_key = ?)
              AND (? IS NULL OR genre = ?)
            ORDER BY id
            """,
            (category_key, category_key, genre, genre),
        )
        return [_film(row) for row in rows]

    async def list_all(self, *, watched: bool | None = None) -> list[Film]:
        """Every film, or only the watched or unwatched ones, sorted by title, then year."""
        rows = await self._db.conn.execute_fetchall(
            """
            SELECT * FROM films
            WHERE ? IS NULL OR (watched_at IS NOT NULL) = ?
            ORDER BY lower(title), year, id
            """,
            (watched, watched),
        )
        return [_film(row) for row in rows]

    async def needing_refresh(self, *, synced_before: str, limit: int) -> list[Film]:
        """Films on TMDB whose details were fetched before this time, or never, oldest first."""
        rows = await self._db.conn.execute_fetchall(
            """
            SELECT * FROM films
            WHERE tmdb_id IS NOT NULL AND (tmdb_synced_at IS NULL OR tmdb_synced_at < ?)
            ORDER BY tmdb_synced_at, id
            LIMIT ?
            """,
            (synced_before, limit),
        )
        return [_film(row) for row in rows]

    async def update(
        self, film_id: int, *, note: str | None, category_key: str | None
    ) -> Film | None:
        """Set a film's note and category. Returns the film, or None if there's no such film."""
        async with self._db.transaction() as conn:
            rows = await conn.execute_fetchall(
                "UPDATE films SET note = ?, category_key = ? WHERE id = ? RETURNING *",
                (note, category_key, film_id),
            )
        return _first(rows)

    async def set_tmdb(
        self,
        film_id: int,
        *,
        tmdb_id: int,
        poster_path: str | None,
        runtime_min: int | None,
        synced_at: str,
    ) -> Film | None:
        """Store a film's TMDB id, poster and runtime. None if there's no such film."""
        async with self._db.transaction() as conn:
            rows = await conn.execute_fetchall(
                """
                UPDATE films SET tmdb_id = ?, poster_path = ?, runtime_min = ?, tmdb_synced_at = ?
                WHERE id = ?
                RETURNING *
                """,
                (tmdb_id, poster_path, runtime_min, synced_at, film_id),
            )
        return _first(rows)

    async def mark_watched(self, film_id: int, watched_at: str) -> Film | None:
        """Mark an unwatched film watched. None if the film is missing or already watched."""
        async with self._db.transaction() as conn:
            rows = await conn.execute_fetchall(
                "UPDATE films SET watched_at = ? WHERE id = ? AND watched_at IS NULL RETURNING *",
                (watched_at, film_id),
            )
        return _first(rows)

    async def mark_unwatched(self, film_id: int) -> Film | None:
        """Mark a watched film unwatched again. None if the film is missing or isn't watched."""
        async with self._db.transaction() as conn:
            rows = await conn.execute_fetchall(
                "UPDATE films SET watched_at = NULL WHERE id = ? AND watched_at IS NOT NULL "
                "RETURNING *",
                (film_id,),
            )
        return _first(rows)

    async def delete(self, film_id: int) -> bool:
        """Delete a film. Returns whether there was one to delete."""
        async with self._db.transaction() as conn:
            cursor = await conn.execute("DELETE FROM films WHERE id = ?", (film_id,))
            deleted = cursor.rowcount > 0
            await cursor.close()
        return deleted


def _values(film: NewFilm) -> tuple[object, ...]:
    """A NewFilm's values, in the column order of the INSERT statements above."""
    return (
        film.slug,
        film.tmdb_id,
        film.title,
        film.year,
        film.category_key,
        film.side,
        film.genre,
        int(film.is_indian),
        film.grade,
        film.note,
        film.why_watch,
        film.poster_path,
        film.runtime_min,
        film.tmdb_synced_at,
        film.added_by,
        film.watched_at,
    )


def _film(row: aiosqlite.Row) -> Film:
    values = dict(row)
    values["is_indian"] = bool(values["is_indian"])
    return Film(**values)


def _first(rows: Iterable[aiosqlite.Row]) -> Film | None:
    return next((_film(row) for row in rows), None)
