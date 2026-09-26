import time
from pathlib import Path

import pytest

from src.domain import Point
from src.errors import DependencyUnavailable
from src.service.geocoding import GeoCache, Geocoder, nominatim_queries
from src.service.regions import Regions
from src.service.ticket_file import COL_ADDRESS, COL_DISTRICT, read_rows
from tests.log_records import events, json_logs

BACK_DIR = Path(__file__).resolve().parents[2]
DOCS_DIR = BACK_DIR.parent / "docs"
TOWNS = {"Домодедово": Point(lat=55.4363, lon=37.7662)}
P1, P2, P3 = Point(lat=55.1, lon=37.1), Point(lat=55.2, lon=37.2), Point(lat=55.3, lon=37.3)


class FakeNominatim:
    def __init__(self, answers: dict[str, Point | None] | None = None, fail: bool = False):
        self.answers = answers or {}
        self.fail = fail
        self.queries: list[str] = []

    async def search(self, query: str) -> Point | None:
        self.queries.append(query)
        if self.fail:
            raise DependencyUnavailable(reason="geocoder_unavailable")
        return self.answers.get(query)


def _geocoder(cache: dict[str, Point], client: FakeNominatim | None) -> Geocoder:
    return Geocoder(GeoCache(cache), client, TOWNS, max_lookups=50)


async def test_remote_town_from_config(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    client = FakeNominatim()
    found = await _geocoder({}, client).locate(
        [("Домодедово, ул.Корнеева, д. 40", "Домодедово"), ("МО, г. Домодедово ул. д. 1", None)]
    )
    assert set(found.values()) == {TOWNS["Домодедово"]}
    assert len(found) == 2
    assert client.queries == []
    assert events(capsys, "geocode_cache_miss") == []


def test_query_from_address() -> None:
    cases = {
        "Город Москва, пр-кт.Волгоградский, д. 128 к 5, кв. 12": "Волгоградский проспект 128к5, Москва",
        "г. Москва, ул Юных Ленинцев, д 83с 4": "Юных Ленинцев улица 83с4, Москва",
        "Город Москва, ул.Земляной Вал, д. 24/30 стр. 1": "Земляной Вал улица 24/30с1, Москва",
        "Москва Бирюлевская ул. д. 44": "Бирюлевская улица 44, Москва",
    }
    for address, first in cases.items():
        assert nominatim_queries(address)[0] == first


def test_query_variants() -> None:
    assert nominatim_queries("Город Москва, ул.2-я Синичкина, д. 9 к 1") == [
        "2-я Синичкина улица 9к1, Москва",
        "улица 2-я Синичкина 9к1, Москва",
        "2-я улица Синичкина 9к1, Москва",
        "улица 2-я Синичкина 9, Москва",
    ]


async def test_cache_hit_no_request(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    client = FakeNominatim()
    found = await _geocoder({"А, д. 1": P1}, client).locate([("А, д. 1", None)])
    assert list(found.values()) == [P1]
    assert client.queries == []
    assert events(capsys, "geocode_cache_miss") == []


async def test_cache_key_normalized() -> None:
    found = await _geocoder({"Город Москва, ул.А, д. 1": P1}, None).locate(
        [("город  москва, УЛ.А,  д. 1", None)]
    )
    assert list(found.values()) == [P1]


async def test_miss_goes_to_nominatim(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    cache = {f"ул.К{i}, д. 1": P1 for i in range(3)}
    client = FakeNominatim(
        {nominatim_queries("ул.X, д. 1")[0]: P2, nominatim_queries("ул.Y, д. 2")[0]: P3}
    )
    addresses = [(a, None) for a in cache] + [("ул.X, д. 1", None), ("ул.Y, д. 2", None)]
    found = await _geocoder(cache, client).locate(addresses)
    assert len(found) == 5
    assert len(client.queries) == 2
    (miss,) = events(capsys, "geocode_cache_miss")
    assert miss["misses"] == 2
    assert miss["lookups_skipped"] == 0
    assert "ул.X" not in str(miss)


async def test_miss_not_found() -> None:
    client = FakeNominatim()
    found = await _geocoder({"ул.А, д. 1": P1}, client).locate(
        [("ул.А, д. 1", None), ("ул.Б, д. 2", None)]
    )
    assert list(found.values()) == [P1]
    assert client.queries == nominatim_queries("ул.Б, д. 2")


async def test_repeated_miss_requested_once() -> None:
    query = nominatim_queries("ул.Б, д. 2")[0]
    client = FakeNominatim({query: P2})
    await _geocoder({}, client).locate([("ул.Б, д. 2", None)] * 3)
    assert client.queries == [query]


async def test_nominatim_disabled() -> None:
    found = await _geocoder({"ул.А, д. 1": P1}, None).locate(
        [("ул.А, д. 1", None), ("ул.Б, д. 2", None)]
    )
    assert list(found.values()) == [P1]


async def test_nominatim_unavailable() -> None:
    with pytest.raises(DependencyUnavailable):
        await _geocoder({}, FakeNominatim(fail=True)).locate([("ул.Б, д. 2", None)])


async def test_geocache_covers_every_source_address() -> None:
    regions = Regions.from_file(BACK_DIR / "data" / "regions.toml")
    geocoder = Geocoder(
        GeoCache.from_file(BACK_DIR / "data" / "geocache.csv"),
        None,
        regions.remote_towns,
        max_lookups=50,
    )
    addresses: list[tuple[str, str | None]] = []
    for path in sorted(DOCS_DIR.glob("*/*.csv")):
        split = read_rows(path.read_bytes(), "csv")
        if split.office_address:
            addresses.append((split.office_address, None))
        addresses += [
            (r.values[COL_ADDRESS], r.values.get(COL_DISTRICT) or None) for r in split.rows
        ]
    assert addresses
    found = await geocoder.locate(addresses)
    missing = {a for a, _ in addresses if " ".join(a.split()).casefold() not in found}
    assert missing == set()


def test_apartment_anywhere_dropped() -> None:
    for address in (
        "Город Москва, ул.Подольская, д. 5, кв. 12, подъезд 3",
        "Город Москва, ул.Подольская, д. 5, подъезд 3, кв. 12",
        "Город Москва, ул.Подольская, д. 5, квартира 12 (домофон 12К)",
        "Город Москва, ул.Подольская, д.5кв.12",
    ):
        queries = nominatim_queries(address)
        assert queries[0] == "Подольская улица 5, Москва"
        assert not any("12" in q or "подъезд" in q for q in queries)


def test_query_linear_time() -> None:
    for address in ("ул a" + " " * 100_000 + "b", "ул " + "a " * 50_000, "д1 " * 30_000):
        started = time.perf_counter()
        nominatim_queries(address)
        # A quadratic pass over 100 000 characters takes minutes, a linear one milliseconds.
        assert time.perf_counter() - started < 0.5


async def test_lookups_capped(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    client = FakeNominatim()
    geocoder = Geocoder(GeoCache({}), client, TOWNS, max_lookups=2)
    await geocoder.locate([(f"ул.Новая, д. {i}", None) for i in range(5)])
    requested = {q.removesuffix(", Москва").rsplit(" ", 1)[1] for q in client.queries}
    assert requested == {"0", "1"}
    (miss,) = events(capsys, "geocode_cache_miss")
    assert (miss["misses"], miss["lookups_skipped"]) == (5, 3)


def test_hyphenated_word_is_not_apartment() -> None:
    assert nominatim_queries("Город Москва, Под-ский пр-кт., д. 7")[0].startswith("Под-ский")
    assert "кв-л" in nominatim_queries("Город Москва, б-р.Самаркандский кв-л 137а, д. 5")[0]
