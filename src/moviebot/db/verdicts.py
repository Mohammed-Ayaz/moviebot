"""VerdictRepository: the SQL for the verdicts table. /verdict (M8) adds the writing side."""

from moviebot.db.database import Database
from moviebot.models import Verdict


class VerdictRepository:
    """Reads verdicts, for /export."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def list_all(self) -> list[Verdict]:
        """Every verdict, film by film, oldest first."""
        rows = await self._db.conn.execute_fetchall(
            "SELECT * FROM verdicts ORDER BY film_id, updated_at, user_id"
        )
        return [Verdict(**dict(row)) for row in rows]
