"""Smoke test: every module imports cleanly and has a docstring."""

import importlib

import pytest

MODULES = [
    "moviebot",
    "moviebot.__main__",
    "moviebot.bot",
    "moviebot.config",
    "moviebot.models",
    "moviebot.cogs",
    "moviebot.cogs.admin",
    "moviebot.cogs.watchlist",
    "moviebot.ui",
    "moviebot.ui.embeds",
    "moviebot.ui.errors",
    "moviebot.ui.views",
    "moviebot.services",
    "moviebot.services.watchlist",
    "moviebot.db",
    "moviebot.db.categories",
    "moviebot.db.database",
    "moviebot.db.films",
    "moviebot.tmdb",
    "moviebot.tmdb.client",
]


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module: str) -> None:
    assert importlib.import_module(module).__doc__
