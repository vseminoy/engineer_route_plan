"""Writing a region's loaded data."""

from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

import aiosql
from psycopg import AsyncConnection

from src.domain import EngineerDraft, EngineerSetParams, RegionDraft, RegionWritten, TicketDraft
from src.repository.db import fetch_all, run_query

QUERIES_DIR = Path(__file__).resolve().parents[2] / "queries"

# aiosql builds the query methods at run time from the `.sql` files, so they have no
# static type. Source: https://nackjicholson.github.io/aiosql/database-driver-adapters.html
queries: Any = aiosql.from_path(QUERIES_DIR, "apsycopg")

# (engineers, morning_share, evening_share, seed) -> the set's generated brigades. The
# caller binds the office point, remote towns and ticket districts of this load — the only
# inputs a set's own row cannot carry — via `functools.partial` before passing this in.
GenerateEngineers = Callable[[int, float, float, str], list[EngineerDraft]]


async def replace_region_data(
    conn: AsyncConnection[Any],
    region: RegionDraft,
    default_set_params: EngineerSetParams,
    generate_engineers: GenerateEngineers,
    tickets: list[TicketDraft],
) -> RegionWritten:
    """Replaces the region's tickets with the given ones in one transaction and returns
    the region id, the brigade count across every set and, by set name, whether that set's
    brigades were kept. Plans of the region (every set), their rows and replan events go
    too: they refer to the tickets being replaced.

    The region's first load creates its `default` set with `default_set_params`; a later
    load finds it (and any `generated` set) already there and regenerates each set's
    brigades from that set's own stored parameters — `generate_engineers` is called once
    per set. A set whose regenerated brigades are exactly the stored ones in name, skills,
    vehicle type and shift keeps their ids and only moves them to the new start points;
    otherwise that set's brigades are replaced. On any error nothing changes."""
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
        sets = await run_query(
            "list_engineer_sets_by_region",
            lambda: fetch_all(queries.list_engineer_sets_by_region(conn, region_id=region_id)),
        )
        if not sets:
            new_id = await run_query(
                "insert_default_engineer_set",
                lambda: queries.insert_default_engineer_set(
                    conn,
                    region_id=region_id,
                    engineers=default_set_params.engineers,
                    morning_share=default_set_params.morning_share,
                    evening_share=default_set_params.evening_share,
                    seed=default_set_params.seed,
                ),
            )
            sets = [
                (
                    new_id,
                    "default",
                    "demo",
                    default_set_params.engineers,
                    default_set_params.morning_share,
                    default_set_params.evening_share,
                    default_set_params.seed,
                )
            ]
        engineers_kept: dict[str, bool] = {}
        total_engineers = 0
        for set_id, set_name, _kind, set_engineers, morning_share, evening_share, seed in sets:
            drafts = generate_engineers(set_engineers, morning_share, evening_share, seed)
            engineers_kept[set_name] = await _store_engineer_set(conn, set_id, drafts)
            total_engineers += len(drafts)
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
    return RegionWritten(
        region_id=region_id, engineers=total_engineers, engineers_kept=engineers_kept
    )


async def _store_engineer_set(
    conn: AsyncConnection[Any], engineer_set_id: int, engineers: list[EngineerDraft]
) -> bool:
    """Runs after the region's plans are gone, since plan rows refer to brigades.
    Returns true when the set's stored brigades are kept and only their start points move."""
    rows = await run_query(
        "list_engineer_set_roster",
        lambda: fetch_all(queries.list_engineer_set_roster(conn, engineer_set_id=engineer_set_id)),
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
                        "engineer_set_id": engineer_set_id,
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
        "delete_engineer_set_engineers",
        lambda: queries.delete_engineer_set_engineers(conn, engineer_set_id=engineer_set_id),
    )
    await run_query(
        "insert_engineers",
        lambda: queries.insert_engineers(
            conn,
            [
                {
                    "engineer_set_id": engineer_set_id,
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
