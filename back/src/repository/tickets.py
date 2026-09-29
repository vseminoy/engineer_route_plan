"""Stored tickets: the row-to-model mapping shared by every ticket query, and reading one
ticket for a status change and writing its new status."""

from collections.abc import Sequence
from typing import Any

from psycopg import AsyncConnection

from src.domain import Point, Skill, Ticket, TicketDraft, TicketStatus, VehicleType
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


async def insert_ticket(conn: AsyncConnection[Any], region_id: int, draft: TicketDraft) -> int:
    """One new ticket (an incident `POST /plan/{plan_id}/replan` creates). Returns its id."""
    ticket_id: int = await run_query(
        "insert_ticket",
        lambda: queries.insert_ticket(
            conn,
            region_id=region_id,
            external_id=draft.external_id,
            type_bk=draft.type_bk,
            type_hd=draft.type_hd,
            required_skill=draft.required_skill.value,
            required_vehicle=draft.required_vehicle.value if draft.required_vehicle else None,
            priority=draft.priority,
            district=draft.district,
            address=draft.address,
            lon=draft.location.lon,
            lat=draft.location.lat,
            window_start=draft.window_start,
            window_end=draft.window_end,
            duration_min=draft.duration_min,
            status=draft.status.value,
            received_at=draft.received_at,
        ),
    )
    return ticket_id


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
