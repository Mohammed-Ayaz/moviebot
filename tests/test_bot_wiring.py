"""Startup wiring follows AGENTS.md. The bot is built offline: nothing here logs in to Discord."""

from unittest.mock import AsyncMock

import discord
import pytest

from moviebot.bot import MovieBot, MovieTree
from moviebot.config import Settings
from moviebot.services.backup import BackupService
from moviebot.services.picker import PickerService
from moviebot.services.watchlist import WatchlistService
from moviebot.ui.views import ListView


def test_no_privileged_intents(bot: MovieBot) -> None:
    assert bot.intents == discord.Intents.default()
    assert not bot.intents.message_content
    assert not bot.intents.members
    assert not bot.intents.presences


def test_bot_never_pings_anyone(bot: MovieBot) -> None:
    mentions = bot.allowed_mentions
    assert mentions is not None
    assert not (mentions.everyone or mentions.users or mentions.roles or mentions.replied_user)


def test_sync_is_the_only_text_command(bot: MovieBot) -> None:
    assert sorted(command.name for command in bot.commands) == ["sync"]


def test_slash_commands_are_registered_on_movie_tree(bot: MovieBot) -> None:
    assert isinstance(bot.tree, MovieTree)
    assert sorted(command.name for command in bot.tree.get_commands()) == [
        "about",
        "add",
        "edit",
        "export",
        "list",
        "ping",
        "remove",
        "suggest",
        "unwatch",
        "watched",
    ]


async def test_startup_never_syncs(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    watchlist: WatchlistService,
    picker: PickerService,
    backup: BackupService,
) -> None:
    async with MovieBot(settings, watchlist=watchlist, picker=picker, backup=backup) as movie_bot:
        sync = AsyncMock()
        monkeypatch.setattr(movie_bot.tree, "sync", sync)
        await movie_bot.setup_hook()
        await movie_bot.on_ready()
    sync.assert_not_awaited()


async def test_list_buttons_expiring_leaves_the_suggest_button_working(
    bot: MovieBot, watchlist: WatchlistService
) -> None:
    """discord.py forgets a persistent button if an expiring view holding one stops."""
    view = ListView(watchlist, await watchlist.list_films())
    bot._connection.store_view(view, 123)  # what sending the /list message does
    view.stop()  # what the 10-minute timeout does

    patterns = {pattern.pattern for pattern in bot._connection._view_store._dynamic_items}
    assert "mb:suggest" in patterns
