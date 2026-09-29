"""Reading a region's brigades and tickets."""

from typing import Any

from psycopg import AsyncConnection

from src.domain import Engineer, Point, Skill, Ticket, VehicleType
from src.repository.db import fetch_all, run_query
from src.repository.region_data import queries
from src.repository.tickets import ticket_from_row


async def get_region_id(conn: AsyncConnection[Any], code: str) -> int | None:
    """`None` until the region's data is loaded for the first time."""
    region_id: int | None = await run_query(
        "get_region_id", lambda: queries.get_region_id(conn, code=code)
    )
    return region_id


async def get_region_office(conn: AsyncConnection[Any], region_id: int) -> Point:
    """The region's office point, for generating a set's brigades outside a file load.
    `region_id` is assumed loaded — the caller has already checked that."""
    row = await run_query(
        "get_region_office", lambda: queries.get_region_office(conn, region_id=region_id)
    )
    lat, lon = row
    return Point(lat=lat, lon=lon)


async def list_engineers(conn: AsyncConnection[Any], engineer_set_id: int) -> list[Engineer]:
    rows = await run_query(
        "list_engineers_by_set",
        lambda: fetch_all(queries.list_engineers_by_set(conn, engineer_set_id=engineer_set_id)),
    )
    return [
        Engineer(
            id=id_,
            name=name,
            vehicle_type=VehicleType(vehicle_type),
            skills=tuple(Skill(s) for s in skills),
            shift_start=shift_start,
            shift_end=shift_end,
            start=Point(lat=lat, lon=lon),
        )
        for id_, name, vehicle_type, skills, shift_start, shift_end, lat, lon in rows
    ]


async def list_tickets(conn: AsyncConnection[Any], region_id: int) -> list[Ticket]:
    rows = await run_query(
        "list_tickets_by_region",
        lambda: fetch_all(queries.list_tickets_by_region(conn, region_id=region_id)),
    )
    return [ticket_from_row(row) for row in rows]


async def list_open_tickets(conn: AsyncConnection[Any], region_id: int) -> list[Ticket]:
    """Tickets a plan can assign: excludes `completed` and `cancelled`."""
    rows = await run_query(
        "list_open_tickets_by_region",
        lambda: fetch_all(queries.list_open_tickets_by_region(conn, region_id=region_id)),
    )
    return [ticket_from_row(row) for row in rows]
