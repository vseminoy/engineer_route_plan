from contextlib import asynccontextmanager
from datetime import datetime, time
from typing import Any

import pytest

from src.domain import Engineer, Point, Skill, VehicleType
from src.errors import DependencyUnavailable, NotFound
from src.repository.plans import AssignmentRow, PlanRow
from src.service.plan_reader import EngineerRouteRead, PlanRead, PlanReader, UnassignedRead

POINT = Point(lat=55.75, lon=37.6)


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
    def __init__(
        self,
        plan: PlanRow | None,
        engineers: list[Engineer] | None = None,
        assignments: list[AssignmentRow] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.plan = plan
        self.engineers = engineers or []
        self.assignments = assignments or []
        self.error = error

    async def get_plan(self, _conn: Any, _plan_id: int) -> PlanRow | None:
        if self.error:
            raise self.error
        return self.plan

    async def list_engineers(self, _conn: Any, _region_id: int) -> list[Engineer]:
        return self.engineers

    async def list_plan_assignments(self, _conn: Any, _plan_id: int) -> list[AssignmentRow]:
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
    plan = PlanRow(id=1, region_id=9, algorithm="or_tools", status="running", failed_reason=None)
    result = await _reader(FakeRepo(plan)).get(1)
    assert result.status == "running"
    assert result.engineers is None
    assert result.unassigned is None


async def test_failed_plan_carries_reason() -> None:
    plan = PlanRow(
        id=1, region_id=9, algorithm="or_tools", status="failed", failed_reason="osrm_unavailable"
    )
    result = await _reader(FakeRepo(plan)).get(1)
    assert result.status == "failed"
    assert result.failed_reason == "osrm_unavailable"
    assert result.engineers is None
    assert result.unassigned is None


async def test_done_plan_lists_every_region_engineer() -> None:
    plan = PlanRow(id=1, region_id=9, algorithm="or_tools", status="done", failed_reason=None)
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
    plan = PlanRow(id=1, region_id=9, algorithm="or_tools", status="done", failed_reason=None)
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
    plan = PlanRow(id=1, region_id=9, algorithm="or_tools", status="done", failed_reason=None)
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
    plan = PlanRow(id=1, region_id=9, algorithm="or_tools", status="done", failed_reason=None)
    repo = FakeRepo(
        plan,
        engineers=[_engineer(1)],
        assignments=[_assigned(20, 1, 2), _assigned(10, 1, 1)],
    )
    (route,) = _engineers(await _reader(repo).get(1))
    assert [v.ticket_id for v in route.route] == [10, 20]


async def test_engineer_without_assignments_has_full_shift_idle() -> None:
    plan = PlanRow(id=1, region_id=9, algorithm="or_tools", status="done", failed_reason=None)
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
