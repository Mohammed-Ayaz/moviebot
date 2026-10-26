"""Embeds: TMDB's credit on /about and on film cards, and how a card shows TMDB's details."""

from dataclasses import replace

from moviebot.cogs.admin import TMDB_LOGO
from moviebot.models import Category, Film, SuggestFilters, Suggestion
from moviebot.ui.embeds import TMDB_NOTICE, about_embed, film_card, suggestion_card

FILM = Film(
    id=1,
    slug="heropanti-2014",
    tmdb_id=101,
    title="Heropanti",
    year=2014,
    category_key=None,
    side=None,
    genre=None,
    is_indian=True,
    grade=None,
    note="Tiger's debut",
    why_watch=None,
    poster_path="/heropanti.jpg",
    runtime_min=146,
    tmdb_synced_at="2026-10-21T18:00:00Z",
    added_by=42,
    added_at="2026-10-21T18:00:00Z",
    watched_at=None,
)


def test_about_shows_tmdbs_exact_notice_and_a_small_logo() -> None:
    embed = about_embed(with_logo=True)

    assert TMDB_NOTICE == "This product uses the TMDB API but is not endorsed or certified by TMDB."
    assert [field.value for field in embed.fields] == [TMDB_NOTICE]
    assert embed.thumbnail.url == "attachment://tmdb-logo.png"
    assert embed.image.url is None  # a thumbnail, not a big image


def test_film_card_shows_poster_runtime_and_credits_tmdb() -> None:
    embed = film_card(FILM, None)

    assert embed.title == "Heropanti (2014)"
    assert embed.image.url == "https://image.tmdb.org/t/p/w500/heropanti.jpg"
    assert {field.name: field.value for field in embed.fields} == {
        "Runtime": "2 h 26 min",
        "Added by": "<@42>",
    }
    assert embed.footer.text == "Film data from TMDB"


def test_film_card_without_tmdb_details_has_no_poster_or_credit() -> None:
    embed = film_card(replace(FILM, tmdb_id=None, poster_path=None, runtime_min=None), None)

    assert embed.image.url is None
    assert embed.footer.text is None
    assert [field.name for field in embed.fields] == ["Added by"]


def test_film_card_shows_why_watch_first() -> None:
    embed = film_card(replace(FILM, why_watch="Tiger's debut, built to launch him."), None)

    first = embed.fields[0]
    assert (first.name, first.value, first.inline) == (
        "Why watch it",
        "Tiger's debut, built to launch him.",
        False,
    )


def test_the_tmdb_logo_that_about_attaches_is_a_png() -> None:
    assert TMDB_LOGO.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_suggestion_card_is_headed_with_what_the_pick_was_narrowed_to() -> None:
    launch = Category(key="launch", name="The launch", position=1, side="bad")
    filters = SuggestFilters(category_key="launch", genre="masala", side="bad")

    plain = suggestion_card(Suggestion(film=FILM, category=None, filters=SuggestFilters()))
    narrowed = suggestion_card(Suggestion(film=FILM, category=launch, filters=filters))

    assert plain.author.name == "Suggestion for tonight"
    assert narrowed.author.name == "Suggestion for tonight · The launch, masala, hate-watch"
    assert narrowed.image.url == "https://image.tmdb.org/t/p/w500/heropanti.jpg"
