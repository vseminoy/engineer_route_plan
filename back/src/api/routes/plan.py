from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Query

from src.api.deps import get_plan_builder, get_plan_reader, get_region_lists, get_replanner
from src.api.schemas.generated import models as api
from src.domain import Point, VehicleType
from src.errors import AppError, DatabaseFailure, DependencyUnavailable, InvalidInput
from src.logging import get_logger
from src.repository.plans import PlanSummaryRow
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
from src.service.region_lists import RegionLists
from src.service.replan import (
    AssignmentChange,
    EngineerUnavailableEvent,
    IncidentInput,
    NewTicketEvent,
    NewUrgentTicketEvent,
    PlanDiff,
    RegularTicketInput,
    ReplanEvent,
    Replanner,
    TicketCancelledEvent,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["plan"])

Builder = Annotated[PlanBuilder, Depends(get_plan_builder)]
Reader = Annotated[PlanReader, Depends(get_plan_reader)]
Lists = Annotated[RegionLists, Depends(get_region_lists)]
ReplannerDep = Annotated[Replanner, Depends(get_replanner)]
# `plan_id`/`baseline_plan_id` as in the contract: a BIGINT key.
PlanId = Annotated[int, Path(ge=1, le=9223372036854775807)]
BaselinePlanId = Annotated[int, Query(ge=1, le=9223372036854775807)]
# The `region`/`engineer_set_id` query parameters as in the contract, same pattern as regions.py.
RegionQuery = Annotated[str, Query(min_length=1, max_length=50, pattern="^[a-z][a-z0-9_]*$")]
EngineerSetIdQuery = Annotated[int | None, Query(ge=1, le=9223372036854775807)]


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
        region=api.RegionCode(p.region_code),
        engineer_set_id=p.engineer_set_id,
        engineers=[_engineer_route(r) for r in p.engineers] if p.engineers is not None else None,
        unassigned=[_unassigned(u) for u in p.unassigned] if p.unassigned is not None else None,
        metrics=_metrics(p.metrics) if p.metrics is not None else None,
        failed_reason=api.PlanFailedReason(p.failed_reason) if p.failed_reason else None,
    )


def _plan_summary(p: PlanSummaryRow) -> api.PlanSummary:
    return api.PlanSummary(
        plan_id=p.id,
        region=api.RegionCode(p.region_code),
        engineer_set_id=p.engineer_set_id,
        plan_date=api.LocalDate(p.plan_date.isoformat()),
        algorithm=api.PlanAlgorithm(p.algorithm),
        status=api.PlanStatus(p.status),
        created_at=api.LocalDateTime(p.created_at.isoformat()),
        parent_plan_id=p.parent_plan_id,
        failed_reason=api.PlanFailedReason(p.failed_reason) if p.failed_reason else None,
    )


@router.get("/plan", response_model=list[api.PlanSummary], operation_id="list_plans")
async def list_plans(
    region: RegionQuery, lists: Lists, engineer_set_id: EngineerSetIdQuery = None
) -> list[api.PlanSummary]:
    try:
        plans = await lists.plans(region, engineer_set_id)
    except AppError as e:
        _log_failed("list_plans_failed", e, region=region, engineer_set_id=engineer_set_id)
        raise
    return [_plan_summary(p) for p in plans]


@router.post("/plan/build", response_model=api.Plan, status_code=202, operation_id="build_plan")
async def build_plan(
    body: api.PlanBuildRequest, background_tasks: BackgroundTasks, builder: Builder
) -> api.Plan:
    plan_date = _plan_date(body.plan_date)
    region = body.region.root
    algorithm = body.algorithm.value
    try:
        queued = await builder.enqueue(region, plan_date, algorithm, body.engineer_set_id)
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
        region=body.region,
        engineer_set_id=queued.engineer_set_id,
    )


@router.get("/plan/{plan_id}", response_model=api.Plan, operation_id="get_plan")
async def get_plan(plan_id: PlanId, reader: Reader) -> api.Plan:
    try:
        plan = await reader.get(plan_id)
    except AppError as e:
        _log_failed("plan_get_failed", e, plan_id=plan_id)
        raise
    return _plan(plan)


@router.delete("/plan/{plan_id}", status_code=204, operation_id="delete_plan")
async def delete_plan(plan_id: PlanId, reader: Reader) -> None:
    try:
        await reader.delete(plan_id)
    except AppError as e:
        _log_failed("plan_delete_failed", e, plan_id=plan_id)
        raise


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


def _field_datetime(value: api.LocalDateTime, field: str) -> datetime:
    """As `_plan_date`: the contract's pattern already rejects a malformed grouping, only
    a non-existent calendar date/time (2026-02-30) still needs rejecting here."""
    try:
        return datetime.fromisoformat(value.root)
    except ValueError:
        raise InvalidInput(
            "datetime_invalid", fields=[(field, "Несуществующие дата или время")]
        ) from None


def _triggered_at(value: api.LocalDateTime) -> datetime:
    return _field_datetime(value, "triggered_at")


def _incident_input(t: api.IncidentTicketInput) -> IncidentInput:
    return IncidentInput(
        external_id=t.external_id,
        type_bk=t.type_bk,
        type_hd=t.type_hd,
        district=t.district,
        address=t.address,
        location=Point(lat=t.location.lat, lon=t.location.lon),
        required_vehicle=VehicleType(t.required_vehicle.value) if t.required_vehicle else None,
    )


def _regular_ticket_input(t: api.RegularTicketInput) -> RegularTicketInput:
    return RegularTicketInput(
        external_id=t.external_id,
        type_bk=t.type_bk,
        type_hd=t.type_hd,
        district=t.district,
        address=t.address,
        location=Point(lat=t.location.lat, lon=t.location.lon),
        required_vehicle=VehicleType(t.required_vehicle.value) if t.required_vehicle else None,
        window_start=_field_datetime(t.window_start, "ticket.window_start"),
        window_end=_field_datetime(t.window_end, "ticket.window_end"),
    )


def _replan_event(body: api.ReplanEventRequest) -> ReplanEvent:
    event = body.root
    if isinstance(event, api.NewUrgentTicketEvent):
        return NewUrgentTicketEvent(
            triggered_at=_triggered_at(event.triggered_at),
            ticket=_incident_input(event.ticket),
            reaction_min=event.reaction_min if event.reaction_min is not None else 120,
        )
    if isinstance(event, api.NewTicketEvent):
        return NewTicketEvent(
            triggered_at=_triggered_at(event.triggered_at),
            ticket=_regular_ticket_input(event.ticket),
        )
    if isinstance(event, api.TicketCancelledEvent):
        return TicketCancelledEvent(
            triggered_at=_triggered_at(event.triggered_at), ticket_id=event.ticket_id
        )
    return EngineerUnavailableEvent(
        triggered_at=_triggered_at(event.triggered_at), engineer_id=event.engineer_id
    )


def _assignment_change(c: AssignmentChange) -> api.AssignmentChange:
    return api.AssignmentChange(
        ticket_id=c.ticket_id,
        before_engineer_id=c.before_engineer_id,
        after_engineer_id=c.after_engineer_id,
        before_sequence_no=c.before_sequence_no,
        after_sequence_no=c.after_sequence_no,
    )


def _plan_diff(d: PlanDiff) -> api.PlanDiff:
    return api.PlanDiff(
        changed_assignments=[_assignment_change(c) for c in d.changed_assignments],
        newly_assigned=d.newly_assigned,
        newly_unassigned=d.newly_unassigned,
        reassigned_from_unavailable_engineer=d.reassigned_from_unavailable_engineer,
        plan_stability=d.plan_stability,
    )


@router.post(
    "/plan/{plan_id}/replan", response_model=api.PlanReplanResult, operation_id="replan_plan"
)
async def replan_plan(
    plan_id: PlanId, body: api.ReplanEventRequest, replanner: ReplannerDep, reader: Reader
) -> api.PlanReplanResult:
    try:
        event = _replan_event(body)
        outcome = await replanner.replan(plan_id, event)
        plan = await reader.get(outcome.plan_id)
    except AppError as e:
        _log_failed("plan_replan_failed", e, plan_id=plan_id)
        raise
    assert plan.engineers is not None
    assert plan.unassigned is not None
    assert plan.metrics is not None
    return api.PlanReplanResult(
        plan_id=outcome.plan_id,
        parent_plan_id=outcome.parent_plan_id,
        algorithm=api.PlanAlgorithm(outcome.algorithm),
        region=api.RegionCode(plan.region_code),
        engineer_set_id=outcome.engineer_set_id,
        status=api.Status1.done,
        engineers=[_engineer_route(r) for r in plan.engineers],
        unassigned=[_unassigned(u) for u in plan.unassigned],
        metrics=_metrics(plan.metrics),
        diff=_plan_diff(outcome.diff),
    )
