"""BlocklistRepository: all the SQL for the blocklist table, the do-not-watch list."""

from moviebot.db.database import Database
from moviebot.models import BlocklistEntry


class BlocklistRepository:
    """Reads and adds do-not-watch entries. The seed import fills this table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, title: str, year: int | None, reason: str | None) -> bool:
        """Add an entry unless this title and year are listed already. Returns whether it was.

        WHERE NOT EXISTS rather than ON CONFLICT, because UNIQUE (title, year) lets two entries
        without a year through: SQLite treats every NULL as different.
        """
        async with self._db.transaction() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO blocklist (title, year, reason)
                SELECT ?, ?, ?
                WHERE NOT EXISTS (SELECT 1 FROM blocklist WHERE title = ? AND year IS ?)
                """,
                (title, year, reason, title, year),
            )
            added = cursor.rowcount > 0
            await cursor.close()
        return added

    async def list_all(self) -> list[BlocklistEntry]:
        """Every entry, sorted by title, then year."""
        rows = await self._db.conn.execute_fetchall(
            "SELECT * FROM blocklist ORDER BY lower(title), year, id"
        )
        return [BlocklistEntry(**dict(row)) for row in rows]
