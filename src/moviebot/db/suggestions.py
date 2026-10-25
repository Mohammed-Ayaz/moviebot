"""SuggestionRepository: all the SQL for the suggestions table."""

from moviebot.db.database import Database


class SuggestionRepository:
    """The suggestion history, which the picker reads to avoid repeats (FR-7)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, film_id: int, requested_by: int) -> int:
        """Record a suggestion, not chosen yet. Returns its id."""
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "INSERT INTO suggestions (film_id, requested_by) VALUES (?, ?)",
                (film_id, requested_by),
            )
            suggestion_id = cursor.lastrowid
            await cursor.close()
        if suggestion_id is None:
            raise RuntimeError("INSERT INTO suggestions returned no id")
        return suggestion_id

    async def recent_film_ids(self, limit: int) -> list[int]:
        """The films in the last `limit` suggestions, newest first."""
        rows = await self._db.conn.execute_fetchall(
            "SELECT film_id FROM suggestions ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [row[0] for row in rows]

    async def choose(self, film_id: int, watched_at: str) -> bool:
        """ "We're watching this": mark the film watched and its latest suggestion chosen.

        Both changes happen in one transaction. Returns False, changing nothing, when the film is
        missing or already watched.
        """
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                "UPDATE films SET watched_at = ? WHERE id = ? AND watched_at IS NULL",
                (watched_at, film_id),
            )
            changed = cursor.rowcount > 0
            await cursor.close()
            if changed:
                cursor = await conn.execute(
                    """
                    UPDATE suggestions SET chosen = 1
                    WHERE id = (SELECT max(id) FROM suggestions WHERE film_id = ?)
                    """,
                    (film_id,),
                )
                await cursor.close()
        return changed
