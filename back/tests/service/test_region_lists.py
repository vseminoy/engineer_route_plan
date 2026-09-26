from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, time
from pathlib import Path
from typing import Any

import pytest
from psycopg_pool import PoolTimeout

from src.domain import Engineer, Point, Skill, Ticket, TicketStatus, VehicleType
from src.errors import DatabaseFailure, DependencyUnavailable, InvalidInput
from src.service.region_lists import RegionLists
from src.service.regions import Regions
from tests.log_records import events, json_logs

REGIONS = Regions.from_file(Path(__file__).resolve().parents[2] / "data" / "regions.toml")
POINT = Point(lat=55.72, lon=37.74)

ENGINEERS = [
    Engineer(
        id=n,
        name=f"Бригада {n}",
        start=POINT,
        shift_start=time(10, 0),
        shift_end=time(23, 30),
        vehicle_type=VehicleType.CAR,
        skills=(Skill.CONNECTION,),
    )
    for n in (1, 2)
]
TICKETS = [
    Ticket(
        id=n,
        external_id=str(n),
        type_bk=None,
        type_hd="Авария",
        required_skill=Skill.EMERGENCY,
        required_vehicle=None,
        priority=1,
        district=None,
        address="Город Москва, ул.Тестовая, д. 1",
        location=POINT,
        window_start=datetime(2026, 8, 17, 10, 0),
        window_end=datetime(2026, 8, 17, 12, 0),
        duration_min=80,
        status=TicketStatus.SENT,
        received_at=datetime(2026, 8, 17, 0, 0),
    )
    for n in (1, 2, 3)
]


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


class FakeRepository:
    def __init__(self, region_id: int | None = 7, error: Exception | None = None) -> None:
        self.region_id = region_id
        self.error = error
        self.calls: list[tuple[str, object]] = []

    async def get_region_id(self, _conn: Any, code: str) -> int | None:
        self.calls.append(("get_region_id", code))
        if self.error:
            raise self.error
        return self.region_id

    async def list_engineers(self, _conn: Any, region_id: int) -> list[Engineer]:
        self.calls.append(("list_engineers", region_id))
        return ENGINEERS

    async def list_tickets(self, _conn: Any, region_id: int) -> list[Ticket]:
        self.calls.append(("list_tickets", region_id))
        return TICKETS


def _lists(repo: FakeRepository, connect: FakeConnect | None = None) -> RegionLists:
    return RegionLists(
        REGIONS,
        connect or FakeConnect(),
        repo.get_region_id,
        repo.list_engineers,
        repo.list_tickets,
    )


def test_regions_in_config_order() -> None:
    connect = FakeConnect()
    regions = _lists(FakeRepository(), connect).all_regions()
    assert [(r.code, r.name) for r in regions] == [
        ("east", "Восток"),
        ("south_east", "Юго-Восток"),
        ("south_center", "Югоцентр"),
    ]
    assert connect.taken == 0


async def test_engineers_of_loaded_region() -> None:
    repo = FakeRepository()
    assert await _lists(repo).engineers("east") == ENGINEERS
    assert repo.calls == [("get_region_id", "east"), ("list_engineers", 7)]


async def test_tickets_of_loaded_region() -> None:
    repo = FakeRepository()
    assert await _lists(repo).tickets("east") == TICKETS
    assert repo.calls == [("get_region_id", "east"), ("list_tickets", 7)]


async def test_region_not_loaded_is_empty() -> None:
    repo = FakeRepository(region_id=None)
    lists = _lists(repo)
    assert await lists.engineers("south_east") == []
    assert await lists.tickets("south_east") == []
    assert [name for name, _ in repo.calls] == ["get_region_id", "get_region_id"]


async def test_unknown_region() -> None:
    connect = FakeConnect()
    with pytest.raises(InvalidInput) as e:
        await _lists(FakeRepository(), connect).engineers("north")
    assert e.value.reason == "unknown_region"
    assert e.value.fields == [("region", "Неизвестный регион")]
    assert connect.taken == 0


@pytest.mark.parametrize(
    "error",
    [DependencyUnavailable(reason="db_unavailable"), DatabaseFailure(reason="db_query_failed")],
)
async def test_repository_failure_propagates(error: Exception) -> None:
    with pytest.raises(type(error)) as e:
        await _lists(FakeRepository(error=error)).tickets("east")
    assert e.value is error


async def test_pool_timeout_is_dependency_unavailable(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    repo = FakeRepository()
    with pytest.raises(DependencyUnavailable) as e:
        await _lists(repo, FakeConnect(PoolTimeout("no connection"))).engineers("east")
    assert e.value.reason == "db_unavailable"
    assert repo.calls == []
    (record,) = events(capsys, "db_query_failed")
    assert record["query"] == "list_engineers"
