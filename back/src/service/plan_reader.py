"""Reads a stored plan for `GET /api/v1/plan/{plan_id}` — no OSRM or solver call.

`running` and `failed` plans have no routes yet (or ever); a `done` plan's assignment
rows are grouped by brigade, sorted back into visit order, and merged with every brigade
of the plan's region — including one with no visits, absent from the stored rows
entirely — so the response always lists all of them. A brigade's idle time is the
waiting time between its visits only — the gap between finishing one visit and leaving
for the next — recomputed here rather than stored: `duration_min` (on-site time) comes
along with each row through its ticket join. Time from shift start to departure for the
first visit, and from finishing the last visit to shift end, is not idle time: the
brigade has no ticket waiting on it there, so nothing to be idle between.

`compare` (`GET /api/v1/plan/{plan_id}/compare`) reads two plans through `get` and
diffs their mandatory metrics (`engineers_used`, `total_distance_km`) — `idle_time` is
excluded, display-only by the same rule that keeps it out of the solver's objective.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Any

from psycopg import AsyncConnection

from src.domain import Engineer
from src.errors import Conflict, InvalidInput, NotFound
from src.repository.db import database_errors
from src.repository.plans import AssignmentRow, PlanRow
from src.service.loader import Connect

GetPlan = Callable[[AsyncConnection[Any], int], Awaitable[PlanRow | None]]
ListEngineers = Callable[[AsyncConnection[Any], int], Awaitable[list[Engineer]]]
ListPlanAssignments = Callable[[AsyncConnection[Any], int], Awaitable[list[AssignmentRow]]]
DeletePlan = Callable[[AsyncConnection[Any], int], Awaitable[None]]


@dataclass(frozen=True)
class VisitRead:
    ticket_id: int
    sequence_no: int
    planned_arrival: datetime
    travel_time_min: int
    travel_distance_km: float
    explanation: str


@dataclass(frozen=True)
class EngineerRouteRead:
    """A brigade with no visits still appears, with an empty `route`."""

    engineer_id: int
    name: str
    route: tuple[VisitRead, ...]
    total_distance_km: float
    total_travel_time_min: int
    idle_time_min: int


@dataclass(frozen=True)
class UnassignedRead:
    ticket_id: int
    reason_code: str
    explanation: str


@dataclass(frozen=True)
class MetricsRead:
    """Mandatory metrics, present only for a `done` plan — see the field descriptions
    on `PlanMetrics` in the contract. `distance_by_engineer`/`idle_time_by_engineer_min`
    key by `engineer_id` (an `int` here; the API layer stringifies the key)."""

    engineers_used: int
    total_distance_km: float
    distance_by_engineer: dict[int, float]
    assigned_count: int
    unassigned_count: int
    idle_time_by_engineer_min: dict[int, int]


@dataclass(frozen=True)
class ComparisonEntryRead:
    metric: str
    main: float
    baseline: float
    delta: float


@dataclass(frozen=True)
class PlanRead:
    """`engineers`/`unassigned`/`metrics` are `None` unless `status == "done"`;
    `engineer_set_id`/`region_code` are always set — they are part of the plan row, not
    of the outcome."""

    plan_id: int
    algorithm: str
    region_code: str
    engineer_set_id: int
    status: str
    failed_reason: str | None
    engineers: tuple[EngineerRouteRead, ...] | None
    unassigned: tuple[UnassignedRead, ...] | None
    metrics: MetricsRead | None


@dataclass(frozen=True)
class PlanReader:
    connect: Connect
    get_plan: GetPlan
    list_engineers: ListEngineers
    list_plan_assignments: ListPlanAssignments
    delete_plan: DeletePlan

    async def get(self, plan_id: int) -> PlanRead:
        async with database_errors("plan_get"), self.connect() as conn:
            row = await self.get_plan(conn, plan_id)
            if row is None:
                raise NotFound("plan_not_found", params={"plan_id": plan_id})
            if row.status != "done":
                return PlanRead(
                    plan_id=row.id,
                    algorithm=row.algorithm,
                    region_code=row.region_code,
                    engineer_set_id=row.engineer_set_id,
                    status=row.status,
                    failed_reason=row.failed_reason,
                    engineers=None,
                    unassigned=None,
                    metrics=None,
                )
            engineers = await self.list_engineers(conn, row.engineer_set_id)
            assignments = await self.list_plan_assignments(conn, plan_id)
        routes = tuple(_engineer_routes(engineers, assignments))
        unassigned = tuple(_unassigned(assignments))
        return PlanRead(
            plan_id=row.id,
            algorithm=row.algorithm,
            region_code=row.region_code,
            engineer_set_id=row.engineer_set_id,
            status=row.status,
            failed_reason=None,
            engineers=routes,
            unassigned=unassigned,
            metrics=_metrics(routes, unassigned),
        )

    async def compare(self, plan_id: int, baseline_plan_id: int) -> tuple[ComparisonEntryRead, ...]:
        """Both plans go through `get`, one at a time — `plan_id` first, so a problem
        with it (not found, not `done`) never touches `baseline_plan_id` at all. Both
        must share `engineer_set_id`: comparing plans of different sets is meaningless
        (different brigade counts)."""
        main = await self.get(plan_id)
        _require_done(main)
        baseline = await self.get(baseline_plan_id)
        _require_done(baseline)
        if main.engineer_set_id != baseline.engineer_set_id:
            raise InvalidInput(
                "engineer_set_mismatch",
                message="Планы построены для разных наборов бригад",
                params={"plan_id": plan_id, "baseline_plan_id": baseline_plan_id},
            )
        assert main.metrics is not None
        assert baseline.metrics is not None
        return tuple(
            ComparisonEntryRead(
                metric=metric, main=main_value, baseline=baseline_value, delta=delta
            )
            for metric, main_value, baseline_value, delta in (
                (
                    "engineers_used",
                    main.metrics.engineers_used,
                    baseline.metrics.engineers_used,
                    main.metrics.engineers_used - baseline.metrics.engineers_used,
                ),
                (
                    "total_distance_km",
                    main.metrics.total_distance_km,
                    baseline.metrics.total_distance_km,
                    round(main.metrics.total_distance_km - baseline.metrics.total_distance_km, 1),
                ),
            )
        )

    async def delete(self, plan_id: int) -> None:
        """Deletes the plan and its whole replan chain. Raises `Conflict` for a plan
        still `running` — the background build behind `POST /plan/build` may still be
        writing assignments into it."""
        async with database_errors("plan_delete"), self.connect() as conn:
            row = await self.get_plan(conn, plan_id)
            if row is None:
                raise NotFound("plan_not_found", params={"plan_id": plan_id})
            if row.status == "running":
                raise Conflict("plan_running", params={"plan_id": plan_id})
            await self.delete_plan(conn, plan_id)


def _visit(a: AssignmentRow) -> VisitRead:
    """`a.engineer_id is not None`: `ck_assignments__assigned_or_reason` guarantees the
    route fields below are all set together."""
    assert a.sequence_no is not None
    assert a.planned_arrival is not None
    assert a.travel_time_min is not None
    assert a.travel_distance_m is not None
    return VisitRead(
        ticket_id=a.ticket_id,
        sequence_no=a.sequence_no,
        planned_arrival=a.planned_arrival,
        travel_time_min=a.travel_time_min,
        travel_distance_km=round(a.travel_distance_m / 1000, 1),
        explanation=a.explanation,
    )


def _engineer_routes(
    engineers: Sequence[Engineer], assignments: Sequence[AssignmentRow]
) -> list[EngineerRouteRead]:
    by_engineer: dict[int, list[AssignmentRow]] = {}
    for a in assignments:
        if a.engineer_id is not None:
            by_engineer.setdefault(a.engineer_id, []).append(a)
    routes = []
    for e in sorted(engineers, key=lambda e: e.id):
        rows = sorted(by_engineer.get(e.id, ()), key=lambda a: a.sequence_no or 0)
        visits = [_visit(a) for a in rows]
        travel_total = sum(v.travel_time_min for v in visits)
        distance_total = sum(v.travel_distance_km for v in visits)
        routes.append(
            EngineerRouteRead(
                engineer_id=e.id,
                name=e.name,
                route=tuple(visits),
                total_distance_km=round(distance_total, 1),
                total_travel_time_min=travel_total,
                idle_time_min=_idle_between_visits(rows),
            )
        )
    return routes


def _idle_between_visits(rows: Sequence[AssignmentRow]) -> int:
    """Sum of the gaps between consecutive visits: the time from finishing one visit
    (`planned_arrival + duration_min`) to leaving for the next (`planned_arrival -
    travel_time_min` of the next row). A route of 0 or 1 visits has no such gap."""
    total = timedelta()
    for prev, curr in pairwise(rows):
        assert prev.planned_arrival is not None
        assert curr.planned_arrival is not None
        assert curr.travel_time_min is not None
        finish = prev.planned_arrival + timedelta(minutes=prev.duration_min)
        departure = curr.planned_arrival - timedelta(minutes=curr.travel_time_min)
        gap = departure - finish
        if gap > timedelta():
            total += gap
    return round(total.total_seconds() / 60)


def _unassigned(assignments: Sequence[AssignmentRow]) -> list[UnassignedRead]:
    unassigned = []
    for a in assignments:
        if a.engineer_id is not None:
            continue
        assert a.unassigned_reason is not None
        unassigned.append(
            UnassignedRead(
                ticket_id=a.ticket_id, reason_code=a.unassigned_reason, explanation=a.explanation
            )
        )
    return unassigned


def _metrics(
    routes: Sequence[EngineerRouteRead], unassigned: Sequence[UnassignedRead]
) -> MetricsRead:
    return MetricsRead(
        engineers_used=sum(1 for r in routes if r.route),
        total_distance_km=round(sum(r.total_distance_km for r in routes), 1),
        distance_by_engineer={r.engineer_id: r.total_distance_km for r in routes},
        assigned_count=sum(len(r.route) for r in routes),
        unassigned_count=len(unassigned),
        idle_time_by_engineer_min={r.engineer_id: r.idle_time_min for r in routes},
    )


def _require_done(plan: PlanRead) -> None:
    if plan.status != "done":
        raise InvalidInput(
            "plan_not_ready",
            message="План ещё не готов для сравнения",
            params={"plan_id": plan.plan_id, "status": plan.status},
        )
