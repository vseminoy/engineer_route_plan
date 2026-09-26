"""Writing a region's loaded data."""

from functools import partial
from pathlib import Path
from typing import Any

import aiosql
from psycopg import AsyncConnection

from src.domain import EngineerDraft, RegionDraft, RegionWritten, TicketDraft
from src.repository.db import fetch_all, run_query

QUERIES_DIR = Path(__file__).resolve().parents[2] / "queries"

# aiosql builds the query methods at run time from the `.sql` files, so they have no
# static type. Source: https://nackjicholson.github.io/aiosql/database-driver-adapters.html
queries: Any = aiosql.from_path(QUERIES_DIR, "apsycopg")


async def replace_region_data(
    conn: AsyncConnection[Any],
    region: RegionDraft,
    engineers: list[EngineerDraft],
    tickets: list[TicketDraft],
) -> RegionWritten:
    """Replaces the region's tickets with the given ones in one transaction and returns
    the region id and whether its brigades were kept. Plans of the region, their rows and
    replan events go too: they refer to the tickets being replaced. When the region's
    brigades are exactly the given ones in name, skills, vehicle type and shift, they keep
    their ids and only move to the given start points; otherwise they are replaced by the
    given ones. On any error nothing changes."""
    async with conn.transaction():
        row = await run_query(
            "upsert_region",
            lambda: queries.upsert_region(
                conn,
                code=region.code,
                name=region.name,
                office_address=region.office_address,
                office_lon=region.office.lon,
                office_lat=region.office.lat,
            ),
        )
        region_id: int = row[0]
        for name in (
            "delete_region_replan_events",
            "delete_region_assignments",
            "delete_region_plans",
            "delete_region_tickets",
        ):
            delete = getattr(queries, name)
            await run_query(name, partial(delete, conn, region_id=region_id))
        engineers_kept = await _store_engineers(conn, region_id, engineers)
        await run_query(
            "insert_tickets",
            lambda: queries.insert_tickets(
                conn,
                [
                    {
                        "region_id": region_id,
                        "external_id": t.external_id,
                        "type_bk": t.type_bk,
                        "type_hd": t.type_hd,
                        "required_skill": t.required_skill.value,
                        "required_vehicle": t.required_vehicle.value
                        if t.required_vehicle
                        else None,
                        "priority": t.priority,
                        "district": t.district,
                        "address": t.address,
                        "lon": t.location.lon,
                        "lat": t.location.lat,
                        "window_start": t.window_start,
                        "window_end": t.window_end,
                        "duration_min": t.duration_min,
                        "status": t.status.value,
                        "received_at": t.received_at,
                    }
                    for t in tickets
                ],
            ),
        )
    return RegionWritten(region_id=region_id, engineers_kept=engineers_kept)


async def _store_engineers(
    conn: AsyncConnection[Any], region_id: int, engineers: list[EngineerDraft]
) -> bool:
    """Runs after the region's plans are gone, since plan rows refer to brigades.
    Returns true when the stored brigades are kept and only their start points move."""
    rows = await run_query(
        "list_region_roster",
        lambda: fetch_all(queries.list_region_roster(conn, region_id=region_id)),
    )
    stored = sorted(
        (name, tuple(sorted(skills)), vehicle_type, shift_start, shift_end)
        for name, skills, vehicle_type, shift_start, shift_end in rows
    )
    given = sorted(
        (
            e.name,
            tuple(sorted(s.value for s in e.skills)),
            e.vehicle_type.value,
            e.shift_start,
            e.shift_end,
        )
        for e in engineers
    )
    if stored == given:
        await run_query(
            "update_engineer_starts",
            lambda: queries.update_engineer_starts(
                conn,
                [
                    {
                        "region_id": region_id,
                        "name": e.name,
                        "start_lon": e.start.lon,
                        "start_lat": e.start.lat,
                    }
                    for e in engineers
                ],
            ),
        )
        return True
    await run_query(
        "delete_region_engineers",
        lambda: queries.delete_region_engineers(conn, region_id=region_id),
    )
    await run_query(
        "insert_engineers",
        lambda: queries.insert_engineers(
            conn,
            [
                {
                    "region_id": region_id,
                    "name": e.name,
                    "start_lon": e.start.lon,
                    "start_lat": e.start.lat,
                    "shift_start": e.shift_start,
                    "shift_end": e.shift_end,
                    "vehicle_type": e.vehicle_type.value,
                    "skills": [s.value for s in e.skills],
                }
                for e in engineers
            ],
        ),
    )
    return False
