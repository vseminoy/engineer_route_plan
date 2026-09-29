import asyncio
from collections.abc import Sequence
from concurrent.futures import Executor, Future
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pytest

from src.clients.osrm import TravelMatrix
from src.domain import Engineer, Point, Skill, Ticket, TicketStatus, VehicleType
from src.errors import DatabaseFailure, DependencyUnavailable, InvalidInput
from src.repository.plans import AssignmentWrite
from src.service.plan_builder import PlanBuilder, QueuedPlan, sweep_running_plans
from src.service.regions import Regions
from tests.log_records import events, json_logs

DAY = date(2026, 9, 1)
POINT = Point(lat=55.75, lon=37.6)
REGIONS = Regions.from_file(Path(__file__).resolve().parents[2] / "data" / "regions.toml")


def _engineer(id: int = 1, vehicle: VehicleType = VehicleType.CAR) -> Engineer:
    return Engineer(
        id=id,
        name=f"Бригада {id}",
        start=POINT,
        shift_start=time(10, 0),
        shift_end=time(20, 0),
        vehicle_type=vehicle,
        skills=(Skill.LOCAL_WORK,),
    )


def _ticket(id: int = 1) -> Ticket:
    return Ticket(
        id=id,
        external_id=f"T{id}",
        type_bk=None,
        type_hd="Локальная заявка",
        required_skill=Skill.LOCAL_WORK,
        required_vehicle=None,
        priority=3,
        district=None,
        address="адрес",
        location=POINT,
        window_start=datetime(2026, 9, 1, 10, 0),
        window_end=datetime(2026, 9, 1, 18, 0),
        duration_min=30,
        status=TicketStatus.SENT,
        received_at=datetime(2026, 9, 1, 0, 0),
    )


def _matrix(n: int) -> TravelMatrix:
    return TravelMatrix(durations_s=[[0.0] * n] * n, distances_m=[[0.0] * n] * n)


class FakeConnect:
    """Stands in for the pool's `connection`, or fails to give one with `error`."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    @asynccontextmanager
    async def __call__(self) -> Any:
        if self.error:
            raise self.error
        yield object()


class FakeOsrm:
    def __init__(
        self,
        matrices: dict[VehicleType, TravelMatrix] | None = None,
        error: Exception | None = None,
        errors_by_vehicle: dict[VehicleType, Exception] | None = None,
    ) -> None:
        self.matrices = matrices or {}
        self.error = error
        self.errors_by_vehicle = errors_by_vehicle or {}
        self.calls: list[VehicleType] = []

    async def table(self, vehicle: VehicleType, points: Sequence[Point]) -> TravelMatrix:
        self.calls.append(vehicle)
        if vehicle in self.errors_by_vehicle:
            raise self.errors_by_vehicle[vehicle]
        if self.error:
            raise self.error
        return self.matrices[vehicle]


class SyncPool(Executor):
    """Runs the submitted callable in-process, synchronously — stands in for the real
    `ProcessPoolExecutor` so unit tests do not pay for a real subprocess."""

    def submit(self, fn: Any, /, *args: Any, **kwargs: Any) -> Future[Any]:
        future: Future[Any] = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as e:  # noqa: BLE001 - mirrors ProcessPoolExecutor.submit
            future.set_exception(e)
        return future


class HangingPool(Executor):
    """A submitted call never completes — stands in for a wedged `or_tools` worker, only
    to exercise the watchdog timeout in `PlanBuilder._solve`."""

    def submit(self, fn: Any, /, *args: Any, **kwargs: Any) -> Future[Any]:
        return Future()  # never resolved


class SequencedPool(Executor):
    """The first submitted call hangs forever, every later one runs synchronously —
    models one build wedged on the executor while a second, later one is submitted to
    the same object afterwards. `PlanBuilder._or_tools_lock` is what actually keeps the
    two from ever being on the executor *at the same time*; this fake just needs to
    behave differently across calls to prove that ordering held."""

    def __init__(self) -> None:
        self._first = True

    def submit(self, fn: Any, /, *args: Any, **kwargs: Any) -> Future[Any]:
        future: Future[Any] = Future()
        if self._first:
            self._first = False
            return future  # never resolved -- the "wedged" build
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as e:  # noqa: BLE001 - mirrors ProcessPoolExecutor.submit
            future.set_exception(e)
        return future


class FakeSolverPool:
    """Implements `solver_pool.SolverPool` over a fake `Executor`; `restart()` records
    the call instead of touching a real process — `ProcessSolverPool.restart()` itself is
    covered on a real `ProcessPoolExecutor` in `tests/service/test_solver_pool.py`."""

    def __init__(self, executor: Executor) -> None:
        self._executor = executor
        self.restart_calls = 0

    @property
    def executor(self) -> Executor:
        return self._executor

    def restart(self) -> None:
        self.restart_calls += 1

    def shutdown(self, *, cancel_futures: bool = False) -> None:
        self._executor.shutdown(cancel_futures=cancel_futures)


class FakeRepo:
    def __init__(
        self,
        region_id: int | None = 1,
        tickets: list[Ticket] | None = None,
        engineers: list[Engineer] | None = None,
        plan_id: int = 1,
        insert_error: Exception | None = None,
        mark_done_error: Exception | None = None,
        mark_failed_error: Exception | None = None,
    ) -> None:
        self.region_id = region_id
        self.tickets = [_ticket()] if tickets is None else tickets
        self.engineers = [_engineer()] if engineers is None else engineers
        self.plan_id = plan_id
        self.insert_error = insert_error
        self.mark_done_error = mark_done_error
        self.mark_failed_error = mark_failed_error
        self.done_calls: list[tuple[int, list[AssignmentWrite]]] = []
        self.failed_calls: list[tuple[int, str]] = []

    async def get_region_id(self, _conn: Any, _code: str) -> int | None:
        return self.region_id

    async def list_open_tickets(self, _conn: Any, _region_id: int) -> list[Ticket]:
        return self.tickets

    async def list_engineers(self, _conn: Any, _region_id: int) -> list[Engineer]:
        return self.engineers

    async def insert_running_plan(
        self, _conn: Any, _region_id: int, _plan_date: date, _algorithm: str, _created_at: datetime
    ) -> int:
        if self.insert_error:
            raise self.insert_error
        return self.plan_id

    async def mark_plan_done(
        self, _conn: Any, plan_id: int, assignments: list[AssignmentWrite]
    ) -> None:
        self.done_calls.append((plan_id, assignments))
        if self.mark_done_error:
            raise self.mark_done_error

    async def mark_plan_failed(self, _conn: Any, plan_id: int, failed_reason: str) -> None:
        self.failed_calls.append((plan_id, failed_reason))
        if self.mark_failed_error:
            raise self.mark_failed_error


def _builder(
    repo: FakeRepo,
    osrm: FakeOsrm | None = None,
    connect: FakeConnect | None = None,
    regions: Regions | None = None,
    max_table_size: int = 1000,
    pool: FakeSolverPool | None = None,
    solver_time_limit: timedelta = timedelta(milliseconds=200),
    solver_watchdog_margin_s: float = 5,
) -> PlanBuilder:
    return PlanBuilder(
        regions=regions or REGIONS,
        connect=connect or FakeConnect(),
        get_region_id=repo.get_region_id,
        list_open_tickets=repo.list_open_tickets,
        list_engineers=repo.list_engineers,
        insert_running_plan=repo.insert_running_plan,
        mark_plan_done=repo.mark_plan_done,
        mark_plan_failed=repo.mark_plan_failed,
        osrm=osrm or FakeOsrm({VehicleType.CAR: _matrix(2)}),
        pool=pool or FakeSolverPool(SyncPool()),
        max_table_size=max_table_size,
        solver_time_limit=solver_time_limit,
        solver_watchdog_margin_s=solver_watchdog_margin_s,
    )


# --- enqueue ------------------------------------------------------------------------


async def test_enqueue_queues_a_running_plan() -> None:
    repo = FakeRepo(plan_id=42)
    queued = await _builder(repo).enqueue("east", DAY, "or_tools")

    assert queued == QueuedPlan(
        plan_id=42, algorithm="or_tools", tickets=repo.tickets, engineers=repo.engineers
    )


async def test_enqueue_unknown_region() -> None:
    with pytest.raises(InvalidInput) as e:
        await _builder(FakeRepo()).enqueue("nonexistent", DAY, "or_tools")
    assert e.value.reason == "unknown_region"


async def test_enqueue_region_not_loaded() -> None:
    with pytest.raises(InvalidInput) as e:
        await _builder(FakeRepo(region_id=None)).enqueue("east", DAY, "or_tools")
    assert e.value.reason == "region_not_loaded"


async def test_enqueue_plan_date_mismatch() -> None:
    mismatched = _ticket()
    mismatched = mismatched.model_copy(
        update={
            "window_start": datetime(2026, 9, 2, 10, 0),
            "window_end": datetime(2026, 9, 2, 12, 0),
        }
    )
    repo = FakeRepo(tickets=[mismatched])
    with pytest.raises(InvalidInput) as e:
        await _builder(repo).enqueue("east", DAY, "or_tools")
    assert e.value.reason == "plan_date_mismatch"


async def test_enqueue_too_many_points() -> None:
    repo = FakeRepo(tickets=[_ticket(1)], engineers=[_engineer(1)])
    with pytest.raises(InvalidInput) as e:
        await _builder(repo, max_table_size=1).enqueue("east", DAY, "or_tools")
    assert e.value.reason == "too_many_points"


async def test_enqueue_insert_failure_propagates() -> None:
    repo = FakeRepo(insert_error=DependencyUnavailable(reason="db_unavailable"))
    with pytest.raises(DependencyUnavailable):
        await _builder(repo).enqueue("east", DAY, "or_tools")


# --- build --------------------------------------------------------------------------


async def test_build_or_tools_persists_done() -> None:
    repo = FakeRepo()
    osrm = FakeOsrm({VehicleType.CAR: _matrix(2)})
    builder = _builder(repo, osrm=osrm)

    await builder.build(7, repo.tickets, repo.engineers, DAY, "or_tools")

    assert repo.failed_calls == []
    (plan_id, assignments) = repo.done_calls[0]
    assert plan_id == 7
    assert {a.ticket_id for a in assignments} == {1}


async def test_build_baseline_persists_done() -> None:
    repo = FakeRepo()
    builder = _builder(repo, osrm=FakeOsrm({VehicleType.CAR: _matrix(2)}))

    await builder.build(7, repo.tickets, repo.engineers, DAY, "baseline_fcfs")

    assert repo.failed_calls == []
    assert repo.done_calls[0][0] == 7


async def test_build_no_engineers_no_matrix_calls() -> None:
    repo = FakeRepo(engineers=[])
    osrm = FakeOsrm({})
    builder = _builder(repo, osrm=osrm)

    await builder.build(7, repo.tickets, [], DAY, "or_tools")

    assert osrm.calls == []
    (_plan_id, assignments) = repo.done_calls[0]
    assert assignments[0].unassigned_reason == "no_skill"


async def test_build_osrm_unavailable_marks_failed() -> None:
    repo = FakeRepo()
    osrm = FakeOsrm(error=DependencyUnavailable(reason="osrm_unavailable"))
    builder = _builder(repo, osrm=osrm)

    await builder.build(7, repo.tickets, repo.engineers, DAY, "or_tools")

    assert repo.done_calls == []
    assert repo.failed_calls == [(7, "osrm_unavailable")]


async def test_build_mixed_matrix_failures_do_not_leak_exception_group() -> None:
    """Two concurrent `table()` calls (one per vehicle type) failing with *different*
    exception types must still collapse to a single plain exception, not an unhandled
    `ExceptionGroup` — `build` catches plain exception types, not groups."""
    engineers = [_engineer(1, VehicleType.CAR), _engineer(2, VehicleType.BIKE)]
    osrm = FakeOsrm(
        errors_by_vehicle={
            VehicleType.CAR: DependencyUnavailable(reason="osrm_unavailable"),
            VehicleType.BIKE: ValueError("malformed response"),
        }
    )
    repo = FakeRepo(engineers=engineers)
    builder = _builder(repo, osrm=osrm)

    await builder.build(7, repo.tickets, engineers, DAY, "or_tools")

    assert repo.done_calls == []
    assert len(repo.failed_calls) == 1
    (plan_id, reason) = repo.failed_calls[0]
    assert plan_id == 7
    assert reason in ("osrm_unavailable", "build_error")


async def test_build_unexpected_error_marks_build_error(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    repo = FakeRepo()
    osrm = FakeOsrm(error=ValueError("boom"))
    builder = _builder(repo, osrm=osrm)

    await builder.build(7, repo.tickets, repo.engineers, DAY, "or_tools")

    assert repo.done_calls == []
    assert repo.failed_calls == [(7, "build_error")]
    (record,) = events(capsys, "plan_build_failed")
    assert record["level"] == "error"


async def test_build_persist_dependency_unavailable_marks_failed() -> None:
    repo = FakeRepo(mark_done_error=DependencyUnavailable(reason="db_unavailable"))
    builder = _builder(repo, osrm=FakeOsrm({VehicleType.CAR: _matrix(2)}))

    await builder.build(7, repo.tickets, repo.engineers, DAY, "or_tools")

    assert repo.failed_calls == [(7, "db_unavailable")]


async def test_build_persist_database_failure_marks_build_error() -> None:
    repo = FakeRepo(mark_done_error=DatabaseFailure(reason="db_query_failed"))
    builder = _builder(repo, osrm=FakeOsrm({VehicleType.CAR: _matrix(2)}))

    await builder.build(7, repo.tickets, repo.engineers, DAY, "or_tools")

    assert repo.failed_calls == [(7, "build_error")]


async def test_build_mark_failed_swallows_its_own_failure() -> None:
    repo = FakeRepo(
        mark_done_error=DependencyUnavailable(reason="db_unavailable"),
        mark_failed_error=DependencyUnavailable(reason="db_unavailable"),
    )
    builder = _builder(repo, osrm=FakeOsrm({VehicleType.CAR: _matrix(2)}))

    await builder.build(7, repo.tickets, repo.engineers, DAY, "or_tools")  # does not raise


async def test_build_logs_finished(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    repo = FakeRepo()
    builder = _builder(repo, osrm=FakeOsrm({VehicleType.CAR: _matrix(2)}))

    await builder.build(7, repo.tickets, repo.engineers, DAY, "or_tools")

    (record,) = events(capsys, "plan_build_finished")
    assert record["plan_id"] == 7
    assert record["algorithm"] == "or_tools"


async def test_build_or_tools_timeout_marks_failed() -> None:
    repo = FakeRepo()
    pool = FakeSolverPool(HangingPool())
    builder = _builder(
        repo,
        osrm=FakeOsrm({VehicleType.CAR: _matrix(2)}),
        pool=pool,
        solver_time_limit=timedelta(milliseconds=1),
        solver_watchdog_margin_s=0.001,
    )

    await builder.build(7, repo.tickets, repo.engineers, DAY, "or_tools")

    assert repo.done_calls == []
    assert repo.failed_calls == [(7, "timeout")]
    assert pool.restart_calls == 1


async def test_build_baseline_never_times_out() -> None:
    repo = FakeRepo()
    pool = FakeSolverPool(HangingPool())
    builder = _builder(
        repo,
        osrm=FakeOsrm({VehicleType.CAR: _matrix(2)}),
        pool=pool,
        solver_time_limit=timedelta(milliseconds=1),
        solver_watchdog_margin_s=0.001,
    )

    await builder.build(7, repo.tickets, repo.engineers, DAY, "baseline_fcfs")

    assert repo.failed_calls == []
    assert repo.done_calls[0][0] == 7
    assert pool.restart_calls == 0


async def test_build_or_tools_within_margin_not_treated_as_timeout() -> None:
    repo = FakeRepo()
    pool = FakeSolverPool(SyncPool())
    builder = _builder(repo, osrm=FakeOsrm({VehicleType.CAR: _matrix(2)}), pool=pool)

    await builder.build(7, repo.tickets, repo.engineers, DAY, "or_tools")

    assert repo.failed_calls == []
    assert repo.done_calls[0][0] == 7
    assert pool.restart_calls == 0


async def test_build_or_tools_timeout_does_not_cancel_a_concurrent_build() -> None:
    """Regression for the race steps 9-10 found: without `PlanBuilder._or_tools_lock`
    serialising submissions to the shared executor, a second build merely queued behind
    a wedged one would have its own future cancelled by `restart()`'s
    `cancel_futures=True` too — surfacing as an unhandled `asyncio.CancelledError`
    (a `BaseException`, caught nowhere in `build`) instead of ever finishing. Both builds
    run on the same `PlanBuilder` (one process-wide instance in the real app), which is
    exactly what makes the lock, a field of `PlanBuilder` and not of the pool, sufficient."""
    repo = FakeRepo()
    pool = FakeSolverPool(SequencedPool())
    builder = _builder(
        repo,
        osrm=FakeOsrm({VehicleType.CAR: _matrix(2)}),
        pool=pool,
        solver_time_limit=timedelta(milliseconds=1),
        solver_watchdog_margin_s=0.05,
    )

    await asyncio.gather(
        builder.build(1, repo.tickets, repo.engineers, DAY, "or_tools"),
        builder.build(2, repo.tickets, repo.engineers, DAY, "or_tools"),
    )

    assert repo.failed_calls == [(1, "timeout")]
    assert repo.done_calls[0][0] == 2
    assert pool.restart_calls == 1


# --- sweep_running_plans --------------------------------------------------------------


class FakeSweepRepo:
    def __init__(
        self, closed_ids: list[int] | None = None, error: Exception | None = None
    ) -> None:
        self.closed_ids = [] if closed_ids is None else closed_ids
        self.error = error
        self.calls: list[str] = []

    async def mark_running_plans_failed(self, _conn: Any, failed_reason: str) -> list[int]:
        self.calls.append(failed_reason)
        if self.error:
            raise self.error
        return self.closed_ids


async def test_sweep_running_plans_returns_closed_ids(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    repo = FakeSweepRepo(closed_ids=[3, 7])

    result = await sweep_running_plans(FakeConnect(), repo.mark_running_plans_failed)

    assert result == [3, 7]
    assert repo.calls == ["shutdown"]
    (record,) = events(capsys, "plan_startup_sweep_finished")
    assert record["count"] == 2


async def test_sweep_running_plans_no_plans_no_log(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    repo = FakeSweepRepo(closed_ids=[])

    result = await sweep_running_plans(FakeConnect(), repo.mark_running_plans_failed)

    assert result == []
    assert events(capsys, "plan_startup_sweep_finished") == []


async def test_sweep_running_plans_db_unavailable_does_not_raise(
    capsys: pytest.CaptureFixture[str],
) -> None:
    json_logs()
    repo = FakeSweepRepo(error=DependencyUnavailable(reason="db_unavailable"))

    result = await sweep_running_plans(FakeConnect(), repo.mark_running_plans_failed)

    assert result == []
    (record,) = events(capsys, "plan_startup_sweep_failed")
    assert record["level"] == "warning"
    assert record["reason"] == "db_unavailable"
