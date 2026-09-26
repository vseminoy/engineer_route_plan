import json

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from src.api.routes.not_implemented import add_not_implemented_stub
from src.app import create_app
from src.config import Settings


def _client() -> TestClient:
    settings = Settings(
        database_url="postgresql://test/test",
        osrm_url_car="http://osrm.test",
        osrm_url_foot="http://osrm.test",
        osrm_url_bike="http://osrm.test",
    )
    return TestClient(create_app(settings=settings))


def test_unimplemented_path_returns_501_without_body() -> None:
    with _client() as client:
        response = client.get("/api/v1/regions")

    assert response.status_code == 501
    assert response.content == b""
    assert "content-type" not in response.headers


@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
def test_stub_answers_any_method(method: str) -> None:
    with _client() as client:
        response = client.request(method, "/api/v1/plan/1/replan")

    assert response.status_code == 501
    assert response.content == b""


@pytest.mark.parametrize("path", ["/api/v1/", "/api/v1/tickets/42/status"])
def test_stub_answers_nested_and_root_paths(path: str) -> None:
    with _client() as client:
        response = client.get(path)

    assert response.status_code == 501
    assert response.content == b""


def _app_with_regions_route() -> FastAPI:
    """`GET /api/v1/regions` registered before the stub, as `create_app` does."""
    router = APIRouter()

    @router.get("/api/v1/regions")
    async def list_regions() -> list[str]:
        return []

    app = FastAPI()
    app.include_router(router)
    add_not_implemented_stub(app)
    return app


def test_implemented_route_takes_precedence_over_stub() -> None:
    with TestClient(_app_with_regions_route()) as client:
        implemented = client.get("/api/v1/regions")
        unimplemented = client.get("/api/v1/engineers")

    assert implemented.status_code == 200
    assert implemented.json() == []
    assert unimplemented.status_code == 501


def test_wrong_method_on_implemented_path_returns_501() -> None:
    # Routing looks for a full path+method match first, and the stub provides one,
    # so an unsupported method gets 501 rather than 405 while the stub exists.
    with TestClient(_app_with_regions_route()) as client:
        response = client.post("/api/v1/regions")

    assert response.status_code == 501
    assert response.content == b""


@pytest.mark.parametrize("path", ["/unknown", "/api/v2/regions"])
def test_path_outside_api_prefix_returns_404(path: str) -> None:
    with _client() as client:
        response = client.get(path)

    assert response.status_code == 404


def test_health_is_not_shadowed_by_stub() -> None:
    with _client() as client:
        response = client.get("/health")

    assert response.status_code == 200


def test_stub_is_absent_from_openapi_schema() -> None:
    settings = Settings(
        database_url="postgresql://test/test",
        osrm_url_car="http://osrm.test",
        osrm_url_foot="http://osrm.test",
        osrm_url_bike="http://osrm.test",
    )
    paths = create_app(settings=settings).openapi()["paths"]

    assert not [path for path in paths if path.startswith("/api/v1")]


def test_stub_request_is_logged_with_request_id(capsys: pytest.CaptureFixture[str]) -> None:
    # Reads the real JSON stderr: `create_app` reconfigures structlog, which
    # `capture_logs()` would not survive.
    with _client() as client:
        response = client.get("/api/v1/regions")

    lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    finished = [e for e in map(json.loads, lines) if e["event"] == "http_request_finished"]

    assert len(finished) == 1
    assert finished[0]["status"] == 501
    assert finished[0]["path"] == "/api/v1/{path:path}"
    assert finished[0]["request_id"] == response.headers["x-request-id"]
