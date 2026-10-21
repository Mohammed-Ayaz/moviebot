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
                INSERT INTO films
                    (slug, tmdb_id, title, year, category_key, note, added_by, watched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING *
                """,
                (
                    film.slug,
                    film.tmdb_id,
                    film.title,
                    film.year,
                    film.category_key,
                    film.note,
                    film.added_by,
                    film.watched_at,
                ),
            )
        added = _first(rows)
        if added is None:
            raise RuntimeError("INSERT ... RETURNING returned no row")
        return added

    async def get(self, film_id: int) -> Film | None:
        """The film with this id, if there is one."""
        rows = await self._db.conn.execute_fetchall("SELECT * FROM films WHERE id = ?", (film_id,))
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

    async def delete(self, film_id: int) -> bool:
        """Delete a film. Returns whether there was one to delete."""
        async with self._db.transaction() as conn:
            cursor = await conn.execute("DELETE FROM films WHERE id = ?", (film_id,))
            deleted = cursor.rowcount > 0
            await cursor.close()
        return deleted


def _film(row: aiosqlite.Row) -> Film:
    values = dict(row)
    values["is_indian"] = bool(values["is_indian"])
    return Film(**values)


def _first(rows: Iterable[aiosqlite.Row]) -> Film | None:
    return next((_film(row) for row in rows), None)
