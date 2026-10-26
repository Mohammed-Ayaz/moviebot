"""The seed import (FR-15): the real seed file, importing twice, and matching films on TMDB."""

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeTmdbClient

from moviebot.db.blocklist import BlocklistRepository
from moviebot.db.categories import CategoryRepository
from moviebot.db.films import FilmRepository
from moviebot.models import InvalidSeed, NewFilm, Seed, SeedReport, TmdbMovie
from moviebot.services.seed import SeedService, parse_fixes, parse_seed
from moviebot.services.watchlist import WatchlistService

ROOT = Path(__file__).resolve().parents[1]
SEED_FILE = ROOT / "watchlist_seed.json"
SCRIPT = ROOT / "scripts" / "import_seed.py"
NOW = datetime(2026, 10, 21, 18, 0, tzinfo=UTC)
IMPORTED_AT = "2026-10-21T18:00:00Z"
HEROPANTI = TmdbMovie(280391, "Heropanti", 2014, poster_path="/heropanti.jpg", runtime_min=146)


def seed_film(
    slug: str, title: str, year: int, category: str, *, note: str, watched: bool = False
) -> dict[str, Any]:
    good = category == "goodhorror"
    return {
        "id": slug,
        "title": title,
        "year": year,
        "category": category,
        "side": "good" if good else "bad",
        "genre": "horror" if good else "masala",
        "indian": True,
        "grade": "good" if good else "bullseye",
        "note": note,
        "watched": watched,
    }


def small_seed(**changes: Any) -> dict[str, Any]:
    """A seed file shaped like the real one: two categories, three films, one blocked film."""
    seed: dict[str, Any] = {
        "categories": [
            {"key": "launch", "number": 1, "name": "The launch", "side": "bad", "blurb": "New."},
            {"key": "goodhorror", "number": 14, "name": "Horror that works", "side": "good"},
        ],
        "films": [
            seed_film("heropanti-2014", "Heropanti", 2014, "launch", note="Debut.", watched=True),
            seed_film("tumbbad-2018", "Tumbbad", 2018, "goodhorror", note="Actually scary."),
            seed_film("ra-one-2011", "Ra.One", 2011, "launch", note="Very expensive."),
        ],
        "didnt_land": [],
        "do_not_watch": [{"title": "Humshakals", "year": 2014, "note": "Nothing happens."}],
    }
    return seed | changes


@pytest.fixture(scope="module")
def real_seed() -> Seed:
    return parse_seed(json.loads(SEED_FILE.read_text(encoding="utf-8")))


@pytest.fixture
def seeder(
    films: FilmRepository,
    categories: CategoryRepository,
    blocklist: BlocklistRepository,
    tmdb: FakeTmdbClient,
) -> SeedService:
    return SeedService(films, categories, blocklist, tmdb, clock=lambda: NOW)


async def test_seed_import_is_idempotent(
    seeder: SeedService,
    real_seed: Seed,
    films: FilmRepository,
    categories: CategoryRepository,
    blocklist: BlocklistRepository,
) -> None:
    first = await seeder.import_seed(real_seed)
    second = await seeder.import_seed(real_seed)

    assert first == SeedReport(
        categories_added=15, films_added=196, films_skipped=0, blocked_added=13
    )
    assert second == SeedReport(
        categories_added=0, films_added=0, films_skipped=196, blocked_added=0
    )
    listed = await films.list_all()
    assert len(listed) == 196
    assert len([film for film in listed if film.watched_at == IMPORTED_AT]) == 17
    assert len(await categories.list_all()) == 15
    assert len(await blocklist.list_all()) == 13


async def test_a_seed_film_keeps_its_details_and_its_note_becomes_why_watch(
    seeder: SeedService, films: FilmRepository
) -> None:
    await seeder.import_seed(parse_seed(small_seed()))

    heropanti = await films.get_by_slug("heropanti-2014")
    tumbbad = await films.get_by_slug("tumbbad-2018")

    assert heropanti is not None
    assert tumbbad is not None
    assert (heropanti.title, heropanti.year, heropanti.category_key) == (
        "Heropanti",
        2014,
        "launch",
    )
    assert (heropanti.side, heropanti.genre, heropanti.grade) == ("bad", "masala", "bullseye")
    assert heropanti.is_indian is True
    assert (heropanti.note, heropanti.why_watch) == (None, "Debut.")
    assert (heropanti.added_by, heropanti.watched_at) == (None, IMPORTED_AT)
    assert tumbbad.watched_at is None


async def test_importing_again_never_undoes_what_members_did(
    seeder: SeedService, films: FilmRepository, watchlist: WatchlistService
) -> None:
    mine = await watchlist.add_film(title="Ra.One", year=2011, note="My pick", added_by=42)
    first = await seeder.import_seed(parse_seed(small_seed()))
    heropanti = await films.get_by_slug("heropanti-2014")
    assert heropanti is not None
    await watchlist.edit_film(heropanti.id, note="Edited")
    await watchlist.unwatch(heropanti.id)

    second = await seeder.import_seed(parse_seed(small_seed()))

    assert (first.films_added, first.films_skipped) == (2, 1)  # Ra.One was already listed
    assert (second.films_added, second.films_skipped) == (0, 3)
    assert await films.get(mine.film.id) == mine.film
    after = await films.get(heropanti.id)
    assert after is not None
    assert (after.note, after.watched_at) == ("Edited", None)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ([], "The seed file must be a JSON object."),
        (small_seed(films={"id": "x"}), '"films" must be a list.'),
        (small_seed(films=[{"title": "X"}]), "films[0]: id is missing."),
        (
            small_seed(films=[{"id": "x y", "title": "X"}]),
            "films[0]: id must be lower-case letters, digits and hyphens.",
        ),
        (
            small_seed(films=[{"id": "x", "title": "X", "year": "2000"}]),
            "films[0]: year must be a whole number from 1888 to 2100.",
        ),
        (
            small_seed(films=[{"id": "x", "title": "X", "category": "nope"}]),
            "films[0]: category \"nope\" isn't one of the file's categories.",
        ),
        (
            small_seed(films=[{"id": "x", "title": "X", "side": "meh"}]),
            "films[0]: side must be one of bad, good, both.",
        ),
        (
            small_seed(films=[{"id": "x", "title": "X", "watched": "yes"}]),
            "films[0]: watched must be true or false.",
        ),
        (
            small_seed(films=[{"id": "x", "title": "X"}, {"id": "x", "title": "Y"}]),
            'The film id "x" appears twice.',
        ),
        (
            small_seed(categories=[{"key": "a:b", "number": 1, "name": "A", "side": "bad"}]),
            "categories[0]: key must be lower-case letters and digits.",
        ),
        (
            small_seed(categories=[{"key": "a", "number": "1", "name": "A", "side": "bad"}]),
            "categories[0]: number must be a whole number.",
        ),
        (
            small_seed(categories=[{"key": "a", "number": 1, "name": "A"}]),
            "categories[0]: side is missing.",
        ),
        (small_seed(films=[{"id": "x", "title": 5}]), "films[0]: title must be text."),
        (
            small_seed(films=[{"id": "x", "title": "X", "note": "n" * 1001}]),
            "films[0]: note can be at most 1000 characters.",
        ),
    ],
)
def test_a_broken_seed_file_is_refused_with_the_reason(data: object, message: str) -> None:
    with pytest.raises(InvalidSeed, match=re.escape(message)):
        parse_seed(data)


def test_the_do_not_watch_lists_are_optional() -> None:
    data = small_seed()
    del data["didnt_land"], data["do_not_watch"]

    assert parse_seed(data).blocklist == ()


async def test_match_tmdb_takes_the_first_title_match_within_a_year(
    seeder: SeedService, films: FilmRepository, tmdb: FakeTmdbClient
) -> None:
    tmdb.add(
        TmdbMovie(1, "Heropanti 2", 2022, poster_path="/two.jpg"),  # a different title
        HEROPANTI,
        TmdbMovie(503919, "Tumbbad", 2019, poster_path="/tumbbad.jpg"),  # TMDB says a year later
        TmdbMovie(9, "Ra.One", 2015, poster_path=None),  # four years out: not the same film
    )
    seed = parse_seed(small_seed())
    await seeder.import_seed(seed)

    matches = await seeder.match_tmdb(seed)

    assert [film.slug for film in matches.matched] == ["heropanti-2014", "tumbbad-2018"]
    assert [film.slug for film in matches.unmatched] == ["ra-one-2011"]
    assert not matches.stopped
    heropanti = await films.get_by_slug("heropanti-2014")
    assert heropanti is not None
    assert (heropanti.tmdb_id, heropanti.poster_path, heropanti.runtime_min) == (
        280391,
        "/heropanti.jpg",
        146,
    )
    assert heropanti.tmdb_synced_at == IMPORTED_AT
    assert (heropanti.title, heropanti.year) == ("Heropanti", 2014)  # the seed's own title stays


async def test_a_tmdb_film_already_on_the_list_is_not_given_to_a_second_film(
    seeder: SeedService, films: FilmRepository, tmdb: FakeTmdbClient
) -> None:
    tmdb.add(HEROPANTI)
    holder = await films.add(
        NewFilm(slug="hero-2014", title="Hero", year=2014, tmdb_id=280391, added_by=42)
    )
    seed = parse_seed(small_seed())
    await seeder.import_seed(seed)

    matches = await seeder.match_tmdb(seed)

    heropanti = await films.get_by_slug("heropanti-2014")
    assert heropanti is not None
    assert matches.taken == ((heropanti, holder),)
    assert heropanti.tmdb_id is None


async def test_match_tmdb_stops_when_tmdb_stops_answering(
    seeder: SeedService, tmdb: FakeTmdbClient
) -> None:
    seed = parse_seed(small_seed())
    await seeder.import_seed(seed)
    tmdb.down = True

    matches = await seeder.match_tmdb(seed)

    assert matches.stopped
    assert (matches.matched, matches.unmatched) == ((), ())


async def test_match_tmdb_again_only_looks_up_films_still_without_a_match(
    seeder: SeedService, tmdb: FakeTmdbClient
) -> None:
    tmdb.add(HEROPANTI)
    seed = parse_seed(small_seed())
    await seeder.import_seed(seed)
    await seeder.match_tmdb(seed)
    tmdb.searches.clear()

    await seeder.match_tmdb(seed)

    assert "Heropanti" not in tmdb.searches
    assert "Tumbbad" in tmdb.searches


async def test_fixes_set_the_tmdb_film_by_hand(
    seeder: SeedService, films: FilmRepository, tmdb: FakeTmdbClient
) -> None:
    tmdb.add(TmdbMovie(57536, "Ra.One", 2011, poster_path="/raone.jpg", runtime_min=156))
    await seeder.import_seed(parse_seed(small_seed()))

    matches = await seeder.apply_fixes(
        [("ra-one-2011", 57536), ("no-such-film", 1), ("tumbbad-2018", 999)]
    )

    assert [film.slug for film in matches.matched] == ["ra-one-2011"]
    assert matches.unknown_slugs == ("no-such-film",)
    assert [film.slug for film in matches.unmatched] == ["tumbbad-2018"]  # TMDB has no film 999
    ra_one = await films.get_by_slug("ra-one-2011")
    assert ra_one is not None
    assert (ra_one.tmdb_id, ra_one.poster_path, ra_one.runtime_min) == (57536, "/raone.jpg", 156)


def test_the_fixes_file_is_read_line_by_line() -> None:
    text = "slug,tmdb_id\nheropanti-2014, 280391\n\nra-one-2011,57536\n"

    assert parse_fixes(text) == [("heropanti-2014", 280391), ("ra-one-2011", 57536)]


@pytest.mark.parametrize(
    ("text", "line"),
    [("heropanti-2014\n", 1), ("heropanti-2014,abc\n", 1), ("ok-2000,1\nx-2000,1,2\n", 2)],
)
def test_a_broken_fixes_line_is_named(text: str, line: int) -> None:
    with pytest.raises(InvalidSeed, match=f"Line {line} should look like"):
        parse_fixes(text)


def test_the_import_script_imports_the_seed_once(tmp_path: Path) -> None:
    env = os.environ | {
        "DISCORD_TOKEN": "test",
        "TMDB_READ_TOKEN": "test",
        "GUILD_ID": "1",
        "DATABASE_PATH": str(tmp_path / "moviebot.db"),
    }

    def run_script() -> str:
        # Run it the way people do. Working in tmp_path keeps any real .env out of the test.
        done = subprocess.run(  # noqa: S603 - runs this repo's own script with this Python
            [sys.executable, str(SCRIPT), str(SEED_FILE)],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert done.returncode == 0, done.stderr
        return done.stdout + done.stderr

    assert "196 films added, 0 already on the list" in run_script()
    assert "0 films added, 196 already on the list" in run_script()
