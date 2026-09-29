"""Reading, creating and deleting a region's engineer sets."""

from functools import partial
from pathlib import Path
from typing import Any

import aiosql
import psycopg.errors
from psycopg import AsyncConnection

from src.domain import EngineerSet, EngineerSetKind, EngineerSetWithRegion
from src.errors import Conflict, DatabaseFailure
from src.repository.db import fetch_all, run_query

QUERIES_DIR = Path(__file__).resolve().parents[2] / "queries"

# aiosql builds the query methods at run time from the `.sql` files, so they have no
# static type. Source: https://nackjicholson.github.io/aiosql/database-driver-adapters.html
queries: Any = aiosql.from_path(QUERIES_DIR, "apsycopg")


def _engineer_set(row: tuple[Any, ...]) -> EngineerSet:
    id_, name, kind, engineers, morning_share, evening_share, seed = row
    return EngineerSet(
        id=id_,
        name=name,
        kind=EngineerSetKind(kind),
        engineers=engineers,
        morning_share=morning_share,
        evening_share=evening_share,
        seed=seed,
    )


async def list_engineer_sets(conn: AsyncConnection[Any], region_id: int) -> list[EngineerSet]:
    rows = await run_query(
        "list_engineer_sets_by_region",
        lambda: fetch_all(queries.list_engineer_sets_by_region(conn, region_id=region_id)),
    )
    return [_engineer_set(r) for r in rows]


async def get_default_engineer_set_id(conn: AsyncConnection[Any], region_id: int) -> int | None:
    id_: int | None = await run_query(
        "get_default_engineer_set_id",
        lambda: queries.get_default_engineer_set_id(conn, region_id=region_id),
    )
    return id_


async def get_engineer_set(
    conn: AsyncConnection[Any], engineer_set_id: int
) -> EngineerSetWithRegion | None:
    row = await run_query(
        "get_engineer_set", lambda: queries.get_engineer_set(conn, engineer_set_id=engineer_set_id)
    )
    if row is None:
        return None
    id_, region_id, name, kind, engineers, morning_share, evening_share, seed = row
    return EngineerSetWithRegion(
        id=id_,
        region_id=region_id,
        name=name,
        kind=EngineerSetKind(kind),
        engineers=engineers,
        morning_share=morning_share,
        evening_share=evening_share,
        seed=seed,
    )


async def insert_generated_engineer_set(
    conn: AsyncConnection[Any],
    region_id: int,
    name: str,
    engineers: int,
    morning_share: float,
    evening_share: float,
    seed: str,
) -> int:
    """Raises `Conflict` when `name` is already taken in the region (`"default"` included)."""
    try:
        row = await run_query(
            "insert_generated_engineer_set",
            lambda: queries.insert_generated_engineer_set(
                conn,
                region_id=region_id,
                name=name,
                engineers=engineers,
                morning_share=morning_share,
                evening_share=evening_share,
                seed=seed,
            ),
        )
    except DatabaseFailure as e:
        if isinstance(e.__cause__, psycopg.errors.UniqueViolation):
            raise Conflict("name_taken", params={"region_id": region_id, "name": name}) from e
        raise
    id_: int = row[0]
    return id_


async def delete_engineer_set(conn: AsyncConnection[Any], engineer_set_id: int) -> None:
    """Deletes the set's replan events, assignments, plans and brigades, then the set
    itself, in one transaction — the same order `replace_region_data` uses for a whole
    region, scoped here to one set."""
    async with conn.transaction():
        for name in (
            "delete_engineer_set_replan_events",
            "delete_engineer_set_assignments",
            "delete_engineer_set_plans",
            "delete_engineer_set_engineers",
            "delete_engineer_set",
        ):
            delete = getattr(queries, name)
            await run_query(name, partial(delete, conn, engineer_set_id=engineer_set_id))
