"""Reads a stored plan for `GET /api/v1/plan/{plan_id}` — no OSRM or solver call.

`running` and `failed` plans have no routes yet (or ever); a `done` plan's assignment
rows are grouped by brigade, sorted back into visit order, and merged with every brigade
of the plan's region — including one with no visits, absent from the stored rows
entirely — so the response always lists all of them. A brigade's idle time is its shift
minus the summed travel and on-site time of its visits, recomputed here rather than
stored: `duration_min` (on-site time) comes along with each row through its ticket join.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg import AsyncConnection

from src.domain import Engineer
from src.errors import NotFound
from src.repository.db import database_errors
from src.repository.plans import AssignmentRow, PlanRow
from src.service.loader import Connect

GetPlan = Callable[[AsyncConnection[Any], int], Awaitable[PlanRow | None]]
ListEngineers = Callable[[AsyncConnection[Any], int], Awaitable[list[Engineer]]]
ListPlanAssignments = Callable[[AsyncConnection[Any], int], Awaitable[list[AssignmentRow]]]


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
class PlanRead:
    """`engineers`/`unassigned` are `None` unless `status == "done"`."""

    plan_id: int
    algorithm: str
    status: str
    failed_reason: str | None
    engineers: tuple[EngineerRouteRead, ...] | None
    unassigned: tuple[UnassignedRead, ...] | None


@dataclass(frozen=True)
class PlanReader:
    connect: Connect
    get_plan: GetPlan
    list_engineers: ListEngineers
    list_plan_assignments: ListPlanAssignments

    async def get(self, plan_id: int) -> PlanRead:
        async with database_errors("plan_get"), self.connect() as conn:
            row = await self.get_plan(conn, plan_id)
            if row is None:
                raise NotFound("plan_not_found", params={"plan_id": plan_id})
            if row.status != "done":
                return PlanRead(
                    plan_id=row.id,
                    algorithm=row.algorithm,
                    status=row.status,
                    failed_reason=row.failed_reason,
                    engineers=None,
                    unassigned=None,
                )
            engineers = await self.list_engineers(conn, row.region_id)
            assignments = await self.list_plan_assignments(conn, plan_id)
        return PlanRead(
            plan_id=row.id,
            algorithm=row.algorithm,
            status=row.status,
            failed_reason=None,
            engineers=tuple(_engineer_routes(engineers, assignments)),
            unassigned=tuple(_unassigned(assignments)),
        )


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
        duration_total = sum(a.duration_min for a in rows)
        routes.append(
            EngineerRouteRead(
                engineer_id=e.id,
                name=e.name,
                route=tuple(visits),
                total_distance_km=round(distance_total, 1),
                total_travel_time_min=travel_total,
                idle_time_min=_shift_min(e) - travel_total - duration_total,
            )
        )
    return routes


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


def _shift_min(e: Engineer) -> int:
    return (e.shift_end.hour * 60 + e.shift_end.minute) - (
        e.shift_start.hour * 60 + e.shift_start.minute
    )
