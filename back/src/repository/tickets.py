"""Stored tickets: the row-to-model mapping shared by every ticket query, and reading one
ticket for a status change and writing its new status."""

from collections.abc import Sequence
from typing import Any

from psycopg import AsyncConnection

from src.domain import Point, Skill, Ticket, TicketStatus, VehicleType
from src.repository.db import run_query
from src.repository.region_data import queries


def ticket_from_row(row: Sequence[Any]) -> Ticket:
    """A ticket from the column list shared by `list_tickets_by_region`, `lock_ticket`
    and `update_ticket_status`."""
    (
        id_,
        external_id,
        type_bk,
        type_hd,
        required_skill,
        required_vehicle,
        priority,
        district,
        address,
        lat,
        lon,
        window_start,
        window_end,
        duration_min,
        status,
        received_at,
    ) = row
    return Ticket(
        id=id_,
        external_id=external_id,
        type_bk=type_bk,
        type_hd=type_hd,
        required_skill=Skill(required_skill),
        required_vehicle=VehicleType(required_vehicle) if required_vehicle else None,
        priority=priority,
        district=district,
        address=address,
        location=Point(lat=lat, lon=lon),
        window_start=window_start,
        window_end=window_end,
        duration_min=duration_min,
        status=TicketStatus(status),
        received_at=received_at,
    )


async def lock_ticket(conn: AsyncConnection[Any], ticket_id: int) -> Ticket | None:
    """The ticket, its row locked until the caller's transaction ends; `None` if there is
    no such ticket."""
    row = await run_query("lock_ticket", lambda: queries.lock_ticket(conn, ticket_id=ticket_id))
    return ticket_from_row(row) if row is not None else None


async def update_ticket_status(
    conn: AsyncConnection[Any],
    ticket_id: int,
    status: TicketStatus,
    cancelled_after_dispatch: bool,
) -> Ticket:
    """Writes the status without checking the transition: the caller holds the row lock
    from `lock_ticket` and has checked it."""
    row = await run_query(
        "update_ticket_status",
        lambda: queries.update_ticket_status(
            conn,
            ticket_id=ticket_id,
            status=status.value,
            cancelled_after_dispatch=cancelled_after_dispatch,
        ),
    )
    return ticket_from_row(row)
