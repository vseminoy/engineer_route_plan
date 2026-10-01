"""Reading and writing plan-build rows: a plan is queued (`running`), then finishes
(`done`, with its assignment rows) or fails (`failed`, with a reason) in one later write."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from psycopg import AsyncConnection

from src.repository.db import database_errors, fetch_all, run_query
from src.repository.region_data import queries


@dataclass(frozen=True, kw_only=True)
class PlanRow:
    id: int
    name: str = ""
    region_id: int
    region_code: str
    engineer_set_id: int
    plan_date: date
    algorithm: str
    status: str
    failed_reason: str | None


@dataclass(frozen=True, kw_only=True)
class PlanSummaryRow:
    """One row of `GET /api/v1/plan` — no routes, no metrics, just the plan itself."""

    id: int
    name: str = ""
    region_code: str
    engineer_set_id: int
    plan_date: date
    algorithm: str
    status: str
    failed_reason: str | None
    parent_plan_id: int | None
    created_at: datetime


@dataclass(frozen=True)
class LatestBaselinePlan:
    """What `PlanBuilder.enqueue` needs of an existing `baseline_fcfs` plan for a
    `(engineer_set_id, plan_date)` key: whether to return it as-is (`running`/`done`) or
    delete it and build fresh (`failed`)."""

    id: int
    status: str


@dataclass(frozen=True)
class AssignmentRow:
    """One row of a `done` plan: assigned (`engineer_id` and the rest of the route
    fields) or not (`unassigned_reason`), never both. `duration_min` and `window_start`
    are the ticket's, needed to compute its brigade's idle time: the route's last visit
    may still be waiting for its own window at `planned_arrival` (the raw arrival, which
    can precede it), and that wait must be measured from `max(planned_arrival,
    window_start)`, not from `planned_arrival` itself."""

    ticket_id: int
    engineer_id: int | None
    sequence_no: int | None
    planned_arrival: datetime | None
    travel_time_min: int | None
    travel_distance_m: int | None
    unassigned_reason: str | None
    explanation: str
    duration_min: int
    window_start: datetime


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
    name_suffix: str = "",
) -> tuple[int, str] | None:
    """Returns the new plan's `(id, name)`, or `None` if a concurrent build already holds
    the active baseline slot for this `(engineer_set_id, plan_date)`
    (`ux_plans__active_baseline_per_set_date`) — the caller re-reads the winner instead
    of treating this as a failure.

    The name embeds the id, which Postgres only assigns at insert time, so it is set in
    a second statement right after — both inside one transaction, since a plan row with
    no name should never be observable even transiently."""
    async with conn.transaction():
        row = await run_query(
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
        if row is None:
            return None
        plan_id: int = row[0]
        name = f"План №{plan_id}{name_suffix}"
        await update_plan_name(conn, plan_id, name)
    return plan_id, name


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


async def delete_plan(conn: AsyncConnection[Any], plan_id: int) -> None:
    """Deletes `plan_id` and every plan replanned from it, directly or through a chain,
    with their assignments and replan events — one transaction. A no-op if `plan_id`
    does not exist (the caller checks existence separately, via `get_plan`). Wrapped in
    `database_errors` itself, not just its queries: a closed connection fails opening
    the transaction, before any named query runs."""
    async with database_errors("delete_plan_tree"), conn.transaction():
        await run_query(
            "delete_plan_tree_replan_events",
            lambda: queries.delete_plan_tree_replan_events(conn, plan_id=plan_id),
        )
        await run_query(
            "delete_plan_tree_assignments",
            lambda: queries.delete_plan_tree_assignments(conn, plan_id=plan_id),
        )
        await run_query(
            "delete_plan_tree", lambda: fetch_all(queries.delete_plan_tree(conn, plan_id=plan_id))
        )


async def get_plan(conn: AsyncConnection[Any], plan_id: int) -> PlanRow | None:
    row = await run_query("get_plan", lambda: queries.get_plan(conn, plan_id=plan_id))
    if row is None:
        return None
    (
        id_,
        name,
        region_id,
        region_code,
        engineer_set_id,
        plan_date,
        algorithm,
        status,
        failed_reason,
    ) = row
    return PlanRow(
        id=id_,
        name=name,
        region_id=region_id,
        region_code=region_code,
        engineer_set_id=engineer_set_id,
        plan_date=plan_date,
        algorithm=algorithm,
        status=status,
        failed_reason=failed_reason,
    )


async def get_plan_summary(conn: AsyncConnection[Any], plan_id: int) -> PlanSummaryRow | None:
    """A plan as a list-row shape, by id — used after `PATCH /plan/{plan_id}` to answer
    with the plan's current summary without re-deriving it from `get_plan`'s richer,
    routes-oriented shape."""
    row = await run_query(
        "get_plan_summary", lambda: queries.get_plan_summary(conn, plan_id=plan_id)
    )
    return _plan_summary_row(row) if row is not None else None


async def get_latest_baseline_plan(
    conn: AsyncConnection[Any], engineer_set_id: int, plan_date: date
) -> LatestBaselinePlan | None:
    """The most recent `baseline_fcfs` plan for this key, any status — `None` if there is
    none yet."""
    row = await run_query(
        "get_latest_baseline_plan",
        lambda: queries.get_latest_baseline_plan(
            conn, engineer_set_id=engineer_set_id, plan_date=plan_date
        ),
    )
    return LatestBaselinePlan(id=row[0], status=row[1]) if row is not None else None


async def update_plan_name(conn: AsyncConnection[Any], plan_id: int, name: str) -> None:
    await run_query(
        "update_plan_name", lambda: queries.update_plan_name(conn, plan_id=plan_id, name=name)
    )


def _plan_summary_row(row: tuple[Any, ...]) -> PlanSummaryRow:
    (
        id_,
        name,
        region_code,
        engineer_set_id,
        plan_date,
        algorithm,
        status,
        failed_reason,
        parent_plan_id,
        created_at,
    ) = row
    return PlanSummaryRow(
        id=id_,
        name=name,
        region_code=region_code,
        engineer_set_id=engineer_set_id,
        plan_date=plan_date,
        algorithm=algorithm,
        status=status,
        failed_reason=failed_reason,
        parent_plan_id=parent_plan_id,
        created_at=created_at,
    )


async def list_plans(
    conn: AsyncConnection[Any], region_id: int, engineer_set_id: int | None
) -> list[PlanSummaryRow]:
    """All plans of the region, or (with `engineer_set_id`) only that set's — always
    sorted by `created_at` descending, by the query itself."""
    if engineer_set_id is None:
        rows = await run_query(
            "list_plans_by_region",
            lambda: fetch_all(queries.list_plans_by_region(conn, region_id=region_id)),
        )
    else:
        rows = await run_query(
            "list_plans_by_engineer_set",
            lambda: fetch_all(
                queries.list_plans_by_engineer_set(conn, engineer_set_id=engineer_set_id)
            ),
        )
    return [_plan_summary_row(row) for row in rows]


async def insert_replanned_plan(
    conn: AsyncConnection[Any],
    region_id: int,
    engineer_set_id: int,
    plan_date: date,
    algorithm: str,
    parent_plan_id: int,
    created_at: datetime,
    assignments: list[AssignmentWrite],
) -> tuple[int, str]:
    """A synchronous, already-`done` plan: `replan` never leaves `running`.
    `engineer_set_id` is always the parent plan's own. Returns the new plan's `(id, name)`
    — name is "План №{id}", set once the id is known (see `insert_running_plan`'s same
    two-step reasoning; replan never produces a `baseline_fcfs` plan, so no suffix)."""
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
        name = f"План №{plan_id}"
        await update_plan_name(conn, plan_id, name)
        await _insert_assignments(conn, plan_id, assignments)
    return plan_id, name


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
            window_start=window_start,
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
            window_start,
        ) in rows
    ]
