"""Assignment of a region's day of tickets to its brigades: a stepwise (lexicographic)
three-phase OR-Tools RoutingModel solve.

A pure function of its input: tickets, brigades, the travel matrices and the plan day. It never
touches the database or OSRM, and it blocks for the whole time limit. The native solver does not
release the GIL, so a thread pool executor does not free the event loop either: an async caller
needs a separate process, and no more than one solve running at a time.

Time inside the model is whole minutes from midnight of the plan day, naive local time of the
region. Travel time from a matrix is rounded up to a whole minute, so a plan never promises an
arrival sooner than the brigade gets there.
"""

import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import NamedTuple

from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from ortools.constraint_solver.routing_parameters_pb2 import RoutingSearchParameters

from src.clients.osrm import TravelMatrix
from src.domain import Engineer, Ticket, VehicleType
from src.logging import get_logger

logger = get_logger(__name__)

_DAY_MIN = 24 * 60


class SolveStatus(StrEnum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"


@dataclass(frozen=True)
class Visit:
    """Arrival may precede `start`: a brigade that comes before the window waits for it.
    Travel is from the previous visit, or from the brigade's start point."""

    ticket_id: int
    arrival: datetime
    start: datetime
    end: datetime
    travel_min: int
    distance_m: float


@dataclass(frozen=True)
class EngineerRoute:
    """A brigade without visits is not used by the plan.

    `idle_min` is the shift length minus the summed visit and travel time (the whole shift for
    a brigade without visits) — reference only, it plays no part in the solver's objective."""

    engineer_id: int
    visits: tuple[Visit, ...]
    idle_min: int


@dataclass(frozen=True)
class DayPlan:
    """`INFEASIBLE` — no solution was found within the time limit: no routes and no
    unassigned tickets, since there is no plan to speak of."""

    status: SolveStatus
    routes: tuple[EngineerRoute, ...]
    unassigned: tuple[int, ...]


class _Modelled(NamedTuple):
    """A ticket handed to OR-Tools: its model node, the brigades it may go to, and its
    window clamped to the plan day, in minutes from midnight."""

    node: int
    ticket: Ticket
    allowed: list[int]
    opens: int
    closes: int


class _Model(NamedTuple):
    """Everything the phases and the single-pass baseline share: a RoutingModel wired with
    nodes, the time dimension, vehicle windows and disjunctions, but no cost structure yet —
    each solve sets its own before calling it."""

    manager: pywrapcp.RoutingIndexManager
    routing: pywrapcp.RoutingModel
    time_dim: pywrapcp.RoutingDimension
    travel_by_vehicle: dict[VehicleType, list[list[int]]]
    matrix_of: list[int]
    zero_cb: int
    travel_cb: dict[VehicleType, int]
    ticket_index: list[int]
    """Routing index of each modelled ticket, aligned with `modelled`."""
    penalty: list[int]
    """Disjunction penalty of each modelled ticket, aligned with `modelled`."""


def solve_day(
    tickets: Sequence[Ticket],
    engineers: Sequence[Engineer],
    matrices: Mapping[VehicleType, TravelMatrix],
    *,
    day: date,
    time_limit: timedelta,
) -> DayPlan:
    """`matrices` hold one matrix per vehicle type of the brigades, all over the same points in
    the same order: the brigades' start points, then the tickets' points."""
    started = time.monotonic()
    _validate(tickets, engineers, matrices)
    midnight, modelled, unassigned = _model_tickets(tickets, engineers, day)

    if not engineers or not modelled:
        return _finished(
            started,
            DayPlan(
                status=SolveStatus.OPTIMAL,
                routes=tuple(
                    EngineerRoute(engineer_id=e.id, visits=(), idle_min=_shift_min(e))
                    for e in engineers
                ),
                unassigned=tuple(unassigned),
            ),
            vehicles=len(engineers),
            nodes=len(modelled),
        )

    return _solve_lexicographic(
        tickets,
        engineers,
        matrices,
        modelled,
        unassigned,
        midnight=midnight,
        time_limit=time_limit,
        started=started,
    )


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
        rows = (*matrix.durations_s, *matrix.distances_m)
        if len(rows) != 2 * points or any(len(row) != points for row in rows):
            raise ValueError("travel matrix size differs from brigades + tickets")
    for e in engineers:
        # A defence in depth: the database's own CHECK already rules this out for a stored
        # brigade, and a shift OR-Tools cannot represent would otherwise surface as a bare
        # native exception instead of this domain error.
        if e.shift_start >= e.shift_end:
            raise ValueError(f"engineer {e.id}: shift does not start before it ends")


def _model_tickets(
    tickets: Sequence[Ticket], engineers: Sequence[Engineer], day: date
) -> tuple[datetime, list[_Modelled], list[int]]:
    midnight = datetime.combine(day, datetime.min.time())
    unassigned: list[int] = []
    modelled: list[_Modelled] = []
    for i, ticket in enumerate(tickets):
        allowed = [
            v
            for v, e in enumerate(engineers)
            if ticket.required_skill in e.skills
            and (ticket.required_vehicle is None or ticket.required_vehicle == e.vehicle_type)
        ]
        opens = max(0, math.ceil((ticket.window_start - midnight).total_seconds() / 60))
        closes = min(_DAY_MIN, math.floor((ticket.window_end - midnight).total_seconds() / 60))
        # OR-Tools reads an empty list of allowed vehicles as "any vehicle", so a ticket no
        # brigade may take never reaches the model.
        if not allowed or opens > closes:
            unassigned.append(ticket.id)
        else:
            modelled.append(_Modelled(len(engineers) + i, ticket, allowed, opens, closes))
    return midnight, modelled, unassigned


def _shift_min(e: Engineer) -> int:
    return (e.shift_end.hour * 60 + e.shift_end.minute) - (
        e.shift_start.hour * 60 + e.shift_start.minute
    )


def _build_model(
    engineers: Sequence[Engineer],
    matrices: Mapping[VehicleType, TravelMatrix],
    modelled: list[_Modelled],
    *,
    penalty_floor: int,
) -> _Model:
    n_vehicles = len(engineers)
    # Model node k: k < n_vehicles — the start point of brigade k, which is also where its
    # route ends; otherwise ticket modelled[k - n_vehicles]. `matrix_of[k]` is its matrix row.
    matrix_of = list(range(n_vehicles)) + [m.node for m in modelled]
    service = [0] * n_vehicles + [m.ticket.duration_min for m in modelled]
    n_nodes = len(matrix_of)
    # A pair without a route costs more than the whole day, which no cumul can absorb.
    no_route = _DAY_MIN + 1

    manager = pywrapcp.RoutingIndexManager(
        n_nodes, n_vehicles, list(range(n_vehicles)), list(range(n_vehicles))
    )
    routing = pywrapcp.RoutingModel(manager)

    def minutes(seconds: float | None) -> int:
        return no_route if seconds is None else math.ceil(seconds / 60)

    travel_by_vehicle: dict[VehicleType, list[list[int]]] = {}
    for vehicle in {e.vehicle_type for e in engineers}:
        durations = matrices[vehicle].durations_s
        travel_by_vehicle[vehicle] = [
            [
                # The route is open: coming back to the start point costs nothing.
                0 if b < n_vehicles else minutes(durations[matrix_of[a]][matrix_of[b]])
                for b in range(n_nodes)
            ]
            for a in range(n_nodes)
        ]
    zero_cb = routing.RegisterTransitCallback(lambda _a, _b: 0)
    travel_cb = {v: routing.RegisterTransitMatrix(m) for v, m in travel_by_vehicle.items()}
    # Work at a node is spent before leaving it, so it rides on the outgoing arc.
    busy_cb = {
        v: routing.RegisterTransitMatrix(
            [[service[a] + m[a][b] for b in range(n_nodes)] for a in range(n_nodes)]
        )
        for v, m in travel_by_vehicle.items()
    }

    routing.AddDimensionWithVehicleTransits(
        [busy_cb[e.vehicle_type] for e in engineers], _DAY_MIN, _DAY_MIN, False, "Time"
    )
    time_dim = routing.GetDimensionOrDie("Time")

    for v, e in enumerate(engineers):
        shift_start = e.shift_start.hour * 60 + e.shift_start.minute
        shift_end = e.shift_end.hour * 60 + e.shift_end.minute
        time_dim.CumulVar(routing.Start(v)).SetRange(shift_start, shift_end)
        time_dim.CumulVar(routing.End(v)).SetRange(shift_start, shift_end)

    # Scales that never overlap: the least urgent rank still outweighs every combination of
    # more urgent ranks. `penalty_floor` is chosen by the caller: large against fixed/travel
    # costs for a single combined objective, or 1 when a phase's objective is coverage alone.
    penalty_of = _penalties([m.ticket.priority for m in modelled], floor=penalty_floor)

    ticket_index: list[int] = []
    penalty: list[int] = []
    for k, m in enumerate(modelled, start=n_vehicles):
        index = manager.NodeToIndex(k)
        time_dim.CumulVar(index).SetRange(m.opens, m.closes)
        # `SetAllowedVehiclesForIndex` does not accept a Python list in OR-Tools 9.15; the
        # vehicle variable restricted the same way is equivalent, -1 keeps "not performed".
        routing.VehicleVar(index).SetValues([-1, *m.allowed])
        p = penalty_of[m.ticket.priority]
        routing.AddDisjunction([index], p)
        ticket_index.append(index)
        penalty.append(p)

    return _Model(
        manager=manager,
        routing=routing,
        time_dim=time_dim,
        travel_by_vehicle=travel_by_vehicle,
        matrix_of=matrix_of,
        zero_cb=zero_cb,
        travel_cb=travel_cb,
        ticket_index=ticket_index,
        penalty=penalty,
    )


def _search_params(time_limit: timedelta) -> RoutingSearchParameters:
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    )
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    params.time_limit.FromTimedelta(time_limit)
    return params


def _set_costs(
    model: _Model,
    engineers: Sequence[Engineer],
    *,
    arc_cb: Callable[[Engineer], int],
    fixed_cost: int,
) -> None:
    """Wires the term this phase (or the single-pass baseline) means to optimise; `arc_cb`
    picks the travel callback per brigade, or `model.zero_cb` to ignore travel. OR-Tools always
    adds an unassigned ticket's disjunction penalty to `ObjectiveValue()` regardless of this
    call, so a phase search can still trade a little of this term for coverage better than
    `_bound_coverage` requires — harmless, since the bound is a hard `<=`, never an `==`, but
    real: a phase does not necessarily find the minimum of its own term at the coverage level
    the previous phase reached, only a minimum among solutions at or above it."""
    for v, e in enumerate(engineers):
        model.routing.SetArcCostEvaluatorOfVehicle(arc_cb(e), v)
        model.routing.SetFixedCostOfVehicle(fixed_cost, v)


def _bound_coverage(model: _Model, max_penalty: int) -> None:
    """Forbids a solve from leaving more weighted-priority penalty unassigned than an earlier
    phase already achieved — a real constraint on `ActiveVar`, not a hope resting on scale.
    `max_penalty` must be the exact integer `_unassigned_penalty` of that phase's own solution,
    never `Assignment.ObjectiveValue()` (a `double`): a phase's own, already-feasible routes must
    still satisfy the bound the next phase reads back, or its warm start is infeasible for it."""
    solver_ = model.routing.solver()
    unassigned_penalty = solver_.Sum(
        p * (1 - model.routing.ActiveVar(idx))
        for idx, p in zip(model.ticket_index, model.penalty, strict=True)
    )
    solver_.Add(unassigned_penalty <= max_penalty)


def _unassigned_penalty(model: _Model, solution: pywrapcp.Assignment) -> int:
    """The exact weighted-priority penalty of the tickets `solution` left unassigned — read as
    integers off the solved `ActiveVar`s, not off `Assignment.ObjectiveValue()`: with several
    priority ranks, the true sum can exceed a `double`'s exact integer range long before it
    approaches the `int64` OR-Tools itself sums costs in."""
    return sum(
        p * (1 - solution.Value(model.routing.ActiveVar(idx)))
        for idx, p in zip(model.ticket_index, model.penalty, strict=True)
    )


def _bound_fleet(model: _Model, max_used: int, n_vehicles: int) -> None:
    """Forbids a solve from using more brigades than an earlier phase already found sufficient."""
    solver_ = model.routing.solver()
    used = [
        solver_.IsDifferentCstVar(
            model.routing.NextVar(model.routing.Start(v)), model.routing.End(v)
        )
        for v in range(n_vehicles)
    ]
    solver_.Add(solver_.Sum(used) <= max_used)


def _routes_of(model: _Model, solution: pywrapcp.Assignment, n_vehicles: int) -> list[list[int]]:
    """Node sequence per vehicle, for warm-starting the next phase's freshly built model."""
    routes = []
    for v in range(n_vehicles):
        nodes = []
        index = solution.Value(model.routing.NextVar(model.routing.Start(v)))
        while not model.routing.IsEnd(index):
            nodes.append(model.manager.IndexToNode(index))
            index = solution.Value(model.routing.NextVar(index))
        routes.append(nodes)
    return routes


def _vehicles_used(model: _Model, solution: pywrapcp.Assignment, n_vehicles: int) -> int:
    return sum(
        1
        for v in range(n_vehicles)
        if solution.Value(model.routing.NextVar(model.routing.Start(v))) != model.routing.End(v)
    )


def _solve_lexicographic(
    tickets: Sequence[Ticket],
    engineers: Sequence[Engineer],
    matrices: Mapping[VehicleType, TravelMatrix],
    modelled: list[_Modelled],
    unassigned: list[int],
    *,
    midnight: datetime,
    time_limit: timedelta,
    started: float,
) -> DayPlan:
    """Three solves of the same input, one objective at a time, each bound by the previous
    phase's result: maximum weighted coverage, then minimum fleet without giving up coverage,
    then minimum travel without giving up either. A single weighted solve only encourages this
    order through scale; a fresh model per phase and a hard bound guarantee it. OR-Tools locks a
    RoutingModel's cost structure in on its first solve, so each phase gets its own model,
    warm-started from the previous phase's own routes (already feasible for the new bound)."""
    n_vehicles = len(engineers)
    third = time_limit / 3

    model1 = _build_model(engineers, matrices, modelled, penalty_floor=1)
    _set_costs(model1, engineers, arc_cb=lambda _e: model1.zero_cb, fixed_cost=0)
    phase_started = time.monotonic()
    solution1 = model1.routing.SolveWithParameters(_search_params(third))
    if solution1 is None:
        return _finished(
            started,
            DayPlan(status=SolveStatus.INFEASIBLE, routes=(), unassigned=()),
            vehicles=n_vehicles,
            nodes=len(modelled),
        )
    unassigned_penalty = _unassigned_penalty(model1, solution1)
    _log_phase(1, unassigned_penalty, phase_started)

    model2 = _build_model(engineers, matrices, modelled, penalty_floor=1)
    _set_costs(model2, engineers, arc_cb=lambda _e: model2.zero_cb, fixed_cost=1)
    _bound_coverage(model2, unassigned_penalty)
    # The previous phase's own routes are already a feasible starting point for this bound.
    warm2 = model2.routing.ReadAssignmentFromRoutes(
        _routes_of(model1, solution1, n_vehicles), ignore_inactive_indices=True
    )
    phase_started = time.monotonic()
    solution2 = model2.routing.SolveFromAssignmentWithParameters(warm2, _search_params(third))
    if solution2 is None:
        raise AssertionError("phase 2: the warm start from phase 1 is itself feasible")
    fleet = _vehicles_used(model2, solution2, n_vehicles)
    _log_phase(2, fleet, phase_started)

    model3 = _build_model(engineers, matrices, modelled, penalty_floor=1)
    _set_costs(model3, engineers, arc_cb=lambda e: model3.travel_cb[e.vehicle_type], fixed_cost=0)
    _bound_coverage(model3, unassigned_penalty)
    _bound_fleet(model3, fleet, n_vehicles)
    warm3 = model3.routing.ReadAssignmentFromRoutes(
        _routes_of(model2, solution2, n_vehicles), ignore_inactive_indices=True
    )
    phase_started = time.monotonic()
    solution3 = model3.routing.SolveFromAssignmentWithParameters(
        warm3, _search_params(time_limit - 2 * third)
    )
    if solution3 is None:
        raise AssertionError("phase 3: the warm start from phase 2 is itself feasible")
    _log_phase(3, round(solution3.ObjectiveValue()), phase_started)

    plan = _extract_plan(
        tickets, engineers, matrices, modelled, unassigned, model3, solution3, midnight=midnight
    )
    return _finished(started, plan, vehicles=n_vehicles, nodes=len(modelled))


def _solve_single_pass_weighted(
    tickets: Sequence[Ticket],
    engineers: Sequence[Engineer],
    matrices: Mapping[VehicleType, TravelMatrix],
    modelled: list[_Modelled],
    unassigned: list[int],
    *,
    midnight: datetime,
    time_limit: timedelta,
    started: float,
) -> DayPlan:
    """One solve, one objective of three scale-dominated terms (coverage penalty ≫ fixed cost
    per brigade ≫ travel) — the approximation `_solve_lexicographic` replaces, kept only for
    that changeset's own test that the lexicographic result never uses more brigades than this
    one does on the same input: a single heuristic search over one combined objective has no
    guarantee of respecting the scale ordering, only an incentive to."""
    n_vehicles = len(engineers)
    travel_bound = n_vehicles * _DAY_MIN
    brigade_cost = travel_bound + 1
    floor = n_vehicles * brigade_cost + travel_bound + 1
    model = _build_model(engineers, matrices, modelled, penalty_floor=floor)
    _set_costs(
        model, engineers, arc_cb=lambda e: model.travel_cb[e.vehicle_type], fixed_cost=brigade_cost
    )
    solution = model.routing.SolveWithParameters(_search_params(time_limit))
    if solution is None:
        return _finished(
            started,
            DayPlan(status=SolveStatus.INFEASIBLE, routes=(), unassigned=()),
            vehicles=n_vehicles,
            nodes=len(modelled),
        )
    plan = _extract_plan(
        tickets, engineers, matrices, modelled, unassigned, model, solution, midnight=midnight
    )
    return _finished(started, plan, vehicles=n_vehicles, nodes=len(modelled))


def _extract_plan(
    tickets: Sequence[Ticket],
    engineers: Sequence[Engineer],
    matrices: Mapping[VehicleType, TravelMatrix],
    modelled: list[_Modelled],
    unassigned: list[int],
    model: _Model,
    solution: pywrapcp.Assignment,
    *,
    midnight: datetime,
) -> DayPlan:
    n_vehicles = len(engineers)
    routing, manager = model.routing, model.manager
    routes = []
    served: set[int] = set()
    for v, e in enumerate(engineers):
        distances = matrices[e.vehicle_type].distances_m
        travel = model.travel_by_vehicle[e.vehicle_type]
        visits = []
        index = routing.Start(v)
        # The earliest times the route allows: propagation keeps each cumul's lower bound at
        # the earliest feasible start.
        free_at = solution.Min(model.time_dim.CumulVar(index))
        node = manager.IndexToNode(index)
        index = solution.Value(routing.NextVar(index))
        travel_total = 0
        duration_total = 0
        while not routing.IsEnd(index):
            nxt = manager.IndexToNode(index)
            start = solution.Min(model.time_dim.CumulVar(index))
            ticket = modelled[nxt - n_vehicles].ticket
            t = travel[node][nxt]
            visits.append(
                Visit(
                    ticket_id=ticket.id,
                    arrival=midnight + timedelta(minutes=free_at + t),
                    start=midnight + timedelta(minutes=start),
                    end=midnight + timedelta(minutes=start + ticket.duration_min),
                    travel_min=t,
                    # `None` (no route) would have made this arc too costly to be in a
                    # solution; a distance the solver actually used is never missing.
                    distance_m=_require(distances[model.matrix_of[node]][model.matrix_of[nxt]]),
                )
            )
            served.add(ticket.id)
            travel_total += t
            duration_total += ticket.duration_min
            free_at = start + ticket.duration_min
            node = nxt
            index = solution.Value(routing.NextVar(index))
        idle = _shift_min(e) - travel_total - duration_total
        routes.append(EngineerRoute(engineer_id=e.id, visits=tuple(visits), idle_min=idle))

    status = (
        SolveStatus.OPTIMAL
        if routing.status() == routing_enums_pb2.RoutingSearchStatus.ROUTING_OPTIMAL
        else SolveStatus.FEASIBLE
    )
    dropped = unassigned + [m.ticket.id for m in modelled if m.ticket.id not in served]
    order = {t.id: i for i, t in enumerate(tickets)}
    return DayPlan(
        status=status,
        routes=tuple(routes),
        unassigned=tuple(sorted(dropped, key=order.__getitem__)),
    )


def _require(distance_m: float | None) -> float:
    if distance_m is None:
        raise AssertionError("solution uses an arc the travel matrix marked as having no route")
    return distance_m


def _penalties(priorities: Sequence[int], *, floor: int) -> dict[int, int]:
    """Penalty of leaving a ticket unassigned, by priority rank (smaller rank — more urgent):
    the least urgent rank gets `floor`, and each more urgent rank more than all less urgent
    tickets together."""
    penalty: dict[int, int] = {}
    below = 0
    for rank in sorted(set(priorities), reverse=True):
        penalty[rank] = floor + below
        below += penalty[rank] * priorities.count(rank)
    # OR-Tools sums costs in int64.
    if below >= 2**62:
        raise ValueError("too many priority ranks for the penalty scale")
    return penalty


def _log_phase(phase: int, objective: int, phase_started: float) -> None:
    logger.info(
        "solver_phase_finished",
        phase=phase,
        objective=objective,
        duration_ms=round((time.monotonic() - phase_started) * 1000),
    )


def _finished(started: float, plan: DayPlan, *, vehicles: int, nodes: int) -> DayPlan:
    fields = {
        "status": str(plan.status),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "vehicles": vehicles,
        "nodes": nodes,
    }
    if plan.status is SolveStatus.INFEASIBLE:
        logger.warning("solver_finished", **fields)
    else:
        logger.info("solver_finished", **fields, dropped=len(plan.unassigned))
    return plan
