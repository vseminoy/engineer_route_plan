from collections.abc import Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import pytest

from src.clients.osrm import TravelMatrix
from src.domain import Engineer, Point, Skill, Ticket, TicketDraft, TicketStatus, VehicleType
from src.errors import Conflict, InvalidInput, NotFound
from src.repository.plans import AssignmentRow, AssignmentWrite, PlanRow
from src.service.replan import (
    IncidentInput,
    NewTicketEvent,
    NewUrgentTicketEvent,
    RegularTicketInput,
    Replanner,
    TicketCancelledEvent,
)
from src.service.ticket_types import TicketTypes

TICKET_TYPES = TicketTypes.from_file(Path(__file__).resolve().parents[2] / "data" / "ticket_types.toml")

DAY = date(2026, 9, 1)
TRIGGERED_AT = datetime(2026, 9, 1, 12, 0)
POINT = Point(lat=55.75, lon=37.6)
OTHER_POINT = Point(lat=55.76, lon=37.61)


def _engineer(
    id: int,
    skills: tuple[Skill, ...],
    shift_start: time = time(8, 0),
    shift_end: time = time(20, 0),
    vehicle: VehicleType = VehicleType.CAR,
    start: Point = POINT,
) -> Engineer:
    return Engineer(
        id=id,
        name=f"Бригада {id}",
        start=start,
        shift_start=shift_start,
        shift_end=shift_end,
        vehicle_type=vehicle,
        skills=skills,
    )


def _ticket(
    id: int,
    required_skill: Skill = Skill.LOCAL_WORK,
    required_vehicle: VehicleType | None = None,
    priority: int = 3,
    window_start: datetime = datetime(2026, 9, 1, 8, 0),
    window_end: datetime = datetime(2026, 9, 1, 20, 0),
    duration_min: int = 30,
    status: TicketStatus = TicketStatus.SENT,
) -> Ticket:
    return Ticket(
        id=id,
        external_id=f"T{id}",
        type_bk=None,
        type_hd="Локальная заявка",
        required_skill=required_skill,
        required_vehicle=required_vehicle,
        priority=priority,
        district=None,
        address="адрес",
        location=OTHER_POINT,
        window_start=window_start,
        window_end=window_end,
        duration_min=duration_min,
        status=status,
        received_at=datetime(2026, 9, 1, 0, 0),
    )


def _row(
    ticket_id: int,
    engineer_id: int | None,
    sequence_no: int | None,
    duration_min: int = 30,
    planned_arrival: datetime | None = datetime(2026, 9, 1, 9, 0),
    unassigned_reason: str | None = None,
) -> AssignmentRow:
    assigned = engineer_id is not None
    return AssignmentRow(
        ticket_id=ticket_id,
        engineer_id=engineer_id,
        sequence_no=sequence_no if assigned else None,
        planned_arrival=planned_arrival if assigned else None,
        travel_time_min=5 if assigned else None,
        travel_distance_m=1000 if assigned else None,
        unassigned_reason=unassigned_reason,
        explanation="назначено" if assigned else "не назначено",
        duration_min=duration_min,
    )


INCIDENT = IncidentInput(
    external_id="INC1",
    type_bk=None,
    type_hd="авария",
    district=None,
    address="ул. Аварийная",
    location=OTHER_POINT,
    required_vehicle=None,
)


class FakeConnect:
    @asynccontextmanager
    async def __call__(self) -> Any:
        yield object()


class FakeOsrm:
    """Every leg takes 5 minutes (300 s) and 1 km, except from a point to itself."""

    def __init__(self) -> None:
        self.calls = 0

    async def table(self, _vehicle: VehicleType, points: Sequence[Point]) -> TravelMatrix:
        self.calls += 1
        n = len(points)
        durations: list[list[float | None]] = [
            [0.0 if i == j else 300.0 for j in range(n)] for i in range(n)
        ]
        distances: list[list[float | None]] = [
            [0.0 if i == j else 1000.0 for j in range(n)] for i in range(n)
        ]
        return TravelMatrix(durations_s=durations, distances_m=distances)


@dataclass
class FakeRepo:
    plan: PlanRow
    engineers: list[Engineer]
    tickets: list[Ticket]
    assignments: list[AssignmentRow]
    next_ticket_id: int = 100
    next_plan_id: int = 2
    inserted_tickets: list[TicketDraft] = field(default_factory=list)
    inserted_plans: list[tuple[int, date, str, int, datetime, list[AssignmentWrite]]] = field(
        default_factory=list
    )

    async def get_plan(self, _conn: Any, plan_id: int) -> PlanRow | None:
        return self.plan if plan_id == self.plan.id else None

    async def list_engineers(self, _conn: Any, _region_id: int) -> list[Engineer]:
        return self.engineers

    async def list_tickets(self, _conn: Any, _region_id: int) -> list[Ticket]:
        return self.tickets

    async def list_plan_assignments(self, _conn: Any, _plan_id: int) -> list[AssignmentRow]:
        return self.assignments

    async def insert_ticket(self, _conn: Any, _region_id: int, draft: TicketDraft) -> int:
        self.inserted_tickets.append(draft)
        ticket_id = self.next_ticket_id
        self.next_ticket_id += 1
        return ticket_id

    async def insert_replanned_plan(
        self,
        _conn: Any,
        region_id: int,
        plan_date: date,
        algorithm: str,
        parent_plan_id: int,
        created_at: datetime,
        assignments: list[AssignmentWrite],
    ) -> int:
        self.inserted_plans.append(
            (region_id, plan_date, algorithm, parent_plan_id, created_at, assignments)
        )
        plan_id = self.next_plan_id
        self.next_plan_id += 1
        return plan_id


def _replanner(repo: FakeRepo, osrm: FakeOsrm) -> Replanner:
    return Replanner(
        connect=FakeConnect(),
        get_plan=repo.get_plan,
        list_engineers=repo.list_engineers,
        list_tickets=repo.list_tickets,
        list_plan_assignments=repo.list_plan_assignments,
        insert_ticket=repo.insert_ticket,
        insert_replanned_plan=repo.insert_replanned_plan,
        osrm=osrm,
        ticket_types=TICKET_TYPES,
        clock=lambda: datetime(2026, 9, 1, 12, 0),
    )


def _plan(status: str = "done", region_id: int = 1) -> PlanRow:
    return PlanRow(
        id=10, region_id=region_id, plan_date=DAY, algorithm="or_tools", status=status, failed_reason=None
    )


def _writes_of(repo: FakeRepo) -> list[AssignmentWrite]:
    return repo.inserted_plans[0][5]


def _by_ticket(writes: list[AssignmentWrite], ticket_id: int) -> AssignmentWrite:
    return next(w for w in writes if w.ticket_id == ticket_id)


# --- new_urgent_ticket: direct assignment -------------------------------------------------


async def test_assigns_to_sole_candidate_with_empty_tail() -> None:
    engineer = _engineer(1, (Skill.EMERGENCY,))
    repo = FakeRepo(plan=_plan(), engineers=[engineer], tickets=[], assignments=[])
    replanner = _replanner(repo, FakeOsrm())
    event = NewUrgentTicketEvent(triggered_at=TRIGGERED_AT, ticket=INCIDENT, reaction_min=120)

    outcome = await replanner.replan(10, event)

    assert outcome.parent_plan_id == 10
    assert outcome.diff.newly_assigned == [100]
    assert outcome.diff.plan_stability == 1
    write = _by_ticket(_writes_of(repo), 100)
    assert write.engineer_id == 1
    assert write.sequence_no == 1
    assert write.planned_arrival == datetime(2026, 9, 1, 12, 5)
    assert "в пределах целевой реакции" in write.explanation
    assert repo.inserted_tickets[0].required_skill == Skill.EMERGENCY
    assert repo.inserted_tickets[0].priority == 1
    assert repo.inserted_tickets[0].duration_min == 80


async def test_no_skilled_engineer_leaves_incident_unassigned() -> None:
    engineer = _engineer(1, (Skill.LOCAL_WORK,))
    repo = FakeRepo(plan=_plan(), engineers=[engineer], tickets=[], assignments=[])
    replanner = _replanner(repo, FakeOsrm())
    event = NewUrgentTicketEvent(triggered_at=TRIGGERED_AT, ticket=INCIDENT, reaction_min=120)

    outcome = await replanner.replan(10, event)

    assert outcome.diff.newly_assigned == []
    assert outcome.diff.plan_stability == 0
    write = _by_ticket(_writes_of(repo), 100)
    assert write.engineer_id is None
    assert write.unassigned_reason == "no_skill"


async def test_vehicle_mismatch_leaves_incident_unassigned_no_vehicle() -> None:
    engineer = _engineer(1, (Skill.EMERGENCY,), vehicle=VehicleType.FOOT)
    incident = IncidentInput(
        external_id="INC2",
        type_bk=None,
        type_hd="авария",
        district=None,
        address="ул. Аварийная",
        location=OTHER_POINT,
        required_vehicle=VehicleType.CAR,
    )
    repo = FakeRepo(plan=_plan(), engineers=[engineer], tickets=[], assignments=[])
    replanner = _replanner(repo, FakeOsrm())
    event = NewUrgentTicketEvent(triggered_at=TRIGGERED_AT, ticket=incident, reaction_min=120)

    outcome = await replanner.replan(10, event)

    write = _by_ticket(_writes_of(repo), 100)
    assert write.unassigned_reason == "no_vehicle"
    assert outcome.diff.plan_stability == 0


async def test_assigns_past_reaction_target_when_no_faster_candidate() -> None:
    engineer = _engineer(1, (Skill.EMERGENCY, Skill.LOCAL_WORK), shift_end=time(23, 0))
    tail_ticket = _ticket(
        50,
        window_start=datetime(2026, 9, 1, 12, 0),
        window_end=datetime(2026, 9, 1, 12, 10),
        duration_min=100,
    )
    repo = FakeRepo(
        plan=_plan(),
        engineers=[engineer],
        tickets=[tail_ticket],
        assignments=[_row(50, 1, 1, duration_min=100)],
    )
    replanner = _replanner(repo, FakeOsrm())
    event = NewUrgentTicketEvent(triggered_at=TRIGGERED_AT, ticket=INCIDENT, reaction_min=60)

    outcome = await replanner.replan(10, event)

    assert outcome.diff.newly_assigned == [100]
    write = _by_ticket(_writes_of(repo), 100)
    assert write.engineer_id == 1
    assert write.sequence_no == 2
    assert write.planned_arrival == datetime(2026, 9, 1, 13, 50)
    assert "превышает целевую реакцию" in write.explanation
    tail_write = _by_ticket(_writes_of(repo), 50)
    assert tail_write.sequence_no == 1


async def test_in_progress_visit_is_carried_forward_unchanged_on_touched_engineer() -> None:
    engineer = _engineer(1, (Skill.EMERGENCY,))
    in_progress = _ticket(30, status=TicketStatus.IN_PROGRESS, duration_min=60)
    tail_ticket = _ticket(50, status=TicketStatus.SENT, duration_min=30)
    frozen_row = _row(30, 1, 1, duration_min=60, planned_arrival=datetime(2026, 9, 1, 10, 0))
    tail_row = _row(50, 1, 2, duration_min=30, planned_arrival=datetime(2026, 9, 1, 9, 0))
    repo = FakeRepo(
        plan=_plan(),
        engineers=[engineer],
        tickets=[in_progress, tail_ticket],
        assignments=[frozen_row, tail_row],
    )
    replanner = _replanner(repo, FakeOsrm())
    event = NewUrgentTicketEvent(triggered_at=TRIGGERED_AT, ticket=INCIDENT, reaction_min=120)

    outcome = await replanner.replan(10, event)

    writes = _writes_of(repo)
    assert {w.ticket_id for w in writes} == {30, 50, 100}
    frozen_write = _by_ticket(writes, 30)
    assert frozen_write.engineer_id == 1
    assert frozen_write.sequence_no == 1
    assert frozen_write.planned_arrival == datetime(2026, 9, 1, 10, 0)
    assert frozen_write.explanation == frozen_row.explanation
    incident_write = _by_ticket(writes, 100)
    assert incident_write.sequence_no == 2
    tail_write = _by_ticket(writes, 50)
    assert tail_write.sequence_no == 3
    assert not any(c.ticket_id == 30 for c in outcome.diff.changed_assignments)
    change = next(c for c in outcome.diff.changed_assignments if c.ticket_id == 50)
    assert change.before_sequence_no == 2
    assert change.after_sequence_no == 3


# --- new_urgent_ticket: eviction and re-offer ---------------------------------------------


async def test_eviction_reoffers_blocking_ticket_to_another_brigade() -> None:
    winner = _engineer(1, (Skill.EMERGENCY, Skill.LOCAL_WORK), shift_end=time(13, 30))
    other = _engineer(2, (Skill.LOCAL_WORK,), start=OTHER_POINT)
    blocking = _ticket(
        50,
        required_skill=Skill.LOCAL_WORK,
        priority=5,
        window_start=datetime(2026, 9, 1, 12, 0),
        window_end=datetime(2026, 9, 1, 13, 0),
        duration_min=30,
    )
    repo = FakeRepo(
        plan=_plan(),
        engineers=[winner, other],
        tickets=[blocking],
        assignments=[_row(50, 1, 1, duration_min=30)],
    )
    replanner = _replanner(repo, FakeOsrm())
    event = NewUrgentTicketEvent(triggered_at=TRIGGERED_AT, ticket=INCIDENT, reaction_min=120)

    outcome = await replanner.replan(10, event)

    writes = _writes_of(repo)
    incident_write = _by_ticket(writes, 100)
    assert incident_write.engineer_id == 1
    assert "вытеснением" in incident_write.explanation
    blocking_write = _by_ticket(writes, 50)
    assert blocking_write.engineer_id == 2
    assert "переставлена" in blocking_write.explanation

    change = next(c for c in outcome.diff.changed_assignments if c.ticket_id == 50)
    assert change.before_engineer_id == 1
    assert change.after_engineer_id == 2
    assert outcome.diff.newly_assigned == [100]
    assert outcome.diff.plan_stability == 2


async def test_eviction_without_matching_reoffer_candidate_unassigns_evicted_ticket() -> None:
    winner = _engineer(1, (Skill.EMERGENCY,), shift_end=time(13, 30))
    blocking = _ticket(
        50,
        required_skill=Skill.EMERGENCY,
        priority=5,
        window_start=datetime(2026, 9, 1, 12, 0),
        window_end=datetime(2026, 9, 1, 13, 0),
        duration_min=30,
    )
    repo = FakeRepo(
        plan=_plan(),
        engineers=[winner],
        tickets=[blocking],
        assignments=[_row(50, 1, 1, duration_min=30)],
    )
    replanner = _replanner(repo, FakeOsrm())
    event = NewUrgentTicketEvent(triggered_at=TRIGGERED_AT, ticket=INCIDENT, reaction_min=120)

    outcome = await replanner.replan(10, event)

    writes = _writes_of(repo)
    incident_write = _by_ticket(writes, 100)
    assert incident_write.engineer_id == 1
    blocking_write = _by_ticket(writes, 50)
    assert blocking_write.engineer_id is None
    assert blocking_write.unassigned_reason == "no_skill"
    assert 50 in outcome.diff.newly_unassigned


# --- ticket_cancelled ----------------------------------------------------------------------


async def test_ticket_cancelled_drops_visit_and_shifts_the_tail() -> None:
    engineer = _engineer(1, (Skill.LOCAL_WORK,))
    cancelled = _ticket(50, status=TicketStatus.CANCELLED)
    kept = _ticket(51, status=TicketStatus.SENT)
    repo = FakeRepo(
        plan=_plan(),
        engineers=[engineer],
        tickets=[cancelled, kept],
        assignments=[_row(50, 1, 1), _row(51, 1, 2)],
    )
    replanner = _replanner(repo, FakeOsrm())
    event = TicketCancelledEvent(triggered_at=TRIGGERED_AT, ticket_id=50)

    outcome = await replanner.replan(10, event)

    writes = _writes_of(repo)
    assert all(w.ticket_id != 50 for w in writes)
    kept_write = _by_ticket(writes, 51)
    assert kept_write.sequence_no == 1
    assert kept_write.planned_arrival == datetime(2026, 9, 1, 12, 5)
    assert "отмены" in kept_write.explanation
    change = next(c for c in outcome.diff.changed_assignments if c.ticket_id == 51)
    assert change.before_sequence_no == 2
    assert change.after_sequence_no == 1
    assert outcome.diff.plan_stability == 1


async def test_ticket_cancelled_ticket_not_found() -> None:
    repo = FakeRepo(plan=_plan(), engineers=[], tickets=[], assignments=[])
    replanner = _replanner(repo, FakeOsrm())
    event = TicketCancelledEvent(triggered_at=TRIGGERED_AT, ticket_id=999)

    with pytest.raises(NotFound) as e:
        await replanner.replan(10, event)
    assert e.value.reason == "ticket_not_found"


async def test_ticket_cancelled_ticket_not_yet_cancelled() -> None:
    ticket = _ticket(50, status=TicketStatus.SENT)
    repo = FakeRepo(plan=_plan(), engineers=[], tickets=[ticket], assignments=[])
    replanner = _replanner(repo, FakeOsrm())
    event = TicketCancelledEvent(triggered_at=TRIGGERED_AT, ticket_id=50)

    with pytest.raises(Conflict) as e:
        await replanner.replan(10, event)
    assert e.value.reason == "ticket_not_cancelled"


# --- new_ticket: free-interval insertion (no announce, no eviction) -----------------------

REGULAR_TICKET = RegularTicketInput(
    external_id="REG1",
    type_bk="Локальная заявка",
    type_hd="Нет линка",
    district=None,
    address="ул. Обычная",
    location=OTHER_POINT,
    required_vehicle=None,
    window_start=datetime(2026, 9, 1, 9, 0),
    window_end=datetime(2026, 9, 1, 20, 0),
)


async def test_new_ticket_fits_free_interval_after_last_visit() -> None:
    engineer = _engineer(1, (Skill.LOCAL_WORK,))
    existing = _ticket(
        50,
        required_skill=Skill.LOCAL_WORK,
        window_start=datetime(2026, 9, 1, 9, 0),
        window_end=datetime(2026, 9, 1, 12, 0),
        duration_min=20,
    )
    repo = FakeRepo(
        plan=_plan(),
        engineers=[engineer],
        tickets=[existing],
        assignments=[_row(50, 1, 1, duration_min=20, planned_arrival=datetime(2026, 9, 1, 9, 5))],
    )
    replanner = _replanner(repo, FakeOsrm())
    event = NewTicketEvent(triggered_at=TRIGGERED_AT, ticket=REGULAR_TICKET)

    outcome = await replanner.replan(10, event)

    writes = _writes_of(repo)
    existing_write = _by_ticket(writes, 50)
    assert existing_write.sequence_no == 1
    assert existing_write.planned_arrival == datetime(2026, 9, 1, 9, 5)
    assert existing_write.explanation == "назначено"
    new_write = _by_ticket(writes, 100)
    assert new_write.engineer_id == 1
    assert new_write.sequence_no == 2
    assert new_write.planned_arrival == datetime(2026, 9, 1, 9, 30)
    assert "свободный интервал" in new_write.explanation
    assert repo.inserted_tickets[0].required_skill == Skill.LOCAL_WORK
    assert repo.inserted_tickets[0].priority == 3
    assert repo.inserted_tickets[0].duration_min == 30
    assert outcome.diff.newly_assigned == [100]
    assert not any(c.ticket_id == 50 for c in outcome.diff.changed_assignments)
    assert outcome.diff.plan_stability == 1


async def test_new_ticket_middle_gap_anchors_on_service_start_not_raw_arrival() -> None:
    """A tail visit that arrived early waits for its own window before starting service —
    the next gap's anchor must be the true end of that wait, not `planned_arrival +
    duration_min` alone (that would understate an early arrival's real finish time)."""
    engineer = _engineer(1, (Skill.LOCAL_WORK,))
    early_arrival = _ticket(
        50,
        required_skill=Skill.LOCAL_WORK,
        window_start=datetime(2026, 9, 1, 9, 0),
        window_end=datetime(2026, 9, 1, 20, 0),
        duration_min=10,
    )
    later = _ticket(
        51,
        required_skill=Skill.LOCAL_WORK,
        window_start=datetime(2026, 9, 1, 9, 0),
        window_end=datetime(2026, 9, 1, 20, 0),
        duration_min=15,
    )
    repo = FakeRepo(
        plan=_plan(),
        engineers=[engineer],
        tickets=[early_arrival, later],
        assignments=[
            _row(50, 1, 1, duration_min=10, planned_arrival=datetime(2026, 9, 1, 8, 10)),
            _row(51, 1, 2, duration_min=15, planned_arrival=datetime(2026, 9, 1, 10, 30)),
        ],
    )
    replanner = _replanner(repo, FakeOsrm())
    event = NewTicketEvent(triggered_at=TRIGGERED_AT, ticket=REGULAR_TICKET)

    outcome = await replanner.replan(10, event)

    writes = _writes_of(repo)
    first = _by_ticket(writes, 50)
    assert first.sequence_no == 1
    new_write = _by_ticket(writes, 100)
    assert new_write.sequence_no == 2
    second = _by_ticket(writes, 51)
    assert second.sequence_no == 3
    # 08:10 arrival waits for the 09:00 window, service ends 09:10; +5 min travel = 09:15.
    # The bug under test anchored on 08:10 + 10 = 08:20 instead, giving 08:25.
    assert new_write.planned_arrival == datetime(2026, 9, 1, 9, 15)
    assert outcome.diff.newly_assigned == [100]


async def test_new_ticket_no_skilled_engineer_is_unassigned() -> None:
    engineer = _engineer(1, (Skill.EMERGENCY,))
    repo = FakeRepo(plan=_plan(), engineers=[engineer], tickets=[], assignments=[])
    replanner = _replanner(repo, FakeOsrm())
    event = NewTicketEvent(triggered_at=TRIGGERED_AT, ticket=REGULAR_TICKET)

    outcome = await replanner.replan(10, event)

    write = _by_ticket(_writes_of(repo), 100)
    assert write.engineer_id is None
    assert write.unassigned_reason == "no_skill"
    assert outcome.diff.plan_stability == 0


async def test_new_ticket_no_free_interval_is_unassigned() -> None:
    engineer = _engineer(1, (Skill.LOCAL_WORK,), shift_start=time(8, 0), shift_end=time(11, 0))
    existing = _ticket(
        50,
        required_skill=Skill.LOCAL_WORK,
        window_start=datetime(2026, 9, 1, 9, 0),
        window_end=datetime(2026, 9, 1, 9, 10),
        duration_min=100,
    )
    repo = FakeRepo(
        plan=_plan(),
        engineers=[engineer],
        tickets=[existing],
        assignments=[_row(50, 1, 1, duration_min=100, planned_arrival=datetime(2026, 9, 1, 9, 5))],
    )
    replanner = _replanner(repo, FakeOsrm())
    event = NewTicketEvent(triggered_at=TRIGGERED_AT, ticket=REGULAR_TICKET)

    outcome = await replanner.replan(10, event)

    write = _by_ticket(_writes_of(repo), 100)
    assert write.engineer_id is None
    assert write.unassigned_reason == "all_eligible_engineers_booked_elsewhere"
    assert outcome.diff.plan_stability == 0


async def test_new_ticket_window_order_is_rejected() -> None:
    repo = FakeRepo(plan=_plan(), engineers=[], tickets=[], assignments=[])
    replanner = _replanner(repo, FakeOsrm())
    bad = replace(REGULAR_TICKET, window_start=datetime(2026, 9, 1, 12, 0), window_end=datetime(2026, 9, 1, 12, 0))
    event = NewTicketEvent(triggered_at=TRIGGERED_AT, ticket=bad)

    with pytest.raises(InvalidInput) as e:
        await replanner.replan(10, event)
    assert e.value.reason == "window_order"


async def test_new_ticket_window_date_mismatch_is_rejected() -> None:
    repo = FakeRepo(plan=_plan(), engineers=[], tickets=[], assignments=[])
    replanner = _replanner(repo, FakeOsrm())
    bad = replace(
        REGULAR_TICKET,
        window_start=datetime(2026, 9, 2, 9, 0),
        window_end=datetime(2026, 9, 2, 20, 0),
    )
    event = NewTicketEvent(triggered_at=TRIGGERED_AT, ticket=bad)

    with pytest.raises(InvalidInput) as e:
        await replanner.replan(10, event)
    assert e.value.reason == "window_date_mismatch"


async def test_new_ticket_unknown_type_is_rejected() -> None:
    repo = FakeRepo(plan=_plan(), engineers=[], tickets=[], assignments=[])
    replanner = _replanner(repo, FakeOsrm())
    bad = replace(REGULAR_TICKET, type_bk=None, type_hd="Совершенно неизвестный тип")
    event = NewTicketEvent(triggered_at=TRIGGERED_AT, ticket=bad)

    with pytest.raises(InvalidInput) as e:
        await replanner.replan(10, event)
    assert e.value.reason == "ticket_type_unknown"


# --- validation ------------------------------------------------------------------------


async def test_plan_not_done_is_rejected() -> None:
    repo = FakeRepo(plan=_plan(status="running"), engineers=[], tickets=[], assignments=[])
    replanner = _replanner(repo, FakeOsrm())
    event = NewUrgentTicketEvent(triggered_at=TRIGGERED_AT, ticket=INCIDENT, reaction_min=120)

    with pytest.raises(InvalidInput) as e:
        await replanner.replan(10, event)
    assert e.value.reason == "plan_not_ready"


async def test_plan_not_found() -> None:
    repo = FakeRepo(plan=_plan(), engineers=[], tickets=[], assignments=[])
    replanner = _replanner(repo, FakeOsrm())
    event = NewUrgentTicketEvent(triggered_at=TRIGGERED_AT, ticket=INCIDENT, reaction_min=120)

    with pytest.raises(NotFound):
        await replanner.replan(999, event)


async def test_triggered_at_outside_plan_date_is_rejected() -> None:
    repo = FakeRepo(plan=_plan(), engineers=[], tickets=[], assignments=[])
    replanner = _replanner(repo, FakeOsrm())
    event = NewUrgentTicketEvent(
        triggered_at=datetime(2026, 9, 2, 12, 0), ticket=INCIDENT, reaction_min=120
    )

    with pytest.raises(InvalidInput) as e:
        await replanner.replan(10, event)
    assert e.value.reason == "triggered_at_out_of_range"


# --- unaffected brigades are copied forward -----------------------------------------------


async def test_untouched_engineer_row_is_copied_forward_unchanged() -> None:
    winner = _engineer(1, (Skill.EMERGENCY,))
    bystander = _engineer(2, (Skill.LOCAL_WORK,), start=OTHER_POINT)
    bystander_ticket = _ticket(60, required_skill=Skill.LOCAL_WORK)
    bystander_row = _row(60, 2, 1, planned_arrival=datetime(2026, 9, 1, 9, 30))
    repo = FakeRepo(
        plan=_plan(),
        engineers=[winner, bystander],
        tickets=[bystander_ticket],
        assignments=[bystander_row],
    )
    replanner = _replanner(repo, FakeOsrm())
    event = NewUrgentTicketEvent(triggered_at=TRIGGERED_AT, ticket=INCIDENT, reaction_min=120)

    outcome = await replanner.replan(10, event)

    write = _by_ticket(_writes_of(repo), 60)
    assert write.engineer_id == 2
    assert write.sequence_no == 1
    assert write.planned_arrival == datetime(2026, 9, 1, 9, 30)
    assert write.explanation == "назначено"
    assert not any(c.ticket_id == 60 for c in outcome.diff.changed_assignments)
