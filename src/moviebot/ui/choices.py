"""Choices offered while someone types an option: categories, films on the list, TMDB films."""

from discord import app_commands

from moviebot.models import Category, Film, TmdbMovie

MAX_CHOICES = 25  # Discord shows at most 25 suggestions,
MAX_NAME = 100  # each named in at most 100 characters


def category_choices(categories: list[Category], typed: str) -> list[app_commands.Choice[str]]:
    """Up to 25 categories whose name or key contains what has been typed so far."""
    typed = typed.lower()
    return [
        app_commands.Choice(name=category.name, value=category.key)
        for category in categories
        if typed in category.name.lower() or typed in category.key
    ][:MAX_CHOICES]


def film_choices(films: list[Film]) -> list[app_commands.Choice[str]]:
    """Films on the list as 'Title (Year)'. The value 'film:<id>' says which one was picked."""
    return [
        app_commands.Choice(name=shorten(film.label), value=f"film:{film.id}")
        for film in films[:MAX_CHOICES]
    ]


def tmdb_choices(movies: list[TmdbMovie]) -> list[app_commands.Choice[str]]:
    """TMDB films as 'Title (Year)'. The value 'tmdb:<id>' says which one was picked."""
    return [
        app_commands.Choice(name=shorten(movie.label), value=f"tmdb:{movie.id}")
        for movie in movies[:MAX_CHOICES]
    ]


def shorten(text: str, limit: int = MAX_NAME) -> str:
    """Fit text into a length limit, ending it with '…' when it has to be cut."""
    return text if len(text) <= limit else text[: limit - 1] + "…"
