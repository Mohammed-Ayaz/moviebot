"""Smoke test: the package and every layer import cleanly."""

import importlib

import pytest

LAYERS = [
    "moviebot",
    "moviebot.cogs",
    "moviebot.ui",
    "moviebot.services",
    "moviebot.db",
    "moviebot.tmdb",
]


@pytest.mark.parametrize("module", LAYERS)
def test_layer_imports(module: str) -> None:
    assert importlib.import_module(module).__doc__
