from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from src.domain import (
    EngineerDraft,
    EngineerSet,
    EngineerSetKind,
    EngineerSetWithRegion,
    Point,
    Skill,
    Ticket,
    TicketStatus,
)
from src.errors import Conflict, DatabaseFailure, DependencyUnavailable, InvalidInput, NotFound
from src.service.engineer_sets import EngineerSets
from src.service.regions import Regions
from tests.log_records import events, json_logs

REGIONS = Regions.from_file(Path(__file__).resolve().parents[2] / "data" / "regions.toml")
OFFICE = Point(lat=55.72, lon=37.74)

SET_A = EngineerSet(
    id=70,
    name="default",
    kind=EngineerSetKind.DEMO,
    engineers=13,
    morning_share=0.25,
    evening_share=0.25,
    seed="east",
)
SET_B = EngineerSet(
    id=71,
    name="Вариант Б",
    kind=EngineerSetKind.GENERATED,
    engineers=15,
    morning_share=0.2,
    evening_share=0.2,
    seed="42",
)


class FakeConnect:
    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[Any]:
        yield object()


class FakeRepo:
    def __init__(
        self,
        region_id: int | None = 7,
        office: Point = OFFICE,
        tickets: list[Ticket] | None = None,
        sets: list[EngineerSet] | None = None,
        set_id: int = 71,
        insert_error: Exception | None = None,
        existing_set: EngineerSetWithRegion | None = None,
    ) -> None:
        self.region_id = region_id
        self.office = office
        self.tickets = tickets or []
        self.sets = sets if sets is not None else [SET_A]
        self.set_id = set_id
        self.insert_error = insert_error
        self.existing_set = existing_set
        self.inserted: list[tuple[int, str, int, float, float, str, int]] = []
        self.deleted: list[int] = []
        self.calls: list[str] = []

    async def get_region_id(self, _conn: Any, code: str) -> int | None:
        self.calls.append("get_region_id")
        return self.region_id

    async def get_region_office(self, _conn: Any, region_id: int) -> Point:
        self.calls.append("get_region_office")
        return self.office

    async def list_tickets(self, _conn: Any, region_id: int) -> list[Ticket]:
        self.calls.append("list_tickets")
        return self.tickets

    async def list_engineer_sets(self, _conn: Any, region_id: int) -> list[EngineerSet]:
        self.calls.append("list_engineer_sets")
        return self.sets

    async def insert_generated_engineer_set(
        self,
        _conn: Any,
        region_id: int,
        name: str,
        engineers: int,
        morning_share: float,
        evening_share: float,
        seed: str,
        drafts: list[EngineerDraft],
    ) -> int:
        self.calls.append("insert_generated_engineer_set")
        if self.insert_error:
            raise self.insert_error
        self.inserted.append(
            (region_id, name, engineers, morning_share, evening_share, seed, len(drafts))
        )
        return self.set_id

    async def get_engineer_set(
        self, _conn: Any, engineer_set_id: int
    ) -> EngineerSetWithRegion | None:
        self.calls.append("get_engineer_set")
        return self.existing_set

    async def delete_engineer_set(self, _conn: Any, engineer_set_id: int) -> None:
        self.calls.append("delete_engineer_set")
        self.deleted.append(engineer_set_id)


def _service(repo: FakeRepo) -> EngineerSets:
    return EngineerSets(
        REGIONS,
        FakeConnect(),
        repo.get_region_id,
        repo.get_region_office,
        repo.list_tickets,
        repo.list_engineer_sets,
        repo.insert_generated_engineer_set,
        repo.get_engineer_set,
        repo.delete_engineer_set,
    )


def _ticket(district: str | None) -> Ticket:
    return Ticket(
        id=1,
        external_id="1",
        type_bk=None,
        type_hd="Авария",
        required_skill=Skill.EMERGENCY,
        required_vehicle=None,
        priority=1,
        district=district,
        address="Город Москва, ул.Тестовая, д. 1",
        location=Point(lat=55.71, lon=37.75),
        window_start=datetime(2026, 8, 17, 10, 0),
        window_end=datetime(2026, 8, 17, 12, 0),
        duration_min=80,
        status=TicketStatus.SENT,
        received_at=datetime(2026, 8, 17, 0, 0),
    )


async def test_list_sets_of_region() -> None:
    repo = FakeRepo(sets=[SET_A, SET_B])
    result = await _service(repo).list("east")
    assert result == [SET_A, SET_B]


async def test_list_sets_unknown_region() -> None:
    with pytest.raises(InvalidInput) as e:
        await _service(FakeRepo()).list("north")
    assert e.value.reason == "unknown_region"


async def test_create_generated_set(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    repo = FakeRepo(tickets=[_ticket(None)])

    created = await _service(repo).create("east", "Вариант Б", 15, 0.2, 0.2, "42")

    assert created.kind is EngineerSetKind.GENERATED
    assert created.id == 71
    assert created.name == "Вариант Б"
    assert created.engineers == 15
    assert created.morning_share == 0.2
    assert created.evening_share == 0.2
    assert created.seed == "42"
    region_id, name, engineers, morning_share, evening_share, seed, drafts_count = repo.inserted[0]
    assert (region_id, name, engineers, morning_share, evening_share, seed) == (
        7,
        "Вариант Б",
        15,
        0.2,
        0.2,
        "42",
    )
    assert drafts_count == 15
    (record,) = events(capsys, "engineer_set_created")
    assert record["region"] == "east"
    assert record["engineer_set_id"] == 71
    assert record["engineers"] == 15


async def test_create_unknown_region() -> None:
    with pytest.raises(InvalidInput) as e:
        await _service(FakeRepo()).create("north", "Вариант Б", 15, 0.2, 0.2, "42")
    assert e.value.reason == "unknown_region"


async def test_create_region_not_loaded() -> None:
    repo = FakeRepo(region_id=None)
    with pytest.raises(InvalidInput) as e:
        await _service(repo).create("east", "Вариант Б", 15, 0.2, 0.2, "42")
    assert e.value.reason == "region_not_loaded"
    assert repo.inserted == []


async def test_create_insufficient_full_day_engineers() -> None:
    repo = FakeRepo()
    with pytest.raises(InvalidInput) as e:
        await _service(repo).create("east", "Вариант Б", 5, 0.25, 0.25, "42")
    assert e.value.reason == "insufficient_full_day_engineers"
    assert repo.inserted == []
    assert "get_region_id" not in repo.calls


async def test_create_name_conflict(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    error = Conflict("name_taken", params={"region_id": 7, "name": "default"})
    repo = FakeRepo(insert_error=error)

    with pytest.raises(Conflict) as e:
        await _service(repo).create("east", "default", 15, 0.2, 0.2, "42")
    assert e.value is error


@pytest.mark.parametrize(
    "error",
    [DependencyUnavailable(reason="db_unavailable"), DatabaseFailure(reason="db_query_failed")],
)
async def test_create_dependency_failure(error: Exception) -> None:
    repo = FakeRepo(insert_error=error)
    with pytest.raises(type(error)) as e:
        await _service(repo).create("east", "Вариант Б", 15, 0.2, 0.2, "42")
    assert e.value is error


async def test_delete_generated_set(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    existing = EngineerSetWithRegion(
        id=71,
        region_id=7,
        name="Вариант Б",
        kind=EngineerSetKind.GENERATED,
        engineers=15,
        morning_share=0.2,
        evening_share=0.2,
        seed="42",
    )
    repo = FakeRepo(existing_set=existing)

    await _service(repo).delete(71)

    assert repo.deleted == [71]
    (record,) = events(capsys, "engineer_set_deleted")
    assert record["engineer_set_id"] == 71


async def test_delete_demo_set_conflict() -> None:
    existing = EngineerSetWithRegion(
        id=70,
        region_id=7,
        name="default",
        kind=EngineerSetKind.DEMO,
        engineers=13,
        morning_share=0.25,
        evening_share=0.25,
        seed="east",
    )
    repo = FakeRepo(existing_set=existing)

    with pytest.raises(Conflict) as e:
        await _service(repo).delete(70)
    assert e.value.reason == "demo_set"
    assert repo.deleted == []


async def test_delete_not_found() -> None:
    repo = FakeRepo(existing_set=None)
    with pytest.raises(NotFound) as e:
        await _service(repo).delete(999)
    assert e.value.reason == "engineer_set_not_found"


@pytest.mark.parametrize(
    "error",
    [DependencyUnavailable(reason="db_unavailable"), DatabaseFailure(reason="db_query_failed")],
)
async def test_delete_dependency_failure(error: Exception) -> None:
    class FailingRepo(FakeRepo):
        async def get_engineer_set(
            self, _conn: Any, engineer_set_id: int
        ) -> EngineerSetWithRegion | None:
            raise error

    repo = FailingRepo()
    with pytest.raises(type(error)) as e:
        await _service(repo).delete(71)
    assert e.value is error
