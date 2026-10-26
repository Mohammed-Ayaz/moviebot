"""BackupService: the JSON file /export sends (FR-14), and the weekly backup (FR-16)."""

import asyncio
import json
import os
from pathlib import Path

import pytest

from moviebot.db.backups import BackupRepository
from moviebot.db.blocklist import BlocklistRepository
from moviebot.db.database import Database, open_database
from moviebot.db.films import FilmRepository
from moviebot.models import Category, NewFilm, NotAllowed
from moviebot.services.backup import EXPORT_INSTRUCTIONS, BackupService

NAMES = {42: "Ayaz"}


async def display_name(user_id: int) -> str | None:
    return NAMES.get(user_id)


async def test_export_holds_every_film_category_verdict_and_do_not_watch_entry(
    backup: BackupService,
    films: FilmRepository,
    blocklist: BlocklistRepository,
    launch: Category,
    db: Database,
) -> None:
    heropanti = await films.add(
        NewFilm(
            slug="heropanti-2014",
            title="Heropanti",
            year=2014,
            tmdb_id=280391,
            category_key="launch",
            side="bad",
            genre="masala",
            grade="yours",
            why_watch="Tiger's debut.",
            watched_at="2026-10-20T10:09:24Z",
        )
    )
    await films.add(NewFilm(slug="tumbbad-2018", title="Tumbbad", year=2018, added_by=42))
    await blocklist.add("Humshakals", 2014, "Nothing happens.")
    await db.conn.execute(
        "INSERT INTO verdicts (film_id, user_id, user_name, verdict, comment, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (heropanti.id, 42, "Ayaz", "liked", "Loved it", "2026-10-20T22:00:00Z"),
    )
    await db.conn.commit()

    export = await backup.export(is_admin=True, display_name=display_name)

    data = json.loads(export.content)
    assert (export.filename, export.film_count) == ("moviebot-export-2026-10-21.json", 2)
    assert list(data) == [
        "format_version",
        "exported_at",
        "instructions",
        "categories",
        "films",
        "do_not_watch",
    ]
    assert (data["format_version"], data["exported_at"]) == (1, "2026-10-21T18:00:00Z")
    assert data["instructions"] == EXPORT_INSTRUCTIONS
    assert data["categories"] == [
        {"key": "launch", "name": "The launch", "side": "bad", "blurb": launch.blurb}
    ]
    assert data["films"][0] == {
        "slug": "heropanti-2014",
        "title": "Heropanti",
        "year": 2014,
        "tmdb_id": 280391,
        "category": "launch",
        "side": "bad",
        "genre": "masala",
        "indian": True,
        "grade": "yours",
        "note": None,
        "why_watch": "Tiger's debut.",
        "added_by": "AI",
        "watched_at": "2026-10-20T10:09:24Z",
        "verdicts": [
            {"by": "Ayaz", "verdict": "liked", "comment": "Loved it", "date": "2026-10-20"}
        ],
    }
    tumbbad = data["films"][1]
    assert (tumbbad["title"], tumbbad["added_by"], tumbbad["verdicts"]) == ("Tumbbad", "Ayaz", [])
    assert data["do_not_watch"] == [
        {"title": "Humshakals", "year": 2014, "reason": "Nothing happens."}
    ]


async def test_export_names_each_member_once_and_says_when_one_has_left(
    backup: BackupService, films: FilmRepository
) -> None:
    await films.add(NewFilm(slug="a", title="A", year=None, added_by=42))
    await films.add(NewFilm(slug="b", title="B", year=None, added_by=42))
    await films.add(NewFilm(slug="c", title="C", year=None, added_by=7))
    asked: list[int] = []

    async def name_of(user_id: int) -> str | None:
        asked.append(user_id)
        return NAMES.get(user_id)

    export = await backup.export(is_admin=True, display_name=name_of)

    added_by = [film["added_by"] for film in json.loads(export.content)["films"]]
    assert added_by == ["Ayaz", "Ayaz", "a former member"]
    assert sorted(asked) == [7, 42]


async def test_only_admins_can_export(backup: BackupService) -> None:
    with pytest.raises(NotAllowed, match="Only admins can do that."):
        await backup.export(is_admin=False, display_name=display_name)


@pytest.mark.parametrize(
    ("last_backup", "due"),
    [(None, True), ("2026-10-15T23:59:59Z", False), ("2026-10-14T00:00:00Z", True)],
)
async def test_a_backup_is_due_at_first_and_then_once_a_week(
    backup: BackupService, backups: BackupRepository, last_backup: str | None, due: bool
) -> None:
    if last_backup is not None:
        await backups.record(last_backup, size_bytes=1)

    assert await backup.backup_due() is due


async def test_a_backup_is_a_whole_copy_of_the_database_in_one_file(
    backup: BackupService, films: FilmRepository, tmp_path: Path
) -> None:
    await films.add(NewFilm(slug="heropanti-2014", title="Heropanti", year=2014))

    copy = await backup.make_backup(tmp_path)

    assert copy.filename == "moviebot-backup-2026-10-21.db"
    assert copy.content[18:20] == b"\x01\x01"  # a plain file, not WAL: no -wal file needed
    assert await asyncio.to_thread(os.listdir, tmp_path) == []  # the working copy is gone
    restored = tmp_path / copy.filename
    await asyncio.to_thread(restored.write_bytes, copy.content)
    db = await open_database(restored)
    try:
        assert [film.title for film in await FilmRepository(db).list_all()] == ["Heropanti"]
    finally:
        await db.close()


async def test_a_posted_backup_is_remembered(
    backup: BackupService, backups: BackupRepository, tmp_path: Path
) -> None:
    copy = await backup.make_backup(tmp_path)

    await backup.backup_posted(copy)

    assert await backups.last_made_at() == "2026-10-21T18:00:00Z"
    assert not await backup.backup_due()
