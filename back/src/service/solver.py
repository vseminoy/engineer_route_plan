"""Assignment of a region's day of tickets to its brigades: one OR-Tools RoutingModel solve.

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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import NamedTuple

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

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
    """A brigade without visits is not used by the plan."""

    engineer_id: int
    visits: tuple[Visit, ...]


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

    if not engineers or not modelled:
        return _finished(
            started,
            DayPlan(
                status=SolveStatus.OPTIMAL,
                routes=tuple(EngineerRoute(engineer_id=e.id, visits=()) for e in engineers),
                unassigned=tuple(unassigned),
            ),
            vehicles=len(engineers),
            nodes=len(modelled),
        )

    return _solve(
        tickets,
        engineers,
        matrices,
        modelled,
        unassigned,
        midnight=midnight,
        time_limit=time_limit,
        started=started,
    )


def _solve(
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

    # Scales that never overlap: all travel of a day < one brigade < the cheapest ticket, and
    # every ticket of a rank outweighs all less urgent tickets together.
    travel_bound = n_vehicles * _DAY_MIN
    brigade_cost = travel_bound + 1
    penalty_of = _penalties(
        [m.ticket.priority for m in modelled], floor=n_vehicles * brigade_cost + travel_bound + 1
    )

    for v, e in enumerate(engineers):
        routing.SetArcCostEvaluatorOfVehicle(travel_cb[e.vehicle_type], v)
        routing.SetFixedCostOfVehicle(brigade_cost, v)
        shift_start = e.shift_start.hour * 60 + e.shift_start.minute
        shift_end = e.shift_end.hour * 60 + e.shift_end.minute
        time_dim.CumulVar(routing.Start(v)).SetRange(shift_start, shift_end)
        time_dim.CumulVar(routing.End(v)).SetRange(shift_start, shift_end)

    for k, m in enumerate(modelled, start=n_vehicles):
        index = manager.NodeToIndex(k)
        time_dim.CumulVar(index).SetRange(m.opens, m.closes)
        # `SetAllowedVehiclesForIndex` does not accept a Python list in OR-Tools 9.15; the
        # vehicle variable restricted the same way is equivalent, -1 keeps "not performed".
        routing.VehicleVar(index).SetValues([-1, *m.allowed])
        routing.AddDisjunction([index], penalty_of[m.ticket.priority])

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    )
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    params.time_limit.FromTimedelta(time_limit)
    solution = routing.SolveWithParameters(params)

    if solution is None:
        return _finished(
            started,
            DayPlan(status=SolveStatus.INFEASIBLE, routes=(), unassigned=()),
            vehicles=n_vehicles,
            nodes=len(modelled),
        )

    routes = []
    served: set[int] = set()
    for v, e in enumerate(engineers):
        distances = matrices[e.vehicle_type].distances_m
        travel = travel_by_vehicle[e.vehicle_type]
        visits = []
        index = routing.Start(v)
        # The earliest times the route allows: propagation keeps each cumul's lower bound at
        # the earliest feasible start.
        free_at = solution.Min(time_dim.CumulVar(index))
        node = manager.IndexToNode(index)
        index = solution.Value(routing.NextVar(index))
        while not routing.IsEnd(index):
            nxt = manager.IndexToNode(index)
            start = solution.Min(time_dim.CumulVar(index))
            ticket = modelled[nxt - n_vehicles].ticket
            visits.append(
                Visit(
                    ticket_id=ticket.id,
                    arrival=midnight + timedelta(minutes=free_at + travel[node][nxt]),
                    start=midnight + timedelta(minutes=start),
                    end=midnight + timedelta(minutes=start + ticket.duration_min),
                    travel_min=travel[node][nxt],
                    # `None` (no route) would have made this arc too costly to be in a
                    # solution; a distance the solver actually used is never missing.
                    distance_m=_require(distances[matrix_of[node]][matrix_of[nxt]]),
                )
            )
            served.add(ticket.id)
            free_at = start + ticket.duration_min
            node = nxt
            index = solution.Value(routing.NextVar(index))
        routes.append(EngineerRoute(engineer_id=e.id, visits=tuple(visits)))

    status = (
        SolveStatus.OPTIMAL
        if routing.status() == routing_enums_pb2.RoutingSearchStatus.ROUTING_OPTIMAL
        else SolveStatus.FEASIBLE
    )
    dropped = unassigned + [m.ticket.id for m in modelled if m.ticket.id not in served]
    order = {t.id: i for i, t in enumerate(tickets)}
    return _finished(
        started,
        DayPlan(
            status=status,
            routes=tuple(routes),
            unassigned=tuple(sorted(dropped, key=order.__getitem__)),
        ),
        vehicles=n_vehicles,
        nodes=len(modelled),
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
