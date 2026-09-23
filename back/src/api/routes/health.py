from importlib.metadata import version

from fastapi import APIRouter

from src.api.schemas.generated.models import HealthStatus, Status

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus, operation_id="get_health")
async def get_health() -> HealthStatus:
    return HealthStatus(status=Status.ok, version=version("engineer-route-plan-backend"))
