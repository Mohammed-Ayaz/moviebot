"""WatchlistService: adding films (FR-2, FR-4) and listing them (FR-3)."""

import json
from pathlib import Path

import pytest
from fakes import FakeTmdbClient

from moviebot.db.categories import CategoryRepository
from moviebot.db.films import FilmRepository
from moviebot.models import (
    AlreadyWatched,
    AmbiguousFilm,
    Category,
    DuplicateFilm,
    FilmNotFound,
    FilmPage,
    InvalidFilm,
    NewFilm,
    NotWatched,
    TmdbMovie,
    TmdbUnavailable,
    UnknownCategory,
    UnknownFilm,
)
from moviebot.services.watchlist import WatchlistService, make_slug, titles_match

SEED_FILE = Path(__file__).parents[1] / "watchlist_seed.json"
WATCHED_AT = "2026-10-20T10:00:00Z"
HEROPANTI = TmdbMovie(101, "Heropanti", 2014, poster_path="/heropanti.jpg", runtime_min=146)
HEROPANTI_2 = TmdbMovie(102, "Heropanti 2", 2022, poster_path="/heropanti-2.jpg", runtime_min=147)
DON_1978 = TmdbMovie(201, "Don", 1978, poster_path="/don-1978.jpg", runtime_min=175)
DON_2006 = TmdbMovie(202, "Don", 2006, poster_path="/don-2006.jpg", runtime_min=171)


def titles(page: FilmPage) -> list[str]:
    return [film.title for film in page.films]


async def test_add_saves_a_trimmed_film_with_its_slug(watchlist: WatchlistService) -> None:
    added = await watchlist.add_film(
        title="  Heropanti ", year=2014, note="  Tiger's debut ", added_by=42
    )

    film = added.film
    assert (film.title, film.year, film.slug) == ("Heropanti", 2014, "heropanti-2014")
    assert (film.note, film.added_by, film.watched_at) == ("Tiger's debut", 42, None)
    assert added.category is None
    assert added.same_title is None


async def test_add_accepts_the_longest_title_and_note(watchlist: WatchlistService) -> None:
    added = await watchlist.add_film(title="x" * 200, note="y" * 500, year=1888)

    assert len(added.film.title) == 200
    assert added.film.note is not None
    assert len(added.film.note) == 500


async def test_add_rejects_duplicate_title_and_year(watchlist: WatchlistService) -> None:
    await watchlist.add_film(title="Heropanti", year=2014)

    with pytest.raises(DuplicateFilm) as caught:
        await watchlist.add_film(title="HEROPANTI", year=2014)

    assert caught.value.existing.title == "Heropanti"
    assert str(caught.value) == "Heropanti (2014) is already on the list."


async def test_add_rejects_duplicate_tmdb_id(
    watchlist: WatchlistService, tmdb: FakeTmdbClient
) -> None:
    tmdb.add(HEROPANTI)
    await watchlist.add_from_tmdb(HEROPANTI.id)
    tmdb.down = True  # the duplicate is found before TMDB is asked

    with pytest.raises(DuplicateFilm, match=r"Heropanti \(2014\)"):
        await watchlist.add_from_tmdb(HEROPANTI.id)


async def test_add_allows_the_same_title_in_another_year(watchlist: WatchlistService) -> None:
    first = await watchlist.add_film(title="Don", year=1978)
    second = await watchlist.add_film(title="Don", year=2006)

    assert (first.film.slug, second.film.slug) == ("don-1978", "don-2006")
    assert second.same_title is None


async def test_add_without_a_year_flags_the_same_title(watchlist: WatchlistService) -> None:
    await watchlist.add_film(title="Heropanti", year=2014)

    added = await watchlist.add_film(title="heropanti")

    assert added.film.slug == "heropanti"
    assert added.same_title is not None
    assert added.same_title.label == "Heropanti (2014)"


@pytest.mark.parametrize(
    ("title", "note", "year", "message"),
    [
        ("   ", None, None, "title must be 1 to 200 characters"),
        ("x" * 201, None, None, "title must be 1 to 200 characters"),
        ("Heropanti", "x" * 501, None, "note can be at most 500 characters"),
        ("Heropanti", None, 1887, "year must be between 1888 and 2100"),
        ("Heropanti", None, 2101, "year must be between 1888 and 2100"),
    ],
)
async def test_add_rejects_bad_input(
    watchlist: WatchlistService, title: str, note: str | None, year: int | None, message: str
) -> None:
    with pytest.raises(InvalidFilm, match=message):
        await watchlist.add_film(title=title, note=note, year=year)


async def test_add_checks_the_category(watchlist: WatchlistService, launch: Category) -> None:
    with pytest.raises(UnknownCategory, match='no category called "nope"'):
        await watchlist.add_film(title="Heropanti", year=2014, category_key="nope")

    added = await watchlist.add_film(title="Heropanti", year=2014, category_key="launch")

    assert added.film.category_key == "launch"
    assert added.category == launch


@pytest.mark.parametrize(
    ("title", "year", "slug"),
    [
        ("Heropanti", None, "heropanti"),
        ("  --Ra.One--  ", 2011, "ra-one-2011"),
        ("दिल", 1990, "film-1990"),  # no a-z or 0-9 in the title at all
    ],
)
def test_make_slug_edge_cases(title: str, year: int | None, slug: str) -> None:
    assert make_slug(title, year) == slug


def test_make_slug_matches_every_id_in_the_seed_file() -> None:
    seed = json.loads(SEED_FILE.read_text(encoding="utf-8"))

    for film in seed["films"]:
        assert make_slug(film["title"], film["year"]) == film["id"]


async def test_slug_gets_a_number_when_taken(watchlist: WatchlistService) -> None:
    slugs = [
        (await watchlist.add_film(title=title, year=2006)).film.slug
        for title in ("Don", "Don!", "Don?")
    ]

    assert slugs == ["don-2006", "don-2006-2", "don-2006-3"]


async def test_list_shows_unwatched_films_10_a_page_by_title(watchlist: WatchlistService) -> None:
    for number in reversed(range(25)):
        await watchlist.add_film(title=f"Film {number:02}", year=2000)

    first = await watchlist.list_films()
    last = await watchlist.list_films(page=3)

    assert (first.page, first.page_count, first.total, first.per_page) == (1, 3, 25, 10)
    assert first.show == "unwatched"
    assert titles(first)[:3] == ["Film 00", "Film 01", "Film 02"]
    assert titles(last) == ["Film 20", "Film 21", "Film 22", "Film 23", "Film 24"]


async def test_list_filters_by_watched_state_and_category(
    watchlist: WatchlistService, films: FilmRepository, launch: Category
) -> None:
    await watchlist.add_film(title="Heropanti", year=2014, category_key="launch")
    await watchlist.add_film(title="Dhoom", year=2004)
    await films.add(
        NewFilm(
            slug="student-of-the-year-2012",
            title="Student of the Year",
            year=2012,
            category_key="launch",
            watched_at=WATCHED_AT,
        )
    )

    assert titles(await watchlist.list_films()) == ["Dhoom", "Heropanti"]
    assert titles(await watchlist.list_films(show="watched")) == ["Student of the Year"]
    assert titles(await watchlist.list_films(show="all")) == [
        "Dhoom",
        "Heropanti",
        "Student of the Year",
    ]
    in_launch = await watchlist.list_films(show="all", category_key="launch")
    assert titles(in_launch) == ["Heropanti", "Student of the Year"]
    assert in_launch.category == launch
    assert in_launch.category_names == {"launch": "The launch"}


async def test_list_keeps_the_page_number_in_range(watchlist: WatchlistService) -> None:
    empty = await watchlist.list_films(page=4)
    assert (empty.page, empty.page_count, empty.total, empty.films) == (1, 1, 0, ())

    for title in ("A", "B", "C"):
        await watchlist.add_film(title=title, year=2000)

    assert (await watchlist.list_films(page=9)).page == 1
    assert (await watchlist.list_films(page=0)).page == 1


async def test_list_rejects_an_unknown_category(watchlist: WatchlistService) -> None:
    with pytest.raises(UnknownCategory):
        await watchlist.list_films(category_key="nope")


async def test_list_categories_in_display_order(
    watchlist: WatchlistService, categories: CategoryRepository, launch: Category
) -> None:
    noir = Category(key="noir", name="A nobody in over his head", position=12, side="good")
    await categories.add(noir)

    assert await watchlist.list_categories() == [launch, noir]


async def test_add_from_tmdb_stores_tmdb_details(
    watchlist: WatchlistService, tmdb: FakeTmdbClient
) -> None:
    tmdb.add(HEROPANTI)

    added = await watchlist.add_from_tmdb(HEROPANTI.id, note="Tiger's debut", added_by=42)

    film = added.film
    assert (film.title, film.year, film.slug, film.tmdb_id) == (
        "Heropanti",
        2014,
        "heropanti-2014",
        101,
    )
    assert (film.poster_path, film.runtime_min) == ("/heropanti.jpg", 146)
    assert film.tmdb_synced_at == "2026-10-21T18:00:00Z"
    assert (film.note, film.added_by) == ("Tiger's debut", 42)
    assert added.tmdb == "found"


async def test_picked_film_already_typed_is_a_duplicate(
    watchlist: WatchlistService, tmdb: FakeTmdbClient
) -> None:
    await watchlist.add_film(
        title="Heropanti", year=2014
    )  # TMDB knows no films yet: saved as typed
    tmdb.add(HEROPANTI)

    with pytest.raises(DuplicateFilm):
        await watchlist.add_from_tmdb(HEROPANTI.id)


async def test_picked_film_while_tmdb_is_down_is_refused(
    watchlist: WatchlistService, tmdb: FakeTmdbClient
) -> None:
    tmdb.add(HEROPANTI)
    tmdb.down = True

    with pytest.raises(TmdbUnavailable):
        await watchlist.add_from_tmdb(HEROPANTI.id)

    assert (await watchlist.list_films()).total == 0


async def test_typed_title_with_one_exact_match_is_used_as_if_picked(
    watchlist: WatchlistService, tmdb: FakeTmdbClient
) -> None:
    tmdb.add(HEROPANTI, HEROPANTI_2)

    added = await watchlist.add_film(title="heropanti")

    assert (added.film.title, added.film.year, added.film.tmdb_id) == ("Heropanti", 2014, 101)
    assert added.film.runtime_min == 146  # the details were fetched after the match
    assert added.tmdb == "found"
    assert added.same_title is None


async def test_typed_title_with_several_matches_is_saved_as_typed(
    watchlist: WatchlistService, tmdb: FakeTmdbClient
) -> None:
    tmdb.add(DON_1978, DON_2006)

    added = await watchlist.add_film(title="Don")

    assert (added.film.title, added.film.year, added.film.tmdb_id) == ("Don", None, None)
    assert added.film.poster_path is None
    assert added.tmdb == "not_found"


async def test_a_typed_year_narrows_the_match_to_within_one_year(
    watchlist: WatchlistService, tmdb: FakeTmdbClient
) -> None:
    tmdb.add(DON_1978, DON_2006)

    added = await watchlist.add_film(title="don", year=2007)

    assert (added.film.title, added.film.year, added.film.tmdb_id) == ("Don", 2006, 202)
    assert added.tmdb == "found"


async def test_typed_title_is_saved_without_a_poster_when_tmdb_is_down(
    watchlist: WatchlistService, tmdb: FakeTmdbClient
) -> None:
    tmdb.add(HEROPANTI)
    tmdb.down = True

    added = await watchlist.add_film(title="Heropanti", year=2014)

    assert (added.film.title, added.film.year, added.film.poster_path) == ("Heropanti", 2014, None)
    assert added.tmdb == "unavailable"


@pytest.mark.parametrize(
    ("typed", "tmdb_title", "expected"),
    [
        ("ra one", "Ra.One", True),
        ("HEROPANTI", "Heropanti", True),
        ("Kabhi Khushi Kabhie Gham", "Kabhi Khushi Kabhie Gham...", True),
        ("Heropanti", "Heropanti 2", False),
        ("!!!", "???", False),
    ],
)
def test_titles_match_ignoring_case_and_punctuation(
    typed: str, tmdb_title: str, expected: bool
) -> None:
    assert titles_match(typed, tmdb_title) is expected


async def test_search_tmdb_for_suggestions(
    watchlist: WatchlistService, tmdb: FakeTmdbClient
) -> None:
    tmdb.add(HEROPANTI, HEROPANTI_2)

    assert await watchlist.search_tmdb("h") == []  # too short to search
    assert tmdb.searches == []
    labels = [movie.label for movie in await watchlist.search_tmdb("herop")]
    assert labels == ["Heropanti (2014)", "Heropanti 2 (2022)"]

    tmdb.down = True
    assert await watchlist.search_tmdb("herop") == []


async def test_search_films_ignores_case_and_punctuation(
    watchlist: WatchlistService, films: FilmRepository
) -> None:
    await films.add(NewFilm(slug="ra-one-2011", title="Ra.One", year=2011))
    await films.add(NewFilm(slug="raees-2017", title="Raees", year=2017, watched_at=WATCHED_AT))

    assert [film.title for film in await watchlist.search_films("RA ONE")] == ["Ra.One"]
    assert [film.title for film in await watchlist.search_films("ra")] == ["Ra.One", "Raees"]
    assert [film.title for film in await watchlist.search_films("ra", watched=True)] == ["Raees"]
    assert [film.title for film in await watchlist.search_films("ra", watched=False)] == ["Ra.One"]


async def test_search_films_returns_at_most_25(
    watchlist: WatchlistService, films: FilmRepository
) -> None:
    for number in range(30):
        await films.add(NewFilm(slug=f"film-{number}", title=f"Film {number:02}", year=2000))

    assert len(await watchlist.search_films("")) == 25


async def test_a_typed_film_name_must_match_exactly_one_film(
    watchlist: WatchlistService, films: FilmRepository
) -> None:
    await films.add(NewFilm(slug="don-1978", title="Don", year=1978))
    await films.add(NewFilm(slug="don-2006", title="Don", year=2006, watched_at=WATCHED_AT))
    await films.add(NewFilm(slug="ra-one-2011", title="Ra.One", year=2011))

    assert (await watchlist.film_named("ra one")).slug == "ra-one-2011"
    assert (await watchlist.film_named("don", watched=False)).year == 1978  # the unwatched Don
    with pytest.raises(AmbiguousFilm, match="Several films are called"):
        await watchlist.film_named("Don")
    with pytest.raises(UnknownFilm, match='no film called "Dhoom"'):
        await watchlist.film_named(" Dhoom ")


async def test_a_typed_name_outside_the_filter_still_finds_the_film(
    watchlist: WatchlistService, films: FilmRepository
) -> None:
    seen = await films.add(
        NewFilm(slug="seen-2000", title="Seen", year=2000, watched_at=WATCHED_AT)
    )

    # /watched looks among unwatched films first, then says this one is already watched.
    assert await watchlist.film_named("seen", watched=False) == seen


async def test_remove_film_deletes_it(watchlist: WatchlistService, films: FilmRepository) -> None:
    added = await watchlist.add_film(title="Heropanti", year=2014)

    removed = await watchlist.remove_film(added.film.id)

    assert removed.title == "Heropanti"
    assert await films.get(added.film.id) is None
    with pytest.raises(FilmNotFound):
        await watchlist.remove_film(added.film.id)


async def test_edit_film_changes_the_note_and_category(
    watchlist: WatchlistService, launch: Category
) -> None:
    added = await watchlist.add_film(title="Heropanti", year=2014, note="Old note")

    edited = await watchlist.edit_film(
        added.film.id, note="  Tiger's debut ", category_key="launch"
    )
    kept = await watchlist.edit_film(added.film.id, note="")  # empty clears it; category is kept

    assert (edited.film.note, edited.film.category_key, edited.category) == (
        "Tiger's debut",
        "launch",
        launch,
    )
    assert (kept.film.note, kept.film.category_key, kept.category) == (None, "launch", launch)


async def test_edit_film_refuses_bad_input(watchlist: WatchlistService) -> None:
    added = await watchlist.add_film(title="Heropanti", year=2014)

    with pytest.raises(UnknownCategory):
        await watchlist.edit_film(added.film.id, note=None, category_key="nope")
    with pytest.raises(InvalidFilm, match="at most 500"):
        await watchlist.edit_film(added.film.id, note="x" * 501)
    with pytest.raises(FilmNotFound):
        await watchlist.edit_film(9999, note=None)


async def test_mark_watched_and_unwatch(watchlist: WatchlistService) -> None:
    added = await watchlist.add_film(title="Heropanti", year=2014)

    with pytest.raises(NotWatched, match="isn't marked as watched"):
        await watchlist.unwatch(added.film.id)
    watched = await watchlist.mark_watched(added.film.id)
    assert watched.watched_at == "2026-10-21T18:00:00Z"
    with pytest.raises(AlreadyWatched):
        await watchlist.mark_watched(added.film.id)
    unwatched = await watchlist.unwatch(added.film.id)
    assert unwatched.watched_at is None
    with pytest.raises(FilmNotFound):
        await watchlist.mark_watched(9999)


async def test_category_lookup(watchlist: WatchlistService, launch: Category) -> None:
    assert await watchlist.category("launch") == launch
    assert await watchlist.category(None) is None
    with pytest.raises(UnknownCategory):
        await watchlist.category("nope")
