from pathlib import Path

import pytest
import schemathesis
from schemathesis import Case, DataGenerationMethod

from src.api.deps import get_loader, get_region_lists
from src.app import create_app
from src.config import Settings
from src.domain import Engineer, Ticket
from src.errors import InvalidInput
from src.service.loader import LoadResult
from tests.api.region_fakes import FakeLists, FakeLoader

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

    async def engineers(self, region: str) -> list[Engineer]:
        _check_region(region)
        return await super().engineers(region)

    async def tickets(self, region: str) -> list[Ticket]:
        _check_region(region)
        return await super().tickets(region)


class _Loader(FakeLoader):
    async def load(self, region: str, source: str, data: bytes | None = None) -> LoadResult:
        _check_region(region)
        return await super().load(region, source, data)


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
_lists, _loader = _Lists(), _Loader()
_app.dependency_overrides[get_region_lists] = lambda: _lists
_app.dependency_overrides[get_loader] = lambda: _loader

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
