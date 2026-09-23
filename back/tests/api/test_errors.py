import json
import re
from enum import StrEnum
from typing import Annotated, Any

import pytest
from fastapi import APIRouter, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from src.api.schemas.generated.common import ValidationError
from src.app import create_app
from src.config import Settings
from src.errors import AppError, Conflict, DependencyUnavailable, InvalidInput, NotFound
from src.logging import get_logger

log = get_logger("test")


class PlanNotFound(NotFound):
    pass


class Kind(StrEnum):
    repair = "repair"
    emergency = "emergency"


class Engineer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skills: Annotated[list[str], Field(min_length=1, max_length=3)]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")
    region: Annotated[str, Field(min_length=2, max_length=10, pattern=r"^[a-z]+$")]
    count: Annotated[int, Field(ge=1, le=5)]
    kind: Kind = Kind.repair
    engineers: list[Engineer] = []


class IdsBody(BaseModel):
    ids: list[int]


class CustomBody(BaseModel):
    code: str

    @field_validator("code")
    @classmethod
    def reject(cls, value: str) -> str:
        raise PydanticCustomError("project_specific", "custom failure")


class _DriverError(Exception):
    sqlstate = "08006"


async def _fetch_sample(sample_id: int) -> None:
    """Stands in for a repository call whose driver fails."""
    try:
        raise _DriverError("connection lost")
    except _DriverError as e:
        log.exception("db_query_failed", query="get_sample", sqlstate=e.sqlstate)
        raise DependencyUnavailable(reason="db_unavailable") from e


_ERRORS: dict[str, AppError] = {
    "not_found": NotFound(reason="x"),
    "plan_not_found": PlanNotFound(reason="plan_not_found"),
    "conflict": Conflict(reason="x"),
    "dependency": DependencyUnavailable(reason="x"),
    "bare": AppError(reason="x"),
}

router = APIRouter(prefix="/t")


@router.get("/invalid-message")
async def invalid_message() -> None:
    raise InvalidInput(reason="file_empty", message="Файл не содержит ни одной заявки")


@router.get("/invalid-fields")
async def invalid_fields() -> None:
    raise InvalidInput(
        reason="window_order", fields=[("window_start", "Начало окна позже его окончания")]
    )


@router.get("/raise/{kind}")
async def raise_error(kind: str) -> None:
    raise _ERRORS[kind]


@router.get("/boom")
async def boom() -> None:
    raise RuntimeError("boom secret")


@router.post("/body")
async def post_body(body: Body, limit: Annotated[int, Query(ge=1, le=100)] = 10) -> None:
    return None


@router.post("/ids")
async def post_ids(body: IdsBody) -> None:
    return None


@router.post("/custom")
async def post_custom(body: CustomBody) -> None:
    return None


@router.get("/samples/{sample_id}")
async def load_sample(sample_id: int) -> None:
    try:
        if sample_id == 5:
            raise NotFound(reason="sample_not_found", params={"sample_id": sample_id})
        await _fetch_sample(sample_id)
    except AppError as e:
        level = log.warning if not isinstance(e, DependencyUnavailable) else log.error
        level("load_sample_failed", reason=e.reason, **e.params)
        raise


def _client() -> TestClient:
    settings = Settings(database_url="postgresql://test/test", osrm_url="http://osrm.test")
    app = create_app(settings=settings)
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def _events(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    # Reads the real JSON stderr rather than `capture_logs()`: that one replaces the
    # processor chain, so `request_id` from contextvars never reaches the captured
    # event, and module loggers cached on first use would not see it at all.
    events = []
    for line in capsys.readouterr().err.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return events


def _valid_body(**overrides: Any) -> dict[str, Any]:
    return {"region": "north", "count": 2, **overrides}


# --- exception → status -------------------------------------------------------


def test_invalid_input_message_returns_400_with_message() -> None:
    with _client() as client:
        response = client.get("/t/invalid-message")

    assert response.status_code == 400
    assert response.json() == {"message": "Файл не содержит ни одной заявки"}
    ValidationError.model_validate(response.json())
    assert response.headers["x-request-id"]


def test_invalid_input_fields_returns_400_with_fields() -> None:
    with _client() as client:
        response = client.get("/t/invalid-fields")

    assert response.status_code == 400
    assert response.json() == {
        "fields": [{"name": "window_start", "message": "Начало окна позже его окончания"}]
    }


@pytest.mark.parametrize(
    ("kind", "status"),
    [("not_found", 404), ("conflict", 409), ("dependency", 503), ("plan_not_found", 404)],
)
def test_bodyless_error_codes(kind: str, status: int) -> None:
    with _client() as client:
        response = client.get(f"/t/raise/{kind}")

    assert response.status_code == status
    assert response.content == b""
    assert "content-type" not in response.headers
    assert response.headers["x-request-id"]


def test_unmapped_app_error_returns_500(capsys: pytest.CaptureFixture[str]) -> None:
    with _client() as client:
        response = client.get("/t/raise/bare")

    assert response.status_code == 500
    assert response.content == b""
    assert [e for e in _events(capsys) if e["event"] == "unhandled_error"]


def test_app_error_is_not_logged_by_handler(capsys: pytest.CaptureFixture[str]) -> None:
    with _client() as client:
        client.get("/t/raise/not_found")

    names = {e["event"] for e in _events(capsys)}
    assert "unhandled_error" not in names
    assert "request_validation_failed" not in names


# --- RequestValidationError ----------------------------------------------------


def test_validation_error_returns_400_not_422() -> None:
    with _client() as client:
        response = client.post("/t/body", json={"region": "north"})

    assert response.status_code == 400
    assert response.json() == {"fields": [{"name": "count", "message": "Обязательное поле"}]}
    assert response.headers["x-request-id"]


@pytest.mark.parametrize(
    ("body", "query", "name"),
    [({"region": "", "count": 2}, "", "region"), (_valid_body(), "?limit=0", "limit")],
    ids=["body", "query"],
)
def test_field_name_drops_body_and_query_prefix(
    body: dict[str, Any], query: str, name: str
) -> None:
    with _client() as client:
        response = client.post(f"/t/body{query}", json=body)

    assert [f["name"] for f in response.json()["fields"]] == [name]


def test_nested_field_name_uses_dots_and_brackets() -> None:
    engineers = [{"skills": ["a"]}, {"skills": ["b"]}, {"skills": []}]
    with _client() as client:
        response = client.post("/t/body", json=_valid_body(engineers=engineers))

    assert [f["name"] for f in response.json()["fields"]] == ["engineers[2].skills"]


def test_every_invalid_field_is_reported() -> None:
    with _client() as client:
        response = client.post("/t/body", json={"region": "A", "count": 0})

    assert sorted(f["name"] for f in response.json()["fields"]) == ["count", "region"]


@pytest.mark.parametrize(
    ("body", "limit"),
    [
        ({"region": "north"}, None),  # missing
        (_valid_body(region="abcdefghijk"), "10"),  # string_too_long
        (_valid_body(region="a"), "2"),  # string_too_short
        (_valid_body(count=0), "1"),  # greater_than_equal
        (_valid_body(count=6), "5"),  # less_than_equal
        (_valid_body(count="x"), None),  # int_parsing
        (_valid_body(extra=1), None),  # extra_forbidden
        (_valid_body(kind="zzz"), None),  # enum
        (_valid_body(region="ABC"), None),  # string_pattern_mismatch
    ],
    ids=[
        "missing",
        "string_too_long",
        "string_too_short",
        "greater_than_equal",
        "less_than_equal",
        "int_parsing",
        "extra_forbidden",
        "enum",
        "string_pattern_mismatch",
    ],
)
def test_pydantic_message_is_translated(body: dict[str, Any], limit: str | None) -> None:
    with _client() as client:
        response = client.post("/t/body", json=body)

    (field,) = response.json()["fields"]
    assert re.search("[а-яА-Я]", field["message"])
    if limit is not None:
        assert limit in field["message"]


def test_unknown_pydantic_type_gets_generic_message() -> None:
    with _client() as client:
        response = client.post("/t/custom", json={"code": "x"})

    assert response.json() == {"fields": [{"name": "code", "message": "Некорректное значение"}]}


def test_malformed_json_body_returns_400_message() -> None:
    with _client() as client:
        response = client.post(
            "/t/body", content=b'{"region": ', headers={"content-type": "application/json"}
        )

    assert response.status_code == 400
    assert response.json() == {"message": "Тело запроса — некорректный JSON"}


def test_undecodable_body_returns_400_message() -> None:
    with _client() as client:
        response = client.post(
            "/t/body", content=b'\xff\xfe{"a":1}', headers={"content-type": "application/json"}
        )

    assert response.status_code == 400
    assert response.json() == {"message": "Тело запроса отсутствует или имеет неверный формат"}


def test_validation_errors_are_capped(capsys: pytest.CaptureFixture[str]) -> None:
    with _client() as client:
        response = client.post("/t/ids", json={"ids": ["a"] * 100})

    assert response.status_code == 400
    assert len(response.json()["fields"]) == 20
    (record,) = [e for e in _events(capsys) if e["event"] == "request_validation_failed"]
    assert len(record["fields"]) == 20
    assert record["errors_total"] == 100


def test_long_field_name_is_truncated() -> None:
    with _client() as client:
        response = client.post("/t/body", json=_valid_body(**{"k" * 500: 1}))

    (field,) = response.json()["fields"]
    assert field["name"] == "k" * 200


def test_malformed_json_is_logged_without_field_names(capsys: pytest.CaptureFixture[str]) -> None:
    with _client() as client:
        client.post("/t/body", content=b'{"region": ', headers={"content-type": "application/json"})

    (record,) = [e for e in _events(capsys) if e["event"] == "request_validation_failed"]
    assert record["fields"] == []


def test_validation_error_is_logged_without_values(capsys: pytest.CaptureFixture[str]) -> None:
    with _client() as client:
        client.post("/t/body?limit=-1", json=_valid_body(region="Секретный адрес"))

    failed = [e for e in _events(capsys) if e["event"] == "request_validation_failed"]
    assert len(failed) == 1
    assert failed[0]["level"] == "warning"
    assert failed[0]["path"] == "/t/body"
    assert failed[0]["fields"] == ["limit", "region"]
    assert "Секретный адрес" not in json.dumps(failed[0], ensure_ascii=False)
    assert "-1" not in json.dumps(failed[0])


# --- Starlette responses and unexpected errors ----------------------------------


def test_unknown_path_returns_404_without_body() -> None:
    with _client() as client:
        response = client.get("/unknown")

    assert response.status_code == 404
    assert response.content == b""
    assert response.headers["x-request-id"]


def test_unmatched_request_logs_marker_not_path(capsys: pytest.CaptureFixture[str]) -> None:
    with _client() as client:
        client.get("/unknown/user@mail.ru")

    (record,) = [e for e in _events(capsys) if e["event"] == "http_request_finished"]
    assert record["path"] == "<unmatched>"
    assert "user@mail.ru" not in json.dumps(record)


def test_method_not_allowed_returns_405_without_body() -> None:
    with _client() as client:
        response = client.post("/health")

    assert response.status_code == 405
    assert response.content == b""
    assert response.headers["allow"] == "GET"
    assert response.headers["x-request-id"]


def test_unhandled_exception_returns_500_without_body() -> None:
    with _client() as client:
        response = client.get("/t/boom")

    assert response.status_code == 500
    assert response.content == b""


def test_500_has_request_id_header() -> None:
    with _client() as client:
        response = client.get("/t/boom", headers={"X-Request-ID": "trace-500"})

    assert response.headers["x-request-id"] == "trace-500"


def test_unhandled_exception_is_logged_with_stack(capsys: pytest.CaptureFixture[str]) -> None:
    with _client() as client:
        response = client.get("/t/boom")

    (record,) = [e for e in _events(capsys) if e["event"] == "unhandled_error"]
    assert record["level"] == "error"
    assert "RuntimeError: boom secret" in record["exception"]
    assert record["request_id"] == response.headers["x-request-id"]
    assert b"boom" not in response.content


# --- log chain of one dependency failure ----------------------------------------


def test_dependency_error_logs_origin_and_route_with_same_request_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with _client() as client:
        response = client.get("/t/samples/1")

    assert response.status_code == 503
    assert response.content == b""
    events = _events(capsys)
    errors = [e for e in events if e["event"].endswith("_failed")]
    assert [e["event"] for e in errors] == ["db_query_failed", "load_sample_failed"]
    assert not [e for e in events if e["event"] == "unhandled_error"]
    origin, route = errors
    assert origin["level"] == "error"
    assert origin["query"] == "get_sample"
    assert origin["sqlstate"] == "08006"
    assert route["level"] == "error"
    assert route["reason"] == "db_unavailable"
    request_id = response.headers["x-request-id"]
    assert origin["request_id"] == route["request_id"] == request_id


def test_client_error_logs_route_failure_at_warning(capsys: pytest.CaptureFixture[str]) -> None:
    with _client() as client:
        response = client.get("/t/samples/5")

    assert response.status_code == 404
    (route,) = [e for e in _events(capsys) if e["event"] == "load_sample_failed"]
    assert route["level"] == "warning"
    assert route["reason"] == "sample_not_found"
    assert route["sample_id"] == 5
