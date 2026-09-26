"""Reading a region's brigades and tickets."""

from typing import Any

from psycopg import AsyncConnection

from src.domain import Engineer, Point, Skill, Ticket, TicketStatus, VehicleType
from src.repository.db import fetch_all, run_query
from src.repository.region_data import queries


async def get_region_id(conn: AsyncConnection[Any], code: str) -> int | None:
    """`None` until the region's data is loaded for the first time."""
    region_id: int | None = await run_query(
        "get_region_id", lambda: queries.get_region_id(conn, code=code)
    )
    return region_id


async def list_engineers(conn: AsyncConnection[Any], region_id: int) -> list[Engineer]:
    rows = await run_query(
        "list_engineers_by_region",
        lambda: fetch_all(queries.list_engineers_by_region(conn, region_id=region_id)),
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
    tickets = []
    for (
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
    ) in rows:
        tickets.append(
            Ticket(
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
        )
    return tickets
