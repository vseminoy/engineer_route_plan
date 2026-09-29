"""Builds a region's day plan: `enqueue` validates and queues the build (a `running` plan
row, with the tickets and brigades it will use), `build` runs it — OSRM, the solver or
baseline, `explain`, then the persisted outcome — in the background, after the request
that queued it has already answered `202`.

`build` has no deadline of its own: the client learns the outcome by polling
`GET /api/v1/plan/{plan_id}` until `status` stops being `running`, so nothing here needs to
answer inside an HTTP request's lifetime. Only the OSRM client's own timeout and the
solver's `time_limit` bound how long a build actually takes. It never raises: every
failure is recorded on the plan row (`failed`, with a reason) instead, since nothing awaits
it once scheduled.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import partial
from typing import Any, Protocol

from psycopg import AsyncConnection

from src.clients.osrm import TravelMatrix
from src.domain import Engineer, EngineerSetWithRegion, Point, Ticket, VehicleType
from src.errors import AppError, DependencyUnavailable, InvalidInput
from src.logging import get_logger
from src.repository.db import database_errors
from src.repository.plans import AssignmentWrite
from src.service import baseline
from src.service.explain import ExplainedPlan, explain
from src.service.loader import Connect
from src.service.regions import Regions
from src.service.solver import SolveStatus, solve_day
from src.service.solver_pool import SolverPool

logger = get_logger(__name__)

GetRegionId = Callable[[AsyncConnection[Any], str], Awaitable[int | None]]
GetDefaultEngineerSetId = Callable[[AsyncConnection[Any], int], Awaitable[int | None]]
GetEngineerSet = Callable[[AsyncConnection[Any], int], Awaitable[EngineerSetWithRegion | None]]
ListTickets = Callable[[AsyncConnection[Any], int], Awaitable[list[Ticket]]]
ListEngineers = Callable[[AsyncConnection[Any], int], Awaitable[list[Engineer]]]
InsertRunningPlan = Callable[[AsyncConnection[Any], int, int, date, str, datetime], Awaitable[int]]
MarkPlanDone = Callable[[AsyncConnection[Any], int, list[AssignmentWrite]], Awaitable[None]]
MarkPlanFailed = Callable[[AsyncConnection[Any], int, str], Awaitable[None]]
MarkRunningPlansFailed = Callable[[AsyncConnection[Any], str], Awaitable[list[int]]]


class _SolverTimedOut(Exception):
    """Raised by `_solve` when the watchdog kills a wedged `or_tools` worker. Caught
    inside `build` only — never escapes this module or reaches a client."""


class TableClient(Protocol):
    """What `PlanBuilder` needs of the OSRM client — narrow enough that tests can stand
    in a fake for it instead of a real `OsrmClient`."""

    async def table(self, vehicle: VehicleType, points: Sequence[Point]) -> TravelMatrix: ...


@dataclass(frozen=True)
class QueuedPlan:
    """What `enqueue` both stores and hands `build`: reading the tickets and brigades
    back from the database a second time could disagree with what was just validated."""

    plan_id: int
    algorithm: str
    engineer_set_id: int
    tickets: list[Ticket]
    engineers: list[Engineer]


@dataclass(frozen=True)
class PlanBuilder:
    regions: Regions
    connect: Connect
    get_region_id: GetRegionId
    get_default_engineer_set_id: GetDefaultEngineerSetId
    get_engineer_set: GetEngineerSet
    list_open_tickets: ListTickets
    list_engineers: ListEngineers
    insert_running_plan: InsertRunningPlan
    mark_plan_done: MarkPlanDone
    mark_plan_failed: MarkPlanFailed
    osrm: TableClient
    pool: SolverPool
    """A `ProcessSolverPool` in the running app; tests stand in a fake implementing the
    same protocol. `.executor` is what `run_in_executor` runs on; `.restart()` is what
    the watchdog calls after killing a wedged worker."""
    max_table_size: int
    solver_time_limit: timedelta
    solver_watchdog_margin_s: float
    clock: Callable[[], datetime] = datetime.now
    _or_tools_lock: asyncio.Lock = field(default_factory=asyncio.Lock, compare=False, repr=False)
    """Serialises `or_tools` submissions to `self.pool`: without it, a second concurrent
    build's future could sit queued in the same executor behind a wedged one, and the
    watchdog's `restart()` would cancel it along with the wedged future it was meant to
    kill — its `CancelledError` is a `BaseException`, uncaught anywhere in `build`, and
    that plan would stay `running` forever. With the lock, at most one future ever exists
    on the executor, so `restart()` only ever touches the one it is meant to.

    Not a guard against every cancellation: `app.py`'s own shutdown can still cancel a
    build waiting on this lock or on `wait_for` inside it (`SolverPool.shutdown()`, unlike
    `restart()`, is not lock-aware). Harmless in practice: the process is exiting anyway,
    and the plan that build was for is exactly what the next startup's `sweep_running_plans`
    closes as `failed_reason='shutdown'`."""

    async def enqueue(
        self, region_code: str, plan_date: date, algorithm: str, engineer_set_id: int | None
    ) -> QueuedPlan:
        """Validates and queues a build. Raises `InvalidInput` before touching OSRM or the
        solver; the plan row is inserted only once every check has passed. Without
        `engineer_set_id` — the region's `default` set."""
        region = self.regions.get(region_code)
        async with database_errors("plan_enqueue"), self.connect() as conn:
            region_id = await self.get_region_id(conn, region.code)
            if region_id is None:
                raise InvalidInput(
                    "region_not_loaded",
                    fields=[("region", "Нет загруженных данных региона")],
                    params={"region": region.code},
                )
            if engineer_set_id is None:
                # A loaded region always has a `default` set — created by its first load
                # (`replace_region_data`) and never removable — so this is never `None`
                # here; `region_id is None` above is what actually covers "not loaded".
                resolved_set_id = await self.get_default_engineer_set_id(conn, region_id)
                assert resolved_set_id is not None
            else:
                owner = await self.get_engineer_set(conn, engineer_set_id)
                if owner is None or owner.region_id != region_id:
                    raise InvalidInput(
                        "engineer_set_not_in_region",
                        fields=[("engineer_set_id", "Набор не принадлежит региону")],
                        params={"engineer_set_id": engineer_set_id, "region": region.code},
                    )
                resolved_set_id = engineer_set_id
            tickets = await self.list_open_tickets(conn, region_id)
            engineers = await self.list_engineers(conn, resolved_set_id)
            _validate_window(tickets, plan_date)
            _validate_size(engineers, tickets, self.max_table_size)
            plan_id = await self.insert_running_plan(
                conn, region_id, resolved_set_id, plan_date, algorithm, self.clock()
            )
        logger.info(
            "plan_enqueued",
            plan_id=plan_id,
            region=region.code,
            engineer_set_id=resolved_set_id,
            algorithm=algorithm,
        )
        return QueuedPlan(
            plan_id=plan_id,
            algorithm=algorithm,
            engineer_set_id=resolved_set_id,
            tickets=tickets,
            engineers=engineers,
        )

    async def build(
        self,
        plan_id: int,
        tickets: Sequence[Ticket],
        engineers: Sequence[Engineer],
        plan_date: date,
        algorithm: str,
    ) -> None:
        try:
            matrices = await self._matrices(engineers, tickets)
            explained = await self._solve(tickets, engineers, matrices, plan_date, algorithm)
        except DependencyUnavailable:
            await self._fail(plan_id, "osrm_unavailable")
            return
        except _SolverTimedOut:
            logger.warning("plan_build_timeout", plan_id=plan_id, algorithm=algorithm)
            await self._fail(plan_id, "timeout")
            return
        except Exception:
            logger.exception("plan_build_failed", plan_id=plan_id, algorithm=algorithm)
            await self._fail(plan_id, "build_error")
            return

        try:
            async with database_errors("plan_build_persist"), self.connect() as conn:
                await self.mark_plan_done(conn, plan_id, _assignment_writes(explained))
        except DependencyUnavailable:
            await self._fail(plan_id, "db_unavailable")
            return
        except AppError:
            # Already logged by `database_errors` (a driver failure) or unreachable (any
            # other `AppError` `mark_plan_done` could raise).
            await self._fail(plan_id, "build_error")
            return
        logger.info("plan_build_finished", plan_id=plan_id, algorithm=algorithm)

    async def _solve(
        self,
        tickets: Sequence[Ticket],
        engineers: Sequence[Engineer],
        matrices: Mapping[VehicleType, TravelMatrix],
        plan_date: date,
        algorithm: str,
    ) -> ExplainedPlan:
        if algorithm == "or_tools":
            # Serialised: at most one future ever sits on `self.pool.executor`, so
            # `restart()` below can never cancel a *different* build's future — see the
            # lock's own docstring on `PlanBuilder`.
            async with self._or_tools_lock:
                loop = asyncio.get_running_loop()
                future = loop.run_in_executor(
                    self.pool.executor,
                    partial(
                        solve_day,
                        tickets,
                        engineers,
                        matrices,
                        day=plan_date,
                        time_limit=self.solver_time_limit,
                    ),
                )
                watchdog_timeout = (
                    self.solver_time_limit.total_seconds() + self.solver_watchdog_margin_s
                )
                try:
                    day_plan = await asyncio.wait_for(future, timeout=watchdog_timeout)
                except TimeoutError:
                    # `time_limit` is the budget the solver itself is handed and expected
                    # to respect; this is the backstop for when it (or the worker process)
                    # does not — a genuine hang, not a slow-but-honest search. The worker
                    # cannot be reasoned with, only ended: `restart()` kills it and stands
                    # up a fresh executor so the next `or_tools` build is not stuck behind
                    # a broken pool. `future.cancel()` is a no-op on the outcome (the
                    # process backing it is already dead) but keeps its exception from
                    # being set-and-never-retrieved once the killed worker's death
                    # surfaces on it.
                    self.pool.restart()
                    future.cancel()
                    raise _SolverTimedOut from None
        else:
            day_plan = baseline.solve_day(tickets, engineers, matrices, day=plan_date)
        return explain(day_plan, tickets, engineers, matrices, day=plan_date)

    async def _matrices(
        self, engineers: Sequence[Engineer], tickets: Sequence[Ticket]
    ) -> Mapping[VehicleType, TravelMatrix]:
        """One matrix per vehicle type of the brigades, over the brigades' start points
        then the tickets' points, in `tickets` order — the point order `solve_day`,
        `baseline.solve_day` and `explain` all assume. Requested at once: the first failed
        graph cancels the rest instead of waiting for them."""
        vehicle_types = {e.vehicle_type for e in engineers}
        points = [e.start for e in engineers] + [t.location for t in tickets]
        try:
            async with asyncio.TaskGroup() as tg:
                tasks = {v: tg.create_task(self.osrm.table(v, points)) for v in vehicle_types}
        except* (DependencyUnavailable, ValueError) as eg:
            # Everything `OsrmClient.table` can raise (a failed request as
            # `DependencyUnavailable`, a malformed answer as `ValueError`). A `TaskGroup`
            # always wraps its tasks' exceptions in a group, even a single one, and a mix
            # of the two types would too: unwrapped to the first one regardless of which,
            # so a caller sees a plain exception either way.
            raise eg.exceptions[0] from None
        return {v: task.result() for v, task in tasks.items()}

    async def _fail(self, plan_id: int, reason: str) -> None:
        try:
            async with database_errors("plan_build_fail"), self.connect() as conn:
                await self.mark_plan_failed(conn, plan_id, reason)
        except AppError:
            # Already logged by `database_errors`; the plan stays `running` forever, same
            # as a backend restart mid-build — a fresh `POST /plan/build` is the recovery.
            pass


async def sweep_running_plans(
    connect: Connect,
    mark_running_plans_failed: MarkRunningPlansFailed,
    failed_reason: str = "shutdown",
) -> list[int]:
    """Closes every plan left `running` from an earlier, ungraceful stop — across every
    region, since a single `backend` instance owns the whole database. Called once from
    `app.py`'s `lifespan`, before the app accepts requests, not per region and not from a
    request handler. Never raises: a database unreachable at startup must not stop the app
    from coming up — the plans stay `running` until the next restart."""
    try:
        async with database_errors("plan_startup_sweep"), connect() as conn:
            closed = await mark_running_plans_failed(conn, failed_reason)
    except AppError as e:
        # Already logged once by `database_errors` (a driver failure) or unreachable (any
        # other `AppError` `mark_running_plans_failed` could raise) -- this record names
        # the sweep specifically, since that one names only the query.
        logger.warning("plan_startup_sweep_failed", reason=e.reason)
        return []
    if closed:
        logger.info("plan_startup_sweep_finished", count=len(closed))
    return closed


def _validate_window(tickets: Sequence[Ticket], plan_date: date) -> None:
    """Brigade shifts are counted from `plan_date`; a ticket of another date would make
    the model meaningless with no signal of that in the output."""
    if any(t.window_start.date() != plan_date for t in tickets):
        raise InvalidInput(
            "plan_date_mismatch",
            message="Не у всех открытых заявок региона окно приходится на дату плана",
        )


def _validate_size(
    engineers: Sequence[Engineer], tickets: Sequence[Ticket], max_table_size: int
) -> None:
    if len(engineers) + len(tickets) > max_table_size:
        raise InvalidInput(
            "too_many_points",
            message="Слишком много точек для одного запроса матрицы времени в пути",
            params={"engineers": len(engineers), "tickets": len(tickets)},
        )


def _assignment_writes(plan: ExplainedPlan) -> list[AssignmentWrite]:
    if plan.status is SolveStatus.INFEASIBLE:
        return []
    writes = [
        AssignmentWrite(
            ticket_id=visit.visit.ticket_id,
            engineer_id=route.engineer_id,
            sequence_no=i,
            planned_arrival=visit.visit.arrival,
            travel_time_min=visit.visit.travel_min,
            travel_distance_m=round(visit.visit.distance_m),
            unassigned_reason=None,
            explanation=visit.explanation,
        )
        for route in plan.routes
        for i, visit in enumerate(route.visits, start=1)
    ]
    writes += [
        AssignmentWrite(
            ticket_id=u.ticket_id,
            engineer_id=None,
            sequence_no=None,
            planned_arrival=None,
            travel_time_min=None,
            travel_distance_m=None,
            unassigned_reason=u.reason.value,
            explanation=u.explanation,
        )
        for u in plan.unassigned
    ]
    return writes
