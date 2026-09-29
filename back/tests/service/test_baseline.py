import math
import random
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timedelta

import pytest

from src.clients.osrm import TravelMatrix
from src.domain import Engineer, Point, Skill, Ticket, TicketStatus, VehicleType
from src.service.baseline import solve_day
from src.service.solver import DayPlan, SolveStatus, Visit
from src.service.solver import solve_day as solver_solve_day
from tests.log_records import events, json_logs

DAY = date(2026, 9, 1)
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


def assert_feasible_fcfs(
    plan: DayPlan,
    tickets: Sequence[Ticket],
    engineers: Sequence[Engineer],
    matrices: Mapping[VehicleType, TravelMatrix],
) -> None:
    """Checks a plan against baseline's own rules, independently of `solve_day`: travel is
    recomputed from the matrix of the brigade's vehicle, rounded up to a minute, and window
    start is used exactly (no whole-minute rounding — that is the solver's own quirk)."""
    by_id = {t.id: t for t in tickets}
    row = {t.id: len(engineers) + i for i, t in enumerate(tickets)}
    placed = [v.ticket_id for r in plan.routes for v in r.visits] + list(plan.unassigned)
    assert sorted(placed) == sorted(by_id), "every ticket once: in a route or unassigned"
    assert [r.engineer_id for r in plan.routes] == [e.id for e in engineers]
    for route, e in zip(plan.routes, engineers, strict=True):
        durations = matrices[e.vehicle_type].durations_s
        here = engineers.index(e)
        free = datetime.combine(DAY, e.shift_start)
        travel_total = 0
        duration_total = 0
        for visit in route.visits:
            t = by_id[visit.ticket_id]
            assert t.required_skill in e.skills, f"skill: ticket {t.id} to brigade {e.id}"
            assert t.required_vehicle in (None, e.vehicle_type), f"vehicle: ticket {t.id}"
            seconds = durations[here][row[t.id]]
            assert seconds is not None, f"no route to ticket {t.id}"
            earliest = free + timedelta(minutes=math.ceil(seconds / 60))
            assert visit.arrival == earliest, f"arrival not the earliest travel allows: ticket {t.id}"
            assert t.window_start <= visit.start <= t.window_end, f"window: ticket {t.id}"
            assert visit.start == max(visit.arrival, t.window_start), f"work not earliest: {t.id}"
            assert visit.end == visit.start + timedelta(minutes=t.duration_min)
            assert visit.end <= datetime.combine(DAY, e.shift_end), f"shift: ticket {t.id}"
            travel_total += math.ceil(seconds / 60)
            duration_total += t.duration_min
            free, here = visit.end, row[t.id]
        shift_min = (e.shift_end.hour * 60 + e.shift_end.minute) - (
            e.shift_start.hour * 60 + e.shift_start.minute
        )
        assert route.idle_min == shift_min - travel_total - duration_total, f"idle time: {e.id}"


def visits_of(plan: DayPlan, engineer_id: int) -> tuple[Visit, ...]:
    return next(r.visits for r in plan.routes if r.engineer_id == engineer_id)


def assigned_to(plan: DayPlan, ticket_id: int) -> int | None:
    for r in plan.routes:
        if any(v.ticket_id == ticket_id for v in r.visits):
            return r.engineer_id
    return None


def solve(
    tickets: Sequence[Ticket],
    engineers: Sequence[Engineer],
    matrices: Mapping[VehicleType, TravelMatrix],
) -> DayPlan:
    plan = solve_day(tickets, engineers, matrices, day=DAY)
    assert_feasible_fcfs(plan, tickets, engineers, matrices)
    return plan


# --- Порядок и первое подходящее назначение ---------------------------------


def test_input_order_ticket_processing() -> None:
    matrices = line([0, 10, 10])
    low = ticket(1, priority=3, window=(at(10), at(22)))
    emergency = ticket(2, priority=1, skill=EMERGENCY, window=(at(10), at(22)), duration=600)
    e = engineer(1, skills=(LOCAL, EMERGENCY), shift=(time(10, 0), time(11, 0)))
    plan = solve([low, emergency], [e], matrices)
    assert assigned_to(plan, 1) == 1
    assert plan.unassigned == (2,)


def test_first_fit_engineer_no_backtracking() -> None:
    # Points in matrix order: far's start, near's start, the ticket.
    matrices = line([20, 5, 0])
    far = engineer(1)
    near = engineer(2)
    t = ticket(1)
    plan = solve([t], [far, near], matrices)
    assert assigned_to(plan, 1) == 1


def test_visit_order_matches_assignment_order() -> None:
    matrices = line([0, 10, 20])
    e = engineer(1)
    first = ticket(1, window=(at(14), at(22)))
    second = ticket(2, window=(at(10), at(22)))
    plan = solve([first, second], [e], matrices)
    visits = visits_of(plan, 1)
    assert [v.ticket_id for v in visits] == [1, 2]


def test_no_global_reoptimization() -> None:
    matrices = line([0, 5, 30, 6])
    e = engineer(1)
    a = ticket(1, window=(at(10), at(22)))
    b = ticket(2, window=(at(10), at(22)))
    better_fit = ticket(3, window=(at(10), at(22)))
    plan = solve([a, b, better_fit], [e], matrices)
    visits = visits_of(plan, 1)
    assert [v.ticket_id for v in visits] == [1, 2, 3]


# --- Допустимость: навык и транспорт -----------------------------------------


def test_skill_required() -> None:
    matrices = line([0, 5, 10])
    without = engineer(1, skills=(LOCAL,))
    with_skill = engineer(2, skills=(LOCAL, EMERGENCY))
    t = ticket(1, skill=EMERGENCY)
    plan = solve([t], [without, with_skill], matrices)
    assert assigned_to(plan, 1) == 2


def test_no_engineer_with_skill() -> None:
    matrices = line([0, 10])
    e = engineer(1, skills=(LOCAL,))
    t = ticket(1, skill=EMERGENCY)
    plan = solve([t], [e], matrices)
    assert plan.unassigned == (1,)


def test_required_vehicle() -> None:
    matrices = line([0, 10, 20])
    on_foot = engineer(1, vehicle=FOOT)
    by_car = engineer(2, vehicle=CAR)
    t = ticket(1, vehicle=CAR)
    plan = solve([t], [on_foot, by_car], matrices)
    assert assigned_to(plan, 1) == 2


def test_no_engineer_with_vehicle() -> None:
    matrices = line([0, 10, 20])
    on_foot = engineer(1, vehicle=FOOT)
    by_car = engineer(2, vehicle=CAR)
    t = ticket(1, vehicle=BIKE)
    plan = solve([t], [on_foot, by_car], matrices)
    assert plan.unassigned == (1,)


# --- Время: окна, смены, переезды --------------------------------------------


def test_early_arrival_waits_for_window() -> None:
    matrices = line([0, 10])
    e = engineer(1, shift=(time(10, 0), time(23, 30)))
    t = ticket(1, window=(at(12), at(14)), duration=30)
    plan = solve([t], [e], matrices)
    visit = visits_of(plan, 1)[0]
    assert visit.arrival == at(10, 10)
    assert visit.start == at(12, 0)


def test_window_unreachable() -> None:
    matrices = line([0, 30])
    e = engineer(1, shift=(time(10, 0), time(23, 30)))
    t = ticket(1, window=(at(10), at(10, 15)))
    plan = solve([t], [e], matrices)
    assert plan.unassigned == (1,)


def test_shift_not_enough_tries_next_engineer() -> None:
    matrices = line([0, 5, 5])
    short = engineer(1, shift=(time(10, 0), time(10, 20)))
    long = engineer(2, shift=(time(10, 0), time(23, 30)))
    t = ticket(1, duration=60)
    plan = solve([t], [short, long], matrices)
    assert assigned_to(plan, 1) == 2


def test_no_route_tries_next_engineer() -> None:
    # Points in matrix order: e1's start, e2's start, the ticket.
    base = line([0, 5, 10])[CAR]
    durations = [row[:] for row in base.durations_s]
    distances = [row[:] for row in base.distances_m]
    durations[0][2] = distances[0][2] = None  # no route from e1's start to the ticket
    matrices = {CAR: TravelMatrix(durations_s=durations, distances_m=distances)}
    e1 = engineer(1)
    e2 = engineer(2)
    t = ticket(1)
    plan = solve([t], [e1, e2], matrices)
    assert assigned_to(plan, 1) == 2


def test_travel_rounded_up_to_minute() -> None:
    matrices = {CAR: TravelMatrix(durations_s=[[0, 61], [61, 0]], distances_m=[[0, 500], [500, 0]])}
    e = engineer(1)
    t = ticket(1)
    plan = solve([t], [e], matrices)
    visit = visits_of(plan, 1)[0]
    assert visit.travel_min == 2
    assert visit.arrival == at(10, 2)


def test_travel_from_previous_visit() -> None:
    matrices = line([0, 100, 101])
    e = engineer(1)
    first = ticket(1, window=(at(10), at(22)))
    second = ticket(2, window=(at(10), at(22)))
    plan = solve([first, second], [e], matrices)
    visits = visits_of(plan, 1)
    assert visits[1].travel_min == 1


# --- Результат и независимость от солвера ------------------------------------


def test_status_always_optimal() -> None:
    matrices = line([0, 10])
    e = engineer(1, skills=(LOCAL,))
    unreachable = ticket(1, skill=EMERGENCY)
    plan = solve([unreachable], [e], matrices)
    assert plan.status is SolveStatus.OPTIMAL


def test_output_shares_dayplan_shape() -> None:
    matrices = line([0, 10, 20])
    engineers = [engineer(1)]
    tickets = [ticket(1), ticket(2)]
    baseline_plan = solve_day(tickets, engineers, matrices, day=DAY)
    solver_plan = solver_solve_day(tickets, engineers, matrices, day=DAY, time_limit=timedelta(milliseconds=200))
    assert isinstance(baseline_plan, DayPlan)
    assert isinstance(solver_plan, DayPlan)
    assert type(baseline_plan.routes[0]) is type(solver_plan.routes[0])
    if baseline_plan.routes[0].visits and solver_plan.routes[0].visits:
        assert type(baseline_plan.routes[0].visits[0]) is type(solver_plan.routes[0].visits[0])


def test_route_per_engineer() -> None:
    matrices = line([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50])
    engineers = [engineer(1), engineer(2), engineer(3)]
    tickets = [ticket(i) for i in range(1, 9)]
    plan = solve(tickets, engineers, matrices)
    assert [r.engineer_id for r in plan.routes] == [1, 2, 3]
    placed = sorted(v.ticket_id for r in plan.routes for v in r.visits)
    assert placed + sorted(plan.unassigned) == sorted(t.id for t in tickets)


def test_visit_fields() -> None:
    matrices = line([0, 10, 20])
    e = engineer(1)
    tickets = [ticket(1), ticket(2)]
    plan = solve(tickets, [e], matrices)
    visit = visits_of(plan, 1)[0]
    assert visit.ticket_id == 1
    assert visit.travel_min == 10
    assert visit.distance_m == 10_000


def test_random_instances_feasible() -> None:
    rng = random.Random(0)
    for seed in range(20):
        rng.seed(seed)
        n_engineers = 3
        n_tickets = 8
        positions = [rng.uniform(-50, 50) for _ in range(n_engineers + n_tickets)]
        matrices = line(positions)
        engineers = [
            engineer(
                i + 1,
                skills=tuple(rng.sample([LOCAL, CONNECTION, EMERGENCY], k=rng.randint(1, 3))),
                vehicle=rng.choice([CAR, FOOT, BIKE]),
                shift=(time(rng.randint(6, 10)), time(rng.randint(18, 23), 30)),
            )
            for i in range(n_engineers)
        ]
        tickets = [
            ticket(
                i + 1,
                skill=rng.choice([LOCAL, CONNECTION, EMERGENCY]),
                window=(at(rng.randint(6, 12)), at(rng.randint(13, 23))),
            )
            for i in range(n_tickets)
        ]
        plan = solve_day(tickets, engineers, matrices, day=DAY)
        assert_feasible_fcfs(plan, tickets, engineers, matrices)


def test_idle_time_computed() -> None:
    matrices = line([0, 10])
    e = engineer(1, shift=(time(10, 0), time(12, 0)))
    t = ticket(1, duration=30)
    plan = solve([t], [e], matrices)
    assert plan.routes[0].idle_min == 120 - 10 - 30


def test_idle_time_whole_shift_when_unused() -> None:
    matrices = line([0, 10])
    e = engineer(1, skills=(LOCAL,), shift=(time(10, 0), time(12, 0)))
    t = ticket(1, skill=EMERGENCY)
    plan = solve([t], [e], matrices)
    assert plan.routes[0].idle_min == 120


def test_no_engineers() -> None:
    plan = solve_day([ticket(1), ticket(2)], [], {}, day=DAY)
    assert plan.routes == ()
    assert sorted(plan.unassigned) == [1, 2]


def test_no_tickets() -> None:
    engineers = [engineer(1), engineer(2)]
    matrices = line([0, 1])
    plan = solve_day([], engineers, matrices, day=DAY)
    assert all(r.visits == () for r in plan.routes)


def test_matrix_size_mismatch() -> None:
    matrices = {CAR: TravelMatrix(durations_s=[[0]], distances_m=[[0]])}
    try:
        solve_day([ticket(1)], [engineer(1)], matrices, day=DAY)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_matrix_size_mismatch_asymmetric() -> None:
    # 1 brigade + 2 tickets = 3 points: durations_s short by one row, distances_m long by one —
    # the same total row count as a correctly sized pair, so summing them must not pass this.
    matrices = {
        CAR: TravelMatrix(
            durations_s=[[0, 0, 0], [0, 0, 0]],
            distances_m=[[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]],
        )
    }
    try:
        solve_day([ticket(1), ticket(2)], [engineer(1)], matrices, day=DAY)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_missing_matrix_for_vehicle() -> None:
    e = engineer(1, vehicle=BIKE)
    matrices = {CAR: TravelMatrix(durations_s=[[0, 0], [0, 0]], distances_m=[[0, 0], [0, 0]])}
    try:
        solve_day([ticket(1)], [e], matrices, day=DAY)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_shift_start_not_before_end_rejected() -> None:
    e = engineer(1, shift=(time(20, 0), time(10, 0)))
    matrices = line([0, 10])
    try:
        solve_day([ticket(1)], [e], matrices, day=DAY)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


# --- Логи ---------------------------------------------------------------------


def test_baseline_finished_logged(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    matrices = line([0, 10])
    plan = solve_day([ticket(1)], [engineer(1)], matrices, day=DAY)
    found = events(capsys, "baseline_finished")
    assert len(found) == 1
    assert found[0]["vehicles"] == 1
    assert found[0]["nodes"] == 1
    assert found[0]["dropped"] == len(plan.unassigned)


def test_logs_no_ticket_data(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    matrices = line([0, 10, 20])
    solve_day([ticket(1), ticket(2)], [engineer(1)], matrices, day=DAY)
    found = events(capsys, "baseline_finished")
    text = str(found)
    assert "адрес" not in text
    assert "55.75" not in text
