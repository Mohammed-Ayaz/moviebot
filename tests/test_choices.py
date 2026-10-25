"""The suggestions offered while someone types a category, a film on the list, or a title."""

from moviebot.models import Category, Film, TmdbMovie
from moviebot.ui.choices import category_choices, film_choices, shorten, tmdb_choices

CATEGORIES = [
    Category(key="launch", name="The launch", position=1, side="bad"),
    Category(key="noir", name="A nobody in over his head", position=12, side="good"),
]


def test_category_choices_match_the_name_or_the_key() -> None:
    assert [choice.value for choice in category_choices(CATEGORIES, "LAUN")] == ["launch"]
    assert [choice.value for choice in category_choices(CATEGORIES, "nobody")] == ["noir"]
    assert [choice.value for choice in category_choices(CATEGORIES, "")] == ["launch", "noir"]
    assert [choice.name for choice in category_choices(CATEGORIES, "noir")] == [
        "A nobody in over his head"
    ]


def make_film(film_id: int, title: str, year: int | None) -> Film:
    return Film(
        id=film_id,
        slug=f"film-{film_id}",
        tmdb_id=None,
        title=title,
        year=year,
        category_key=None,
        side=None,
        genre=None,
        is_indian=True,
        grade=None,
        note=None,
        why_watch=None,
        poster_path=None,
        runtime_min=None,
        tmdb_synced_at=None,
        added_by=None,
        added_at="2026-10-25T18:00:00Z",
        watched_at=None,
    )


def test_film_choices_show_title_and_year_and_carry_the_film_id() -> None:
    choices = film_choices([make_film(7, "Heropanti", 2014), make_film(8, "Mystery", None)])

    assert [(choice.name, choice.value) for choice in choices] == [
        ("Heropanti (2014)", "film:7"),
        ("Mystery", "film:8"),
    ]


def test_tmdb_choices_carry_the_tmdb_id() -> None:
    choices = tmdb_choices([TmdbMovie(280391, "Heropanti", 2014, poster_path=None)])

    assert [(choice.name, choice.value) for choice in choices] == [
        ("Heropanti (2014)", "tmdb:280391")
    ]


def test_long_names_are_shortened_to_discords_limit() -> None:
    name = film_choices([make_film(1, "x" * 150, 2000)])[0].name

    assert len(name) == 100
    assert name.endswith("…")
    assert shorten("Short", 45) == "Short"
