"""BackupRepository: copies of the database file, and the backups table that remembers them."""

from pathlib import Path

from moviebot.db.database import Database


class BackupRepository:
    """Makes copies of the database, and records when each weekly backup was posted (FR-16)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def copy_to(self, path: Path) -> None:
        """Copy the whole database into a new file at path."""
        await self._db.backup_to(path)

    async def last_made_at(self) -> str | None:
        """When the last backup posted was made, or None if there never was one."""
        rows = await self._db.conn.execute_fetchall("SELECT max(made_at) FROM backups")
        return list(rows)[0][0]

    async def record(self, made_at: str, *, size_bytes: int) -> None:
        """Remember that the backup made at this time reached the backup channel."""
        async with self._db.transaction() as conn:
            await conn.execute_fetchall(
                "INSERT INTO backups (made_at, size_bytes) VALUES (?, ?)", (made_at, size_bytes)
            )
