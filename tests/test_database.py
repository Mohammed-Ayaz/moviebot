"""The database module: pragmas, and migrations applied in order, once, and all or nothing."""

from pathlib import Path

import aiosqlite
import pytest

from moviebot.db.database import Database, MigrationError, open_database, schema_version
from moviebot.db.films import FilmRepository
from moviebot.models import NewFilm

TABLES = {"categories", "films", "suggestions", "verdicts", "blocklist"}


def write_migrations(folder: Path, files: dict[str, str]) -> Path:
    folder.mkdir()
    for name, sql in files.items():
        (folder / name).write_text(sql, encoding="utf-8")
    return folder


async def table_names(db: Database) -> set[str]:
    rows = await db.conn.execute_fetchall("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row[0] for row in rows}


async def test_real_migrations_create_the_schema(db: Database) -> None:
    assert TABLES <= await table_names(db)
    assert await schema_version(db.conn) == 1


async def test_migrations_apply_in_order(tmp_path: Path) -> None:
    migrations = write_migrations(
        tmp_path / "migrations",
        {
            "0010_add_row.sql": "INSERT INTO things (name, size) VALUES ('chair', 4);",
            "0001_create.sql": "CREATE TABLE things (name TEXT);",
            "0002_add_size.sql": "ALTER TABLE things ADD COLUMN size INTEGER;",
        },
    )
    db = await open_database(":memory:", migrations_dir=migrations)
    try:
        assert await schema_version(db.conn) == 10
        rows = await db.conn.execute_fetchall("SELECT name, size FROM things")
        assert [tuple(row) for row in rows] == [("chair", 4)]
    finally:
        await db.close()


async def test_migrations_run_only_once(tmp_path: Path) -> None:
    path = tmp_path / "moviebot.db"
    first = await open_database(path)
    await first.close()
    # 0001 creates tables, so running it a second time would fail with "table already exists".
    second = await open_database(path)
    try:
        assert await schema_version(second.conn) == 1
    finally:
        await second.close()


async def test_failed_migration_rolls_back(tmp_path: Path) -> None:
    migrations = write_migrations(
        tmp_path / "migrations",
        {
            "0001_create.sql": "CREATE TABLE things (name TEXT);",
            "0002_broken.sql": "CREATE TABLE half_done (x TEXT);\nINSERT INTO missing VALUES (1);",
        },
    )
    path = tmp_path / "test.db"
    with pytest.raises(aiosqlite.OperationalError):
        await open_database(path, migrations_dir=migrations)

    db = await open_database(path, migrations_dir=write_migrations(tmp_path / "none", {}))
    try:
        assert await schema_version(db.conn) == 1
        tables = await table_names(db)
        assert "things" in tables
        assert "half_done" not in tables
    finally:
        await db.close()


async def test_badly_named_migration_is_refused(tmp_path: Path) -> None:
    migrations = write_migrations(tmp_path / "migrations", {"1_create.sql": "SELECT 1;"})
    with pytest.raises(MigrationError):
        await open_database(":memory:", migrations_dir=migrations)


async def test_connection_sets_pragmas(tmp_path: Path) -> None:
    db = await open_database(tmp_path / "data" / "moviebot.db")  # also creates the data folder
    try:
        assert list(await db.conn.execute_fetchall("PRAGMA journal_mode"))[0][0] == "wal"
        assert list(await db.conn.execute_fetchall("PRAGMA foreign_keys"))[0][0] == 1
        assert list(await db.conn.execute_fetchall("PRAGMA busy_timeout"))[0][0] == 5000
    finally:
        await db.close()


async def test_films_survive_reopening_the_database(tmp_path: Path) -> None:
    path = tmp_path / "data" / "moviebot.db"
    db = await open_database(path)
    await FilmRepository(db).add(NewFilm(slug="heropanti-2014", title="Heropanti", year=2014))
    await db.close()

    db = await open_database(path)
    try:
        film = await FilmRepository(db).find_by_title("Heropanti")
        assert film is not None
        assert film.year == 2014
    finally:
        await db.close()
