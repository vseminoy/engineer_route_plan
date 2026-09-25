"""Writing a region's loaded data."""

from functools import partial
from pathlib import Path
from typing import Any

import aiosql
from psycopg import AsyncConnection

from src.domain import EngineerDraft, RegionDraft, TicketDraft
from src.repository.db import run_query

QUERIES_DIR = Path(__file__).resolve().parents[2] / "queries"

# aiosql builds the query methods at run time from the `.sql` files, so they have no
# static type. Source: https://nackjicholson.github.io/aiosql/database-driver-adapters.html
queries: Any = aiosql.from_path(QUERIES_DIR, "apsycopg")


async def replace_region_data(
    conn: AsyncConnection[Any],
    region: RegionDraft,
    engineers: list[EngineerDraft],
    tickets: list[TicketDraft],
) -> int:
    """Replaces everything stored for the region with the given brigades and tickets in
    one transaction and returns the region id. Plans of the region, their rows and
    replan events go too: they refer to the tickets and brigades being replaced. On any
    error nothing changes."""
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
            "delete_region_engineers",
        ):
            delete = getattr(queries, name)
            await run_query(name, partial(delete, conn, region_id=region_id))
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
    return region_id
