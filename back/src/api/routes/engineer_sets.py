from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from src.api.deps import get_engineer_sets
from src.api.schemas.generated import models as api
from src.domain import EngineerSet
from src.errors import AppError, DatabaseFailure, DependencyUnavailable
from src.logging import get_logger
from src.service.engineer_sets import EngineerSets

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["engineer-sets"])

# The `region` query parameter as `RegionCode` in the contract, same pattern as regions.py.
RegionQuery = Annotated[str, Query(min_length=1, max_length=50, pattern="^[a-z][a-z0-9_]*$")]
Sets = Annotated[EngineerSets, Depends(get_engineer_sets)]
# The `engineer_set_id` path parameter as in the contract: a BIGINT key.
EngineerSetId = Annotated[int, Path(ge=1, le=9223372036854775807)]


def _log_failed(event: str, error: AppError, **params: object) -> None:
    """A dependency's failure at `error`; the client's mistake (bad input, an unknown
    resource) at `warning`."""
    failed = isinstance(error, DependencyUnavailable | DatabaseFailure)
    log = logger.error if failed else logger.warning
    log(event, reason=error.reason, **(params | error.params))


def _description(e: EngineerSet) -> str:
    return (
        f"Бригад: {e.engineers}; утренняя смена: {round(e.morning_share * 100)}%; "
        f"вечерняя смена: {round(e.evening_share * 100)}%; seed: {e.seed}"
    )


def _engineer_set(e: EngineerSet) -> api.EngineerSet:
    return api.EngineerSet(
        id=e.id,
        name=e.name,
        kind=api.EngineerSetKind(e.kind.value),
        engineers=e.engineers,
        morning_share=e.morning_share,
        evening_share=e.evening_share,
        seed=e.seed,
        description=_description(e),
    )


@router.get(
    "/engineer-sets", response_model=list[api.EngineerSet], operation_id="list_engineer_sets"
)
async def list_engineer_sets(region: RegionQuery, sets: Sets) -> list[api.EngineerSet]:
    try:
        engineer_sets = await sets.list(region)
    except AppError as e:
        _log_failed("list_engineer_sets_failed", e, region=region)
        raise
    return [_engineer_set(s) for s in engineer_sets]


@router.post(
    "/engineer-sets",
    response_model=api.EngineerSet,
    status_code=201,
    operation_id="create_engineer_set",
)
async def create_engineer_set(body: api.EngineerSetCreateRequest, sets: Sets) -> api.EngineerSet:
    region = body.region.root
    try:
        created = await sets.create(
            region, body.name, body.engineers, body.morning_share, body.evening_share, body.seed
        )
    except AppError as e:
        _log_failed("engineer_set_create_failed", e, region=region)
        raise
    return _engineer_set(created)


@router.delete(
    "/engineer-sets/{engineer_set_id}", status_code=204, operation_id="delete_engineer_set"
)
async def delete_engineer_set(engineer_set_id: EngineerSetId, sets: Sets) -> None:
    try:
        await sets.delete(engineer_set_id)
    except AppError as e:
        _log_failed("engineer_set_delete_failed", e, engineer_set_id=engineer_set_id)
        raise
