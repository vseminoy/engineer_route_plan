from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from src.api.deps import get_region_lists, get_ticket_statuses
from src.api.schemas.generated import models as api
from src.domain import Engineer, Ticket, TicketStatus
from src.errors import AppError, DatabaseFailure, DependencyUnavailable
from src.logging import get_logger
from src.service.region_lists import RegionLists
from src.service.ticket_status import TicketStatuses

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["regions"])

# The `region` query parameter as `RegionCode` in the contract.
RegionQuery = Annotated[str, Query(min_length=1, max_length=50, pattern="^[a-z][a-z0-9_]*$")]
Lists = Annotated[RegionLists, Depends(get_region_lists)]
# The `ticket_id` path parameter as in the contract: a BIGINT key.
TicketId = Annotated[int, Path(ge=1, le=9223372036854775807)]
Statuses = Annotated[TicketStatuses, Depends(get_ticket_statuses)]


def _log_failed(event: str, error: AppError, **params: object) -> None:
    """A dependency's failure at `error`; the client's mistake (bad input, an unknown
    resource) at `warning`."""
    failed = isinstance(error, DependencyUnavailable | DatabaseFailure)
    log = logger.error if failed else logger.warning
    log(event, reason=error.reason, **(params | error.params))


def _engineer(e: Engineer) -> api.Engineer:
    return api.Engineer(
        id=e.id,
        name=e.name,
        vehicle_type=api.VehicleType(e.vehicle_type.value),
        skills=[api.Skill(s.value) for s in e.skills],
        shift_start=api.LocalTime(e.shift_start.strftime("%H:%M")),
        shift_end=api.LocalTime(e.shift_end.strftime("%H:%M")),
        start=api.Point(lat=e.start.lat, lon=e.start.lon),
    )


def _ticket(t: Ticket) -> api.Ticket:
    return api.Ticket(
        id=t.id,
        external_id=t.external_id,
        type_bk=t.type_bk,
        type_hd=t.type_hd,
        required_skill=api.Skill(t.required_skill.value),
        required_vehicle=api.VehicleType(t.required_vehicle.value) if t.required_vehicle else None,
        priority=t.priority,
        district=t.district,
        address=t.address,
        location=api.Point(lat=t.location.lat, lon=t.location.lon),
        window_start=api.LocalDateTime(t.window_start.isoformat()),
        window_end=api.LocalDateTime(t.window_end.isoformat()),
        duration_min=t.duration_min,
        status=api.TicketStatus(t.status.value),
        received_at=api.LocalDateTime(t.received_at.isoformat()),
    )


@router.get("/regions", response_model=list[api.Region], operation_id="list_regions")
async def list_regions(lists: Lists) -> list[api.Region]:
    return [api.Region(code=api.RegionCode(r.code), name=r.name) for r in lists.all_regions()]


@router.get("/engineers", response_model=list[api.Engineer], operation_id="list_engineers")
async def list_engineers(region: RegionQuery, lists: Lists) -> list[api.Engineer]:
    try:
        engineers = await lists.engineers(region)
    except AppError as e:
        _log_failed("list_engineers_failed", e, region=region)
        raise
    return [_engineer(e) for e in engineers]


@router.get("/tickets", response_model=list[api.Ticket], operation_id="list_tickets")
async def list_tickets(region: RegionQuery, lists: Lists) -> list[api.Ticket]:
    try:
        tickets = await lists.tickets(region)
    except AppError as e:
        _log_failed("list_tickets_failed", e, region=region)
        raise
    return [_ticket(t) for t in tickets]


@router.patch(
    "/tickets/{ticket_id}/status",
    response_model=api.Ticket,
    operation_id="change_ticket_status",
)
async def change_ticket_status(
    ticket_id: TicketId, body: api.TicketStatusChange, statuses: Statuses
) -> api.Ticket:
    try:
        ticket = await statuses.change(ticket_id, TicketStatus(body.status.value))
    except AppError as e:
        _log_failed("ticket_status_change_failed", e, ticket_id=ticket_id)
        raise
    return _ticket(ticket)
