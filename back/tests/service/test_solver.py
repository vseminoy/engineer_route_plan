import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date, datetime, time, timedelta

import pytest
from ortools.constraint_solver import pywrapcp

from src.clients.osrm import TravelMatrix
from src.domain import Engineer, Point, Skill, Ticket, TicketStatus, VehicleType
from src.service.solver import DayPlan, EngineerRoute, SolveStatus, Visit, solve_day
from tests.log_records import events, json_logs, records

DAY = date(2026, 9, 1)
LIMIT = timedelta(milliseconds=200)
POINT = Point(lat=55.75, lon=37.6)
CAR, FOOT, BIKE = VehicleType.CAR, VehicleType.FOOT, VehicleType.BIKE
LOCAL, CONNECTION, EMERGENCY = Skill.LOCAL_WORK, Skill.CONNECTION, Skill.EMERGENCY
# Minutes per unit of distance on the line of positions the tests place points on.
PACE = {CAR: 1.0, FOOT: 6.0, BIKE: 3.0, VehicleType.PUBLIC_TRANSPORT: 1.5}


def at(hh: int, mm: int = 0, day: date = DAY) -> datetime:
    return datetime.combine(day, time(hh, mm))


def engineer(
    id: int,
    skills: Sequence[Skill] = (LOCAL,),
    vehicle: VehicleType = CAR,
    shift: tuple[time, time] = (time(10, 0), time(23, 30)),
) -> Engineer:
    return Engineer(
        id=id,
        name=f"Бригада {id}",
        start=POINT,
        shift_start=shift[0],
        shift_end=shift[1],
        vehicle_type=vehicle,
        skills=tuple(skills),
    )


def ticket(
    id: int,
    skill: Skill = LOCAL,
    window: tuple[datetime, datetime] = (at(10), at(22)),
    duration: int = 30,
    priority: int = 3,
    vehicle: VehicleType | None = None,
) -> Ticket:
    return Ticket(
        id=id,
        external_id=f"T{id}",
        type_bk=None,
        type_hd="Тест",
        required_skill=skill,
        required_vehicle=vehicle,
        priority=priority,
        district=None,
        address="адрес",
        location=POINT,
        window_start=window[0],
        window_end=window[1],
        duration_min=duration,
        status=TicketStatus.SENT,
        received_at=at(0),
    )


def line(positions: Sequence[float], vehicles: Sequence[VehicleType] = tuple(PACE)) -> dict:
    """Matrices over points on a line: travel = distance × pace of the vehicle, in seconds;
    distance in km × 1000 metres."""
    return {
        v: TravelMatrix(
            durations_s=[[abs(a - b) * PACE[v] * 60 for b in positions] for a in positions],
            distances_m=[[abs(a - b) * 1000 for b in positions] for a in positions],
        )
        for v in vehicles
    }


def solve(
    tickets: Sequence[Ticket],
    engineers: Sequence[Engineer],
    matrices: Mapping[VehicleType, TravelMatrix],
) -> DayPlan:
    plan = solve_day(tickets, engineers, matrices, day=DAY, time_limit=LIMIT)
    if plan.status is not SolveStatus.INFEASIBLE:
        assert_feasible(plan, tickets, engineers, matrices)
    return plan


def assert_feasible(
    plan: DayPlan,
    tickets: Sequence[Ticket],
    engineers: Sequence[Engineer],
    matrices: Mapping[VehicleType, TravelMatrix],
) -> None:
    """Checks a plan against the hard constraints independently of the solver: travel is
    recomputed from the matrix of the brigade's vehicle, rounded up to a minute."""
    by_id = {t.id: t for t in tickets}
    row = {t.id: len(engineers) + i for i, t in enumerate(tickets)}
    placed = [v.ticket_id for r in plan.routes for v in r.visits] + list(plan.unassigned)
    assert sorted(placed) == sorted(by_id), "every ticket once: in a route or unassigned"
    assert [r.engineer_id for r in plan.routes] == [e.id for e in engineers]
    for route, e in zip(plan.routes, engineers, strict=True):
        durations = matrices[e.vehicle_type].durations_s
        here = engineers.index(e)
        free = datetime.combine(DAY, e.shift_start)
        for visit in route.visits:
            t = by_id[visit.ticket_id]
            assert t.required_skill in e.skills, f"skill: ticket {t.id} to brigade {e.id}"
            assert t.required_vehicle in (None, e.vehicle_type), f"vehicle: ticket {t.id}"
            seconds = durations[here][row[t.id]]
            assert seconds is not None, f"no route to ticket {t.id}"
            earliest = free + timedelta(minutes=math.ceil(seconds / 60))
            assert visit.arrival == earliest, (
                f"arrival not the earliest travel allows: ticket {t.id}"
            )
            assert t.window_start <= visit.start <= t.window_end, f"window: ticket {t.id}"
            # The model works in whole minutes: a window opening mid-minute is only reachable
            # from the next one, same as the solver's own rounding of `window_start`.
            opens = t.window_start.replace(second=0, microsecond=0)
            if opens < t.window_start:
                opens += timedelta(minutes=1)
            expected_start = max(visit.arrival, opens)
            assert visit.start == expected_start, f"work not the earliest start: ticket {t.id}"
            assert visit.end == visit.start + timedelta(minutes=t.duration_min)
            assert visit.end <= datetime.combine(DAY, e.shift_end), f"shift: ticket {t.id}"
            free, here = visit.end, row[t.id]


def visits_of(plan: DayPlan, engineer_id: int) -> tuple[Visit, ...]:
    return next(r.visits for r in plan.routes if r.engineer_id == engineer_id)


def assigned_to(plan: DayPlan, ticket_id: int) -> int | None:
    for r in plan.routes:
        if any(v.ticket_id == ticket_id for v in r.visits):
            return r.engineer_id
    return None


# --- Допустимость: навык и транспорт ---


def test_skill_required() -> None:
    plan = solve(
        [ticket(1, EMERGENCY, priority=1)],
        [engineer(1, [LOCAL]), engineer(2, [EMERGENCY])],
        line([0, 10, 1]),
    )
    assert assigned_to(plan, 1) == 2


def test_no_engineer_with_skill() -> None:
    plan = solve([ticket(1, EMERGENCY)], [engineer(1, [LOCAL, CONNECTION])], line([0, 1]))
    assert plan.unassigned == (1,)
    assert all(not r.visits for r in plan.routes)


def test_required_vehicle() -> None:
    plan = solve(
        [ticket(1, vehicle=FOOT)],
        [engineer(1, vehicle=CAR), engineer(2, vehicle=FOOT)],
        line([0, 5, 1]),
    )
    assert assigned_to(plan, 1) == 2


def test_no_engineer_with_vehicle() -> None:
    plan = solve(
        [ticket(1, vehicle=BIKE)],
        [engineer(1, vehicle=CAR), engineer(2, vehicle=FOOT), engineer(3, [CONNECTION], BIKE)],
        line([0, 0, 0, 1]),
    )
    assert plan.unassigned == (1,)


def test_skill_and_vehicle_together() -> None:
    plan = solve(
        [ticket(1, vehicle=FOOT)],
        [engineer(1, [LOCAL], CAR), engineer(2, [CONNECTION], FOOT), engineer(3, [LOCAL], FOOT)],
        line([0, 0, 0, 1]),
    )
    assert assigned_to(plan, 1) == 3


# --- Время: окна, смены, переезды ---


def test_early_arrival_waits_for_window() -> None:
    plan = solve([ticket(1, window=(at(12), at(14)))], [engineer(1)], line([0, 10]))
    (visit,) = visits_of(plan, 1)
    assert (visit.arrival, visit.start, visit.end) == (at(10, 10), at(12), at(12, 30))


def test_arrival_inside_window() -> None:
    plan = solve([ticket(1, window=(at(10, 30), at(11)))], [engineer(1)], line([0, 20]))
    (visit,) = visits_of(plan, 1)
    assert (visit.arrival, visit.start) == (at(10, 20), at(10, 30))


def test_window_unreachable() -> None:
    plan = solve([ticket(1, window=(at(10), at(10, 15)))], [engineer(1)], line([0, 30]))
    assert plan.unassigned == (1,)


def _not_called(*args: object, **kwargs: object) -> None:
    raise AssertionError("OR-Tools called")


def test_window_outside_plan_day(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pywrapcp.RoutingModel, "SolveWithParameters", _not_called)
    next_day = DAY + timedelta(days=1)
    plan = solve(
        [ticket(1, window=(at(10, day=next_day), at(12, day=next_day)))],
        [engineer(1)],
        line([0, 1]),
    )
    assert plan.unassigned == (1,)
    assert plan.status is SolveStatus.OPTIMAL


def test_window_starts_the_day_before() -> None:
    previous_day = DAY - timedelta(days=1)
    plan = solve(
        [ticket(1, window=(at(22, day=previous_day), at(11)))],
        [engineer(1)],
        line([0, 10]),
    )
    (visit,) = visits_of(plan, 1)
    # The window opened before midnight: only its part inside the plan day counts, so the
    # earliest possible start is the brigade's own departure, not the window's own start.
    assert visit.start == at(10, 10)


def test_window_ends_the_day_after() -> None:
    next_day = DAY + timedelta(days=1)
    fits = solve(
        [ticket(1, window=(at(23), at(1, day=next_day)), duration=30)],
        [engineer(1, shift=(time(10), time(23, 59)))],
        line([0, 5]),
    )
    (visit,) = visits_of(fits, 1)
    # The brigade may arrive well ahead of the window and wait for it, same as
    # `test_early_arrival_waits_for_window`; the window itself opens at 23:00.
    assert visit.start == at(23, 0)

    too_long = solve(
        [ticket(1, window=(at(23), at(1, day=next_day)), duration=70)],
        [engineer(1, shift=(time(10), time(23, 59)))],
        line([0, 5]),
    )
    assert too_long.unassigned == (1,)


def test_window_with_seconds_rounds_up() -> None:
    window = (at(10).replace(second=30), at(12))
    plan = solve([ticket(1, window=window)], [engineer(1)], line([0, 0]))
    (visit,) = visits_of(plan, 1)
    assert visit.start == at(10, 1)


def test_departure_not_before_shift() -> None:
    plan = solve(
        [ticket(1, window=(at(10), at(16)))],
        [engineer(1, shift=(time(15, 30), time(23, 30)))],
        line([0, 10]),
    )
    (visit,) = visits_of(plan, 1)
    assert (visit.arrival, visit.start) == (at(15, 40), at(15, 40))


def test_work_ends_within_shift() -> None:
    plan = solve(
        [ticket(1, window=(at(17), at(17, 30)), duration=70)],
        [engineer(1, shift=(time(10), time(18)))],
        line([0, 10]),
    )
    assert plan.unassigned == (1,)


def test_return_trip_not_counted() -> None:
    plan = solve(
        [ticket(1, window=(at(17), at(17, 30)), duration=55)],
        [engineer(1, shift=(time(10), time(18)))],
        line([0, 60]),
    )
    (visit,) = visits_of(plan, 1)
    assert visit.end == at(17, 55)


def test_shift_capacity() -> None:
    tickets = [ticket(i, duration=50) for i in range(1, 5)]
    plan = solve(tickets, [engineer(1, shift=(time(10), time(12)))], line([0, 5, 10, 15, 20]))
    visits = visits_of(plan, 1)
    assert len(visits) == 2
    assert len(plan.unassigned) == 2
    assert visits[-1].end <= at(12)


def test_travel_by_engineer_profile() -> None:
    plan = solve(
        [ticket(1, window=(at(10), at(10, 30)))],
        [engineer(1, vehicle=CAR), engineer(2, vehicle=FOOT)],
        line([0, 0, 10]),
    )
    assert assigned_to(plan, 1) == 1
    assert visits_of(plan, 1)[0].arrival == at(10, 10)


def test_no_route_between_points() -> None:
    matrices = line([0, 5, 1], [CAR])
    matrices[CAR].durations_s[0][2] = None
    matrices[CAR].distances_m[0][2] = None
    plan = solve([ticket(1)], [engineer(1), engineer(2)], matrices)
    assert assigned_to(plan, 1) == 2

    alone = line([0, 1], [CAR])
    alone[CAR].durations_s[0][1] = None
    alone[CAR].distances_m[0][1] = None
    assert solve([ticket(1)], [engineer(1)], alone).unassigned == (1,)


def test_travel_rounded_up_to_minute() -> None:
    matrices = {CAR: TravelMatrix(durations_s=[[0, 61], [61, 0]], distances_m=[[0, 900], [900, 0]])}
    plan = solve([ticket(1, window=(at(10), at(12)))], [engineer(1)], matrices)
    (visit,) = visits_of(plan, 1)
    assert visit.travel_min == 2
    assert visit.arrival == at(10, 2)


def test_times_naive_whole_minutes() -> None:
    matrices = {
        CAR: TravelMatrix(
            durations_s=[[0, 61, 95], [61, 0, 37], [95, 37, 0]],
            distances_m=[[0, 1, 2], [1, 0, 1], [2, 1, 0]],
        )
    }
    plan = solve([ticket(1), ticket(2)], [engineer(1)], matrices)
    moments = [m for r in plan.routes for v in r.visits for m in (v.arrival, v.start, v.end)]
    assert len(moments) == 6
    for m in moments:
        assert m.tzinfo is None
        assert (m.second, m.microsecond) == (0, 0)
        assert m.date() == DAY


# --- Целевая функция ---


def test_emergency_over_any_lower() -> None:
    skills = [LOCAL, CONNECTION, EMERGENCY]
    tickets = [ticket(1, EMERGENCY, (at(10), at(10, 10)), duration=80, priority=1)] + [
        ticket(i, CONNECTION, (at(10), at(10, 50)), duration=25, priority=2) for i in (2, 3, 4)
    ]
    plan = solve(
        tickets,
        [engineer(1, skills, shift=(time(10), time(11, 30)))],
        line([0, 0, 0, 0, 0]),
    )
    assert assigned_to(plan, 1) == 1
    assert plan.unassigned == (2, 3, 4)


def test_connection_over_repairs() -> None:
    tickets = [ticket(1, CONNECTION, (at(10), at(10, 10)), duration=80, priority=2)] + [
        ticket(i, LOCAL, (at(10), at(10, 40)), duration=30, priority=3) for i in (2, 3)
    ]
    plan = solve(
        tickets,
        [engineer(1, [LOCAL, CONNECTION], shift=(time(10), time(11, 30)))],
        line([0, 0, 0, 0]),
    )
    assert assigned_to(plan, 1) == 1
    assert plan.unassigned == (2, 3)


def test_fewer_engineers_preferred() -> None:
    plan = solve([ticket(i) for i in (1, 2, 3)], [engineer(1), engineer(2)], line([0, 0, 1, 1, 1]))
    used = [r for r in plan.routes if r.visits]
    assert len(used) == 1
    assert len(used[0].visits) == 3


def test_coverage_over_engineers() -> None:
    tickets = [
        ticket(1, window=(at(10), at(10, 10)), duration=60),
        ticket(2, window=(at(10), at(10, 10)), duration=60),
        ticket(3, window=(at(11), at(11, 30)), duration=60),
    ]
    plan = solve(tickets, [engineer(1), engineer(2)], line([0, 0, 0, 0, 0]))
    assert plan.unassigned == ()
    assert sum(1 for r in plan.routes if r.visits) == 2


def test_shorter_order_chosen() -> None:
    plan = solve(
        [ticket(1, duration=10), ticket(2, duration=10), ticket(3, duration=10)],
        [engineer(1)],
        line([0, 30, 10, 20]),
    )
    visits = visits_of(plan, 1)
    assert [v.ticket_id for v in visits] == [2, 3, 1]
    assert sum(v.travel_min for v in visits) == 30


# --- Бригада — одна «машина»; результат ---


def _random_instance(seed: int) -> tuple[list[Ticket], list[Engineer], dict]:
    rnd = random.Random(seed)
    shifts = [(time(10), time(18)), (time(15, 30), time(23, 30)), (time(10), time(23, 30))]
    engineers = [
        engineer(
            i,
            rnd.sample(list(Skill), rnd.randint(1, 3)),
            rnd.choice(list(VehicleType)),
            rnd.choice(shifts),
        )
        for i in (1, 2, 3)
    ]
    tickets = []
    for i in range(101, 109):
        opens = rnd.randint(9 * 60, 21 * 60)
        tickets.append(
            ticket(
                i,
                rnd.choice(list(Skill)),
                (at(0) + timedelta(minutes=opens), at(0) + timedelta(minutes=opens + 120)),
                duration=rnd.choice([20, 30, 70, 80]),
                priority=rnd.randint(1, 3),
                vehicle=rnd.choice([None, None, *VehicleType]),
            )
        )
    positions = [rnd.uniform(0, 30) for _ in range(len(engineers) + len(tickets))]
    return tickets, engineers, line(positions)


def test_route_per_engineer() -> None:
    tickets, engineers, matrices = _random_instance(7)
    plan = solve(tickets, engineers, matrices)
    assert [r.engineer_id for r in plan.routes] == [1, 2, 3]
    placed = [v.ticket_id for r in plan.routes for v in r.visits] + list(plan.unassigned)
    assert sorted(placed) == [t.id for t in tickets]


def test_visit_fields() -> None:
    plan = solve(
        [ticket(1, duration=20), ticket(2, duration=20)],
        [engineer(1, vehicle=BIKE)],
        line([0, 2, 5]),
    )
    first, second = visits_of(plan, 1)
    assert (first.ticket_id, first.travel_min, first.distance_m) == (1, 6, 2000)
    assert (first.arrival, first.start, first.end) == (at(10, 6), at(10, 6), at(10, 26))
    assert (second.ticket_id, second.travel_min, second.distance_m) == (2, 9, 3000)
    assert (second.arrival, second.start, second.end) == (at(10, 35), at(10, 35), at(10, 55))


@pytest.mark.parametrize("seed", range(20))
def test_random_instances_feasible(seed: int) -> None:
    plan = solve(*_random_instance(seed))
    assert plan.status in (SolveStatus.OPTIMAL, SolveStatus.FEASIBLE)


def test_no_engineers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pywrapcp.RoutingModel, "SolveWithParameters", _not_called)
    plan = solve([ticket(1), ticket(2)], [], line([0, 1]))
    assert plan == DayPlan(status=SolveStatus.OPTIMAL, routes=(), unassigned=(1, 2))


def test_no_tickets() -> None:
    plan = solve([], [engineer(1), engineer(2)], line([0, 0]))
    assert plan == DayPlan(
        status=SolveStatus.OPTIMAL,
        routes=(EngineerRoute(1, ()), EngineerRoute(2, ())),
        unassigned=(),
    )


def test_matrix_size_mismatch() -> None:
    with pytest.raises(ValueError):
        solve_day([ticket(1)], [engineer(1)], line([0, 1, 2]), day=DAY, time_limit=LIMIT)


def test_shift_start_not_before_end_rejected() -> None:
    broken = engineer(1, shift=(time(20, 0), time(10, 0)))
    with pytest.raises(ValueError, match="shift"):
        solve_day([ticket(1)], [broken], line([0, 1]), day=DAY, time_limit=LIMIT)


def test_missing_matrix_for_vehicle() -> None:
    with pytest.raises(ValueError):
        solve_day(
            [ticket(1)],
            [engineer(1, vehicle=BIKE)],
            line([0, 1], [CAR]),
            day=DAY,
            time_limit=LIMIT,
        )


# --- Статус решения и логи ---


def test_penalties_reject_too_many_ranks() -> None:
    from src.service.solver import _penalties

    with pytest.raises(ValueError, match="too many priority ranks"):
        _penalties([1] * 500, floor=2**61)


def test_penalties_dominate_strictly() -> None:
    from src.service.solver import _penalties

    priorities = [1] * 2 + [2] * 300 + [3] * 500
    penalty = _penalties(priorities, floor=1000)
    below_rank_1 = penalty[2] * priorities.count(2) + penalty[3] * priorities.count(3)
    assert penalty[1] > below_rank_1
    assert penalty[2] > penalty[3] * priorities.count(3)


def test_status_feasible_or_optimal(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    plan = solve(*_random_instance(3))
    assert plan.status in (SolveStatus.OPTIMAL, SolveStatus.FEASIBLE)
    (record,) = events(capsys, "solver_finished")
    assert record["level"] == "info"
    assert record["status"] == plan.status
    assert record["vehicles"] == 3
    assert 0 < record["nodes"] <= 8
    assert record["dropped"] == len(plan.unassigned)
    assert isinstance(record["duration_ms"], int)


def test_no_solution(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    monkeypatch.setattr(pywrapcp.RoutingModel, "SolveWithParameters", lambda *a, **k: None)
    plan = solve([ticket(1)], [engineer(1)], line([0, 1]))
    assert plan == DayPlan(status=SolveStatus.INFEASIBLE, routes=(), unassigned=())
    (record,) = events(capsys, "solver_finished")
    assert (record["level"], record["status"]) == ("warning", "INFEASIBLE")


def test_logs_no_ticket_data(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    tickets = [ticket(90001), ticket(90002, EMERGENCY)]
    solve(tickets, [engineer(1)], line([0, 1, 2]))
    found = records(capsys)
    assert found
    text = repr(found)
    for secret in ("90001", "90002", "адрес", str(POINT.lat), str(POINT.lon)):
        assert secret not in text


# --- Проверка допустимости assert_feasible ловит нарушение ---


def _feasible() -> tuple[DayPlan, list[Ticket], list[Engineer], dict]:
    tickets = [ticket(1, window=(at(11), at(12)), vehicle=CAR)]
    engineers = [engineer(1, shift=(time(10), time(18)))]
    matrices = line([0, 10])
    plan = DayPlan(
        status=SolveStatus.FEASIBLE,
        routes=(EngineerRoute(1, (Visit(1, at(10, 10), at(11), at(11, 30), 10, 10000),)),),
        unassigned=(),
    )
    assert_feasible(plan, tickets, engineers, matrices)
    return plan, tickets, engineers, matrices


def _with_visit(plan: DayPlan, **changes: object) -> DayPlan:
    visit = replace(plan.routes[0].visits[0], **changes)  # type: ignore[arg-type]
    return replace(plan, routes=(EngineerRoute(1, (visit,)),))


def test_checker_fails_on_skill() -> None:
    plan, tickets, _, matrices = _feasible()
    with pytest.raises(AssertionError, match="skill"):
        assert_feasible(plan, tickets, [engineer(1, [CONNECTION])], matrices)


def test_checker_fails_on_vehicle() -> None:
    plan, tickets, _, matrices = _feasible()
    with pytest.raises(AssertionError, match="vehicle"):
        assert_feasible(plan, tickets, [engineer(1, vehicle=FOOT)], matrices)


def test_checker_fails_on_window() -> None:
    plan, tickets, engineers, matrices = _feasible()
    late = _with_visit(plan, start=at(12, 5), end=at(12, 35))
    with pytest.raises(AssertionError, match="window"):
        assert_feasible(late, tickets, engineers, matrices)
    too_soon = _with_visit(plan, arrival=at(10, 5))
    with pytest.raises(AssertionError, match="travel"):
        assert_feasible(too_soon, tickets, engineers, matrices)


def test_checker_fails_on_shift() -> None:
    plan, tickets, _, matrices = _feasible()
    starts_later = [engineer(1, shift=(time(10, 55), time(18)))]
    with pytest.raises(AssertionError, match="travel"):
        assert_feasible(plan, tickets, starts_later, matrices)
    ends_sooner = [engineer(1, shift=(time(10), time(11, 20)))]
    with pytest.raises(AssertionError, match="shift"):
        assert_feasible(plan, tickets, ends_sooner, matrices)
