"""FilmRepository and CategoryRepository: the SQL itself, on a fresh in-memory database."""

from dataclasses import replace

import aiosqlite
import pytest

from moviebot.db.categories import CategoryRepository
from moviebot.db.database import Database
from moviebot.db.films import FilmRepository
from moviebot.db.suggestions import SuggestionRepository
from moviebot.models import Category, NewFilm

WATCHED_AT = "2026-10-20T10:00:00Z"


async def test_add_returns_the_stored_film(films: FilmRepository) -> None:
    film = await films.add(
        NewFilm(slug="heropanti-2014", title="Heropanti", year=2014, added_by=42)
    )

    assert film.id > 0
    assert (film.slug, film.title, film.year, film.added_by) == (
        "heropanti-2014",
        "Heropanti",
        2014,
        42,
    )
    assert film.added_at.endswith("Z")
    assert film.is_indian is True
    assert film.watched_at is None
    assert await films.get(film.id) == film


async def test_unique_index_refuses_same_title_and_year(films: FilmRepository) -> None:
    await films.add(NewFilm(slug="heropanti-2014", title="Heropanti", year=2014))

    with pytest.raises(aiosqlite.IntegrityError):
        await films.add(NewFilm(slug="heropanti-2014-2", title="HEROPANTI", year=2014))

    # The failed insert was rolled back, so the next one works.
    await films.add(NewFilm(slug="heropanti-2-2022", title="Heropanti 2", year=2022))


async def test_films_without_a_year_never_match_as_duplicates(films: FilmRepository) -> None:
    await films.add(NewFilm(slug="mystery", title="Mystery", year=None))
    await films.add(NewFilm(slug="mystery-2", title="Mystery", year=None))

    assert await films.find_duplicate(title="mystery", year=None, tmdb_id=None) is None
    same_title = await films.find_by_title("MYSTERY")
    assert same_title is not None
    assert same_title.slug == "mystery"


async def test_find_duplicate_by_tmdb_id_or_title_and_year(films: FilmRepository) -> None:
    film = await films.add(NewFilm(slug="heropanti-2014", title="Heropanti", year=2014, tmdb_id=7))

    assert await films.find_duplicate(title="Other", year=1999, tmdb_id=7) == film
    assert await films.find_duplicate(title="heroPANTI", year=2014, tmdb_id=None) == film
    assert await films.find_duplicate(title="Heropanti", year=2015, tmdb_id=None) is None
    assert await films.slug_taken("heropanti-2014")
    assert not await films.slug_taken("heropanti")


async def test_count_and_list_page_filter_and_page(films: FilmRepository, launch: Category) -> None:
    for number in range(12):
        category = launch.key if number < 5 else None
        await films.add(
            NewFilm(
                slug=f"film-{number}", title=f"Film {number:02}", year=2000, category_key=category
            )
        )
    await films.add(NewFilm(slug="seen-2001", title="Seen", year=2001, watched_at=WATCHED_AT))

    assert await films.count(show="unwatched", category_key=None) == 12
    assert await films.count(show="watched", category_key=None) == 1
    assert await films.count(show="all", category_key=None) == 13
    assert await films.count(show="unwatched", category_key="launch") == 5

    second_page = await films.list_page(show="unwatched", category_key=None, limit=10, offset=10)
    assert [film.title for film in second_page] == ["Film 10", "Film 11"]
    watched = await films.list_page(show="watched", category_key=None, limit=10, offset=0)
    assert [film.title for film in watched] == ["Seen"]


async def test_delete_removes_the_film(films: FilmRepository) -> None:
    film = await films.add(NewFilm(slug="heropanti-2014", title="Heropanti", year=2014))

    assert await films.delete(film.id) is True
    assert await films.get(film.id) is None
    assert await films.delete(film.id) is False


async def test_unknown_category_is_refused_by_the_foreign_key(films: FilmRepository) -> None:
    with pytest.raises(aiosqlite.IntegrityError):
        await films.add(NewFilm(slug="x", title="X", year=None, category_key="nope"))


async def test_category_add_leaves_an_existing_key_alone(
    categories: CategoryRepository, launch: Category
) -> None:
    assert await categories.add(replace(launch, name="Renamed")) is False
    assert await categories.get("launch") == launch
    assert await categories.get("nope") is None
    assert await categories.list_all() == [launch]


async def test_add_stores_tmdb_details_and_finds_by_tmdb_id(films: FilmRepository) -> None:
    film = await films.add(
        NewFilm(
            slug="heropanti-2014",
            title="Heropanti",
            year=2014,
            tmdb_id=101,
            poster_path="/heropanti.jpg",
            runtime_min=146,
            tmdb_synced_at="2026-10-21T18:00:00Z",
        )
    )

    assert (film.poster_path, film.runtime_min) == ("/heropanti.jpg", 146)
    assert film.tmdb_synced_at == "2026-10-21T18:00:00Z"
    assert await films.get_by_tmdb_id(101) == film
    assert await films.get_by_tmdb_id(999) is None


async def test_unwatched_filters_by_category_and_genre(
    films: FilmRepository, launch: Category
) -> None:
    masala = await films.add(
        NewFilm(slug="a", title="A", year=2000, category_key="launch", genre="masala", side="bad")
    )
    drama = await films.add(NewFilm(slug="b", title="B", year=2000, genre="drama"))
    await films.add(NewFilm(slug="c", title="C", year=2000, genre="masala", watched_at=WATCHED_AT))

    assert await films.unwatched() == [masala, drama]
    assert await films.unwatched(category_key="launch") == [masala]
    assert await films.unwatched(genre="drama") == [drama]
    assert (masala.side, masala.genre) == ("bad", "masala")


async def test_list_all_sorts_by_title_and_filters_by_watched(films: FilmRepository) -> None:
    unwatched = await films.add(NewFilm(slug="b-2001", title="b film", year=2001))
    watched = await films.add(
        NewFilm(slug="a-2000", title="A film", year=2000, watched_at=WATCHED_AT)
    )

    assert await films.list_all() == [watched, unwatched]
    assert await films.list_all(watched=True) == [watched]
    assert await films.list_all(watched=False) == [unwatched]


async def test_update_sets_the_note_and_category(films: FilmRepository, launch: Category) -> None:
    film = await films.add(NewFilm(slug="heropanti-2014", title="Heropanti", year=2014))

    updated = await films.update(film.id, note="Tiger's debut", category_key="launch")

    assert updated is not None
    assert (updated.note, updated.category_key) == ("Tiger's debut", "launch")
    assert await films.update(9999, note=None, category_key=None) is None


async def test_watched_and_unwatched_change_only_the_right_films(films: FilmRepository) -> None:
    film = await films.add(NewFilm(slug="heropanti-2014", title="Heropanti", year=2014))

    assert await films.mark_unwatched(film.id) is None  # not watched yet
    watched = await films.mark_watched(film.id, WATCHED_AT)
    assert watched is not None
    assert watched.watched_at == WATCHED_AT
    assert await films.mark_watched(film.id, "2026-10-25T20:00:00Z") is None  # already watched
    unwatched = await films.mark_unwatched(film.id)
    assert unwatched is not None
    assert unwatched.watched_at is None


async def test_removing_a_film_removes_its_suggestion_history(
    db: Database, films: FilmRepository, suggestions: SuggestionRepository
) -> None:
    film = await films.add(NewFilm(slug="heropanti-2014", title="Heropanti", year=2014))
    await suggestions.add(film.id, requested_by=1)

    await films.delete(film.id)

    rows = await db.conn.execute_fetchall("SELECT count(*) FROM suggestions")
    assert list(rows)[0][0] == 0


async def test_add_if_new_leaves_out_a_film_already_listed(films: FilmRepository) -> None:
    first = await films.add_if_new(
        NewFilm(
            slug="heropanti-2014",
            title="Heropanti",
            year=2014,
            tmdb_id=1,
            why_watch="An AI wrote this.",
            grade="yours",
            is_indian=False,
        )
    )

    assert first is not None
    assert (first.why_watch, first.grade, first.is_indian) == ("An AI wrote this.", "yours", False)
    assert await films.add_if_new(NewFilm(slug="heropanti-2014", title="Other", year=2000)) is None
    assert await films.add_if_new(NewFilm(slug="x-2014", title="HEROPANTI", year=2014)) is None
    assert await films.add_if_new(NewFilm(slug="y", title="Y", year=None, tmdb_id=1)) is None
    assert await films.list_all() == [first]


async def test_set_tmdb_stores_the_details_and_get_by_slug_finds_the_film(
    films: FilmRepository,
) -> None:
    film = await films.add(NewFilm(slug="heropanti-2014", title="Heropanti", year=2014))

    updated = await films.set_tmdb(
        film.id,
        tmdb_id=280391,
        poster_path="/heropanti.jpg",
        runtime_min=146,
        synced_at="2026-10-21T18:00:00Z",
    )

    assert updated is not None
    assert (updated.tmdb_id, updated.poster_path, updated.runtime_min) == (
        280391,
        "/heropanti.jpg",
        146,
    )
    assert updated.tmdb_synced_at == "2026-10-21T18:00:00Z"
    assert await films.get_by_slug("heropanti-2014") == updated
    assert await films.get_by_slug("nope") is None
    missing = await films.set_tmdb(
        999, tmdb_id=1, poster_path=None, runtime_min=None, synced_at="2026-10-21T18:00:00Z"
    )
    assert missing is None


async def test_needing_refresh_finds_tmdb_films_fetched_before_the_cutoff(
    films: FilmRepository,
) -> None:
    old = await films.add(
        NewFilm(slug="a", title="A", year=None, tmdb_id=1, tmdb_synced_at="2026-01-01T00:00:00Z")
    )
    never = await films.add(NewFilm(slug="b", title="B", year=None, tmdb_id=2))
    await films.add(
        NewFilm(slug="c", title="C", year=None, tmdb_id=3, tmdb_synced_at="2026-09-01T00:00:00Z")
    )
    await films.add(NewFilm(slug="d", title="D", year=None))  # not on TMDB

    due = await films.needing_refresh(synced_before="2026-05-01T00:00:00Z", limit=10)

    assert due == [never, old]  # never fetched comes first, then the oldest
    assert await films.needing_refresh(synced_before="2026-05-01T00:00:00Z", limit=1) == [never]
