import sys
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from scripts import build_geocache
from scripts.build_geocache import build, read_cache
from src.clients.nominatim import NominatimClient
from src.service.geocoding import nominatim_queries

HEADER = "Заявка;Тип заявки BK;Тип заявки HD;Начало;Окончание;Район;Адрес"
TOWNS = ["Домодедово"]
FOUND = [{"lat": "55.7000000", "lon": "37.7000000"}]


def _sources(tmp_path: Path, rows: list[tuple[str, str]]) -> Path:
    directory = tmp_path / "sources"
    directory.mkdir()
    lines = [
        f"{i};Подключение;Заявка на подключение;17.08.2026 10:00;17.08.2026 12:00;{d};{a}"
        for i, (d, a) in enumerate(rows, start=1)
    ]
    (directory / "region.csv").write_bytes("\n".join([HEADER, *lines]).encode("cp1251"))
    return directory


def _client(handler: Callable[[str], httpx.Response]) -> tuple[NominatimClient, list[str]]:
    queries: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        query = request.url.params["q"]
        queries.append(query)
        return handler(query)

    async def no_sleep(_: float) -> None:
        return None

    http = httpx.AsyncClient(
        base_url="https://nominatim.test", transport=httpx.MockTransport(respond)
    )
    return NominatimClient(http, sleep=no_sleep), queries


A1 = "Город Москва, ул.Первая, д. 1"
A2 = "Город Москва, ул.Вторая, д. 2"


async def test_remote_town_not_stored(tmp_path: Path) -> None:
    town = "Домодедово, ул.Корнеева, д. 40, кв. 186"
    cache = tmp_path / "geocache.csv"
    cache.write_text(f"{town};55.4;37.9\n", encoding="utf-8")
    client, queries = _client(lambda _: httpx.Response(200, json=FOUND))
    await build([_sources(tmp_path, [("Домодедово", town), ("Выхино", A1)])], cache, client, TOWNS)
    assert all("Корнеева" not in q for q in queries)
    assert [address for address, _, _ in read_cache(cache).values()] == [A1]


async def test_next_variant_on_not_found(tmp_path: Path) -> None:
    second = nominatim_queries(A1)[1]
    client, queries = _client(lambda q: httpx.Response(200, json=FOUND if q == second else []))
    cache = tmp_path / "geocache.csv"
    assert await build([_sources(tmp_path, [("Выхино", A1)])], cache, client, TOWNS) == []
    assert queries == nominatim_queries(A1)[:2]
    assert list(read_cache(cache).values()) == [(A1, "55.7000000", "37.7000000")]


async def test_refused_stops_requests(tmp_path: Path) -> None:
    client, queries = _client(lambda _: httpx.Response(429))
    cache = tmp_path / "geocache.csv"
    not_found = await build(
        [_sources(tmp_path, [("Выхино", A1), ("Выхино", A2)])], cache, client, TOWNS
    )
    assert len(queries) == 1
    assert sorted(not_found) == [A2, A1]


async def test_existing_entries_not_requested(tmp_path: Path) -> None:
    cache = tmp_path / "geocache.csv"
    cache.write_text(f"{A1};55.1;37.1\n", encoding="utf-8")
    client, queries = _client(lambda _: httpx.Response(200, json=FOUND))
    await build([_sources(tmp_path, [("Выхино", A1), ("Выхино", A2)])], cache, client, TOWNS)
    assert queries == [nominatim_queries(A2)[0]]
    entries = read_cache(cache)
    assert entries[" ".join(A1.split()).casefold()] == (A1, "55.1", "37.1")


def test_not_found_listed_and_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def respond(query: str) -> httpx.Response:
        return httpx.Response(503) if "Вторая" in query else httpx.Response(200, json=[])

    client, _ = _client(respond)
    cache = tmp_path / "geocache.csv"
    sources = _sources(tmp_path, [("Выхино", A1), ("Выхино", A2)])
    monkeypatch.setattr(build_geocache, "NominatimClient", lambda _http: client)
    monkeypatch.setattr(
        sys, "argv", ["build_geocache", "--sources", str(sources), "--cache", str(cache)]
    )
    with pytest.raises(SystemExit) as e:
        build_geocache.main()
    assert e.value.code == 1
    out = capsys.readouterr().out
    assert A1 in out and A2 in out
    assert read_cache(cache) == {}


def test_all_found_exit_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _client(lambda _: httpx.Response(200, json=FOUND))
    cache = tmp_path / "geocache.csv"
    sources = _sources(tmp_path, [("Выхино", A1)])
    monkeypatch.setattr(build_geocache, "NominatimClient", lambda _http: client)
    monkeypatch.setattr(
        sys, "argv", ["build_geocache", "--sources", str(sources), "--cache", str(cache)]
    )
    with pytest.raises(SystemExit) as e:
        build_geocache.main()
    assert e.value.code == 0
    assert len(read_cache(cache)) == 1
