"""Replanning a region's day plan by one event (Contract Net Protocol, Smith 1980):
`new_urgent_ticket` (announce/bid/award over brigades with the `emergency` skill, with an
eviction cascade of depth exactly 1) and `ticket_cancelled` (drop one visit and shift its
brigade's tail). Synchronous: the caller gets the finished plan in the same request,
unlike `plan_builder.build`.

Does not run the solver again — the point is minimal change (`plan_stability`), which a
full re-solve of the day cannot promise. Feasibility checks (skill, vehicle, window,
shift) are written fresh here, against the brigade's *actual* route reconstructed from the
parent plan rather than an empty schedule, in the style of `baseline.py`; `solver.py`'s own
internals are built around `RoutingModel` and do not fit inserting one ticket into an
already-standing route.
"""

import math
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from typing import Any

from psycopg import AsyncConnection

from src.clients.osrm import TravelMatrix
from src.domain import Engineer, Point, Skill, Ticket, TicketDraft, TicketStatus, VehicleType
from src.errors import Conflict, InvalidInput, NotFound
from src.logging import get_logger
from src.repository.db import database_errors
from src.repository.plans import AssignmentRow, AssignmentWrite, PlanRow
from src.service.explain import UnassignedReason
from src.service.loader import Connect
from src.service.plan_builder import TableClient
from src.service.ticket_types import Classification, TicketTypes

logger = get_logger(__name__)

GetPlan = Callable[[AsyncConnection[Any], int], Awaitable[PlanRow | None]]
ListEngineers = Callable[[AsyncConnection[Any], int], Awaitable[list[Engineer]]]
ListTickets = Callable[[AsyncConnection[Any], int], Awaitable[list[Ticket]]]
ListPlanAssignments = Callable[[AsyncConnection[Any], int], Awaitable[list[AssignmentRow]]]
InsertTicket = Callable[[AsyncConnection[Any], int, TicketDraft], Awaitable[int]]
InsertReplannedPlan = Callable[
    [AsyncConnection[Any], int, int, date, str, int, datetime, list[AssignmentWrite]],
    Awaitable[int],
]

# A ticket's server-assigned fields for `new_urgent_ticket`; on-site time is a fixed
# estimate, there being no historical data for an accident yet.
_INCIDENT_SKILL = Skill.EMERGENCY
_INCIDENT_PRIORITY = 1
_INCIDENT_DURATION_MIN = 80
# Never a real ticket id (those are positive, database-assigned): stands in for the
# incident while its bid is computed, before it is actually inserted.
_PLACEHOLDER_TICKET_ID = -1


@dataclass(frozen=True)
class IncidentInput:
    """The client's input for `new_urgent_ticket`; `required_skill`, `priority`,
    `duration_min` and the window are added by `Replanner`, not carried here."""

    external_id: str
    type_bk: str | None
    type_hd: str
    district: str | None
    address: str
    location: Point
    required_vehicle: VehicleType | None


@dataclass(frozen=True)
class NewUrgentTicketEvent:
    triggered_at: datetime
    ticket: IncidentInput
    reaction_min: int


@dataclass(frozen=True)
class RegularTicketInput:
    """The client's input for `new_ticket`; `required_skill`/`priority`/`duration_min`
    come from the ticket-type table (`type_bk`/`type_hd`), as at file load, not from this
    input — unlike `IncidentInput`'s window, this one's window is the client's own."""

    external_id: str
    type_bk: str | None
    type_hd: str
    district: str | None
    address: str
    location: Point
    required_vehicle: VehicleType | None
    window_start: datetime
    window_end: datetime


@dataclass(frozen=True)
class NewTicketEvent:
    triggered_at: datetime
    ticket: RegularTicketInput


@dataclass(frozen=True)
class TicketCancelledEvent:
    triggered_at: datetime
    ticket_id: int


ReplanEvent = NewUrgentTicketEvent | NewTicketEvent | TicketCancelledEvent


@dataclass(frozen=True)
class AssignmentChange:
    ticket_id: int
    before_engineer_id: int
    after_engineer_id: int
    before_sequence_no: int
    after_sequence_no: int


@dataclass(frozen=True)
class PlanDiff:
    changed_assignments: list[AssignmentChange]
    newly_assigned: list[int]
    newly_unassigned: list[int]
    plan_stability: int


@dataclass(frozen=True)
class ReplanOutcome:
    plan_id: int
    parent_plan_id: int
    algorithm: str
    engineer_set_id: int
    diff: PlanDiff


@dataclass(frozen=True)
class _StopDef:
    """A ticket as a stop to walk through: its own location/window/duration, independent
    of any particular route."""

    ticket_id: int
    location: Point
    window_start: datetime
    window_end: datetime
    duration_min: int


@dataclass(frozen=True)
class _StopResult:
    ticket_id: int
    arrival: datetime
    start: datetime
    end: datetime
    travel_min: int
    distance_m: float


@dataclass(frozen=True)
class _CandidateState:
    """One brigade's reconstructed state at `triggered_at`, with a travel matrix already
    fetched over its anchor point, its tail (in original order) and the target ticket —
    reused across the strict bid, the naive (eviction) bid, and every eviction retry."""

    engineer: Engineer
    frozen: list[AssignmentRow]
    """The brigade's `in_progress` visit, if any — unchanged, and always first."""
    stops: list[_StopDef]
    """Tail stops (nodes `1..len(tail)`) followed by the target (node `target_node`)."""
    target_node: int
    available_nodes: list[int]
    matrix: TravelMatrix
    anchor_time: datetime
    shift_end: datetime


@dataclass(frozen=True)
class _Bid:
    engineer: Engineer
    frozen: list[AssignmentRow]
    order: list[int]
    """Node order after the anchor, the target included wherever it was inserted."""
    results: list[_StopResult]
    target_node: int

    @property
    def target_result(self) -> _StopResult:
        return self.results[self.order.index(self.target_node)]


@dataclass(frozen=True)
class _FreeSlot:
    """A `new_ticket` candidate's winning gap: `position` is where it goes in `tail`
    (`0..len(tail)`); nothing in `tail` is recomputed, so `result` is the only new time."""

    engineer: Engineer
    frozen: list[AssignmentRow]
    tail: list[AssignmentRow]
    position: int
    result: _StopResult


@dataclass(frozen=True)
class Replanner:
    connect: Connect
    get_plan: GetPlan
    list_engineers: ListEngineers
    list_tickets: ListTickets
    list_plan_assignments: ListPlanAssignments
    insert_ticket: InsertTicket
    insert_replanned_plan: InsertReplannedPlan
    osrm: TableClient
    ticket_types: TicketTypes
    clock: Callable[[], datetime] = datetime.now

    async def replan(self, plan_id: int, event: ReplanEvent) -> ReplanOutcome:
        async with database_errors("plan_replan_read"), self.connect() as conn:
            plan = await self.get_plan(conn, plan_id)
            if plan is None:
                raise NotFound("plan_not_found", params={"plan_id": plan_id})
            if plan.status != "done":
                raise InvalidInput(
                    "plan_not_ready",
                    message="План-родитель ещё не готов для перепланирования",
                    params={"plan_id": plan_id, "status": plan.status},
                )
            if event.triggered_at.date() != plan.plan_date:
                raise InvalidInput(
                    "triggered_at_out_of_range",
                    message="Момент события не приходится на дату плана",
                    params={"plan_id": plan_id},
                )
            engineers = await self.list_engineers(conn, plan.engineer_set_id)
            tickets = await self.list_tickets(conn, plan.region_id)
            parent_rows = await self.list_plan_assignments(conn, plan_id)

        tickets_by_id: dict[int, Ticket] = {t.id: t for t in tickets}
        draft: TicketDraft | None = None
        if isinstance(event, NewUrgentTicketEvent):
            draft = _incident_draft(plan.plan_date, event)
            new_ticket = _ticket_from_draft(_PLACEHOLDER_TICKET_ID, draft)
            tickets_by_id[_PLACEHOLDER_TICKET_ID] = new_ticket
            writes = await self._new_urgent_ticket(
                plan, event, new_ticket, engineers, tickets_by_id, parent_rows
            )
            event_type = "new_urgent_ticket"
        elif isinstance(event, NewTicketEvent):
            _validate_regular_ticket_window(plan.plan_date, event.ticket)
            classification = self.ticket_types.classify(event.ticket.type_bk, event.ticket.type_hd)
            if classification is None:
                raise InvalidInput(
                    "ticket_type_unknown",
                    message="Пара типов заявки (type_bk, type_hd) не найдена в таблице соответствия",
                )
            draft = _regular_draft(event, classification)
            new_ticket = _ticket_from_draft(_PLACEHOLDER_TICKET_ID, draft)
            tickets_by_id[_PLACEHOLDER_TICKET_ID] = new_ticket
            writes = await self._new_ticket(
                plan, event, new_ticket, engineers, tickets_by_id, parent_rows
            )
            event_type = "new_ticket"
        else:
            ticket = tickets_by_id.get(event.ticket_id)
            if ticket is None:
                raise NotFound("ticket_not_found", params={"ticket_id": event.ticket_id})
            if ticket.status is not TicketStatus.CANCELLED:
                raise Conflict("ticket_not_cancelled", params={"ticket_id": event.ticket_id})
            writes = await self._ticket_cancelled(
                plan, event, engineers, tickets_by_id, parent_rows
            )
            event_type = "ticket_cancelled"

        async with database_errors("plan_replan_write"), self.connect() as conn:
            if draft is not None:
                ticket_id = await self.insert_ticket(conn, plan.region_id, draft)
                writes = _remap_ticket_id(writes, _PLACEHOLDER_TICKET_ID, ticket_id)
            diff = _diff(parent_rows, writes)
            new_plan_id = await self.insert_replanned_plan(
                conn,
                plan.region_id,
                plan.engineer_set_id,
                plan.plan_date,
                plan.algorithm,
                plan.id,
                self.clock(),
                writes,
            )

        logger.info(
            "plan_replan_finished",
            plan_id=new_plan_id,
            parent_plan_id=plan_id,
            event_type=event_type,
            plan_stability=diff.plan_stability,
        )
        return ReplanOutcome(
            plan_id=new_plan_id,
            parent_plan_id=plan_id,
            algorithm=plan.algorithm,
            engineer_set_id=plan.engineer_set_id,
            diff=diff,
        )

    async def _new_urgent_ticket(
        self,
        plan: PlanRow,
        event: NewUrgentTicketEvent,
        new_ticket: Ticket,
        engineers: Sequence[Engineer],
        tickets_by_id: dict[int, Ticket],
        parent_rows: Sequence[AssignmentRow],
    ) -> list[AssignmentWrite]:
        rows_by_engineer = _rows_by_engineer(parent_rows)
        target = _stop_def(new_ticket)
        ticket_id = new_ticket.id
        touched: dict[int, list[AssignmentWrite]] = {}
        unassigned_writes: list[AssignmentWrite] = []

        skilled = [e for e in engineers if _INCIDENT_SKILL in e.skills]
        candidates = [e for e in skilled if new_ticket.required_vehicle in (None, e.vehicle_type)]
        if not candidates:
            reason = UnassignedReason.NO_SKILL if not skilled else UnassignedReason.NO_VEHICLE
            unassigned_writes.append(
                _unassigned_write(ticket_id, reason, _incident_unassigned_text(reason))
            )
            return _assemble(parent_rows, touched, unassigned_writes)

        states = {
            e.id: await _candidate_state(
                self.osrm,
                e,
                rows_by_engineer.get(e.id, ()),
                tickets_by_id,
                event.triggered_at,
                plan.plan_date,
                target,
            )
            for e in candidates
        }
        bids = [b for e in candidates if (b := _bid(states[e.id], strict=True)) is not None]

        if bids:
            winner = _select_winner(bids, event.triggered_at, event.reaction_min)
            note = _incident_note(
                winner.engineer, ticket_id, event.triggered_at, event.reaction_min
            )
            touched[winner.engineer.id] = _writes_from_bid(winner.engineer, winner, note)
            return _assemble(parent_rows, touched, unassigned_writes)

        no_slot_reason = UnassignedReason.ALL_ELIGIBLE_ENGINEERS_BOOKED_ELSEWHERE
        naive_bids = [b for e in candidates if (b := _bid(states[e.id], strict=False)) is not None]
        if not naive_bids:
            unassigned_writes.append(
                _unassigned_write(
                    ticket_id, no_slot_reason, _incident_unassigned_text(no_slot_reason)
                )
            )
            return _assemble(parent_rows, touched, unassigned_writes)

        most_suitable = min(naive_bids, key=lambda b: b.target_result.arrival)
        engineer = most_suitable.engineer
        state = states[engineer.id]
        eviction_order = sorted(
            state.available_nodes,
            key=lambda n: (-tickets_by_id[state.stops[n - 1].ticket_id].priority, n),
        )
        eviction_bid: _Bid | None = None
        evicted_node: int | None = None
        for node in eviction_order:
            reduced = [n for n in state.available_nodes if n != node]
            candidate_bid = _bid(state, reduced, strict=True)
            if candidate_bid is not None:
                eviction_bid = candidate_bid
                evicted_node = node
                break

        if eviction_bid is None or evicted_node is None:
            unassigned_writes.append(
                _unassigned_write(
                    ticket_id, no_slot_reason, _incident_unassigned_text(no_slot_reason)
                )
            )
            return _assemble(parent_rows, touched, unassigned_writes)

        note = _incident_note(
            engineer, ticket_id, event.triggered_at, event.reaction_min, evicted=True
        )
        touched[engineer.id] = _writes_from_bid(engineer, eviction_bid, note)

        evicted_ticket = tickets_by_id[state.stops[evicted_node - 1].ticket_id]
        evict_target = _stop_def(evicted_ticket)
        remaining = [
            e
            for e in engineers
            if e.id != engineer.id
            and evicted_ticket.required_skill in e.skills
            and evicted_ticket.required_vehicle in (None, e.vehicle_type)
        ]
        reoffer_bids: list[_Bid] = []
        for candidate in remaining:
            cstate = await _candidate_state(
                self.osrm,
                candidate,
                rows_by_engineer.get(candidate.id, ()),
                tickets_by_id,
                event.triggered_at,
                plan.plan_date,
                evict_target,
            )
            b = _bid(cstate, strict=True)
            if b is not None:
                reoffer_bids.append(b)

        if reoffer_bids:
            reoffer_winner = min(reoffer_bids, key=lambda b: b.target_result.arrival)
            touched[reoffer_winner.engineer.id] = _writes_from_bid(
                reoffer_winner.engineer, reoffer_winner, _reoffer_note(reoffer_winner.engineer)
            )
        else:
            reason = UnassignedReason.NO_SKILL if not remaining else no_slot_reason
            unassigned_writes.append(
                _unassigned_write(evicted_ticket.id, reason, _evicted_unassigned_text(reason))
            )
        return _assemble(parent_rows, touched, unassigned_writes)

    async def _new_ticket(
        self,
        plan: PlanRow,
        event: NewTicketEvent,
        new_ticket: Ticket,
        engineers: Sequence[Engineer],
        tickets_by_id: Mapping[int, Ticket],
        parent_rows: Sequence[AssignmentRow],
    ) -> list[AssignmentWrite]:
        """No announce, no eviction: a candidate only offers a gap in its actual
        route that the new ticket fits into without moving anything already there —
        `tail` itself is never recomputed, only copied forward with a shifted
        `sequence_no`."""
        rows_by_engineer = _rows_by_engineer(parent_rows)
        target = _stop_def(new_ticket)
        ticket_id = new_ticket.id

        skilled = [e for e in engineers if new_ticket.required_skill in e.skills]
        candidates = [e for e in skilled if new_ticket.required_vehicle in (None, e.vehicle_type)]
        if not candidates:
            reason = UnassignedReason.NO_SKILL if not skilled else UnassignedReason.NO_VEHICLE
            write = _unassigned_write(ticket_id, reason, _regular_unassigned_text(reason))
            return _assemble(parent_rows, {}, [write])

        best: _FreeSlot | None = None
        for engineer in candidates:
            anchor_point, anchor_time, frozen, tail = _state_at(
                rows_by_engineer.get(engineer.id, ()), tickets_by_id, engineer, event.triggered_at
            )
            points = [
                anchor_point,
                *(tickets_by_id[r.ticket_id].location for r in tail),
                target.location,
            ]
            matrix = await self.osrm.table(engineer.vehicle_type, points)
            shift_end = datetime.combine(plan.plan_date, engineer.shift_end)
            found = _free_slot_position(matrix, anchor_time, tail, tickets_by_id, target, shift_end)
            if found is None:
                continue
            position, result = found
            if best is None or result.arrival < best.result.arrival:
                best = _FreeSlot(
                    engineer=engineer, frozen=frozen, tail=tail, position=position, result=result
                )

        if best is None:
            reason = UnassignedReason.ALL_ELIGIBLE_ENGINEERS_BOOKED_ELSEWHERE
            write = _unassigned_write(ticket_id, reason, _regular_unassigned_text(reason))
            return _assemble(parent_rows, {}, [write])

        offset = len(best.frozen)
        before = [
            _copy_write(best.engineer, r, offset + i)
            for i, r in enumerate(best.tail[: best.position], start=1)
        ]
        new_write = AssignmentWrite(
            ticket_id=best.result.ticket_id,
            engineer_id=best.engineer.id,
            sequence_no=offset + best.position + 1,
            planned_arrival=best.result.arrival,
            travel_time_min=best.result.travel_min,
            travel_distance_m=round(best.result.distance_m),
            unassigned_reason=None,
            explanation=_regular_assigned_text(best.engineer, best.result.arrival),
        )
        after = [
            _copy_write(best.engineer, r, offset + best.position + 1 + i)
            for i, r in enumerate(best.tail[best.position :], start=1)
        ]
        touched = {
            best.engineer.id: _frozen_writes(best.engineer, best.frozen)
            + before
            + [new_write]
            + after
        }
        return _assemble(parent_rows, touched, [])

    async def _ticket_cancelled(
        self,
        plan: PlanRow,
        event: TicketCancelledEvent,
        engineers: Sequence[Engineer],
        tickets_by_id: Mapping[int, Ticket],
        parent_rows: Sequence[AssignmentRow],
    ) -> list[AssignmentWrite]:
        parent_row = next((r for r in parent_rows if r.ticket_id == event.ticket_id), None)
        touched: dict[int, list[AssignmentWrite]] = {}
        if parent_row is not None and parent_row.engineer_id is not None:
            engineer = next(e for e in engineers if e.id == parent_row.engineer_id)
            rows_by_engineer = _rows_by_engineer(parent_rows)
            anchor_point, anchor_time, frozen, tail_rows = _state_at(
                rows_by_engineer.get(engineer.id, ()), tickets_by_id, engineer, event.triggered_at
            )
            tail = [
                _stop_def(tickets_by_id[r.ticket_id])
                for r in sorted(tail_rows, key=lambda r: r.sequence_no or 0)
            ]
            points = [anchor_point, *(s.location for s in tail)]
            matrix = await self.osrm.table(engineer.vehicle_type, points)
            shift_end = datetime.combine(plan.plan_date, engineer.shift_end)
            node_order = list(range(1, len(tail) + 1))
            results = _walk(matrix, anchor_time, node_order, tail, shift_end, strict=True)
            if results is None:
                # Dropping one stop only pulls the rest earlier, never later, so this
                # cannot make a tail that was feasible in the parent plan infeasible.
                results = _walk(matrix, anchor_time, node_order, tail, shift_end, strict=False)
            assert results is not None
            note = _cancel_note(engineer)
            offset = len(frozen)
            tail_writes = [
                AssignmentWrite(
                    ticket_id=r.ticket_id,
                    engineer_id=engineer.id,
                    sequence_no=offset + i,
                    planned_arrival=r.arrival,
                    travel_time_min=r.travel_min,
                    travel_distance_m=round(r.distance_m),
                    unassigned_reason=None,
                    explanation=note(r),
                )
                for i, r in enumerate(results, start=1)
            ]
            touched[engineer.id] = _frozen_writes(engineer, frozen) + tail_writes
        return _assemble(parent_rows, touched, [])


def _incident_draft(plan_date: date, event: NewUrgentTicketEvent) -> TicketDraft:
    day_end = datetime.combine(plan_date, time(23, 59))
    return TicketDraft(
        external_id=event.ticket.external_id,
        type_bk=event.ticket.type_bk,
        type_hd=event.ticket.type_hd,
        required_skill=_INCIDENT_SKILL,
        required_vehicle=event.ticket.required_vehicle,
        priority=_INCIDENT_PRIORITY,
        district=event.ticket.district,
        address=event.ticket.address,
        location=event.ticket.location,
        window_start=event.triggered_at,
        window_end=day_end,
        duration_min=_INCIDENT_DURATION_MIN,
        status=TicketStatus.SENT,
        received_at=event.triggered_at,
    )


def _validate_regular_ticket_window(plan_date: date, ticket: RegularTicketInput) -> None:
    if ticket.window_start >= ticket.window_end:
        raise InvalidInput("window_order", message="Начало окна заявки должно быть раньше конца")
    if ticket.window_start.date() != plan_date or ticket.window_end.date() != plan_date:
        raise InvalidInput(
            "window_date_mismatch", message="Окно заявки не приходится на дату плана"
        )


def _regular_draft(event: NewTicketEvent, classification: Classification) -> TicketDraft:
    return TicketDraft(
        external_id=event.ticket.external_id,
        type_bk=event.ticket.type_bk,
        type_hd=event.ticket.type_hd,
        required_skill=classification.skill,
        required_vehicle=event.ticket.required_vehicle,
        priority=classification.priority,
        district=event.ticket.district,
        address=event.ticket.address,
        location=event.ticket.location,
        window_start=event.ticket.window_start,
        window_end=event.ticket.window_end,
        duration_min=classification.duration_min,
        status=TicketStatus.SENT,
        received_at=event.triggered_at,
    )


def _ticket_from_draft(ticket_id: int, draft: TicketDraft) -> Ticket:
    return Ticket(
        id=ticket_id,
        external_id=draft.external_id,
        type_bk=draft.type_bk,
        type_hd=draft.type_hd,
        required_skill=draft.required_skill,
        required_vehicle=draft.required_vehicle,
        priority=draft.priority,
        district=draft.district,
        address=draft.address,
        location=draft.location,
        window_start=draft.window_start,
        window_end=draft.window_end,
        duration_min=draft.duration_min,
        status=draft.status,
        received_at=draft.received_at,
    )


def _stop_def(ticket: Ticket) -> _StopDef:
    return _StopDef(
        ticket_id=ticket.id,
        location=ticket.location,
        window_start=ticket.window_start,
        window_end=ticket.window_end,
        duration_min=ticket.duration_min,
    )


def _rows_by_engineer(rows: Sequence[AssignmentRow]) -> dict[int, list[AssignmentRow]]:
    by_engineer: dict[int, list[AssignmentRow]] = {}
    for r in rows:
        if r.engineer_id is not None:
            by_engineer.setdefault(r.engineer_id, []).append(r)
    return by_engineer


def _state_at(
    rows: Sequence[AssignmentRow],
    tickets_by_id: Mapping[int, Ticket],
    engineer: Engineer,
    triggered_at: datetime,
) -> tuple[Point, datetime, list[AssignmentRow], list[AssignmentRow]]:
    """The point and time the brigade is free from, the frozen visits (in original order)
    and the visits still open to being moved or evicted (also in original order).
    `completed`/`cancelled` tickets are not open any more and drop out entirely — a
    from-scratch build would not carry them either. `in_progress` is still open (only
    `completed`/`cancelled` are excluded from what a plan covers), but is frozen: it
    freezes the anchor at its own planned end, keeps its own row unchanged as the first
    frozen visit, and is not part of the tail (it cannot be moved or evicted)."""
    anchor_point = engineer.start
    anchor_time = triggered_at
    frozen: list[AssignmentRow] = []
    tail: list[AssignmentRow] = []
    for row in sorted(rows, key=lambda r: r.sequence_no or 0):
        ticket = tickets_by_id[row.ticket_id]
        if ticket.status is TicketStatus.COMPLETED:
            anchor_point = ticket.location
            continue
        if ticket.status is TicketStatus.CANCELLED:
            continue
        if ticket.status is TicketStatus.IN_PROGRESS:
            assert row.planned_arrival is not None
            anchor_point = ticket.location
            anchor_time = row.planned_arrival + timedelta(minutes=row.duration_min)
            frozen.append(row)
            continue
        tail.append(row)
    return anchor_point, anchor_time, frozen, tail


def _walk(
    matrix: TravelMatrix,
    anchor_time: datetime,
    node_order: Sequence[int],
    stops: Sequence[_StopDef],
    shift_end: datetime,
    *,
    strict: bool,
) -> list[_StopResult] | None:
    """Walks `node_order` (node `n` is `stops[n - 1]`) from the anchor (node 0), one leg at
    a time. `strict` rejects a stop arriving after its own `window_end` or finishing after
    `shift_end`; without it, the same times are still computed (a brigade that is already
    running over keeps moving, it does not stop), only nothing is ever rejected on their
    account. Either way, a leg with no route at all (`None` in the matrix) always fails:
    that is not a schedule violation to look past, there is no way to get there."""
    time_ = anchor_time
    from_node = 0
    results: list[_StopResult] = []
    for node in node_order:
        stop = stops[node - 1]
        duration_s = matrix.durations_s[from_node][node]
        distance_m = matrix.distances_m[from_node][node]
        if duration_s is None or distance_m is None:
            return None
        travel_min = math.ceil(duration_s / 60)
        arrival = time_ + timedelta(minutes=travel_min)
        start = max(arrival, stop.window_start)
        if strict and start > stop.window_end:
            return None
        end = start + timedelta(minutes=stop.duration_min)
        if strict and end > shift_end:
            return None
        results.append(
            _StopResult(
                ticket_id=stop.ticket_id,
                arrival=arrival,
                start=start,
                end=end,
                travel_min=travel_min,
                distance_m=distance_m,
            )
        )
        time_ = end
        from_node = node
    return results


def _free_slot_position(
    matrix: TravelMatrix,
    anchor_time: datetime,
    tail: Sequence[AssignmentRow],
    tickets_by_id: Mapping[int, Ticket],
    target: _StopDef,
    shift_end: datetime,
) -> tuple[int, _StopResult] | None:
    """The gap (`0..len(tail)`) with the earliest arrival on `target` that fits without
    moving anything already in `tail`: arriving in `target`'s own window, and — unless
    it is the last gap, checked against `shift_end` instead — not later at the next
    already-promised visit than that visit's own stored `planned_arrival`. Point `i`
    of `matrix` is `tail[i - 1]` for `1 <= i <= len(tail)`, the anchor is point `0`, and
    `target` is point `len(tail) + 1` — the same layout `_candidate_state` builds."""
    k = len(tail)
    best: tuple[int, _StopResult] | None = None
    for p in range(k + 1):
        prev_time = anchor_time if p == 0 else _visit_end(tail[p - 1], tickets_by_id)
        duration_s = matrix.durations_s[p][k + 1]
        distance_m = matrix.distances_m[p][k + 1]
        if duration_s is None or distance_m is None:
            continue
        travel_min = math.ceil(duration_s / 60)
        arrival = prev_time + timedelta(minutes=travel_min)
        start = max(arrival, target.window_start)
        if start > target.window_end:
            continue
        end = start + timedelta(minutes=target.duration_min)
        if p < k:
            next_duration_s = matrix.durations_s[k + 1][p + 1]
            if next_duration_s is None:
                continue
            next_arrival = end + timedelta(minutes=math.ceil(next_duration_s / 60))
            next_planned_arrival = tail[p].planned_arrival
            assert next_planned_arrival is not None
            if next_arrival > next_planned_arrival:
                continue
        elif end > shift_end:
            continue
        result = _StopResult(
            ticket_id=target.ticket_id,
            arrival=arrival,
            start=start,
            end=end,
            travel_min=travel_min,
            distance_m=distance_m,
        )
        if best is None or result.arrival < best[1].arrival:
            best = (p, result)
    return best


def _visit_end(row: AssignmentRow, tickets_by_id: Mapping[int, Ticket]) -> datetime:
    """A brigade that arrives before a ticket's window opens waits for it (as `_walk` and
    `baseline.py` both do) — `row.planned_arrival` is the raw arrival, not the start of
    service, so skipping this `max()` would understate how long the visit actually took."""
    assert row.planned_arrival is not None
    window_start = tickets_by_id[row.ticket_id].window_start
    start = max(row.planned_arrival, window_start)
    return start + timedelta(minutes=row.duration_min)


def _copy_write(engineer: Engineer, row: AssignmentRow, sequence_no: int) -> AssignmentWrite:
    """`row` unchanged but for `sequence_no` — a `new_ticket` gap insertion never
    recomputes an existing visit's time, so this is a copy, not a recomputation."""
    return AssignmentWrite(
        ticket_id=row.ticket_id,
        engineer_id=engineer.id,
        sequence_no=sequence_no,
        planned_arrival=row.planned_arrival,
        travel_time_min=row.travel_time_min,
        travel_distance_m=row.travel_distance_m,
        unassigned_reason=None,
        explanation=row.explanation,
    )


async def _candidate_state(
    osrm: TableClient,
    engineer: Engineer,
    rows: Sequence[AssignmentRow],
    tickets_by_id: Mapping[int, Ticket],
    triggered_at: datetime,
    plan_date: date,
    target: _StopDef,
) -> _CandidateState:
    anchor_point, anchor_time, frozen, tail_rows = _state_at(
        rows, tickets_by_id, engineer, triggered_at
    )
    tail = [
        _stop_def(tickets_by_id[r.ticket_id])
        for r in sorted(tail_rows, key=lambda r: r.sequence_no or 0)
    ]
    stops = [*tail, target]
    points = [anchor_point, *(s.location for s in tail), target.location]
    matrix = await osrm.table(engineer.vehicle_type, points)
    return _CandidateState(
        engineer=engineer,
        frozen=frozen,
        stops=stops,
        target_node=len(tail) + 1,
        available_nodes=list(range(1, len(tail) + 1)),
        matrix=matrix,
        anchor_time=anchor_time,
        shift_end=datetime.combine(plan_date, engineer.shift_end),
    )


def _best_position(
    engineer: Engineer,
    frozen: list[AssignmentRow],
    stops: Sequence[_StopDef],
    available_nodes: Sequence[int],
    target_node: int,
    matrix: TravelMatrix,
    anchor_time: datetime,
    shift_end: datetime,
    *,
    strict: bool,
) -> _Bid | None:
    best: _Bid | None = None
    for p in range(len(available_nodes) + 1):
        order = [*available_nodes[:p], target_node, *available_nodes[p:]]
        results = _walk(matrix, anchor_time, order, stops, shift_end, strict=strict)
        if results is None:
            continue
        bid = _Bid(
            engineer=engineer, frozen=frozen, order=order, results=results, target_node=target_node
        )
        if best is None or bid.target_result.arrival < best.target_result.arrival:
            best = bid
    return best


def _bid(
    state: _CandidateState, available_nodes: Sequence[int] | None = None, *, strict: bool
) -> _Bid | None:
    nodes = state.available_nodes if available_nodes is None else available_nodes
    return _best_position(
        state.engineer,
        state.frozen,
        state.stops,
        nodes,
        state.target_node,
        state.matrix,
        state.anchor_time,
        state.shift_end,
        strict=strict,
    )


def _select_winner(bids: Sequence[_Bid], triggered_at: datetime, reaction_min: int) -> _Bid:
    deadline = triggered_at + timedelta(minutes=reaction_min)
    within_reaction = [b for b in bids if b.target_result.arrival <= deadline]
    pool = within_reaction if within_reaction else bids
    return min(pool, key=lambda b: b.target_result.arrival)


def _frozen_writes(engineer: Engineer, frozen: Sequence[AssignmentRow]) -> list[AssignmentWrite]:
    """The brigade's already-`in_progress` visit(s), carried forward unchanged and first —
    they are open tickets, so `_assemble` must still see a row for them, but they were
    never part of the tail: nothing here was computed against a travel matrix."""
    return [
        AssignmentWrite(
            ticket_id=r.ticket_id,
            engineer_id=engineer.id,
            sequence_no=i,
            planned_arrival=r.planned_arrival,
            travel_time_min=r.travel_time_min,
            travel_distance_m=r.travel_distance_m,
            unassigned_reason=None,
            explanation=r.explanation,
        )
        for i, r in enumerate(frozen, start=1)
    ]


def _writes_from_bid(
    engineer: Engineer, bid: _Bid, note: Callable[[_StopResult], str]
) -> list[AssignmentWrite]:
    offset = len(bid.frozen)
    tail_writes = [
        AssignmentWrite(
            ticket_id=r.ticket_id,
            engineer_id=engineer.id,
            sequence_no=offset + i,
            planned_arrival=r.arrival,
            travel_time_min=r.travel_min,
            travel_distance_m=round(r.distance_m),
            unassigned_reason=None,
            explanation=note(r),
        )
        for i, r in enumerate(bid.results, start=1)
    ]
    return _frozen_writes(engineer, bid.frozen) + tail_writes


def _unassigned_write(
    ticket_id: int, reason: UnassignedReason, explanation: str
) -> AssignmentWrite:
    return AssignmentWrite(
        ticket_id=ticket_id,
        engineer_id=None,
        sequence_no=None,
        planned_arrival=None,
        travel_time_min=None,
        travel_distance_m=None,
        unassigned_reason=reason.value,
        explanation=explanation,
    )


def _visit_text(engineer: Engineer, arrival: datetime, reason: str) -> str:
    return f"Бригада «{engineer.name}», прибытие {arrival:%H:%M} — {reason}."


def _incident_note(
    engineer: Engineer,
    target_ticket_id: int,
    triggered_at: datetime,
    reaction_min: int,
    *,
    evicted: bool = False,
) -> Callable[[_StopResult], str]:
    deadline = triggered_at + timedelta(minutes=reaction_min)

    def note(result: _StopResult) -> str:
        if result.ticket_id != target_ticket_id:
            return _visit_text(
                engineer, result.arrival, "маршрут пересчитан из-за вставки аварийной заявки"
            )
        within = result.arrival <= deadline
        placed = (
            "вставлена вытеснением менее приоритетной заявки" if evicted else "вставлена в маршрут"
        )
        reaction = (
            f"в пределах целевой реакции {reaction_min} мин"
            if within
            else f"превышает целевую реакцию {reaction_min} мин — только эта бригада успевает"
        )
        return f"Авария {placed} бригады «{engineer.name}»: прибытие {result.arrival:%H:%M}, {reaction}."

    return note


def _reoffer_note(engineer: Engineer) -> Callable[[_StopResult], str]:
    def note(result: _StopResult) -> str:
        return _visit_text(
            engineer, result.arrival, "переставлена в маршрут после вытеснения аварийной заявкой"
        )

    return note


def _cancel_note(engineer: Engineer) -> Callable[[_StopResult], str]:
    def note(result: _StopResult) -> str:
        return _visit_text(
            engineer, result.arrival, "время визита пересчитано после отмены другой заявки"
        )

    return note


def _incident_unassigned_text(reason: UnassignedReason) -> str:
    if reason is UnassignedReason.NO_SKILL:
        return "Ни одна бригада региона не обладает навыком «Авария»."
    if reason is UnassignedReason.NO_VEHICLE:
        return "Ни одна бригада с навыком «Авария» не располагает нужным транспортом."
    return (
        "Ни одна бригада с навыком «Авария» не успевает принять заявку без нарушения окон "
        "уже согласованных заявок."
    )


def _evicted_unassigned_text(reason: UnassignedReason) -> str:
    if reason is UnassignedReason.NO_SKILL:
        return "Заявка снята вытеснением: ни одна другая бригада не обладает нужным навыком."
    if reason is UnassignedReason.NO_VEHICLE:
        return "Заявка снята вытеснением: ни одна другая бригада не располагает нужным транспортом."
    return "Заявка снята вытеснением и не нашла места среди остальных бригад без нарушения окон."


def _regular_assigned_text(engineer: Engineer, arrival: datetime) -> str:
    return (
        f"Бригада «{engineer.name}», прибытие {arrival:%H:%M} — вставлена в свободный "
        "интервал маршрута, без сдвига уже стоящих заявок."
    )


def _regular_unassigned_text(reason: UnassignedReason) -> str:
    if reason is UnassignedReason.NO_SKILL:
        return "Ни одна бригада региона с нужным навыком не найдена."
    if reason is UnassignedReason.NO_VEHICLE:
        return "Ни одна бригада с нужным навыком не располагает нужным транспортом."
    return "Свободного интервала без сдвига уже стоящих заявок не нашлось ни у одной бригады."


def _remap_ticket_id(
    writes: Sequence[AssignmentWrite], old: int, new: int
) -> list[AssignmentWrite]:
    return [replace(w, ticket_id=new) if w.ticket_id == old else w for w in writes]


def _assemble(
    parent_rows: Sequence[AssignmentRow],
    touched: Mapping[int, list[AssignmentWrite]],
    extra_unassigned: Sequence[AssignmentWrite],
) -> list[AssignmentWrite]:
    """Every open ticket of the region gets exactly one row: a touched brigade's whole
    route is replaced by its entry of `touched` (so a ticket evicted off it and left
    unassigned is dropped here, not copied forward), a ticket named in `extra_unassigned`
    is exactly that, and every other parent row is copied forward unchanged."""
    handled_ticket_ids = {w.ticket_id for rows in touched.values() for w in rows}
    handled_ticket_ids |= {w.ticket_id for w in extra_unassigned}
    writes = [w for rows in touched.values() for w in rows]
    writes += list(extra_unassigned)
    for row in parent_rows:
        if row.ticket_id in handled_ticket_ids:
            continue
        if row.engineer_id is not None and row.engineer_id in touched:
            continue
        writes.append(
            AssignmentWrite(
                ticket_id=row.ticket_id,
                engineer_id=row.engineer_id,
                sequence_no=row.sequence_no,
                planned_arrival=row.planned_arrival,
                travel_time_min=row.travel_time_min,
                travel_distance_m=row.travel_distance_m,
                unassigned_reason=row.unassigned_reason,
                explanation=row.explanation,
            )
        )
    return writes


def _diff(parent_rows: Sequence[AssignmentRow], new_writes: Sequence[AssignmentWrite]) -> PlanDiff:
    parent_by_ticket = {r.ticket_id: r for r in parent_rows}
    changed: list[AssignmentChange] = []
    newly_assigned: list[int] = []
    newly_unassigned: list[int] = []
    changed_engineers: set[int] = set()

    for w in new_writes:
        before = parent_by_ticket.get(w.ticket_id)
        if before is None:
            if w.engineer_id is not None:
                newly_assigned.append(w.ticket_id)
                changed_engineers.add(w.engineer_id)
            continue
        if before.engineer_id is not None and w.engineer_id is not None:
            assert before.sequence_no is not None
            assert w.sequence_no is not None
            if before.engineer_id != w.engineer_id or before.sequence_no != w.sequence_no:
                changed.append(
                    AssignmentChange(
                        ticket_id=w.ticket_id,
                        before_engineer_id=before.engineer_id,
                        after_engineer_id=w.engineer_id,
                        before_sequence_no=before.sequence_no,
                        after_sequence_no=w.sequence_no,
                    )
                )
                changed_engineers.add(before.engineer_id)
                changed_engineers.add(w.engineer_id)
        elif before.engineer_id is not None and w.engineer_id is None:
            newly_unassigned.append(w.ticket_id)
            changed_engineers.add(before.engineer_id)
        elif before.engineer_id is None and w.engineer_id is not None:
            newly_assigned.append(w.ticket_id)
            changed_engineers.add(w.engineer_id)

    return PlanDiff(
        changed_assignments=changed,
        newly_assigned=sorted(newly_assigned),
        newly_unassigned=sorted(newly_unassigned),
        plan_stability=len(changed_engineers),
    )
