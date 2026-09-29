from datetime import date
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Query

from src.api.deps import get_plan_builder, get_plan_reader
from src.api.schemas.generated import models as api
from src.errors import AppError, DatabaseFailure, DependencyUnavailable, InvalidInput
from src.logging import get_logger
from src.service.plan_builder import PlanBuilder
from src.service.plan_reader import (
    ComparisonEntryRead,
    EngineerRouteRead,
    MetricsRead,
    PlanRead,
    PlanReader,
    UnassignedRead,
    VisitRead,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["plan"])

Builder = Annotated[PlanBuilder, Depends(get_plan_builder)]
Reader = Annotated[PlanReader, Depends(get_plan_reader)]
# `plan_id`/`baseline_plan_id` as in the contract: a BIGINT key.
PlanId = Annotated[int, Path(ge=1, le=9223372036854775807)]
BaselinePlanId = Annotated[int, Query(ge=1, le=9223372036854775807)]


def _log_failed(event: str, error: AppError, **params: object) -> None:
    """A dependency's failure at `error`; the client's mistake (bad input, an unknown
    resource) at `warning`."""
    failed = isinstance(error, DependencyUnavailable | DatabaseFailure)
    log = logger.error if failed else logger.warning
    log(event, reason=error.reason, **(params | error.params))


def _log_compare_failed(error: AppError, plan_id: int, baseline_plan_id: int) -> None:
    """Not `_log_failed`: `error.params["plan_id"]` (from `PlanReader.compare`) names
    whichever of the two plans actually failed, which may be `baseline_plan_id` — merging
    it in would silently overwrite the path's own `plan_id` in the log record."""
    failed = isinstance(error, DependencyUnavailable | DatabaseFailure)
    log = logger.error if failed else logger.warning
    log(
        "plan_compare_failed",
        reason=error.reason,
        plan_id=plan_id,
        baseline_plan_id=baseline_plan_id,
    )


def _plan_date(value: api.LocalDate) -> date:
    """The contract's pattern accepts any well-formed digit grouping; a non-existent
    calendar date (2026-02-30) still needs rejecting here, as `400`."""
    try:
        return date.fromisoformat(value.root)
    except ValueError:
        raise InvalidInput(
            "plan_date_invalid", fields=[("plan_date", "Несуществующая дата")]
        ) from None


def _visit(v: VisitRead) -> api.Visit:
    return api.Visit(
        ticket_id=v.ticket_id,
        sequence_no=v.sequence_no,
        planned_arrival=api.LocalDateTime(v.planned_arrival.isoformat()),
        travel_time_min=v.travel_time_min,
        travel_distance_km=v.travel_distance_km,
        explanation=v.explanation,
    )


def _engineer_route(r: EngineerRouteRead) -> api.EngineerRoute:
    return api.EngineerRoute(
        engineer_id=r.engineer_id,
        name=r.name,
        route=[_visit(v) for v in r.route],
        total_distance_km=r.total_distance_km,
        total_travel_time_min=r.total_travel_time_min,
        idle_time_min=r.idle_time_min,
    )


def _unassigned(u: UnassignedRead) -> api.UnassignedTicket:
    return api.UnassignedTicket(
        ticket_id=u.ticket_id,
        reason_code=api.UnassignedReason(u.reason_code),
        explanation=u.explanation,
    )


def _metrics(m: MetricsRead) -> api.PlanMetrics:
    return api.PlanMetrics(
        engineers_used=m.engineers_used,
        total_distance_km=m.total_distance_km,
        distance_by_engineer={str(k): v for k, v in m.distance_by_engineer.items()},
        assigned_count=m.assigned_count,
        unassigned_count=m.unassigned_count,
        idle_time_by_engineer_min={str(k): v for k, v in m.idle_time_by_engineer_min.items()},
    )


def _comparison_entry(e: ComparisonEntryRead) -> api.PlanComparisonEntry:
    return api.PlanComparisonEntry(
        metric=api.PlanComparisonMetric(e.metric), main=e.main, baseline=e.baseline, delta=e.delta
    )


def _plan(p: PlanRead) -> api.Plan:
    return api.Plan(
        plan_id=p.plan_id,
        algorithm=api.PlanAlgorithm(p.algorithm),
        status=api.PlanStatus(p.status),
        engineers=[_engineer_route(r) for r in p.engineers] if p.engineers is not None else None,
        unassigned=[_unassigned(u) for u in p.unassigned] if p.unassigned is not None else None,
        metrics=_metrics(p.metrics) if p.metrics is not None else None,
        failed_reason=api.PlanFailedReason(p.failed_reason) if p.failed_reason else None,
    )


@router.post("/plan/build", response_model=api.Plan, status_code=202, operation_id="build_plan")
async def build_plan(
    body: api.PlanBuildRequest, background_tasks: BackgroundTasks, builder: Builder
) -> api.Plan:
    plan_date = _plan_date(body.plan_date)
    region = body.region.root
    algorithm = body.algorithm.value
    try:
        queued = await builder.enqueue(region, plan_date, algorithm)
    except AppError as e:
        _log_failed("plan_build_failed", e, region=region, plan_date=str(plan_date))
        raise
    background_tasks.add_task(
        builder.build, queued.plan_id, queued.tickets, queued.engineers, plan_date, algorithm
    )
    return api.Plan(
        plan_id=queued.plan_id,
        algorithm=api.PlanAlgorithm(queued.algorithm),
        status=api.PlanStatus.running,
    )


@router.get("/plan/{plan_id}", response_model=api.Plan, operation_id="get_plan")
async def get_plan(plan_id: PlanId, reader: Reader) -> api.Plan:
    try:
        plan = await reader.get(plan_id)
    except AppError as e:
        _log_failed("plan_get_failed", e, plan_id=plan_id)
        raise
    return _plan(plan)


@router.get(
    "/plan/{plan_id}/compare",
    response_model=list[api.PlanComparisonEntry],
    operation_id="compare_plan",
)
async def compare_plan(
    plan_id: PlanId, baseline_plan_id: BaselinePlanId, reader: Reader
) -> list[api.PlanComparisonEntry]:
    try:
        entries = await reader.compare(plan_id, baseline_plan_id)
    except AppError as e:
        _log_compare_failed(e, plan_id, baseline_plan_id)
        raise
    return [_comparison_entry(e) for e in entries]
