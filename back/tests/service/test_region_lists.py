from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, time
from pathlib import Path
from typing import Any

import pytest
from psycopg_pool import PoolTimeout

from src.domain import (
    Engineer,
    EngineerSetKind,
    EngineerSetWithRegion,
    Point,
    Skill,
    Ticket,
    TicketStatus,
    VehicleType,
)
from src.errors import DatabaseFailure, DependencyUnavailable, InvalidInput
from src.service.region_lists import RegionLists
from src.service.regions import Regions
from tests.log_records import events, json_logs

REGIONS = Regions.from_file(Path(__file__).resolve().parents[2] / "data" / "regions.toml")
POINT = Point(lat=55.72, lon=37.74)
DEFAULT_SET_ID = 70

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
    def __init__(
        self,
        region_id: int | None = 7,
        error: Exception | None = None,
        default_set_id: int | None = DEFAULT_SET_ID,
        engineer_set_region: dict[int, int] | None = None,
    ) -> None:
        self.region_id = region_id
        self.error = error
        self.default_set_id = default_set_id
        # engineer_set_id -> region_id it belongs to; DEFAULT_SET_ID -> region_id by default.
        self.engineer_set_region: dict[int, int] = engineer_set_region or (
            {DEFAULT_SET_ID: region_id} if region_id is not None else {}
        )
        self.calls: list[tuple[str, object]] = []

    async def get_region_id(self, _conn: Any, code: str) -> int | None:
        self.calls.append(("get_region_id", code))
        if self.error:
            raise self.error
        return self.region_id

    async def get_default_engineer_set_id(self, _conn: Any, region_id: int) -> int | None:
        self.calls.append(("get_default_engineer_set_id", region_id))
        return self.default_set_id

    async def get_engineer_set(
        self, _conn: Any, engineer_set_id: int
    ) -> EngineerSetWithRegion | None:
        self.calls.append(("get_engineer_set", engineer_set_id))
        region_id = self.engineer_set_region.get(engineer_set_id)
        if region_id is None:
            return None
        return EngineerSetWithRegion(
            id=engineer_set_id,
            region_id=region_id,
            name="default" if engineer_set_id == DEFAULT_SET_ID else "Вариант Б",
            kind=EngineerSetKind.DEMO
            if engineer_set_id == DEFAULT_SET_ID
            else EngineerSetKind.GENERATED,
            engineers=13,
            morning_share=0.25,
            evening_share=0.25,
            seed="east",
        )

    async def list_engineers(self, _conn: Any, engineer_set_id: int) -> list[Engineer]:
        self.calls.append(("list_engineers", engineer_set_id))
        return ENGINEERS

    async def list_tickets(self, _conn: Any, region_id: int) -> list[Ticket]:
        self.calls.append(("list_tickets", region_id))
        return TICKETS


def _lists(repo: FakeRepository, connect: FakeConnect | None = None) -> RegionLists:
    return RegionLists(
        REGIONS,
        connect or FakeConnect(),
        repo.get_region_id,
        repo.get_default_engineer_set_id,
        repo.get_engineer_set,
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


async def test_engineers_of_default_set() -> None:
    repo = FakeRepository()
    assert await _lists(repo).engineers("east", None) == ENGINEERS
    assert repo.calls == [
        ("get_region_id", "east"),
        ("get_default_engineer_set_id", 7),
        ("list_engineers", DEFAULT_SET_ID),
    ]


async def test_engineers_of_given_set() -> None:
    repo = FakeRepository(engineer_set_region={9: 7})
    assert await _lists(repo).engineers("east", 9) == ENGINEERS
    assert repo.calls == [
        ("get_region_id", "east"),
        ("get_engineer_set", 9),
        ("list_engineers", 9),
    ]
    assert ("get_default_engineer_set_id", 7) not in repo.calls


async def test_engineers_set_not_in_region() -> None:
    repo = FakeRepository(region_id=7, engineer_set_region={9: 8})
    with pytest.raises(InvalidInput) as e:
        await _lists(repo).engineers("east", 9)
    assert e.value.fields == [("engineer_set_id", "Набор не принадлежит региону")]


async def test_engineers_set_not_found() -> None:
    repo = FakeRepository(region_id=7, engineer_set_region={})
    with pytest.raises(InvalidInput) as e:
        await _lists(repo).engineers("east", 9)
    assert e.value.fields == [("engineer_set_id", "Набор не принадлежит региону")]


async def test_tickets_of_loaded_region() -> None:
    repo = FakeRepository()
    assert await _lists(repo).tickets("east") == TICKETS
    assert repo.calls == [("get_region_id", "east"), ("list_tickets", 7)]


async def test_region_not_loaded_is_empty() -> None:
    repo = FakeRepository(region_id=None)
    lists = _lists(repo)
    assert await lists.engineers("south_east", None) == []
    assert await lists.tickets("south_east") == []
    assert [name for name, _ in repo.calls] == ["get_region_id", "get_region_id"]


async def test_unknown_region() -> None:
    connect = FakeConnect()
    with pytest.raises(InvalidInput) as e:
        await _lists(FakeRepository(), connect).engineers("north", None)
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
        await _lists(repo, FakeConnect(PoolTimeout("no connection"))).engineers("east", None)
    assert e.value.reason == "db_unavailable"
    assert repo.calls == []
    (record,) = events(capsys, "db_query_failed")
    assert record["query"] == "list_engineers"
