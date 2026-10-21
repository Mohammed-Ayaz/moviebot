"""Smoke test: every module imports cleanly and has a docstring."""

import importlib

import pytest

MODULES = [
    "moviebot",
    "moviebot.__main__",
    "moviebot.bot",
    "moviebot.config",
    "moviebot.cogs",
    "moviebot.cogs.admin",
    "moviebot.ui",
    "moviebot.services",
    "moviebot.db",
    "moviebot.tmdb",
]


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module: str) -> None:
    assert importlib.import_module(module).__doc__
