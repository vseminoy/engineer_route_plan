from pathlib import Path

import pytest
import schemathesis
from schemathesis import Case, DataGenerationMethod

from src.app import create_app
from src.config import Settings

# specs/openapi.yaml declares `openapi: 3.1.0` (profile.yaml, stack.contract). 3.1
# support in schemathesis is gated behind an experimental flag, without which schema
# loading raises SchemaError("...currently not fully supported").
# Source: schemathesis.experimental.OPEN_API_3_1
# (https://github.com/schemathesis/schemathesis/discussions/1822), verified against
# the installed schemathesis==3.39.16.
schemathesis.experimental.OPEN_API_3_1.enable()

_OPENAPI_PATH = Path(__file__).resolve().parents[3] / "specs" / "openapi.yaml"

_app = create_app(
    settings=Settings(database_url="postgresql://test/test", osrm_url="http://osrm.test")
)

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
