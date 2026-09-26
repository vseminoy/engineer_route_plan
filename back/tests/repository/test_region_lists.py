from collections.abc import AsyncIterator
from datetime import datetime, time
from typing import Any

import pytest
from psycopg import AsyncConnection

from src.domain import (
    EngineerDraft,
    Point,
    RegionDraft,
    Skill,
    TicketDraft,
    TicketStatus,
    VehicleType,
)
from src.errors import DependencyUnavailable
from src.repository.region_data import replace_region_data
from src.repository.region_lists import get_region_id, list_engineers, list_tickets
from tests.conftest import RW_PASSWORD, Database
from tests.log_records import events, json_logs

pytestmark = pytest.mark.integration

OFFICE = Point(lat=55.7003202, lon=37.74794)
TICKET_POINT = Point(lat=55.71, lon=37.75)


def _region(code: str) -> RegionDraft:
    return RegionDraft(code=code, name=code, office_address="офис", office=OFFICE)


def _engineer(n: int, start: Point = OFFICE) -> EngineerDraft:
    return EngineerDraft(
        name=f"Бригада {n}",
        start=start,
        shift_start=time(10, 0),
        shift_end=time(23, 30),
        vehicle_type=VehicleType.BIKE,
        skills=(Skill.CONNECTION, Skill.EMERGENCY),
    )


def _ticket(external_id: str, location: Point = TICKET_POINT) -> TicketDraft:
    return TicketDraft(
        external_id=external_id,
        type_bk=None,
        type_hd="Авария",
        required_skill=Skill.EMERGENCY,
        priority=1,
        district=None,
        address="Город Москва, ул.Тестовая, д. 1",
        location=location,
        window_start=datetime(2026, 8, 17, 10, 0),
        window_end=datetime(2026, 8, 17, 12, 0),
        duration_min=80,
        status=TicketStatus.SENT,
        received_at=datetime(2026, 8, 17, 0, 0),
    )


@pytest.fixture
async def conn(migrated_db: Database) -> AsyncIterator[AsyncConnection[Any]]:
    """`app_rw` on a database emptied of data before the test."""
    with migrated_db.connect() as owner:
        owner.execute(
            "TRUNCATE replan_events, assignments, plans, tickets, engineers, regions"
            " RESTART IDENTITY"
        )
        owner.commit()
    async with await AsyncConnection.connect(
        host=migrated_db.host,
        port=migrated_db.port,
        dbname=migrated_db.dbname,
        user="app_rw",
        password=RW_PASSWORD,
    ) as c:
        yield c


async def test_get_region_id(conn: AsyncConnection[Any]) -> None:
    written = await replace_region_data(conn, _region("east"), [_engineer(1)], [_ticket("1")])
    await conn.commit()
    assert await get_region_id(conn, "east") == written.region_id
    assert await get_region_id(conn, "south_east") is None


async def test_list_engineers_of_region(conn: AsyncConnection[Any]) -> None:
    start = Point(lat=55.4363, lon=37.7662)
    east = await replace_region_data(
        conn, _region("east"), [_engineer(1, start), _engineer(2)], [_ticket("1")]
    )
    await replace_region_data(conn, _region("south_east"), [_engineer(9)], [_ticket("2")])
    await conn.commit()
    engineers = await list_engineers(conn, east.region_id)
    assert [e.name for e in engineers] == ["Бригада 1", "Бригада 2"]
    assert engineers[0].id < engineers[1].id
    first = engineers[0]
    assert first.start == start
    assert first.skills == (Skill.CONNECTION, Skill.EMERGENCY)
    assert first.vehicle_type is VehicleType.BIKE
    assert (first.shift_start, first.shift_end) == (time(10, 0), time(23, 30))


async def test_list_tickets_of_region(conn: AsyncConnection[Any]) -> None:
    location = Point(lat=55.6, lon=37.9)
    east = await replace_region_data(
        conn,
        _region("east"),
        [_engineer(1)],
        [_ticket("1", location), _ticket("2"), _ticket("3")],
    )
    await replace_region_data(conn, _region("south_east"), [_engineer(1)], [_ticket("9")])
    await conn.commit()
    tickets = await list_tickets(conn, east.region_id)
    assert [t.external_id for t in tickets] == ["1", "2", "3"]
    assert [t.id for t in tickets] == sorted(t.id for t in tickets)
    first = tickets[0]
    assert first.location == location
    assert first.window_start == datetime(2026, 8, 17, 10, 0)
    assert first.window_start.tzinfo is None
    assert first.received_at == datetime(2026, 8, 17, 0, 0)
    assert (first.type_bk, first.district, first.required_vehicle) == (None, None, None)
    assert first.type_hd == "Авария"


async def test_lists_of_region_without_rows(conn: AsyncConnection[Any]) -> None:
    assert await list_engineers(conn, 12345) == []
    assert await list_tickets(conn, 12345) == []


async def test_lists_db_unavailable(
    conn: AsyncConnection[Any], capsys: pytest.CaptureFixture[str]
) -> None:
    json_logs()
    await conn.close()
    with pytest.raises(DependencyUnavailable) as e:
        await list_engineers(conn, 1)
    assert e.value.reason == "db_unavailable"
    failed = events(capsys, "db_query_failed")
    assert failed[-1]["query"] == "list_engineers_by_region"
