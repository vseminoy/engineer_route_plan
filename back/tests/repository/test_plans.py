from collections.abc import AsyncIterator
from datetime import date, datetime, time
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
from src.errors import DatabaseFailure, DependencyUnavailable
from src.repository.plans import (
    AssignmentWrite,
    get_plan,
    insert_running_plan,
    list_plan_assignments,
    mark_plan_done,
    mark_plan_failed,
)
from src.repository.region_data import replace_region_data
from tests.conftest import RW_PASSWORD, Database
from tests.log_records import events, json_logs

pytestmark = pytest.mark.integration

OFFICE = Point(lat=55.7003202, lon=37.74794)
TICKET_POINT = Point(lat=55.71, lon=37.75)
PLAN_DATE = date(2026, 8, 17)


def _engineer() -> EngineerDraft:
    return EngineerDraft(
        name="Бригада 1",
        start=OFFICE,
        shift_start=time(10, 0),
        shift_end=time(23, 30),
        vehicle_type=VehicleType.CAR,
        skills=(Skill.CONNECTION,),
    )


def _ticket(external_id: str) -> TicketDraft:
    return TicketDraft(
        external_id=external_id,
        type_bk=None,
        type_hd="Заявка на подключение",
        required_skill=Skill.CONNECTION,
        priority=2,
        district=None,
        address="Город Москва, ул.Тестовая, д. 1",
        location=TICKET_POINT,
        window_start=datetime(2026, 8, 17, 10, 0),
        window_end=datetime(2026, 8, 17, 12, 0),
        duration_min=70,
        status=TicketStatus.SENT,
        received_at=datetime(2026, 8, 17, 0, 0),
    )


@pytest.fixture
async def conn(migrated_db: Database) -> AsyncIterator[AsyncConnection[Any]]:
    """`app_rw` on a database emptied of data before the test; region `east` holds one
    brigade (id 1) and two tickets (ids 1 and 2)."""
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
        region = RegionDraft(code="east", name="Восток", office_address="офис", office=OFFICE)
        await replace_region_data(c, region, [_engineer()], [_ticket("1"), _ticket("2")])
        await c.commit()
        yield c


async def _plan_row(conn: AsyncConnection[Any], plan_id: int) -> tuple[Any, ...]:
    cur = await conn.execute("SELECT status, failed_reason FROM plans WHERE id = %s", (plan_id,))
    row = await cur.fetchone()
    assert row is not None
    return tuple(row)


async def test_insert_running_plan(conn: AsyncConnection[Any]) -> None:
    plan_id = await insert_running_plan(conn, 1, PLAN_DATE, "or_tools", datetime(2026, 8, 17, 9, 0))
    await conn.commit()

    assert await _plan_row(conn, plan_id) == ("running", None)
    plan = await get_plan(conn, plan_id)
    assert plan is not None
    assert (plan.region_id, plan.algorithm, plan.status, plan.failed_reason) == (
        1,
        "or_tools",
        "running",
        None,
    )


async def test_get_plan_missing(conn: AsyncConnection[Any]) -> None:
    assert await get_plan(conn, 999) is None


async def test_mark_plan_done_writes_assignments(conn: AsyncConnection[Any]) -> None:
    plan_id = await insert_running_plan(conn, 1, PLAN_DATE, "or_tools", datetime(2026, 8, 17, 9, 0))
    await conn.commit()

    await mark_plan_done(
        conn,
        plan_id,
        [
            AssignmentWrite(
                ticket_id=1,
                engineer_id=1,
                sequence_no=1,
                planned_arrival=datetime(2026, 8, 17, 10, 30),
                travel_time_min=15,
                travel_distance_m=5400,
                unassigned_reason=None,
                explanation="назначено",
            ),
            AssignmentWrite(
                ticket_id=2,
                engineer_id=None,
                sequence_no=None,
                planned_arrival=None,
                travel_time_min=None,
                travel_distance_m=None,
                unassigned_reason="no_skill",
                explanation="нет навыка",
            ),
        ],
    )
    await conn.commit()

    assert await _plan_row(conn, plan_id) == ("done", None)
    rows = await list_plan_assignments(conn, plan_id)
    by_ticket = {r.ticket_id: r for r in rows}
    assert by_ticket[1].engineer_id == 1
    assert by_ticket[1].sequence_no == 1
    assert by_ticket[1].duration_min == 70
    assert by_ticket[2].engineer_id is None
    assert by_ticket[2].unassigned_reason == "no_skill"


async def test_mark_plan_done_rolls_back_together(conn: AsyncConnection[Any]) -> None:
    """A row that violates a constraint rolls back the whole transaction: the plan stays
    `running`, not partially `done`."""
    plan_id = await insert_running_plan(conn, 1, PLAN_DATE, "or_tools", datetime(2026, 8, 17, 9, 0))
    await conn.commit()

    with pytest.raises(DatabaseFailure):
        await mark_plan_done(
            conn,
            plan_id,
            [
                AssignmentWrite(
                    ticket_id=1,
                    engineer_id=None,
                    sequence_no=None,
                    planned_arrival=None,
                    travel_time_min=None,
                    travel_distance_m=None,
                    unassigned_reason=None,
                    explanation="строка нарушает ck_assignments__assigned_or_reason",
                ),
            ],
        )

    assert await _plan_row(conn, plan_id) == ("running", None)
    assert await list_plan_assignments(conn, plan_id) == []


async def test_mark_plan_failed(conn: AsyncConnection[Any]) -> None:
    plan_id = await insert_running_plan(conn, 1, PLAN_DATE, "or_tools", datetime(2026, 8, 17, 9, 0))
    await conn.commit()

    await mark_plan_failed(conn, plan_id, "osrm_unavailable")
    await conn.commit()

    assert await _plan_row(conn, plan_id) == ("failed", "osrm_unavailable")
    assert await list_plan_assignments(conn, plan_id) == []


async def test_plan_queries_db_unavailable(
    conn: AsyncConnection[Any], capsys: pytest.CaptureFixture[str]
) -> None:
    json_logs()
    await conn.close()
    with pytest.raises(DependencyUnavailable) as e:
        await get_plan(conn, 1)
    assert e.value.reason == "db_unavailable"
    assert events(capsys, "db_query_failed")[-1]["query"] == "get_plan"
