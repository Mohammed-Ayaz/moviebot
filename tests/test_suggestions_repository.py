"""SuggestionRepository: the suggestion history, and "We're watching this" in one transaction."""

from moviebot.db.database import Database
from moviebot.db.films import FilmRepository
from moviebot.db.suggestions import SuggestionRepository
from moviebot.models import Film, NewFilm

WATCHED_AT = "2026-10-20T10:00:00Z"
LATER = "2026-10-25T20:00:00Z"


async def add_film(films: FilmRepository, number: int, watched_at: str | None = None) -> Film:
    return await films.add(
        NewFilm(slug=f"film-{number}", title=f"Film {number}", year=2000, watched_at=watched_at)
    )


async def chosen_flags(db: Database) -> list[tuple[int, int]]:
    rows = await db.conn.execute_fetchall("SELECT id, chosen FROM suggestions ORDER BY id")
    return [(row[0], row[1]) for row in rows]


async def test_recent_film_ids_are_the_latest_suggestions_newest_first(
    films: FilmRepository, suggestions: SuggestionRepository
) -> None:
    first, second, third = [await add_film(films, number) for number in range(3)]
    for film in (first, second, third, first):
        await suggestions.add(film.id, requested_by=1)

    assert await suggestions.recent_film_ids(3) == [first.id, third.id, second.id]


async def test_choose_marks_the_film_watched_and_its_latest_suggestion_chosen(
    db: Database, films: FilmRepository, suggestions: SuggestionRepository
) -> None:
    film = await add_film(films, 1)
    older = await suggestions.add(film.id, requested_by=1)
    latest = await suggestions.add(film.id, requested_by=2)

    assert await suggestions.choose(film.id, WATCHED_AT) is True

    stored = await films.get(film.id)
    assert stored is not None
    assert stored.watched_at == WATCHED_AT
    assert await chosen_flags(db) == [(older, 0), (latest, 1)]


async def test_choose_changes_nothing_for_a_watched_or_missing_film(
    db: Database, films: FilmRepository, suggestions: SuggestionRepository
) -> None:
    film = await add_film(films, 1, watched_at=WATCHED_AT)
    suggestion = await suggestions.add(film.id, requested_by=1)

    assert await suggestions.choose(film.id, LATER) is False
    assert await suggestions.choose(9999, LATER) is False

    stored = await films.get(film.id)
    assert stored is not None
    assert stored.watched_at == WATCHED_AT
    assert await chosen_flags(db) == [(suggestion, 0)]
