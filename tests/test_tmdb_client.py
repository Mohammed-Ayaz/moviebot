"""TmdbClient against a fake TMDB server on localhost: real HTTP, but never the internet."""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from moviebot.models import TmdbMovie
from moviebot.tmdb.client import TmdbClient, TmdbError

FAKE_KEY = "fake-tmdb-read-key"
HEROPANTI = {
    "id": 280391,
    "title": "Heropanti",
    "release_date": "2014-05-23",
    "poster_path": "/h.jpg",
}


@dataclass
class Seen:
    """One request the fake TMDB received."""

    path: str
    query: dict[str, str]
    authorization: str | None
    accept: str | None


class FakeTmdb:
    """A tiny stand-in for TMDB: records each request and answers from a queue."""

    def __init__(self) -> None:
        self.url = ""
        self.requests: list[Seen] = []
        self._answers: list[tuple[int, Any, dict[str, str], float]] = []

    def answer(
        self,
        body: Any = None,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        delay: float = 0,
    ) -> None:
        self._answers.append((status, {} if body is None else body, headers or {}, delay))

    async def handle(self, request: web.Request) -> web.Response:
        self.requests.append(
            Seen(
                path=request.path,
                query=dict(request.query),
                authorization=request.headers.get("Authorization"),
                accept=request.headers.get("Accept"),
            )
        )
        status, body, headers, delay = self._answers.pop(0)
        if delay:
            await asyncio.sleep(delay)
        return web.json_response(body, status=status, headers=headers)


class FakeClock:
    """A monotonic clock that the tests move by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeSleep:
    """Records how long the client asked to wait, without waiting."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


@pytest.fixture
async def tmdb_server() -> AsyncIterator[FakeTmdb]:
    fake = FakeTmdb()
    app = web.Application()
    app.router.add_get("/3/search/movie", fake.handle)
    app.router.add_get("/3/movie/{movie_id}", fake.handle)
    server = TestServer(app)
    await server.start_server()
    fake.url = str(server.make_url("")).rstrip("/")
    try:
        yield fake
    finally:
        await server.close()


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as client_session:
        yield client_session


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def sleep() -> FakeSleep:
    return FakeSleep()


@pytest.fixture
def client(
    session: aiohttp.ClientSession, tmdb_server: FakeTmdb, clock: FakeClock, sleep: FakeSleep
) -> TmdbClient:
    return TmdbClient(
        session, FAKE_KEY, api_url=tmdb_server.url, clock=clock, sleep=sleep, cache_size=2
    )


async def test_search_sends_the_token_and_reads_the_results(
    client: TmdbClient, tmdb_server: FakeTmdb
) -> None:
    no_date = {"id": 2, "title": "No Date", "release_date": "", "poster_path": None}
    tmdb_server.answer({"results": [HEROPANTI, no_date, {"title": "No id"}]})

    movies = await client.search("  Herop ")

    assert movies == [
        TmdbMovie(id=280391, title="Heropanti", year=2014, poster_path="/h.jpg"),
        TmdbMovie(id=2, title="No Date", year=None, poster_path=None),
    ]
    [seen] = tmdb_server.requests
    assert seen.path == "/3/search/movie"
    assert seen.query == {"query": "Herop", "include_adult": "false", "page": "1"}
    assert seen.authorization == f"Bearer {FAKE_KEY}"
    assert seen.accept == "application/json"


async def test_search_with_a_year_returns_at_most_25(
    client: TmdbClient, tmdb_server: FakeTmdb
) -> None:
    tmdb_server.answer({"results": [{**HEROPANTI, "id": number} for number in range(1, 31)]})

    movies = await client.search("Heropanti", 2014)

    assert len(movies) == 25
    assert tmdb_server.requests[0].query["primary_release_year"] == "2014"


async def test_search_results_are_cached_for_10_minutes(
    client: TmdbClient, tmdb_server: FakeTmdb, clock: FakeClock
) -> None:
    tmdb_server.answer({"results": [HEROPANTI]})
    tmdb_server.answer({"results": []})

    first = await client.search("Herop")
    clock.now += 599
    again = await client.search(" HEROP ")  # the same search once trimmed and lower-cased
    clock.now += 2
    later = await client.search("herop")

    assert first == again
    assert later == []
    assert len(tmdb_server.requests) == 2


async def test_cache_forgets_the_oldest_search_when_full(
    client: TmdbClient, tmdb_server: FakeTmdb
) -> None:
    for _ in range(4):
        tmdb_server.answer({"results": []})

    for query in ("one", "two", "three", "one"):  # these tests use a cache of 2 searches
        await client.search(query)

    assert len(tmdb_server.requests) == 4  # "three" pushed out "one", so it was fetched again


async def test_retries_once_after_429_using_retry_after(
    client: TmdbClient, tmdb_server: FakeTmdb, sleep: FakeSleep
) -> None:
    tmdb_server.answer(status=429, headers={"Retry-After": "2"})
    tmdb_server.answer({"results": [HEROPANTI]})

    movies = await client.search("Herop")

    assert [movie.id for movie in movies] == [280391]
    assert sleep.waits == [2.0]
    assert len(tmdb_server.requests) == 2


async def test_gives_up_after_a_second_server_error(
    client: TmdbClient, tmdb_server: FakeTmdb, sleep: FakeSleep
) -> None:
    tmdb_server.answer(status=503)
    tmdb_server.answer(status=503)

    with pytest.raises(TmdbError, match="503"):
        await client.search("Herop")

    assert sleep.waits == [1.0]  # no Retry-After header, so it waits 1 second
    assert len(tmdb_server.requests) == 2


async def test_does_not_wait_when_tmdb_asks_for_too_long(
    client: TmdbClient, tmdb_server: FakeTmdb, sleep: FakeSleep
) -> None:
    tmdb_server.answer(status=429, headers={"Retry-After": "30"})

    with pytest.raises(TmdbError):
        await client.search("Herop")

    assert sleep.waits == []
    assert len(tmdb_server.requests) == 1


async def test_rejected_token_fails_at_once_and_is_logged_without_the_token(
    client: TmdbClient, tmdb_server: FakeTmdb, sleep: FakeSleep, caplog: pytest.LogCaptureFixture
) -> None:
    tmdb_server.answer({"status_message": "Invalid API key"}, status=401)

    with caplog.at_level(logging.WARNING), pytest.raises(TmdbError):
        await client.search("Herop")

    assert sleep.waits == []
    assert any("TMDB_READ_TOKEN" in record.getMessage() for record in caplog.records)
    assert all(FAKE_KEY not in record.getMessage() for record in caplog.records)


async def test_slow_answer_becomes_tmdb_error(
    session: aiohttp.ClientSession, tmdb_server: FakeTmdb
) -> None:
    tmdb_server.answer({"results": []}, delay=1)
    client = TmdbClient(session, FAKE_KEY, api_url=tmdb_server.url, timeout=0.2)

    with pytest.raises(TmdbError):
        await client.search("Herop")


async def test_unreachable_tmdb_becomes_tmdb_error(session: aiohttp.ClientSession) -> None:
    client = TmdbClient(session, FAKE_KEY, api_url="http://127.0.0.1:9", timeout=2)

    with pytest.raises(TmdbError):
        await client.details(1)


async def test_details_read_runtime_and_poster(client: TmdbClient, tmdb_server: FakeTmdb) -> None:
    tmdb_server.answer({**HEROPANTI, "runtime": 146})

    movie = await client.details(280391)

    assert movie == TmdbMovie(
        id=280391, title="Heropanti", year=2014, poster_path="/h.jpg", runtime_min=146
    )
    assert tmdb_server.requests[0].path == "/3/movie/280391"


async def test_details_without_an_id_are_refused(client: TmdbClient, tmdb_server: FakeTmdb) -> None:
    tmdb_server.answer({"title": "Mystery"})

    with pytest.raises(TmdbError):
        await client.details(5)
