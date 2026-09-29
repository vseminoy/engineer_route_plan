from datetime import date
from pathlib import Path

import pytest
import schemathesis
from schemathesis import Case, DataGenerationMethod

from src.api.deps import (
    get_engineer_sets,
    get_loader,
    get_plan_builder,
    get_plan_reader,
    get_region_lists,
    get_replanner,
    get_ticket_statuses,
)
from src.app import create_app
from src.config import Settings
from src.domain import Engineer, EngineerSet, Ticket
from src.errors import InvalidInput
from src.service.loader import LoadResult
from src.service.plan_builder import QueuedPlan
from src.service.plan_reader import MetricsRead, PlanRead
from tests.api.region_fakes import (
    ENGINEER,
    ENGINEER_SET,
    TICKET,
    FakeEngineerSets,
    FakeLists,
    FakeLoader,
    FakePlanBuilder,
    FakePlanReader,
    FakeReplanner,
    FakeStatuses,
)

# specs/openapi.yaml declares `openapi: 3.1.0` (profile.yaml, stack.contract). 3.1
# support in schemathesis is gated behind an experimental flag, without which schema
# loading raises SchemaError("...currently not fully supported").
# Source: schemathesis.experimental.OPEN_API_3_1
# (https://github.com/schemathesis/schemathesis/discussions/1822), verified against
# the installed schemathesis==3.39.16.
schemathesis.experimental.OPEN_API_3_1.enable()

_OPENAPI_PATH = Path(__file__).resolve().parents[3] / "specs" / "openapi.yaml"

_REGIONS = frozenset({"east", "south_east", "south_center"})


def _check_region(region: str) -> None:
    if region not in _REGIONS:
        raise InvalidInput("unknown_region", fields=[("region", "Неизвестный регион")])


class _Lists(FakeLists):
    """Valid results for a configured region, the contract's `400` for any other."""

    async def engineers(self, region: str, engineer_set_id: int | None = None) -> list[Engineer]:
        _check_region(region)
        return await super().engineers(region, engineer_set_id)

    async def tickets(self, region: str) -> list[Ticket]:
        _check_region(region)
        return await super().tickets(region)


class _Loader(FakeLoader):
    async def load(self, region: str, source: str, data: bytes | None = None) -> LoadResult:
        _check_region(region)
        return await super().load(region, source, data)


class _PlanBuilder(FakePlanBuilder):
    async def enqueue(
        self, region: str, plan_date: date, algorithm: str, engineer_set_id: int | None
    ) -> QueuedPlan:
        _check_region(region)
        return await super().enqueue(region, plan_date, algorithm, engineer_set_id)


class _EngineerSets(FakeEngineerSets):
    """Valid results for a configured region, the contract's `400` for any other."""

    async def list(self, region: str) -> list[EngineerSet]:
        _check_region(region)
        return await super().list(region)

    async def create(
        self,
        region: str,
        name: str,
        engineers: int,
        morning_share: float,
        evening_share: float,
        seed: str,
    ) -> EngineerSet:
        _check_region(region)
        return await super().create(region, name, engineers, morning_share, evening_share, seed)


_DONE_PLAN = PlanRead(
    plan_id=1,
    algorithm="or_tools",
    engineer_set_id=70,
    status="done",
    failed_reason=None,
    engineers=(),
    unassigned=(),
    metrics=MetricsRead(
        engineers_used=0,
        total_distance_km=0,
        distance_by_engineer={},
        assigned_count=0,
        unassigned_count=0,
        idle_time_by_engineer_min={},
    ),
)


_app = create_app(
    settings=Settings(
        database_url="postgresql://test/test",
        osrm_url_car="http://osrm.test",
        osrm_url_foot="http://osrm.test",
        osrm_url_bike="http://osrm.test",
    )
)
# The data services stand in for the database: the positive cases then check the shape
# of successful answers, which a missing database would turn into `503`.
_lists, _loader, _statuses = _Lists(), _Loader(), FakeStatuses()
_plan_builder = _PlanBuilder(
    queued=QueuedPlan(
        plan_id=1, algorithm="or_tools", engineer_set_id=70, tickets=[TICKET], engineers=[ENGINEER]
    )
)
_plan_reader = FakePlanReader(_DONE_PLAN)
_replanner = FakeReplanner()
_engineer_sets = _EngineerSets(sets=[ENGINEER_SET])
_app.dependency_overrides[get_region_lists] = lambda: _lists
_app.dependency_overrides[get_loader] = lambda: _loader
_app.dependency_overrides[get_ticket_statuses] = lambda: _statuses
_app.dependency_overrides[get_plan_builder] = lambda: _plan_builder
_app.dependency_overrides[get_plan_reader] = lambda: _plan_reader
_app.dependency_overrides[get_replanner] = lambda: _replanner
_app.dependency_overrides[get_engineer_sets] = lambda: _engineer_sets

# Negative cases send requests that break the spec's constraints; the contract
# answers them with `400`, never `422`.
schema = schemathesis.openapi.from_path(
    _OPENAPI_PATH,
    app=_app,
    data_generation_methods=[DataGenerationMethod.positive, DataGenerationMethod.negative],
)


@pytest.mark.integration
@schema.parametrize()
def test_api_conforms_to_openapi_schema(case: Case) -> None:
    case.call_and_validate()
