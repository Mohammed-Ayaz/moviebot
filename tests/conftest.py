"""Shared fixtures. Every test gets a fresh in-memory database built by the real migrations."""

import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from fakes import FakeTmdbClient

from moviebot.db.categories import CategoryRepository
from moviebot.db.database import Database, open_database
from moviebot.db.films import FilmRepository
from moviebot.db.suggestions import SuggestionRepository
from moviebot.models import Category
from moviebot.services.picker import PickerService
from moviebot.services.watchlist import WatchlistService

NOW = datetime(2026, 10, 21, 18, 0, tzinfo=UTC)


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    database = await open_database(":memory:")
    yield database
    await database.close()


@pytest.fixture
def films(db: Database) -> FilmRepository:
    return FilmRepository(db)


@pytest.fixture
def categories(db: Database) -> CategoryRepository:
    return CategoryRepository(db)


@pytest.fixture
def suggestions(db: Database) -> SuggestionRepository:
    return SuggestionRepository(db)


@pytest.fixture
async def launch(categories: CategoryRepository) -> Category:
    """The first category from the seed file, already in the database."""
    category = Category(
        key="launch",
        name="The launch",
        position=1,
        side="bad",
        blurb="A production house spends real money introducing a new face.",
    )
    await categories.add(category)
    return category


@pytest.fixture
def tmdb() -> FakeTmdbClient:
    """A fake TMDB that knows no films until a test adds some."""
    return FakeTmdbClient()


@pytest.fixture
def watchlist(
    films: FilmRepository, categories: CategoryRepository, tmdb: FakeTmdbClient
) -> WatchlistService:
    return WatchlistService(films, categories, tmdb, clock=lambda: NOW)


@pytest.fixture
def picker(
    films: FilmRepository, categories: CategoryRepository, suggestions: SuggestionRepository
) -> PickerService:
    """A picker with a fixed random seed, so every run makes the same picks."""
    # Picking films needs no cryptographic randomness, hence the noqa for ruff's S311.
    rng = random.Random(1234)  # noqa: S311
    return PickerService(films, categories, suggestions, rng=rng, clock=lambda: NOW)
