import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from psycopg_pool import PoolTimeout

from src.domain import EngineerDraft, Point, RegionDraft, RegionWritten, TicketDraft
from src.errors import DatabaseFailure, DependencyUnavailable, InvalidInput
from src.service.geocoding import GeoCache, Geocoder
from src.service.loader import Loader
from src.service.regions import Regions
from src.service.ticket_file import InvalidRow
from src.service.ticket_types import TicketTypes
from tests.log_records import events, json_logs, records

BACK_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACK_DIR / "data"
REGIONS = Regions.from_file(DATA_DIR / "regions.toml")
TYPES = TicketTypes.from_file(DATA_DIR / "ticket_types.toml")

HEADER = "Заявка;Тип заявки BK;Тип заявки HD;Начало;Окончание;Район;Адрес"
OFFICE = "г. Москва, ул Юных Ленинцев, д 83с 4"
ADDRESSES = [f"Город Москва, ул.Тестовая, д. {i}" for i in range(1, 4)]
CACHE = {OFFICE: Point(lat=55.70, lon=37.74)} | {
    a: Point(lat=55.71 + i / 100, lon=37.75) for i, a in enumerate(ADDRESSES)
}


def _ticket(n: int, address: str, start: str = "17.08.2026 10:00") -> str:
    return f"{n};Подключение;Заявка на подключение;{start};17.08.2026 12:00;Выхино;{address}"


FILE_ROWS = [
    _ticket(1, ADDRESSES[0]),
    _ticket(2, ADDRESSES[1]),
    "",
    _ticket(3, ADDRESSES[2], start="не дата"),
    ";;;;;;",
    _ticket(4, ADDRESSES[2]),
    f"Адрес Офиса;{OFFICE};;;;;",
]
CSV = ("\n".join([HEADER, *FILE_ROWS]) + "\n").encode("cp1251")


class FakeRepository:
    def __init__(self, error: Exception | None = None, engineers_kept: bool = False) -> None:
        self.error = error
        self.engineers_kept = engineers_kept
        self.calls: list[tuple[RegionDraft, list[EngineerDraft], list[TicketDraft]]] = []

    async def __call__(
        self,
        _conn: Any,
        region: RegionDraft,
        engineers: list[EngineerDraft],
        tickets: list[TicketDraft],
    ) -> RegionWritten:
        if self.error:
            raise self.error
        self.calls.append((region, engineers, tickets))
        return RegionWritten(region_id=1, engineers_kept=self.engineers_kept)


class FakeConnect:
    """Stands in for the pool's `connection`: counts the connections taken, or fails to
    give one with `error`."""

    def __init__(self, error: Exception | None = None) -> None:
        self.taken = 0
        self.error = error

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[Any]:
        if self.error:
            raise self.error
        self.taken += 1
        yield object()


class FakeNominatim:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.queries: list[str] = []

    async def search(self, query: str) -> Point | None:
        self.queries.append(query)
        if self.fail:
            raise DependencyUnavailable(reason="geocoder_unavailable")
        return None


def _loader(
    repo: FakeRepository,
    cache: dict[str, Point] | None = None,
    client: FakeNominatim | None = None,
    connect: FakeConnect | None = None,
) -> Loader:
    geocoder = Geocoder(
        GeoCache(CACHE if cache is None else cache),
        client,
        REGIONS.remote_towns,
        max_lookups=50,
    )
    return Loader(REGIONS, TYPES, geocoder, connect or FakeConnect(), repo)


async def test_load_csv(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    repo = FakeRepository(engineers_kept=True)
    result = await _loader(repo).load("east", "csv", CSV)
    ((region, engineers, tickets),) = repo.calls
    assert region.code == "east"
    assert region.office_address == OFFICE
    assert region.office == CACHE[OFFICE]
    assert len(engineers) == 13
    assert [t.external_id for t in tickets] == ["1", "2", "4"]
    assert (result.rows_total, result.rows_skipped) == (7, 3)
    assert result.rows_invalid == [InvalidRow(5, "bad_datetime", "Начало")]
    (record,) = events(capsys, "data_load_finished")
    assert {
        k: record[k]
        for k in (
            "source",
            "region",
            "rows_total",
            "rows_skipped",
            "rows_invalid",
            "engineers",
            "engineers_kept",
            "tickets",
        )
    } == {
        "source": "csv",
        "region": "east",
        "rows_total": 7,
        "rows_skipped": 3,
        "rows_invalid": 1,
        "engineers": 13,
        "engineers_kept": True,
        "tickets": 3,
    }
    assert record["invalid_by_reason"] == {"bad_datetime": 1}
    assert isinstance(record["duration_ms"], int) and record["duration_ms"] >= 0
    assert isinstance(record["wait_ms"], int) and 0 <= record["wait_ms"] <= record["duration_ms"]


async def test_load_json() -> None:
    columns = HEADER.split(";")
    items = [dict(zip(columns, row.split(";"), strict=False)) for row in FILE_ROWS]
    items[2] = dict.fromkeys(columns, "")
    repo = FakeRepository()
    result = await _loader(repo).load(
        "east", "json", json.dumps(items, ensure_ascii=False).encode()
    )
    assert [t.external_id for t in repo.calls[0][2]] == ["1", "2", "4"]
    assert (result.rows_total, result.rows_skipped, len(result.rows_invalid)) == (7, 3, 1)


async def test_load_demo(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    repo = FakeRepository()
    loader = Loader(
        REGIONS,
        TYPES,
        Geocoder(
            GeoCache.from_file(DATA_DIR / "geocache.csv"),
            None,
            REGIONS.remote_towns,
            max_lookups=50,
        ),
        FakeConnect(),
        repo,
    )
    result = await loader.load("south_east", "demo")
    assert (result.tickets, result.rows_invalid) == (83, [])
    assert events(capsys, "data_load_finished")[0]["source"] == "demo"


@pytest.mark.parametrize("code", sorted(REGIONS.regions))
async def test_load_demo_offline(code: str) -> None:
    client = FakeNominatim()
    geocoder = Geocoder(
        GeoCache.from_file(DATA_DIR / "geocache.csv"),
        client,
        REGIONS.remote_towns,
        max_lookups=50,
    )
    result = await Loader(REGIONS, TYPES, geocoder, FakeConnect(), FakeRepository()).load(
        code, "demo"
    )
    assert result.rows_invalid == []
    assert result.tickets == {"east": 66, "south_east": 83, "south_center": 56}[code]
    assert client.queries == []


async def test_office_without_sentinel_is_region_center() -> None:
    repo = FakeRepository()
    data = f"{HEADER}\n{_ticket(1, ADDRESSES[0])}\n".encode()
    await _loader(repo).load("east", "csv", data)
    region = repo.calls[0][0]
    assert region.office == REGIONS.regions["east"].center
    assert region.office_address == "Восток"


async def test_office_not_geocoded_is_region_center() -> None:
    repo = FakeRepository()
    cache = {a: p for a, p in CACHE.items() if a != OFFICE}
    await _loader(repo, cache).load("east", "csv", CSV)
    assert repo.calls[0][0].office == REGIONS.regions["east"].center


async def test_ticket_without_point_is_invalid(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    repo = FakeRepository()
    cache = {a: p for a, p in CACHE.items() if a != ADDRESSES[1]}
    result = await _loader(repo, cache, FakeNominatim()).load("east", "csv", CSV)
    assert [t.external_id for t in repo.calls[0][2]] == ["1", "4"]
    assert InvalidRow(3, "address_not_found", "Адрес") in result.rows_invalid
    (record,) = events(capsys, "data_load_finished")
    assert record["invalid_by_reason"] == {"bad_datetime": 1, "address_not_found": 1}


@pytest.mark.parametrize(
    "data",
    [
        f"{HEADER}\n{_ticket(1, ADDRESSES[0], start='x')}\n".encode(),
        f"{HEADER}\nАдрес офиса;{OFFICE};;;;;\n".encode(),
    ],
)
async def test_no_valid_tickets(capsys: pytest.CaptureFixture[str], data: bytes) -> None:
    json_logs()
    repo = FakeRepository()
    with pytest.raises(InvalidInput) as e:
        await _loader(repo).load("east", "csv", data)
    assert e.value.reason == "no_valid_tickets"
    assert e.value.message
    assert repo.calls == []
    (record,) = events(capsys, "data_load_failed")
    assert record["reason"] == "no_valid_tickets"
    assert isinstance(record["duration_ms"], int)
    assert record["rows_total"] == 1


async def test_encoding_error_logged(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    repo = FakeRepository()
    with pytest.raises(InvalidInput) as e:
        await _loader(repo).load("east", "json", CSV)
    assert e.value.reason == "file_encoding_invalid"
    assert repo.calls == []
    (record,) = events(capsys, "data_load_failed")
    assert (record["reason"], record["source"], record["region"]) == (
        "file_encoding_invalid",
        "json",
        "east",
    )


async def test_geocoder_unavailable(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    repo = FakeRepository()
    with pytest.raises(DependencyUnavailable) as e:
        await _loader(repo, {}, FakeNominatim(fail=True)).load("east", "csv", CSV)
    assert e.value.reason == "geocoder_unavailable"
    assert repo.calls == []
    assert events(capsys, "data_load_failed")[0]["reason"] == "geocoder_unavailable"


@pytest.mark.parametrize(
    "error",
    [DependencyUnavailable(reason="db_unavailable"), DatabaseFailure(reason="db_query_failed")],
)
async def test_repository_failure(capsys: pytest.CaptureFixture[str], error: Exception) -> None:
    json_logs()
    with pytest.raises(type(error)) as e:
        await _loader(FakeRepository(error)).load("east", "csv", CSV)
    assert e.value is error
    assert events(capsys, "data_load_failed")[0]["reason"] == error.reason  # type: ignore[attr-defined]  # AppError


async def test_logs_no_addresses(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    cache = {a: p for a, p in CACHE.items() if a != ADDRESSES[1]}
    await _loader(FakeRepository(), cache, FakeNominatim()).load("east", "csv", CSV)
    logged = str(records(capsys))
    assert "Тестовая" not in logged
    assert "Юных Ленинцев" not in logged


async def test_connection_taken_only_to_write() -> None:
    connect = FakeConnect()
    await _loader(FakeRepository(), connect=connect).load("east", "csv", CSV)
    assert connect.taken == 1
    connect = FakeConnect()
    with pytest.raises(DependencyUnavailable):
        await _loader(FakeRepository(), {}, FakeNominatim(fail=True), connect).load(
            "east", "csv", CSV
        )
    assert connect.taken == 0


async def test_client_error_logged_as_warning(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    with pytest.raises(InvalidInput):
        await _loader(FakeRepository()).load("east", "json", CSV)
    with pytest.raises(DatabaseFailure):
        await _loader(FakeRepository(DatabaseFailure(reason="db_query_failed"))).load(
            "east", "csv", CSV
        )
    levels = [r["level"] for r in events(capsys, "data_load_failed")]
    assert levels == ["warning", "error"]


async def test_unknown_region_logged(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    repo = FakeRepository()
    with pytest.raises(InvalidInput) as e:
        await _loader(repo).load("north", "csv", CSV)
    assert e.value.reason == "unknown_region"
    assert repo.calls == []
    (record,) = events(capsys, "data_load_failed")
    assert (record["reason"], record["region"], record["level"]) == (
        "unknown_region",
        "north",
        "warning",
    )


async def test_too_many_rows() -> None:
    rows = "\n".join(_ticket(i, ADDRESSES[0]) for i in range(501))
    repo = FakeRepository()
    with pytest.raises(InvalidInput) as e:
        await _loader(repo).load("east", "csv", f"{HEADER}\n{rows}\n".encode())
    assert e.value.reason == "too_many_rows"
    assert repo.calls == []


async def test_pool_timeout_is_dependency_unavailable(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    repo = FakeRepository()
    connect = FakeConnect(PoolTimeout("no free connection"))
    with pytest.raises(DependencyUnavailable) as e:
        await _loader(repo, connect=connect).load("east", "csv", CSV)
    assert e.value.reason == "db_unavailable"
    assert repo.calls == []
    logged = records(capsys)
    (db,) = [r for r in logged if r["event"] == "db_query_failed"]
    assert db["query"] == "replace_region_data"
    (failed,) = [r for r in logged if r["event"] == "data_load_failed"]
    assert (failed["reason"], failed["level"]) == ("db_unavailable", "error")


async def test_unknown_region_code_bounded_in_log(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    with pytest.raises(InvalidInput):
        await _loader(FakeRepository()).load("X" * 5000 + "\nFAKE", "csv", CSV)
    (record,) = events(capsys, "data_load_failed")
    assert len(record["region"]) == 50


class CountingLoader(Loader):
    """Records how many file reads run at once; each read takes a while in its thread."""

    reading = 0
    most_at_once = 0

    def _parse(self, *args: Any) -> Any:
        CountingLoader.reading += 1
        CountingLoader.most_at_once = max(CountingLoader.most_at_once, CountingLoader.reading)
        time.sleep(0.02)
        CountingLoader.reading -= 1
        return super()._parse(*args)


async def test_files_read_one_at_a_time() -> None:
    CountingLoader.reading = CountingLoader.most_at_once = 0
    repo = FakeRepository()
    base = _loader(repo)
    loader = CountingLoader(base.regions, base.types, base.geocoder, base.connect, repo)
    await asyncio.gather(*(loader.load("east", "csv", CSV) for _ in range(3)))
    assert len(repo.calls) == 3
    assert CountingLoader.most_at_once == 1


class SlowRepository(FakeRepository):
    """Records how many writes run at once; each write yields to the event loop."""

    def __init__(self) -> None:
        super().__init__()
        self.running = 0
        self.most_at_once = 0

    async def __call__(
        self,
        conn: Any,
        region: RegionDraft,
        engineers: list[EngineerDraft],
        tickets: list[TicketDraft],
    ) -> RegionWritten:
        self.running += 1
        self.most_at_once = max(self.most_at_once, self.running)
        await asyncio.sleep(0.02)
        self.running -= 1
        return await super().__call__(conn, region, engineers, tickets)


async def test_writes_one_at_a_time(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    repo = SlowRepository()
    loader = _loader(repo)
    await asyncio.gather(*(loader.load("east", "csv", CSV) for _ in range(3)))
    assert len(repo.calls) == 3
    assert repo.most_at_once == 1
    # Each write takes at least 20 ms, so the last load in the queue waits for two.
    waits = sorted(r["wait_ms"] for r in events(capsys, "data_load_finished"))
    assert waits[-1] >= 15
