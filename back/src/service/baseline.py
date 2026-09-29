"""Baseline plan: first-come-first-served assignment, independent of the OR-Tools solver.

A pure function with the same input/output shape as `src.service.solver.solve_day` — tickets,
brigades, travel matrices by vehicle type and the plan day in, a `DayPlan` out — so the two plans
are comparable without a separate mapping. The algorithm itself does not use OR-Tools and does not
build on the solver's model: one pass over the tickets in input order, each one going to the first
brigade (in input order) that can take it at the end of its current route, with no reordering and no
search for a better fit.
"""

import math
import time
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta

from src.clients.osrm import TravelMatrix
from src.domain import Engineer, Ticket, VehicleType
from src.logging import get_logger
from src.service.solver import DayPlan, EngineerRoute, SolveStatus, Visit

logger = get_logger(__name__)


def solve_day(
    tickets: Sequence[Ticket],
    engineers: Sequence[Engineer],
    matrices: Mapping[VehicleType, TravelMatrix],
    *,
    day: date,
) -> DayPlan:
    """`matrices` hold one matrix per vehicle type of the brigades, all over the same points in
    the same order: the brigades' start points, then the tickets' points (row/column `i` is
    brigade `i` for `i < len(engineers)`, else ticket `i - len(engineers)`).

    Deterministic and never searches, so the result is always `OPTIMAL`: a ticket either meets
    the rule for some brigade or it does not, there is no solution to fail to find in time."""
    started = time.monotonic()
    _validate(tickets, engineers, matrices)
    n_engineers = len(engineers)

    free_at = [datetime.combine(day, e.shift_start) for e in engineers]
    shift_end = [datetime.combine(day, e.shift_end) for e in engineers]
    last_point = list(range(n_engineers))
    visits: list[list[Visit]] = [[] for _ in engineers]
    unassigned: list[int] = []

    for i, ticket in enumerate(tickets):
        node = n_engineers + i
        placed = False
        for v, engineer in enumerate(engineers):
            if ticket.required_skill not in engineer.skills:
                continue
            if (
                ticket.required_vehicle is not None
                and ticket.required_vehicle != engineer.vehicle_type
            ):
                continue
            matrix = matrices[engineer.vehicle_type]
            duration_s = matrix.durations_s[last_point[v]][node]
            distance_m = matrix.distances_m[last_point[v]][node]
            if duration_s is None or distance_m is None:
                continue
            travel_min = math.ceil(duration_s / 60)
            arrival = free_at[v] + timedelta(minutes=travel_min)
            start = max(arrival, ticket.window_start)
            if start > ticket.window_end:
                continue
            end = start + timedelta(minutes=ticket.duration_min)
            if end > shift_end[v]:
                continue
            visits[v].append(
                Visit(
                    ticket_id=ticket.id,
                    arrival=arrival,
                    start=start,
                    end=end,
                    travel_min=travel_min,
                    distance_m=distance_m,
                )
            )
            free_at[v] = end
            last_point[v] = node
            placed = True
            break
        if not placed:
            unassigned.append(ticket.id)

    routes = tuple(
        EngineerRoute(
            engineer_id=e.id,
            visits=tuple(visits[v]),
            idle_min=_idle_min(e, visits[v]),
        )
        for v, e in enumerate(engineers)
    )
    plan = DayPlan(status=SolveStatus.OPTIMAL, routes=routes, unassigned=tuple(unassigned))
    logger.info(
        "baseline_finished",
        duration_ms=round((time.monotonic() - started) * 1000),
        vehicles=len(engineers),
        nodes=len(tickets),
        dropped=len(unassigned),
    )
    return plan


def _validate(
    tickets: Sequence[Ticket],
    engineers: Sequence[Engineer],
    matrices: Mapping[VehicleType, TravelMatrix],
) -> None:
    points = len(engineers) + len(tickets)
    for vehicle in {e.vehicle_type for e in engineers}:
        matrix = matrices.get(vehicle)
        if matrix is None:
            raise ValueError(f"no travel matrix for vehicle type {vehicle}")
        # Checked separately, not as a summed total: an asymmetric short/long pair between the
        # two matrices would otherwise cancel out and pass this check, then fail deep in
        # solve_day's indexing with an unhandled IndexError instead of this ValueError.
        if len(matrix.durations_s) != points or len(matrix.distances_m) != points:
            raise ValueError("travel matrix size differs from brigades + tickets")
        rows = (*matrix.durations_s, *matrix.distances_m)
        if any(len(row) != points for row in rows):
            raise ValueError("travel matrix size differs from brigades + tickets")
    for e in engineers:
        # A defence in depth: the database's own CHECK already rules this out for a stored
        # brigade, and a shift `datetime.combine` cannot represent otherwise would surface as a
        # silently wrong plan (every visit past midnight) rather than this domain error.
        if e.shift_start >= e.shift_end:
            raise ValueError(f"engineer {e.id}: shift does not start before it ends")


def _shift_min(e: Engineer) -> int:
    return (e.shift_end.hour * 60 + e.shift_end.minute) - (
        e.shift_start.hour * 60 + e.shift_start.minute
    )


def _idle_min(e: Engineer, visits: Sequence[Visit]) -> int:
    travel_total = sum(v.travel_min for v in visits)
    duration_total = sum((v.end - v.start) // timedelta(minutes=1) for v in visits)
    return _shift_min(e) - travel_total - duration_total
