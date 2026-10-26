"""BackupService: the JSON file /export sends (FR-14), and the weekly database backup (FR-16)."""

import asyncio
import json
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from moviebot.db.backups import BackupRepository
from moviebot.db.blocklist import BlocklistRepository
from moviebot.db.categories import CategoryRepository
from moviebot.db.films import FilmRepository
from moviebot.db.verdicts import VerdictRepository
from moviebot.models import BackupCopy, ExportFile, Film, NotAllowed, Verdict

BACKUP_EVERY_DAYS = 7  # FR-16 and NFR-6: at most a week of changes can be lost
WORKING_COPY = ".backup-in-progress.db"  # made beside the database, removed once read
STAMP = "%Y-%m-%dT%H:%M:%SZ"  # ISO 8601 UTC, as the database stores times
FORMAT_VERSION = 1
SEED_ADDER = "AI"  # added_by for films from the seed file or an import
FORMER_MEMBER = "a former member"  # added_by for someone the server no longer knows
EXPORT_INSTRUCTIONS = (
    "Movie Night Bot export. Verdicts show what members thought of films they watched, and "
    "comments say why. You may change only two things. 1) Write or rewrite why_watch on any "
    "film: up to 1,000 characters on why this group should watch it. 2) Add new films to films "
    "with title, year and why_watch, plus category, side, genre, indian and grade if you can; "
    "leave out slug. Do not add films already in films or do_not_watch. Do not edit or remove "
    "anything else, because the import ignores it. Reply with the whole file as valid JSON in "
    "this format."
)

DisplayName = Callable[[int], Awaitable[str | None]]  # a member's name from their Discord id


class BackupService:
    """Builds /export's file and the weekly backup. Never imports discord."""

    def __init__(
        self,
        films: FilmRepository,
        categories: CategoryRepository,
        blocklist: BlocklistRepository,
        verdicts: VerdictRepository,
        backups: BackupRepository,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._films = films
        self._categories = categories
        self._blocklist = blocklist
        self._verdicts = verdicts
        self._backups = backups
        self._clock = clock

    async def export(self, *, is_admin: bool, display_name: DisplayName) -> ExportFile:
        """The whole list as one JSON file, in the format of the spec's Appendix (FR-14).

        Raises NotAllowed unless the person is an admin. display_name looks up a member's name
        from their Discord id, or None if they've left, because the file never holds Discord ids.
        """
        if not is_admin:
            raise NotAllowed
        films = await self._films.list_all()
        adders = {film.added_by for film in films if film.added_by is not None}
        names = {user_id: await display_name(user_id) or FORMER_MEMBER for user_id in adders}
        verdicts: defaultdict[int, list[Verdict]] = defaultdict(list)
        for verdict in await self._verdicts.list_all():
            verdicts[verdict.film_id].append(verdict)
        now = self._now()
        data = {
            "format_version": FORMAT_VERSION,
            "exported_at": now.strftime(STAMP),
            "instructions": EXPORT_INSTRUCTIONS,
            "categories": [
                {"key": each.key, "name": each.name, "side": each.side, "blurb": each.blurb}
                for each in await self._categories.list_all()
            ],
            "films": [_film(film, names, verdicts[film.id]) for film in films],
            "do_not_watch": [
                {"title": entry.title, "year": entry.year, "reason": entry.reason}
                for entry in await self._blocklist.list_all()
            ],
        }
        return ExportFile(
            filename=f"moviebot-export-{now:%Y-%m-%d}.json",
            content=json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
            film_count=len(films),
        )

    async def backup_due(self) -> bool:
        """Whether the weekly backup is due: there's never been one, or the last one was made
        7 or more days ago, counting calendar days in UTC (FR-16)."""
        last = await self._backups.last_made_at()
        if last is None:
            return True
        made = datetime.strptime(last, STAMP).replace(tzinfo=UTC)
        return (self._now().date() - made.date()).days >= BACKUP_EVERY_DAYS

    async def make_backup(self, folder: Path) -> BackupCopy:
        """Copy the database, through a working file in folder that's removed afterwards."""
        made_at = self._now()
        working = folder / WORKING_COPY
        await asyncio.to_thread(working.unlink, missing_ok=True)  # left by a crash, if any
        try:
            await self._backups.copy_to(working)
            content = await asyncio.to_thread(working.read_bytes)
        finally:
            await asyncio.to_thread(working.unlink, missing_ok=True)
        return BackupCopy(
            filename=f"moviebot-backup-{made_at:%Y-%m-%d}.db",
            content=content,
            made_at=made_at.strftime(STAMP),
        )

    async def backup_posted(self, copy: BackupCopy) -> None:
        """Remember that this copy reached the backup channel, so the next one is due in a week."""
        await self._backups.record(copy.made_at, size_bytes=len(copy.content))

    def _now(self) -> datetime:
        return self._clock().astimezone(UTC)


def _film(film: Film, names: dict[int, str], verdicts: list[Verdict]) -> dict[str, Any]:
    """One film in the export file, with what members thought of it."""
    return {
        "slug": film.slug,
        "title": film.title,
        "year": film.year,
        "tmdb_id": film.tmdb_id,
        "category": film.category_key,
        "side": film.side,
        "genre": film.genre,
        "indian": film.is_indian,
        "grade": film.grade,
        "note": film.note,
        "why_watch": film.why_watch,
        "added_by": SEED_ADDER if film.added_by is None else names[film.added_by],
        "watched_at": film.watched_at,
        "verdicts": [
            {
                "by": verdict.user_name,
                "verdict": verdict.verdict,
                "comment": verdict.comment,
                "date": verdict.updated_at[:10],
            }
            for verdict in verdicts
        ],
    }
