"""The database: one shared connection, its pragmas, and the numbered migrations.

The bot opens one connection at startup and shares it. Writes go through Database.transaction(),
which holds a lock, so two commands running at the same time can't mix their statements into
one transaction.
"""

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

log = logging.getLogger(__name__)

# migrations/ sits at the repo root, beside src/. The bot always runs from a checkout of the repo.
MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"
MIGRATION_NAME = re.compile(r"(\d{4})_[a-z0-9_]+\.sql")
IN_MEMORY = ":memory:"


class MigrationError(Exception):
    """The migrations folder is missing, or a file in it is badly named."""


class Database:
    """The shared connection, and a lock that keeps write transactions apart."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn
        self._write_lock = asyncio.Lock()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        """Run writes as one transaction: commit when the block ends, roll back if it raises."""
        async with self._write_lock:
            try:
                yield self.conn
                await self.conn.commit()
            except BaseException:
                await self.conn.rollback()
                raise

    async def backup_to(self, path: Path) -> None:
        """Copy the whole database into a new file at path, with SQLite's backup API (FR-16).

        The copy runs in aiosqlite's worker thread, so the bot keeps answering. It holds the
        write lock, so it never catches a transaction half done. The copy is then switched out
        of WAL mode, so the one file holds everything.
        """
        async with self._write_lock, aiosqlite.connect(path) as target:
            await self.conn.backup(target)
            await target.execute_fetchall("PRAGMA journal_mode = DELETE")

    async def close(self) -> None:
        """Close the connection, once, at shutdown."""
        await self.conn.close()


async def open_database(path: str | Path, migrations_dir: Path = MIGRATIONS_DIR) -> Database:
    """Open the database (creating its folder), set the pragmas and apply pending migrations."""
    if str(path) != IN_MEMORY:
        await asyncio.to_thread(Path(path).parent.mkdir, parents=True, exist_ok=True)
    conn = await aiosqlite.connect(path)
    try:
        conn.row_factory = aiosqlite.Row
        await conn.execute_fetchall("PRAGMA journal_mode = WAL")  # reads don't block the writer
        await conn.execute_fetchall("PRAGMA foreign_keys = ON")  # off by default in SQLite
        await conn.execute_fetchall("PRAGMA busy_timeout = 5000")  # wait up to 5 s for a lock
        await apply_migrations(conn, migrations_dir)
    except BaseException:
        await conn.close()
        raise
    return Database(conn)


async def schema_version(conn: aiosqlite.Connection) -> int:
    """The number of the last migration applied, stored in PRAGMA user_version."""
    rows = list(await conn.execute_fetchall("PRAGMA user_version"))
    return int(rows[0][0])


async def apply_migrations(
    conn: aiosqlite.Connection, migrations_dir: Path = MIGRATIONS_DIR
) -> list[str]:
    """Apply every migration numbered above the schema version, in order. Returns their names.

    Each file runs in one transaction that also sets PRAGMA user_version to the file's number,
    so a file that fails leaves the database exactly as it was. This is the one place that
    builds SQL text: PRAGMA can't take ? placeholders, and the SQL comes from files in the repo.
    """
    current = await schema_version(conn)
    applied: list[str] = []
    for number, path in await asyncio.to_thread(_find_migrations, migrations_dir):
        if number <= current:
            continue
        sql = await asyncio.to_thread(path.read_text, encoding="utf-8")
        try:
            await conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")
        except BaseException:
            await conn.rollback()
            raise
        log.info("Applied migration %s", path.name)
        applied.append(path.name)
    return applied


def _find_migrations(migrations_dir: Path) -> list[tuple[int, Path]]:
    """The migration files, sorted by number. Refuses bad names and repeated numbers."""
    if not migrations_dir.is_dir():
        raise MigrationError(f"No migrations folder at {migrations_dir}")
    found: dict[int, Path] = {}
    for path in migrations_dir.glob("*.sql"):
        match = MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise MigrationError(f"{path.name}: name migrations like 0002_add_thing.sql")
        number = int(match.group(1))
        if number in found:
            raise MigrationError(f"{path.name} and {found[number].name} share number {number}")
        found[number] = path
    return sorted(found.items())
