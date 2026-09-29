"""Reading and writing plan-build rows: a plan is queued (`running`), then finishes
(`done`, with its assignment rows) or fails (`failed`, with a reason) in one later write."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from psycopg import AsyncConnection

from src.repository.db import fetch_all, run_query
from src.repository.region_data import queries


@dataclass(frozen=True)
class PlanRow:
    id: int
    region_id: int
    engineer_set_id: int
    plan_date: date
    algorithm: str
    status: str
    failed_reason: str | None


@dataclass(frozen=True)
class AssignmentRow:
    """One row of a `done` plan: assigned (`engineer_id` and the rest of the route
    fields) or not (`unassigned_reason`), never both. `duration_min` is the ticket's
    on-site time, needed to compute its brigade's idle time."""

    ticket_id: int
    engineer_id: int | None
    sequence_no: int | None
    planned_arrival: datetime | None
    travel_time_min: int | None
    travel_distance_m: int | None
    unassigned_reason: str | None
    explanation: str
    duration_min: int


@dataclass(frozen=True)
class AssignmentWrite:
    """One row to persist for a finished build; same shape as `AssignmentRow` minus
    `duration_min`, which is not written (it is the ticket's, read back through the join
    in `list_plan_assignments`)."""

    ticket_id: int
    engineer_id: int | None
    sequence_no: int | None
    planned_arrival: datetime | None
    travel_time_min: int | None
    travel_distance_m: int | None
    unassigned_reason: str | None
    explanation: str


async def insert_running_plan(
    conn: AsyncConnection[Any],
    region_id: int,
    engineer_set_id: int,
    plan_date: date,
    algorithm: str,
    created_at: datetime,
) -> int:
    plan_id: int = await run_query(
        "insert_running_plan",
        lambda: queries.insert_running_plan(
            conn,
            region_id=region_id,
            engineer_set_id=engineer_set_id,
            plan_date=plan_date,
            algorithm=algorithm,
            created_at=created_at,
        ),
    )
    return plan_id


async def _insert_assignments(
    conn: AsyncConnection[Any], plan_id: int, assignments: list[AssignmentWrite]
) -> None:
    if not assignments:
        return
    await run_query(
        "insert_assignments",
        lambda: queries.insert_assignments(
            conn,
            [
                {
                    "plan_id": plan_id,
                    "ticket_id": a.ticket_id,
                    "engineer_id": a.engineer_id,
                    "sequence_no": a.sequence_no,
                    "planned_arrival": a.planned_arrival,
                    "travel_time_min": a.travel_time_min,
                    "travel_distance_m": a.travel_distance_m,
                    "unassigned_reason": a.unassigned_reason,
                    "explanation": a.explanation,
                }
                for a in assignments
            ],
        ),
    )


async def mark_plan_done(
    conn: AsyncConnection[Any], plan_id: int, assignments: list[AssignmentWrite]
) -> None:
    async with conn.transaction():
        await run_query("mark_plan_done", lambda: queries.mark_plan_done(conn, plan_id=plan_id))
        await _insert_assignments(conn, plan_id, assignments)


async def mark_plan_failed(conn: AsyncConnection[Any], plan_id: int, failed_reason: str) -> None:
    await run_query(
        "mark_plan_failed",
        lambda: queries.mark_plan_failed(conn, plan_id=plan_id, failed_reason=failed_reason),
    )


async def mark_running_plans_failed(conn: AsyncConnection[Any], failed_reason: str) -> list[int]:
    """Closes every plan left `running`, across all regions. Returns the closed ids."""
    rows = await run_query(
        "sweep_running_plans",
        lambda: fetch_all(queries.sweep_running_plans(conn, failed_reason=failed_reason)),
    )
    return [row[0] for row in rows]


async def get_plan(conn: AsyncConnection[Any], plan_id: int) -> PlanRow | None:
    row = await run_query("get_plan", lambda: queries.get_plan(conn, plan_id=plan_id))
    if row is None:
        return None
    id_, region_id, engineer_set_id, plan_date, algorithm, status, failed_reason = row
    return PlanRow(
        id=id_,
        region_id=region_id,
        engineer_set_id=engineer_set_id,
        plan_date=plan_date,
        algorithm=algorithm,
        status=status,
        failed_reason=failed_reason,
    )


async def insert_replanned_plan(
    conn: AsyncConnection[Any],
    region_id: int,
    engineer_set_id: int,
    plan_date: date,
    algorithm: str,
    parent_plan_id: int,
    created_at: datetime,
    assignments: list[AssignmentWrite],
) -> int:
    """A synchronous, already-`done` plan: `replan` never leaves `running`.
    `engineer_set_id` is always the parent plan's own. Returns the new plan's id."""
    async with conn.transaction():
        plan_id: int = await run_query(
            "insert_replanned_plan",
            lambda: queries.insert_replanned_plan(
                conn,
                region_id=region_id,
                engineer_set_id=engineer_set_id,
                plan_date=plan_date,
                algorithm=algorithm,
                parent_plan_id=parent_plan_id,
                created_at=created_at,
            ),
        )
        await _insert_assignments(conn, plan_id, assignments)
    return plan_id


async def list_plan_assignments(conn: AsyncConnection[Any], plan_id: int) -> list[AssignmentRow]:
    rows = await run_query(
        "list_plan_assignments",
        lambda: fetch_all(queries.list_plan_assignments(conn, plan_id=plan_id)),
    )
    return [
        AssignmentRow(
            ticket_id=ticket_id,
            engineer_id=engineer_id,
            sequence_no=sequence_no,
            planned_arrival=planned_arrival,
            travel_time_min=travel_time_min,
            travel_distance_m=travel_distance_m,
            unassigned_reason=unassigned_reason,
            explanation=explanation,
            duration_min=duration_min,
        )
        for (
            ticket_id,
            engineer_id,
            sequence_no,
            planned_arrival,
            travel_time_min,
            travel_distance_m,
            unassigned_reason,
            explanation,
            duration_min,
        ) in rows
    ]
