"""TmdbClient: the only code that calls TMDB.

Search and details over one shared aiohttp session, with a 5-second timeout, one retry when TMDB
is busy, and a 10-minute cache for searches. The token travels in a header and is never logged.
"""

import asyncio
import logging
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import aiohttp

from moviebot.models import TmdbMovie

log = logging.getLogger(__name__)

API_URL = "https://api.themoviedb.org"
TIMEOUT_SECONDS = 5.0
CACHE_SECONDS = 600.0
CACHE_SIZE = 500
MAX_RESULTS = 25
MAX_RETRY_WAIT = 5.0  # seconds: if TMDB asks for a longer wait, give up instead


class TmdbError(Exception):
    """TMDB couldn't be reached, refused the request, or answered with something unusable."""


class TmdbApi(Protocol):
    """What the services need from TMDB. TmdbClient and the tests' FakeTmdbClient both fit it."""

    async def search(self, query: str, year: int | None = None) -> list[TmdbMovie]: ...

    async def details(self, movie_id: int) -> TmdbMovie: ...


class TmdbClient:
    """Calls TMDB's API with a read access token, sent as a Bearer header."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token: str,
        *,
        api_url: str = API_URL,
        timeout: float = TIMEOUT_SECONDS,
        cache_size: int = CACHE_SIZE,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._session = session
        self._headers = {"Authorization": f"Bearer {token}", "accept": "application/json"}
        self._api_url = api_url
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._cache_size = cache_size
        self._clock = clock
        self._sleep = sleep
        self._cache: OrderedDict[tuple[str, int | None], tuple[float, list[TmdbMovie]]]
        self._cache = OrderedDict()

    async def search(self, query: str, year: int | None = None) -> list[TmdbMovie]:
        """Up to 25 films for this query, TMDB's best match first. Cached for 10 minutes."""
        query = query.strip()
        key = (query.lower(), year)
        cached = self._cache.get(key)
        if cached is not None and self._clock() - cached[0] < CACHE_SECONDS:
            self._cache.move_to_end(key)
            return list(cached[1])

        params = {"query": query, "include_adult": "false", "page": "1"}
        if year is not None:
            params["primary_release_year"] = str(year)
        data = await self._get("/3/search/movie", params)
        results = data.get("results")
        found = (_movie(item) for item in (results if isinstance(results, list) else []))
        movies = [movie for movie in found if movie is not None][:MAX_RESULTS]
        self._remember(key, movies)
        return list(movies)

    async def details(self, movie_id: int) -> TmdbMovie:
        """One film by its TMDB id, including its runtime."""
        movie = _movie(await self._get(f"/3/movie/{movie_id}", {}))
        if movie is None:
            raise TmdbError(f"TMDB sent an unusable answer for film {movie_id}")
        return movie

    def _remember(self, key: tuple[str, int | None], movies: list[TmdbMovie]) -> None:
        """Cache a search, dropping the least recently used one past the size limit."""
        self._cache[key] = (self._clock(), movies)
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        """GET a TMDB path. On 429 or 5xx, wait as TMDB asks (1 s if it doesn't) and retry once."""
        status, retry_after, data = await self._request(path, params)
        if status == 429 or status >= 500:
            wait = _retry_wait(retry_after)
            if wait <= MAX_RETRY_WAIT:
                await self._sleep(wait)
                status, retry_after, data = await self._request(path, params)
        if status == 200:
            if isinstance(data, dict):
                return data
            raise TmdbError(f"TMDB sent an unexpected answer for {path}")
        if status == 401:
            log.warning("TMDB rejected the token: check TMDB_READ_TOKEN in .env")
        raise TmdbError(f"TMDB answered {status} for {path}")

    async def _request(self, path: str, params: dict[str, str]) -> tuple[int, str | None, Any]:
        """One HTTP request: the status, the Retry-After header, and the JSON when it's a 200."""
        try:
            async with self._session.get(
                self._api_url + path, params=params, headers=self._headers, timeout=self._timeout
            ) as response:
                data = await response.json() if response.status == 200 else None
                return response.status, response.headers.get("Retry-After"), data
        except (aiohttp.ClientError, TimeoutError, ValueError) as error:
            raise TmdbError(
                f"TMDB couldn't be reached for {path}: {type(error).__name__}"
            ) from error


def _movie(item: object) -> TmdbMovie | None:
    """A TmdbMovie from TMDB's JSON for one film, or None when it has no usable id or title."""
    if not isinstance(item, dict):
        return None
    movie_id, title = item.get("id"), item.get("title")
    if not isinstance(movie_id, int) or not isinstance(title, str) or not title.strip():
        return None
    release = item.get("release_date")
    poster = item.get("poster_path")
    runtime = item.get("runtime")
    return TmdbMovie(
        id=movie_id,
        title=title.strip(),
        year=int(release[:4]) if isinstance(release, str) and release[:4].isdigit() else None,
        poster_path=poster if isinstance(poster, str) and poster else None,
        runtime_min=runtime if isinstance(runtime, int) and runtime > 0 else None,
    )


def _retry_wait(retry_after: str | None) -> float:
    """Seconds to wait before the retry: Retry-After when it's a number, otherwise 1."""
    try:
        return max(0.0, float(retry_after)) if retry_after else 1.0
    except ValueError:
        return 1.0
