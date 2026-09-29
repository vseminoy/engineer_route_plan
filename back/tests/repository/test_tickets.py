import asyncio
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
    Skill,
    TicketDraft,
    TicketStatus,
    VehicleType,
)
from src.errors import DatabaseFailure, DependencyUnavailable
from src.repository.region_data import replace_region_data
from src.repository.region_lists import list_tickets
from src.repository.tickets import lock_ticket, update_ticket_status
from tests.conftest import RW_PASSWORD, Database
from tests.log_records import events, json_logs

pytestmark = pytest.mark.integration

OFFICE = Point(lat=55.7003202, lon=37.74794)
TICKET_POINT = Point(lat=55.71, lon=37.75)


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


async def _connect(db: Database) -> AsyncConnection[Any]:
    return await AsyncConnection.connect(
        host=db.host, port=db.port, dbname=db.dbname, user="app_rw", password=RW_PASSWORD
    )


@pytest.fixture
async def conn(migrated_db: Database) -> AsyncIterator[AsyncConnection[Any]]:
    """`app_rw` on a database emptied of data before the test; region `east` holds two
    tickets, ids 1 and 2."""
    with migrated_db.connect() as owner:
        owner.execute(
            "TRUNCATE replan_events, assignments, plans, tickets, engineers, engineer_sets, regions"
            " RESTART IDENTITY"
        )
        owner.commit()
    async with await _connect(migrated_db) as c:
        region = RegionDraft(code="east", name="Восток", office_address="офис", office=OFFICE)
        engineers = [_engineer()]
        params = EngineerSetParams(engineers=1, morning_share=0.25, evening_share=0.25, seed="east")
        await replace_region_data(
            c, region, params, lambda *_a: engineers, [_ticket("1"), _ticket("2")]
        )
        await c.commit()
        yield c


class _Bogus:
    """A status outside the domain enum, to reach the database constraint."""

    value = "bogus"


async def _row(conn: AsyncConnection[Any], ticket_id: int) -> tuple[Any, ...]:
    cur = await conn.execute(
        "SELECT status, cancelled_after_dispatch FROM tickets WHERE id = %s", (ticket_id,)
    )
    row = await cur.fetchone()
    assert row is not None
    return tuple(row)


async def test_lock_ticket(conn: AsyncConnection[Any]) -> None:
    listed = {t.id: t for t in await list_tickets(conn, 1)}
    async with conn.transaction():
        ticket = await lock_ticket(conn, 1)
    assert ticket == listed[1]
    assert ticket.location == TICKET_POINT
    assert ticket.window_start == datetime(2026, 8, 17, 10, 0)


async def test_lock_ticket_missing(conn: AsyncConnection[Any]) -> None:
    async with conn.transaction():
        assert await lock_ticket(conn, 999) is None


async def test_update_ticket_status(conn: AsyncConnection[Any]) -> None:
    before = {t.id: t for t in await list_tickets(conn, 1)}
    async with conn.transaction():
        updated = await update_ticket_status(conn, 1, TicketStatus.COMPLETED, False)
    assert updated == before[1].model_copy(update={"status": TicketStatus.COMPLETED})
    after = {t.id: t for t in await list_tickets(conn, 1)}
    assert after[1].status is TicketStatus.COMPLETED
    assert after[2] == before[2]
    assert await _row(conn, 1) == ("completed", False)


async def test_update_ticket_status_cancelled_after_dispatch(conn: AsyncConnection[Any]) -> None:
    async with conn.transaction():
        await update_ticket_status(conn, 1, TicketStatus.CANCELLED, True)
    assert await _row(conn, 1) == ("cancelled", True)


async def test_update_ticket_status_check_constraint(
    conn: AsyncConnection[Any], capsys: pytest.CaptureFixture[str]
) -> None:
    json_logs()
    with pytest.raises(DatabaseFailure) as e:
        async with conn.transaction():
            await update_ticket_status(conn, 1, _Bogus(), False)  # type: ignore[arg-type]
    assert e.value.reason == "db_query_failed"
    cause = e.value.__cause__
    assert isinstance(cause, psycopg.Error)
    assert cause.diag.constraint_name == "ck_tickets__status"
    assert await _row(conn, 1) == ("sent", False)
    assert events(capsys, "db_query_failed")[-1]["query"] == "update_ticket_status"


async def test_lock_ticket_waits_for_concurrent_change(
    conn: AsyncConnection[Any], migrated_db: Database
) -> None:
    async with await _connect(migrated_db) as other:
        async with conn.transaction():
            await lock_ticket(conn, 1)
            await update_ticket_status(conn, 1, TicketStatus.EN_ROUTE, False)

            async def lock_in_other() -> Any:
                async with other.transaction():
                    return await lock_ticket(other, 1)

            waiting = asyncio.create_task(lock_in_other())
            done, _ = await asyncio.wait({waiting}, timeout=0.3)
            assert not done
        ticket = await asyncio.wait_for(waiting, timeout=5)
    assert ticket.status is TicketStatus.EN_ROUTE


@pytest.mark.parametrize("query", ["lock_ticket", "update_ticket_status"])
async def test_ticket_queries_db_unavailable(
    conn: AsyncConnection[Any], capsys: pytest.CaptureFixture[str], query: str
) -> None:
    json_logs()
    await conn.close()
    with pytest.raises(DependencyUnavailable) as e:
        if query == "lock_ticket":
            await lock_ticket(conn, 1)
        else:
            await update_ticket_status(conn, 1, TicketStatus.EN_ROUTE, False)
    assert e.value.reason == "db_unavailable"
    assert events(capsys, "db_query_failed")[-1]["query"] == query
