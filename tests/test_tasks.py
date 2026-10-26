"""The bot's daily background tasks: the weekly backup (FR-16) and the TMDB refresh."""

import asyncio
import logging
from pathlib import Path
from typing import Any, cast

import discord
import pytest
from fakes import FakeTmdbClient

from moviebot.bot import MovieBot
from moviebot.config import Settings
from moviebot.db.backups import BackupRepository
from moviebot.db.films import FilmRepository
from moviebot.models import NewFilm, TmdbMovie
from moviebot.services.backup import BackupService
from moviebot.services.picker import PickerService
from moviebot.services.watchlist import WatchlistService

CHANNEL_ID = 99


class FakeHTTPResponse:
    def __init__(self, status: int, reason: str) -> None:
        self.status = status
        self.reason = reason


class FakeChannel(discord.abc.Messageable):
    """A text channel that records what's sent, or refuses it like a channel the bot can't use."""

    def __init__(self, *, refuse: bool = False) -> None:
        self.refuse = refuse
        self.sent: list[dict[str, Any]] = []

    async def _get_channel(self) -> Any:
        return self

    async def send(self, content: str | None = None, **fields: Any) -> Any:  # type: ignore[override]
        if self.refuse:
            raise discord.Forbidden(cast(Any, FakeHTTPResponse(403, "Forbidden")), "No access")
        self.sent.append({"content": content, **fields})


def with_backups(tmp_path: Path) -> Settings:
    """Settings with a backup channel. The working copy goes in tmp_path, beside the database."""
    return Settings.from_env(
        {
            "DISCORD_TOKEN": "discord-test-token",
            "TMDB_READ_TOKEN": "tmdb-test-token",
            "GUILD_ID": "1",
            "BACKUP_CHANNEL_ID": str(CHANNEL_ID),
            "DATABASE_PATH": str(tmp_path / "moviebot.db"),
        }
    )


async def settle() -> None:
    """Let cancelled background tasks finish."""
    for _ in range(3):
        await asyncio.sleep(0)


async def test_the_backup_task_runs_only_when_a_backup_channel_is_set(
    settings: Settings,
    watchlist: WatchlistService,
    picker: PickerService,
    backup: BackupService,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with MovieBot(settings, watchlist=watchlist, picker=picker, backup=backup) as bot:
        await bot.setup_hook()
        assert not bot.daily_backup.is_running()
    assert "Weekly backups are off" in caplog.text

    configured = with_backups(tmp_path)
    async with MovieBot(configured, watchlist=watchlist, picker=picker, backup=backup) as bot:
        await bot.setup_hook()
        assert bot.daily_backup.is_running()
    await settle()
    assert not bot.daily_backup.is_running()  # closing the bot stops it


async def test_the_weekly_backup_is_posted_once_and_remembered(
    watchlist: WatchlistService,
    picker: PickerService,
    backup: BackupService,
    backups: BackupRepository,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = FakeChannel()
    configured = with_backups(tmp_path)
    async with MovieBot(configured, watchlist=watchlist, picker=picker, backup=backup) as bot:
        monkeypatch.setattr(bot, "get_channel", {CHANNEL_ID: channel}.get)
        await bot.daily_backup()
        await bot.daily_backup()  # the next check: the last backup is still recent

    [post] = channel.sent
    assert post["file"].filename == "moviebot-backup-2026-10-21.db"
    assert await backups.last_made_at() == "2026-10-21T18:00:00Z"


async def test_a_backup_that_couldnt_be_posted_is_tried_again(
    watchlist: WatchlistService,
    picker: PickerService,
    backup: BackupService,
    backups: BackupRepository,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    configured = with_backups(tmp_path)
    async with MovieBot(configured, watchlist=watchlist, picker=picker, backup=backup) as bot:
        monkeypatch.setattr(bot, "get_channel", {CHANNEL_ID: FakeChannel(refuse=True)}.get)
        with caplog.at_level(logging.ERROR):
            await bot.daily_backup()

    assert await backups.last_made_at() is None
    assert await backup.backup_due()
    assert "The weekly backup couldn't be posted" in caplog.text


async def test_the_tmdb_refresh_runs_with_the_bot_and_stops_with_it(
    settings: Settings,
    watchlist: WatchlistService,
    picker: PickerService,
    backup: BackupService,
) -> None:
    async with MovieBot(settings, watchlist=watchlist, picker=picker, backup=backup) as bot:
        await bot.setup_hook()
        assert bot.daily_tmdb_refresh.is_running()
    await settle()
    assert not bot.daily_tmdb_refresh.is_running()


async def test_the_refresh_task_refreshes_old_tmdb_details(
    bot: MovieBot, films: FilmRepository, tmdb: FakeTmdbClient
) -> None:
    tmdb.add(TmdbMovie(101, "Heropanti", 2014, poster_path="/new.jpg", runtime_min=146))
    film = await films.add(
        NewFilm(
            slug="heropanti-2014",
            title="Heropanti",
            year=2014,
            tmdb_id=101,
            poster_path="/old.jpg",
            tmdb_synced_at="2026-01-01T00:00:00Z",
        )
    )

    await bot.daily_tmdb_refresh()

    refreshed = await films.get(film.id)
    assert refreshed is not None
    assert refreshed.poster_path == "/new.jpg"


async def test_a_wrong_backup_channel_id_is_explained(
    watchlist: WatchlistService,
    picker: PickerService,
    backup: BackupService,
    backups: BackupRepository,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def unknown_channel(channel_id: int) -> Any:
        raise discord.NotFound(cast(Any, FakeHTTPResponse(404, "Not Found")), "Unknown Channel")

    configured = with_backups(tmp_path)
    async with MovieBot(configured, watchlist=watchlist, picker=picker, backup=backup) as bot:
        monkeypatch.setattr(bot, "get_channel", {}.get)
        monkeypatch.setattr(bot, "fetch_channel", unknown_channel)
        with caplog.at_level(logging.ERROR):
            await bot.daily_backup()

    assert await backups.last_made_at() is None
    assert "can't find a channel with the ID in BACKUP_CHANNEL_ID" in caplog.text
