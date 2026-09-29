from contextlib import asynccontextmanager
from datetime import date, datetime, time
from typing import Any

import pytest

from src.domain import Engineer, Point, Skill, VehicleType
from src.errors import DependencyUnavailable, InvalidInput, NotFound
from src.repository.plans import AssignmentRow, PlanRow
from src.service.plan_reader import EngineerRouteRead, PlanRead, PlanReader, UnassignedRead

POINT = Point(lat=55.75, lon=37.6)
DAY = date(2026, 9, 1)


def _engineer(id: int, shift_start: time = time(10, 0), shift_end: time = time(20, 0)) -> Engineer:
    return Engineer(
        id=id,
        name=f"Бригада {id}",
        start=POINT,
        shift_start=shift_start,
        shift_end=shift_end,
        vehicle_type=VehicleType.CAR,
        skills=(Skill.LOCAL_WORK,),
    )


def _assigned(
    ticket_id: int,
    engineer_id: int,
    sequence_no: int,
    travel_min: int = 10,
    duration: int = 30,
    distance_m: int = 1500,
) -> AssignmentRow:
    return AssignmentRow(
        ticket_id=ticket_id,
        engineer_id=engineer_id,
        sequence_no=sequence_no,
        planned_arrival=datetime(2026, 9, 1, 10, 0),
        travel_time_min=travel_min,
        travel_distance_m=distance_m,
        unassigned_reason=None,
        explanation="назначено",
        duration_min=duration,
    )


def _unassigned(ticket_id: int, reason: str = "no_skill") -> AssignmentRow:
    return AssignmentRow(
        ticket_id=ticket_id,
        engineer_id=None,
        sequence_no=None,
        planned_arrival=None,
        travel_time_min=None,
        travel_distance_m=None,
        unassigned_reason=reason,
        explanation="не назначено",
        duration_min=30,
    )


class FakeConnect:
    @asynccontextmanager
    async def __call__(self) -> Any:
        yield object()


class FakeRepo:
    """`plans`/`engineers_by_set`/`assignments_by_plan` (keyed by id) let `compare`'s
    two `get` calls each see a different plan; the single-plan `plan`/`engineers`/
    `assignments` keep every other test's fixtures unchanged."""

    def __init__(
        self,
        plan: PlanRow | None = None,
        engineers: list[Engineer] | None = None,
        assignments: list[AssignmentRow] | None = None,
        error: Exception | None = None,
        plans: dict[int, PlanRow] | None = None,
        engineers_by_set: dict[int, list[Engineer]] | None = None,
        assignments_by_plan: dict[int, list[AssignmentRow]] | None = None,
    ) -> None:
        self.plan = plan
        self.engineers = engineers or []
        self.assignments = assignments or []
        self.error = error
        self.plans = plans
        self.engineers_by_set = engineers_by_set
        self.assignments_by_plan = assignments_by_plan
        self.get_plan_calls: list[int] = []

    async def get_plan(self, _conn: Any, plan_id: int) -> PlanRow | None:
        self.get_plan_calls.append(plan_id)
        if self.error:
            raise self.error
        if self.plans is not None:
            return self.plans.get(plan_id)
        return self.plan

    async def list_engineers(self, _conn: Any, engineer_set_id: int) -> list[Engineer]:
        if self.engineers_by_set is not None:
            return self.engineers_by_set.get(engineer_set_id, [])
        return self.engineers

    async def list_plan_assignments(self, _conn: Any, plan_id: int) -> list[AssignmentRow]:
        if self.assignments_by_plan is not None:
            return self.assignments_by_plan.get(plan_id, [])
        return self.assignments


def _engineers(plan: PlanRead) -> tuple[EngineerRouteRead, ...]:
    assert plan.engineers is not None
    return plan.engineers


def _unassigned_of(plan: PlanRead) -> tuple[UnassignedRead, ...]:
    assert plan.unassigned is not None
    return plan.unassigned


def _reader(repo: FakeRepo) -> PlanReader:
    return PlanReader(
        connect=FakeConnect(),
        get_plan=repo.get_plan,
        list_engineers=repo.list_engineers,
        list_plan_assignments=repo.list_plan_assignments,
    )


async def test_plan_not_found() -> None:
    with pytest.raises(NotFound) as e:
        await _reader(FakeRepo(None)).get(1)
    assert e.value.reason == "plan_not_found"
    assert e.value.params == {"plan_id": 1}


async def test_running_plan_has_no_routes() -> None:
    plan = PlanRow(
        id=1,
        region_id=9,
        region_code="east",
        engineer_set_id=70,
        plan_date=DAY,
        algorithm="or_tools",
        status="running",
        failed_reason=None,
    )
    result = await _reader(FakeRepo(plan)).get(1)
    assert result.status == "running"
    assert result.engineers is None
    assert result.unassigned is None
    assert result.metrics is None


async def test_failed_plan_carries_reason() -> None:
    plan = PlanRow(
        id=1,
        region_id=9,
        region_code="east",
        engineer_set_id=70,
        plan_date=DAY,
        algorithm="or_tools",
        status="failed",
        failed_reason="osrm_unavailable",
    )
    result = await _reader(FakeRepo(plan)).get(1)
    assert result.status == "failed"
    assert result.failed_reason == "osrm_unavailable"
    assert result.engineers is None
    assert result.unassigned is None
    assert result.metrics is None


async def test_done_plan_lists_every_set_engineer() -> None:
    plan = PlanRow(
        id=1,
        region_id=9,
        region_code="east",
        engineer_set_id=70,
        plan_date=DAY,
        algorithm="or_tools",
        status="done",
        failed_reason=None,
    )
    repo = FakeRepo(
        plan,
        engineers=[_engineer(2), _engineer(1)],
        assignments=[_assigned(10, 1, 1), _unassigned(11)],
    )
    result = await _reader(repo).get(1)
    assert result.failed_reason is None
    engineers = _engineers(result)
    assert [r.engineer_id for r in engineers] == [1, 2]
    used, unused = engineers
    assert [v.ticket_id for v in used.route] == [10]
    assert unused.route == ()
    unassigned = _unassigned_of(result)
    assert [u.ticket_id for u in unassigned] == [11]
    assert unassigned[0].reason_code == "no_skill"


async def test_visit_fields_and_distance_rounding() -> None:
    plan = PlanRow(
        id=1,
        region_id=9,
        region_code="east",
        engineer_set_id=70,
        plan_date=DAY,
        algorithm="or_tools",
        status="done",
        failed_reason=None,
    )
    row = _assigned(10, 1, 1, travel_min=12, distance_m=1234)
    repo = FakeRepo(plan, engineers=[_engineer(1)], assignments=[row])

    (route,) = _engineers(await _reader(repo).get(1))
    visit = route.route[0]

    assert visit.sequence_no == 1
    assert visit.travel_time_min == 12
    assert visit.travel_distance_km == 1.2
    assert visit.planned_arrival == datetime(2026, 9, 1, 10, 0)
    assert visit.explanation == "назначено"


async def test_idle_time_is_shift_minus_travel_and_duration() -> None:
    plan = PlanRow(
        id=1,
        region_id=9,
        region_code="east",
        engineer_set_id=70,
        plan_date=DAY,
        algorithm="or_tools",
        status="done",
        failed_reason=None,
    )
    engineer = _engineer(1, shift_start=time(10, 0), shift_end=time(12, 0))  # 120 min shift
    repo = FakeRepo(
        plan,
        engineers=[engineer],
        assignments=[
            _assigned(10, 1, 1, travel_min=15, duration=30),
            _assigned(11, 1, 2, travel_min=5, duration=20),
        ],
    )
    (route,) = _engineers(await _reader(repo).get(1))
    assert route.total_travel_time_min == 20
    assert route.idle_time_min == 120 - 20 - 50


async def test_visits_sorted_by_sequence_no() -> None:
    plan = PlanRow(
        id=1,
        region_id=9,
        region_code="east",
        engineer_set_id=70,
        plan_date=DAY,
        algorithm="or_tools",
        status="done",
        failed_reason=None,
    )
    repo = FakeRepo(
        plan,
        engineers=[_engineer(1)],
        assignments=[_assigned(20, 1, 2), _assigned(10, 1, 1)],
    )
    (route,) = _engineers(await _reader(repo).get(1))
    assert [v.ticket_id for v in route.route] == [10, 20]


async def test_engineer_without_assignments_has_full_shift_idle() -> None:
    plan = PlanRow(
        id=1,
        region_id=9,
        region_code="east",
        engineer_set_id=70,
        plan_date=DAY,
        algorithm="or_tools",
        status="done",
        failed_reason=None,
    )
    engineer = _engineer(1, shift_start=time(9, 0), shift_end=time(18, 0))
    repo = FakeRepo(plan, engineers=[engineer], assignments=[])
    (route,) = _engineers(await _reader(repo).get(1))
    assert route.total_distance_km == 0
    assert route.total_travel_time_min == 0
    assert route.idle_time_min == 9 * 60


async def test_get_plan_dependency_unavailable_propagates() -> None:
    repo = FakeRepo(None, error=DependencyUnavailable(reason="db_unavailable"))
    with pytest.raises(DependencyUnavailable):
        await _reader(repo).get(1)


# --- metrics --------------------------------------------------------------------------


async def test_metrics_engineers_used_counts_used_only() -> None:
    plan = PlanRow(
        id=1,
        region_id=9,
        region_code="east",
        engineer_set_id=70,
        plan_date=DAY,
        algorithm="or_tools",
        status="done",
        failed_reason=None,
    )
    repo = FakeRepo(plan, engineers=[_engineer(1), _engineer(2)], assignments=[_assigned(10, 1, 1)])

    result = await _reader(repo).get(1)

    assert result.metrics is not None
    assert result.metrics.engineers_used == 1


async def test_metrics_total_distance_km_sums_all_routes() -> None:
    plan = PlanRow(
        id=1,
        region_id=9,
        region_code="east",
        engineer_set_id=70,
        plan_date=DAY,
        algorithm="or_tools",
        status="done",
        failed_reason=None,
    )
    repo = FakeRepo(
        plan,
        engineers=[_engineer(1), _engineer(2)],
        assignments=[
            _assigned(10, 1, 1, distance_m=21400),
            _assigned(11, 2, 1, distance_m=14000),
        ],
    )

    result = await _reader(repo).get(1)

    assert result.metrics is not None
    assert result.metrics.total_distance_km == 35.4


async def test_metrics_distance_and_idle_by_engineer_cover_every_engineer() -> None:
    plan = PlanRow(
        id=1,
        region_id=9,
        region_code="east",
        engineer_set_id=70,
        plan_date=DAY,
        algorithm="or_tools",
        status="done",
        failed_reason=None,
    )
    unused = _engineer(2, shift_start=time(9, 0), shift_end=time(18, 0))
    repo = FakeRepo(plan, engineers=[_engineer(1), unused], assignments=[_assigned(10, 1, 1)])

    result = await _reader(repo).get(1)

    assert result.metrics is not None
    assert set(result.metrics.distance_by_engineer) == {1, 2}
    assert result.metrics.distance_by_engineer[2] == 0
    assert set(result.metrics.idle_time_by_engineer_min) == {1, 2}
    assert result.metrics.idle_time_by_engineer_min[2] == 9 * 60


async def test_metrics_assigned_and_unassigned_counts() -> None:
    plan = PlanRow(
        id=1,
        region_id=9,
        region_code="east",
        engineer_set_id=70,
        plan_date=DAY,
        algorithm="or_tools",
        status="done",
        failed_reason=None,
    )
    repo = FakeRepo(
        plan,
        engineers=[_engineer(1)],
        assignments=[_assigned(10, 1, 1), _assigned(11, 1, 2), _unassigned(12)],
    )

    result = await _reader(repo).get(1)

    assert result.metrics is not None
    assert (result.metrics.assigned_count, result.metrics.unassigned_count) == (2, 1)


# --- compare ----------------------------------------------------------------------------


def _multi_repo(
    main_status: str = "done",
    baseline_status: str = "done",
    plan_ids: frozenset[int] = frozenset({1, 2}),
    baseline_engineer_set_id: int = 100,
) -> FakeRepo:
    """Both plans built for engineer set 100 (5 brigades) by default — `compare` requires
    a shared set. Plan 1 (`main`) uses 2 of them, 30.0 km total; plan 2 (`baseline`) the
    other 3, 40.0 km total. `plan_ids` drops one of the two plans out of `get_plan`'s
    dict, as if it never existed."""
    plans = {
        1: PlanRow(
            id=1,
            region_id=100,
            region_code="east",
            engineer_set_id=100,
            plan_date=DAY,
            algorithm="or_tools",
            status=main_status,
            failed_reason=None,
        ),
        2: PlanRow(
            id=2,
            region_id=100,
            region_code="east",
            engineer_set_id=baseline_engineer_set_id,
            plan_date=DAY,
            algorithm="baseline_fcfs",
            status=baseline_status,
            failed_reason=None,
        ),
    }
    return FakeRepo(
        plans={k: v for k, v in plans.items() if k in plan_ids},
        engineers_by_set={
            100: [_engineer(1), _engineer(2), _engineer(3), _engineer(4), _engineer(5)],
            200: [_engineer(1), _engineer(2), _engineer(3), _engineer(4), _engineer(5)],
        },
        assignments_by_plan={
            1: [
                _assigned(10, 1, 1, distance_m=15000),
                _assigned(11, 2, 1, distance_m=15000),
            ],
            2: [
                _assigned(20, 3, 1, distance_m=10000),
                _assigned(21, 4, 1, distance_m=15000),
                _assigned(22, 5, 1, distance_m=15000),
            ],
        },
    )


async def test_compare_returns_engineers_used_and_total_distance_km() -> None:
    entries = await _reader(_multi_repo()).compare(1, 2)

    assert [e.metric for e in entries] == ["engineers_used", "total_distance_km"]
    engineers_used, total_distance_km = entries
    assert (engineers_used.main, engineers_used.baseline) == (2, 3)
    assert (total_distance_km.main, total_distance_km.baseline) == (30.0, 40.0)


async def test_compare_delta_is_main_minus_baseline() -> None:
    entries = await _reader(_multi_repo()).compare(1, 2)

    by_metric = {e.metric: e for e in entries}
    assert by_metric["total_distance_km"].delta == -10.0
    assert by_metric["engineers_used"].delta == -1


async def test_compare_excludes_idle_time() -> None:
    entries = await _reader(_multi_repo()).compare(1, 2)

    assert "idle_time" not in {e.metric for e in entries}


async def test_compare_engineer_set_mismatch() -> None:
    repo = _multi_repo(baseline_engineer_set_id=200)

    with pytest.raises(InvalidInput) as e:
        await _reader(repo).compare(1, 2)

    assert e.value.reason == "engineer_set_mismatch"


async def test_compare_same_engineer_set_ok() -> None:
    entries = await _reader(_multi_repo(baseline_engineer_set_id=100)).compare(1, 2)
    assert [e.metric for e in entries] == ["engineers_used", "total_distance_km"]


async def test_compare_main_not_found() -> None:
    repo = _multi_repo(plan_ids=frozenset({2}))

    with pytest.raises(NotFound) as e:
        await _reader(repo).compare(1, 2)

    assert e.value.reason == "plan_not_found"
    assert e.value.params == {"plan_id": 1}
    assert repo.get_plan_calls == [1]


async def test_compare_baseline_not_found() -> None:
    repo = _multi_repo(plan_ids=frozenset({1}))

    with pytest.raises(NotFound) as e:
        await _reader(repo).compare(1, 2)

    assert e.value.reason == "plan_not_found"
    assert e.value.params == {"plan_id": 2}
    assert repo.get_plan_calls == [1, 2]


@pytest.mark.parametrize("status", ["running", "failed"])
async def test_compare_main_not_ready(status: str) -> None:
    repo = _multi_repo(main_status=status)

    with pytest.raises(InvalidInput) as e:
        await _reader(repo).compare(1, 2)

    assert e.value.reason == "plan_not_ready"
    assert e.value.params is not None and e.value.params["plan_id"] == 1
    assert repo.get_plan_calls == [1]


@pytest.mark.parametrize("status", ["running", "failed"])
async def test_compare_baseline_not_ready(status: str) -> None:
    repo = _multi_repo(baseline_status=status)

    with pytest.raises(InvalidInput) as e:
        await _reader(repo).compare(1, 2)

    assert e.value.reason == "plan_not_ready"
    assert e.value.params is not None and e.value.params["plan_id"] == 2
    assert repo.get_plan_calls == [1, 2]


async def test_compare_dependency_unavailable_propagates() -> None:
    repo = _multi_repo()
    repo.error = DependencyUnavailable(reason="db_unavailable")

    with pytest.raises(DependencyUnavailable):
        await _reader(repo).compare(1, 2)
