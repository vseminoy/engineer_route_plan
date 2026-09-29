from collections.abc import AsyncIterator
from datetime import datetime, time
from typing import Any

import psycopg
import pytest
from psycopg import AsyncConnection

from src.domain import (
    EngineerDraft,
    EngineerSetParams,
    Point,
    RegionDraft,
    RegionWritten,
    Skill,
    TicketDraft,
    TicketStatus,
    VehicleType,
)
from src.errors import DatabaseFailure
from src.repository.region_data import replace_region_data
from tests.conftest import RW_PASSWORD, Database
from tests.log_records import events, json_logs

pytestmark = pytest.mark.integration

OFFICE = Point(lat=55.7003202, lon=37.74794)


def _region(code: str = "east", name: str = "Восток", office: Point = OFFICE) -> RegionDraft:
    return RegionDraft(code=code, name=name, office_address="г. Москва, офис", office=office)


def _engineer(n: int, skills: tuple[Skill, ...] = (Skill.CONNECTION,), **kw: Any) -> EngineerDraft:
    values: dict[str, Any] = {
        "name": f"Бригада {n}",
        "start": OFFICE,
        "shift_start": time(10, 0),
        "shift_end": time(23, 30),
        "vehicle_type": VehicleType.CAR,
        "skills": skills,
    }
    values.update(kw)
    return EngineerDraft.model_construct(**values)


def _ticket(external_id: str) -> TicketDraft:
    return TicketDraft(
        external_id=external_id,
        type_bk="Подключение",
        type_hd="Заявка на подключение",
        required_skill=Skill.CONNECTION,
        priority=2,
        district="Выхино",
        address="Город Москва, ул.Тестовая, д. 1",
        location=Point(lat=55.71, lon=37.75),
        window_start=datetime(2026, 8, 17, 10, 0),
        window_end=datetime(2026, 8, 17, 12, 0),
        duration_min=70,
        status=TicketStatus.SENT,
        received_at=datetime(2026, 8, 17, 0, 0),
    )


def _params(engineers: list[EngineerDraft], seed: str = "east") -> EngineerSetParams:
    return EngineerSetParams(
        engineers=len(engineers) or 1, morning_share=0.25, evening_share=0.25, seed=seed
    )


async def _write(
    conn: AsyncConnection[Any],
    region: RegionDraft,
    engineers: list[EngineerDraft],
    tickets: list[TicketDraft],
) -> RegionWritten:
    """Wraps `replace_region_data`'s generator callback for a fixed brigade list —
    these tests give the exact brigades to store, not generator parameters."""
    return await replace_region_data(
        conn, region, _params(engineers, region.code), lambda *_a: engineers, tickets
    )


@pytest.fixture
async def conn(migrated_db: Database) -> AsyncIterator[AsyncConnection[Any]]:
    """`app_rw`, the application's role, on a database emptied of data before the test."""
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
        yield c


async def _one(conn: AsyncConnection[Any], sql: str) -> Any:
    cur = await conn.execute(sql)
    row = await cur.fetchone()
    assert row is not None
    return row[0] if len(row) == 1 else row


async def _add_plans(conn: AsyncConnection[Any], region_id: int) -> None:
    """Two plans (the second derived from the first), a plan row and a replan event, all
    scoped to the region's default engineer set."""
    engineer_set_id = await _one(
        conn, f"SELECT id FROM engineer_sets WHERE region_id = {region_id} AND kind = 'demo'"
    )
    cur = await conn.execute(
        "INSERT INTO plans (region_id, engineer_set_id, plan_date, algorithm, status, created_at)"
        " VALUES (%s, %s, '2026-08-17', 'or_tools', 'done', '2026-08-17 09:00') RETURNING id",
        (region_id, engineer_set_id),
    )
    p1 = (await cur.fetchone())[0]  # type: ignore[index]  # RETURNING always yields a row
    cur = await conn.execute(
        "INSERT INTO plans (region_id, engineer_set_id, plan_date, algorithm, status,"
        " parent_plan_id, created_at)"
        " VALUES (%s, %s, '2026-08-17', 'or_tools', 'done', %s, '2026-08-17 13:00') RETURNING id",
        (region_id, engineer_set_id, p1),
    )
    p2 = (await cur.fetchone())[0]  # type: ignore[index]  # RETURNING always yields a row
    await conn.execute(
        "INSERT INTO assignments (plan_id, ticket_id, explanation, unassigned_reason)"
        " SELECT %s, id, 'нет навыка', 'no_skill' FROM tickets WHERE region_id = %s",
        (p2, region_id),
    )
    await conn.execute(
        "INSERT INTO replan_events (plan_id, event_type, payload, triggered_at, result_plan_id)"
        " VALUES (%s, 'new_ticket', '{}', '2026-08-17 13:00', %s)",
        (p1, p2),
    )
    await conn.commit()


async def test_replace_inserts_region_engineers_tickets(conn: AsyncConnection[Any]) -> None:
    ticket = _ticket("1")
    written = await _write(
        conn, _region(), [_engineer(1), _engineer(2)], [ticket, _ticket("2"), _ticket("3")]
    )
    await conn.commit()
    region_id = written.region_id
    assert not written.engineers_kept["default"]
    assert await _one(conn, "SELECT count(*) FROM regions") == 1
    assert (
        await _one(
            conn,
            "SELECT count(*) FROM engineers e JOIN engineer_sets s ON s.id = e.engineer_set_id"
            f" WHERE s.region_id = {region_id}",
        )
        == 2
    )
    assert await _one(conn, f"SELECT count(*) FROM tickets WHERE region_id = {region_id}") == 3
    engineer = await _one(
        conn,
        "SELECT ST_Y(start_geom), ST_X(start_geom), shift_start, shift_end, skills"
        " FROM engineers ORDER BY id LIMIT 1",
    )
    assert engineer == (OFFICE.lat, OFFICE.lon, time(10, 0), time(23, 30), ["connection"])
    stored = await _one(
        conn,
        "SELECT ST_Y(geom), ST_X(geom), window_start, window_end, received_at, status"
        " FROM tickets ORDER BY id LIMIT 1",
    )
    assert stored == (
        ticket.location.lat,
        ticket.location.lon,
        ticket.window_start,
        ticket.window_end,
        ticket.received_at,
        "sent",
    )
    assert stored[2].tzinfo is None


async def test_replace_same_code_keeps_region_id(conn: AsyncConnection[Any]) -> None:
    first = await _write(conn, _region(), [_engineer(1)], [_ticket("1")])
    moved = Point(lat=55.8, lon=37.8)
    second = await _write(
        conn, _region(name="Восток-2", office=moved), [_engineer(1)], [_ticket("1")]
    )
    await conn.commit()
    assert first.region_id == second.region_id
    assert await _one(conn, "SELECT name, ST_Y(office_geom) FROM regions") == ("Восток-2", 55.8)


async def test_replace_removes_previous_region_data(conn: AsyncConnection[Any]) -> None:
    written = await _write(conn, _region(), [_engineer(1)], [_ticket("old")])
    await conn.commit()
    await _add_plans(conn, written.region_id)
    await _write(conn, _region(), [_engineer(7)], [_ticket("new")])
    await conn.commit()
    for table in ("plans", "assignments", "replan_events"):
        assert await _one(conn, f"SELECT count(*) FROM {table}") == 0
    assert await _one(conn, "SELECT array_agg(external_id) FROM tickets") == ["new"]
    assert await _one(conn, "SELECT array_agg(name) FROM engineers") == ["Бригада 7"]


async def _engineer_rows(conn: AsyncConnection[Any]) -> list[tuple[Any, ...]]:
    cur = await conn.execute(
        "SELECT id, name, ST_Y(start_geom), ST_X(start_geom), skills, vehicle_type,"
        " shift_start, shift_end FROM engineers ORDER BY id"
    )
    return list(await cur.fetchall())


async def test_replace_same_roster_keeps_engineers(conn: AsyncConnection[Any]) -> None:
    written = await _write(conn, _region(), [_engineer(1), _engineer(2)], [_ticket("old")])
    await conn.commit()
    before = await _engineer_rows(conn)
    await _add_plans(conn, written.region_id)
    await conn.execute(
        "INSERT INTO assignments (plan_id, ticket_id, engineer_id, sequence_no, planned_arrival,"
        " travel_time_min, travel_distance_m, explanation)"
        " SELECT p.id, t.id, %s, 1, '2026-08-17 10:00', 10, 1000, 'назначена'"
        " FROM plans p, tickets t WHERE p.parent_plan_id IS NULL",
        (before[0][0],),
    )
    await conn.commit()
    moved = Point(lat=55.43, lon=37.76)
    written = await _write(
        conn,
        _region(),
        [_engineer(1, start=moved), _engineer(2, start=moved)],
        [_ticket("new")],
    )
    await conn.commit()
    assert written.engineers_kept["default"]
    after = await _engineer_rows(conn)
    assert [row[0] for row in after] == [row[0] for row in before]
    assert all(row[2:4] == (moved.lat, moved.lon) for row in after)
    assert [row[1:2] + row[4:] for row in after] == [row[1:2] + row[4:] for row in before]
    assert await _one(conn, "SELECT array_agg(external_id) FROM tickets") == ["new"]
    for table in ("plans", "assignments", "replan_events"):
        assert await _one(conn, f"SELECT count(*) FROM {table}") == 0


async def test_replace_changed_roster_recreates_engineers(conn: AsyncConnection[Any]) -> None:
    await _write(conn, _region(), [_engineer(1), _engineer(2)], [_ticket("1")])
    await conn.commit()
    before = {row[0] for row in await _engineer_rows(conn)}
    written = await _write(
        conn, _region(), [_engineer(1), _engineer(2), _engineer(3)], [_ticket("1")]
    )
    await conn.commit()
    assert not written.engineers_kept["default"]
    after = await _engineer_rows(conn)
    assert [row[1] for row in after] == ["Бригада 1", "Бригада 2", "Бригада 3"]
    assert before.isdisjoint(row[0] for row in after)


async def test_replace_skills_order_keeps_engineers(conn: AsyncConnection[Any]) -> None:
    both = (Skill.CONNECTION, Skill.EMERGENCY)
    await _write(conn, _region(), [_engineer(1, skills=both)], [_ticket("1")])
    await conn.commit()
    before = [row[0] for row in await _engineer_rows(conn)]
    written = await _write(
        conn, _region(), [_engineer(1, skills=tuple(reversed(both)))], [_ticket("1")]
    )
    await conn.commit()
    assert written.engineers_kept["default"]
    assert [row[0] for row in await _engineer_rows(conn)] == before


@pytest.mark.parametrize(
    "changed",
    [
        {"skills": (Skill.EMERGENCY,)},
        {"vehicle_type": VehicleType.FOOT},
        {"shift_start": time(15, 30)},
        {"shift_end": time(18, 0)},
    ],
    ids=["skills", "vehicle", "shift_start", "shift_end"],
)
async def test_replace_changed_brigade_recreates_engineers(
    conn: AsyncConnection[Any], changed: dict[str, Any]
) -> None:
    await _write(conn, _region(), [_engineer(1), _engineer(2)], [_ticket("1")])
    await conn.commit()
    before = {row[0] for row in await _engineer_rows(conn)}
    written = await _write(conn, _region(), [_engineer(1), _engineer(2, **changed)], [_ticket("1")])
    await conn.commit()
    assert not written.engineers_kept["default"]
    after = await _engineer_rows(conn)
    assert [row[1] for row in after] == ["Бригада 1", "Бригада 2"]
    assert before.isdisjoint(row[0] for row in after)


async def test_replace_keeps_other_regions(conn: AsyncConnection[Any]) -> None:
    await _write(conn, _region(), [_engineer(1)], [_ticket("e1")])
    await _write(
        conn, _region("south_east", "Юго-Восток"), [_engineer(2)], [_ticket("s1"), _ticket("s2")]
    )
    await _write(conn, _region(), [_engineer(3)], [_ticket("e2")])
    await conn.commit()
    assert (
        await _one(
            conn,
            "SELECT count(*) FROM tickets t JOIN regions r ON r.id = t.region_id"
            " WHERE r.code = 'south_east'",
        )
        == 2
    )


async def test_replace_duplicate_external_id_loads_both(conn: AsyncConnection[Any]) -> None:
    await _write(conn, _region(), [_engineer(1)], [_ticket("7"), _ticket("7")])
    await conn.commit()
    assert await _one(conn, "SELECT count(DISTINCT id) FROM tickets WHERE external_id = '7'") == 2


async def _assert_rolled_back(
    conn: AsyncConnection[Any],
    engineer: EngineerDraft,
    constraint: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    json_logs()
    await _write(conn, _region(), [_engineer(1)], [_ticket("kept")])
    await conn.commit()
    with pytest.raises(DatabaseFailure) as e:
        await _write(conn, _region(), [engineer], [_ticket("new")])
    await conn.rollback()
    assert e.value.reason == "db_query_failed"
    cause = e.value.__cause__
    assert isinstance(cause, psycopg.Error) and cause.diag.constraint_name == constraint
    assert await _one(conn, "SELECT array_agg(external_id) FROM tickets") == ["kept"]
    assert await _one(conn, "SELECT array_agg(name) FROM engineers") == ["Бригада 1"]
    (record,) = events(capsys, "db_query_failed")
    assert (record["query"], record["sqlstate"]) == ("insert_engineers", "23514")


async def test_replace_constraint_violation_rolls_back(
    conn: AsyncConnection[Any], capsys: pytest.CaptureFixture[str]
) -> None:
    four = (Skill.LOCAL_WORK, Skill.CONNECTION, Skill.EMERGENCY, Skill.LOCAL_WORK)
    await _assert_rolled_back(conn, _engineer(9, four), "ck_engineers__skills", capsys)


async def test_replace_overnight_shift_rolls_back(
    conn: AsyncConnection[Any], capsys: pytest.CaptureFixture[str]
) -> None:
    overnight = _engineer(9, shift_start=time(22, 0), shift_end=time(6, 0))
    await _assert_rolled_back(conn, overnight, "ck_engineers__shift_order", capsys)
