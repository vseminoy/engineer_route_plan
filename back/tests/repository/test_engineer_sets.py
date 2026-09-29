from collections.abc import AsyncIterator
from datetime import datetime, time
from typing import Any

import pytest
from psycopg import AsyncConnection

from src.domain import (
    EngineerDraft,
    EngineerSetKind,
    EngineerSetParams,
    Point,
    RegionDraft,
    Skill,
    TicketDraft,
    TicketStatus,
    VehicleType,
)
from src.errors import Conflict, DependencyUnavailable
from src.repository.engineer_sets import (
    delete_engineer_set,
    get_default_engineer_set_id,
    get_engineer_set,
    insert_generated_engineer_set,
    list_engineer_sets,
)
from src.repository.region_data import replace_region_data
from tests.conftest import RW_PASSWORD, Database
from tests.log_records import events, json_logs

pytestmark = pytest.mark.integration

OFFICE = Point(lat=55.7003202, lon=37.74794)
TICKET_POINT = Point(lat=55.71, lon=37.75)


def _region(code: str = "east", name: str = "Восток") -> RegionDraft:
    return RegionDraft(code=code, name=name, office_address="офис", office=OFFICE)


def _engineer(n: int) -> EngineerDraft:
    return EngineerDraft(
        name=f"Бригада {n}",
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
    default engineer set with one brigade."""
    with migrated_db.connect() as owner:
        owner.execute(
            "TRUNCATE replan_events, assignments, plans, tickets, engineers, engineer_sets, regions"
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
        params = EngineerSetParams(engineers=1, morning_share=0.25, evening_share=0.25, seed="east")
        await replace_region_data(c, _region(), params, lambda *_a: [_engineer(1)], [_ticket("1")])
        await c.commit()
        yield c


async def test_list_engineer_sets_by_region(conn: AsyncConnection[Any]) -> None:
    default_set_id = await get_default_engineer_set_id(conn, 1)
    assert default_set_id is not None
    variant_b_id = await insert_generated_engineer_set(
        conn, 1, "Вариант Б", 15, 0.2, 0.2, "42", [_engineer(2), _engineer(3)]
    )
    await insert_generated_engineer_set(conn, 1, "Вариант В", 5, 0.25, 0.25, "5", [_engineer(4)])
    await conn.commit()

    sets = await list_engineer_sets(conn, 1)

    assert [s.id for s in sets] == sorted(s.id for s in sets)
    assert sets[0].kind is EngineerSetKind.DEMO
    assert sets[0].name == "default"
    b = next(s for s in sets if s.id == variant_b_id)
    assert (b.name, b.kind, b.engineers, b.morning_share, b.evening_share, b.seed) == (
        "Вариант Б",
        EngineerSetKind.GENERATED,
        15,
        0.2,
        0.2,
        "42",
    )


async def test_list_engineer_sets_other_region_excluded(conn: AsyncConnection[Any]) -> None:
    other = await replace_region_data(
        conn,
        _region("south_east", "Юго-Восток"),
        EngineerSetParams(engineers=1, morning_share=0.25, evening_share=0.25, seed="south_east"),
        lambda *_a: [_engineer(9)],
        [_ticket("2")],
    )
    await conn.commit()

    east_sets = await list_engineer_sets(conn, 1)
    other_sets = await list_engineer_sets(conn, other.region_id)

    assert {s.id for s in east_sets}.isdisjoint({s.id for s in other_sets})


async def test_get_default_engineer_set_id(conn: AsyncConnection[Any]) -> None:
    set_id = await get_default_engineer_set_id(conn, 1)
    assert set_id is not None
    fetched = await get_engineer_set(conn, set_id)
    assert fetched is not None
    assert fetched.kind is EngineerSetKind.DEMO
    assert fetched.name == "default"


async def test_get_default_engineer_set_id_missing_region(conn: AsyncConnection[Any]) -> None:
    assert await get_default_engineer_set_id(conn, 12345) is None


async def test_get_engineer_set(conn: AsyncConnection[Any]) -> None:
    set_id = await insert_generated_engineer_set(
        conn, 1, "Вариант Б", 15, 0.2, 0.2, "42", [_engineer(2)]
    )
    await conn.commit()

    fetched = await get_engineer_set(conn, set_id)

    assert fetched is not None
    assert fetched.region_id == 1
    assert (fetched.name, fetched.kind, fetched.engineers, fetched.seed) == (
        "Вариант Б",
        EngineerSetKind.GENERATED,
        15,
        "42",
    )


async def test_get_engineer_set_missing(conn: AsyncConnection[Any]) -> None:
    assert await get_engineer_set(conn, 999999) is None


async def test_insert_generated_engineer_set(conn: AsyncConnection[Any]) -> None:
    set_id = await insert_generated_engineer_set(
        conn, 1, "Вариант Б", 15, 0.2, 0.2, "42", [_engineer(2), _engineer(3)]
    )
    await conn.commit()

    fetched = await get_engineer_set(conn, set_id)
    assert fetched is not None
    assert fetched.kind is EngineerSetKind.GENERATED
    count = await conn.execute(
        "SELECT count(*) FROM engineers WHERE engineer_set_id = %s", (set_id,)
    )
    row = await count.fetchone()
    assert row is not None
    assert row[0] == 2


async def test_insert_generated_engineer_set_name_conflict(conn: AsyncConnection[Any]) -> None:
    with pytest.raises(Conflict) as e:
        await insert_generated_engineer_set(conn, 1, "default", 15, 0.2, 0.2, "42", [_engineer(2)])
    assert e.value.reason == "name_taken"
    await conn.rollback()

    await insert_generated_engineer_set(conn, 1, "Вариант Б", 15, 0.2, 0.2, "42", [_engineer(2)])
    await conn.commit()
    with pytest.raises(Conflict) as e2:
        await insert_generated_engineer_set(conn, 1, "Вариант Б", 5, 0.2, 0.2, "1", [_engineer(3)])
    assert e2.value.reason == "name_taken"


async def test_delete_engineer_set_cascade(conn: AsyncConnection[Any]) -> None:
    set_id = await insert_generated_engineer_set(
        conn, 1, "Вариант Б", 1, 0.25, 0.25, "42", [_engineer(2)]
    )
    await conn.commit()
    default_id = await get_default_engineer_set_id(conn, 1)
    assert default_id is not None

    plan_cur = await conn.execute(
        "INSERT INTO plans (region_id, engineer_set_id, plan_date, algorithm, status, created_at)"
        " VALUES (1, %s, '2026-08-17', 'or_tools', 'done', '2026-08-17 09:00') RETURNING id",
        (set_id,),
    )
    p1 = (await plan_cur.fetchone())[0]  # type: ignore[index]
    child_cur = await conn.execute(
        "INSERT INTO plans (region_id, engineer_set_id, plan_date, algorithm, status,"
        " parent_plan_id, created_at) VALUES (1, %s, '2026-08-17', 'or_tools', 'done', %s,"
        " '2026-08-17 13:00') RETURNING id",
        (set_id, p1),
    )
    p2 = (await child_cur.fetchone())[0]  # type: ignore[index]
    await conn.execute(
        "INSERT INTO assignments (plan_id, ticket_id, explanation, unassigned_reason)"
        " SELECT %s, id, 'нет навыка', 'no_skill' FROM tickets WHERE region_id = 1",
        (p2,),
    )
    await conn.execute(
        "INSERT INTO replan_events (plan_id, event_type, payload, triggered_at, result_plan_id)"
        " VALUES (%s, 'new_ticket', '{}', '2026-08-17 13:00', %s)",
        (p1, p2),
    )
    await conn.commit()

    other_plan_cur = await conn.execute(
        "INSERT INTO plans (region_id, engineer_set_id, plan_date, algorithm, status, created_at)"
        " VALUES (1, %s, '2026-08-17', 'or_tools', 'done', '2026-08-17 09:00') RETURNING id",
        (default_id,),
    )
    other_plan = (await other_plan_cur.fetchone())[0]  # type: ignore[index]
    await conn.commit()

    await delete_engineer_set(conn, set_id)
    await conn.commit()

    assert await get_engineer_set(conn, set_id) is None
    for table in ("plans", "assignments", "replan_events"):
        cur = await conn.execute(
            f"SELECT count(*) FROM {table} WHERE plan_id = ANY(%s)", ([p1, p2],)
        )
        row = await cur.fetchone()
        assert row is not None
    count_cur = await conn.execute(
        "SELECT count(*) FROM engineers WHERE engineer_set_id = %s", (set_id,)
    )
    row = await count_cur.fetchone()
    assert row is not None and row[0] == 0
    remaining = await conn.execute("SELECT count(*) FROM plans WHERE id = %s", (other_plan,))
    row = await remaining.fetchone()
    assert row is not None and row[0] == 1
    default_still_there = await get_engineer_set(conn, default_id)
    assert default_still_there is not None


@pytest.mark.parametrize(
    "query",
    [
        "list_engineer_sets_by_region",
        "get_default_engineer_set_id",
        "get_engineer_set",
        "insert_generated_engineer_set",
        "delete_engineer_set",
    ],
)
async def test_engineer_sets_queries_db_unavailable(
    conn: AsyncConnection[Any], capsys: pytest.CaptureFixture[str], query: str
) -> None:
    json_logs()
    await conn.close()
    with pytest.raises(DependencyUnavailable) as e:
        if query == "list_engineer_sets_by_region":
            await list_engineer_sets(conn, 1)
        elif query == "get_default_engineer_set_id":
            await get_default_engineer_set_id(conn, 1)
        elif query == "get_engineer_set":
            await get_engineer_set(conn, 1)
        elif query == "insert_generated_engineer_set":
            await insert_generated_engineer_set(conn, 1, "Вариант Б", 1, 0.25, 0.25, "1", [])
        else:
            await delete_engineer_set(conn, 1)
    assert e.value.reason == "db_unavailable"
    assert events(capsys, "db_query_failed")[-1]["query"] == query
