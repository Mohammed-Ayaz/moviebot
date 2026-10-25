"""Test doubles shared by the tests."""

from collections.abc import Iterable
from dataclasses import replace

from moviebot.models import TmdbMovie
from moviebot.tmdb.client import TmdbError


class FakeTmdbClient:
    """Stands in for TmdbClient: canned films, no network. Set down = True to fail every call."""

    def __init__(self, movies: Iterable[TmdbMovie] = ()) -> None:
        self.movies = {movie.id: movie for movie in movies}
        self.down = False
        self.searches: list[str] = []

    def add(self, *movies: TmdbMovie) -> None:
        for movie in movies:
            self.movies[movie.id] = movie

    async def search(self, query: str, year: int | None = None) -> list[TmdbMovie]:
        """Films whose title contains the query, ignoring case. Like TMDB, no runtimes here."""
        self._check()
        self.searches.append(query)
        wanted = query.strip().lower()
        return [
            replace(movie, runtime_min=None)
            for movie in self.movies.values()
            if wanted in movie.title.lower() and (year is None or movie.year == year)
        ]

    async def details(self, movie_id: int) -> TmdbMovie:
        self._check()
        if movie_id not in self.movies:
            raise TmdbError(f"TMDB answered 404 for /3/movie/{movie_id}")
        return self.movies[movie_id]

    def _check(self) -> None:
        if self.down:
            raise TmdbError("TMDB couldn't be reached (the fake is set to down)")
