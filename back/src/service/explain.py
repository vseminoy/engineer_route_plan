"""Attribution of why a ticket was left unassigned, and a natural-language explanation of
every row of a plan — assigned or not.

A pure function over an already-built `DayPlan` (the solver's or the baseline's; both share the
shape), independent of both: neither algorithm records which constraint group actually rejected
a ticket, only whether it left it unassigned, so attribution re-derives that from the same
tickets, brigades and travel matrices the algorithm itself used.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from src.clients.osrm import TravelMatrix
from src.domain import Engineer, Skill, Ticket, VehicleType
from src.logging import get_logger
from src.service.solver import DayPlan, SolveStatus, Visit

logger = get_logger(__name__)

_SKILL_RU = {
    Skill.LOCAL_WORK: "Локальная заявка",
    Skill.CONNECTION: "Подключение",
    Skill.EMERGENCY: "Авария",
}
# The phrase after "доезжает" in the assigned-visit text.
_VEHICLE_PHRASE_RU = {
    VehicleType.CAR: "на автомобиле",
    VehicleType.FOOT: "пешком",
    VehicleType.BIKE: "на велосипеде",
    VehicleType.PUBLIC_TRANSPORT: "на общественном транспорте",
}
# The noun form, for naming a ticket's required vehicle type.
_VEHICLE_NAME_RU = {
    VehicleType.CAR: "автомобиль",
    VehicleType.FOOT: "пешком",
    VehicleType.BIKE: "велосипед",
    VehicleType.PUBLIC_TRANSPORT: "общественный транспорт",
}


class UnassignedReason(StrEnum):
    NO_SKILL = "no_skill"
    NO_VEHICLE = "no_vehicle"
    NO_TIME_SLOT = "no_time_slot"
    SHIFT_OVERFLOW = "shift_overflow"
    ALL_ELIGIBLE_ENGINEERS_BOOKED_ELSEWHERE = "all_eligible_engineers_booked_elsewhere"


@dataclass(frozen=True)
class ExplainedVisit:
    visit: Visit
    explanation: str


@dataclass(frozen=True)
class ExplainedRoute:
    """Same shape as `EngineerRoute`, each visit paired with its explanation text."""

    engineer_id: int
    visits: tuple[ExplainedVisit, ...]
    idle_min: int


@dataclass(frozen=True)
class UnassignedTicket:
    ticket_id: int
    reason: UnassignedReason
    explanation: str


@dataclass(frozen=True)
class ExplainedPlan:
    status: SolveStatus
    routes: tuple[ExplainedRoute, ...]
    unassigned: tuple[UnassignedTicket, ...]


def explain(
    plan: DayPlan,
    tickets: Sequence[Ticket],
    engineers: Sequence[Engineer],
    matrices: Mapping[VehicleType, TravelMatrix],
    *,
    day: date,
) -> ExplainedPlan:
    """`tickets`, `engineers` and `matrices` must be exactly what was passed to whichever
    algorithm produced `plan`: attribution reads travel by the same point order (brigades'
    starts, then tickets, in this `tickets` order) `solve_day`/`baseline.solve_day` used."""
    if plan.status is SolveStatus.INFEASIBLE:
        return ExplainedPlan(status=plan.status, routes=(), unassigned=())
    _validate(tickets, engineers, matrices)

    by_id = {t.id: t for t in tickets}
    by_engineer_id = {e.id: e for e in engineers}
    node_of = {t.id: len(engineers) + i for i, t in enumerate(tickets)}
    midnight = datetime.combine(day, datetime.min.time())

    routes = []
    for route in plan.routes:
        engineer = by_engineer_id[route.engineer_id]
        visits = tuple(
            ExplainedVisit(visit=v, explanation=_assigned_text(engineer, by_id[v.ticket_id], v))
            for v in route.visits
        )
        routes.append(
            ExplainedRoute(engineer_id=route.engineer_id, visits=visits, idle_min=route.idle_min)
        )

    unassigned = []
    reason_counts: dict[str, int] = {}
    for ticket_id in plan.unassigned:
        ticket = by_id[ticket_id]
        reason, eligible = _attribute(ticket, engineers, matrices, node_of[ticket_id], midnight)
        unassigned.append(
            UnassignedTicket(
                ticket_id=ticket_id,
                reason=reason,
                explanation=_unassigned_text(ticket, reason, eligible),
            )
        )
        logger.debug("unassigned_reason_attributed", ticket_id=ticket_id, reason_code=str(reason))
        reason_counts[str(reason)] = reason_counts.get(str(reason), 0) + 1
    if unassigned:
        logger.info("unassigned_reasons_summary", **reason_counts)

    return ExplainedPlan(status=plan.status, routes=tuple(routes), unassigned=tuple(unassigned))


def _validate(
    tickets: Sequence[Ticket],
    engineers: Sequence[Engineer],
    matrices: Mapping[VehicleType, TravelMatrix],
) -> None:
    """Same shape check as `solver._validate`/`baseline._validate`: attribution indexes the
    matrix by position exactly as they do, so a caller passing mismatched input must fail loudly
    here rather than read a wrong row silently or hit a bare `IndexError` deep in `_attribute`."""
    points = len(engineers) + len(tickets)
    for vehicle in {e.vehicle_type for e in engineers}:
        matrix = matrices.get(vehicle)
        if matrix is None:
            raise ValueError(f"no travel matrix for vehicle type {vehicle}")
        rows = (*matrix.durations_s, *matrix.distances_m)
        if len(rows) != 2 * points or any(len(row) != points for row in rows):
            raise ValueError("travel matrix size differs from brigades + tickets")


def _attribute(
    ticket: Ticket,
    engineers: Sequence[Engineer],
    matrices: Mapping[VehicleType, TravelMatrix],
    node: int,
    midnight: datetime,
) -> tuple[UnassignedReason, int]:
    """Groups of constraints in order, without regard to the plan's actual routes (only a
    candidate's own start point and own shift): the first group that leaves no candidate names
    the reason. Returns the reason and, for `all_eligible_engineers_booked_elsewhere`, how many
    candidates were technically eligible."""
    by_skill = [(i, e) for i, e in enumerate(engineers) if ticket.required_skill in e.skills]
    if not by_skill:
        return UnassignedReason.NO_SKILL, 0

    by_vehicle = [(i, e) for i, e in by_skill if ticket.required_vehicle in (None, e.vehicle_type)]
    if not by_vehicle:
        return UnassignedReason.NO_VEHICLE, 0

    window_reachable = False
    fits_shift = 0
    for i, e in by_vehicle:
        seconds = matrices[e.vehicle_type].durations_s[i][node]
        if seconds is None:
            continue
        travel_min = math.ceil(seconds / 60)
        shift_start = datetime.combine(midnight.date(), e.shift_start)
        shift_end = datetime.combine(midnight.date(), e.shift_end)
        arrival = shift_start + timedelta(minutes=travel_min)
        start = max(arrival, ticket.window_start)
        if start > ticket.window_end:
            continue
        window_reachable = True
        if start + timedelta(minutes=ticket.duration_min) <= shift_end:
            fits_shift += 1

    if not window_reachable:
        return UnassignedReason.NO_TIME_SLOT, 0
    if fits_shift == 0:
        return UnassignedReason.SHIFT_OVERFLOW, 0
    return UnassignedReason.ALL_ELIGIBLE_ENGINEERS_BOOKED_ELSEWHERE, fits_shift


def _assigned_text(engineer: Engineer, ticket: Ticket, visit: Visit) -> str:
    return (
        f"Назначена бригада «{engineer.name}»: обладает навыком «{_SKILL_RU[ticket.required_skill]}», "
        f"свободна в окне {ticket.window_start:%H:%M}–{ticket.window_end:%H:%M}, "
        f"доезжает {_VEHICLE_PHRASE_RU[engineer.vehicle_type]} за {visit.travel_min} мин."
    )


def _unassigned_text(ticket: Ticket, reason: UnassignedReason, eligible: int) -> str:
    skill = _SKILL_RU[ticket.required_skill]
    window = f"{ticket.window_start:%H:%M}–{ticket.window_end:%H:%M}"
    vehicle = (
        f" и транспортом «{_VEHICLE_NAME_RU[ticket.required_vehicle]}»"
        if ticket.required_vehicle
        else ""
    )
    if reason is UnassignedReason.NO_SKILL:
        return f"Ни одна бригада региона с навыком «{skill}» не найдена."
    if reason is UnassignedReason.NO_VEHICLE:
        return f"Ни одна бригада с навыком «{skill}»{vehicle} не найдена."
    if reason is UnassignedReason.NO_TIME_SLOT:
        return f"Ни одна бригада с навыком «{skill}»{vehicle} не успевает прибыть в окно {window}."
    if reason is UnassignedReason.SHIFT_OVERFLOW:
        return (
            f"Бригада с навыком «{skill}»{vehicle} успевает прибыть в окно {window}, но не "
            "успевает закончить работу до конца своей смены."
        )
    return (
        f"Технически подходящих бригад с навыком «{skill}»{vehicle} — {eligible}, но все "
        f"заняты другими заявками в окно {window}."
    )
