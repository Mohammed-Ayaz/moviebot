"""Shared fixtures. Every test gets a fresh in-memory database built by the real migrations."""

from collections.abc import AsyncIterator

import pytest

from moviebot.db.categories import CategoryRepository
from moviebot.db.database import Database, open_database
from moviebot.db.films import FilmRepository
from moviebot.models import Category
from moviebot.services.watchlist import WatchlistService


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
def watchlist(films: FilmRepository, categories: CategoryRepository) -> WatchlistService:
    return WatchlistService(films, categories)
