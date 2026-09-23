import json

import pytest
from fastapi.testclient import TestClient

from src import app as app_module
from src.config import Settings


class _FakePool:
    def __init__(self) -> None:
        self.opened_wait: bool | str = "unset"
        self.closed_called = False

    async def open(self, wait: bool = True) -> None:
        self.opened_wait = wait

    async def close(self) -> None:
        self.closed_called = True


def _fake_settings() -> Settings:
    return Settings(database_url="postgresql://test/test", osrm_url="http://osrm.test")


def test_lifespan_creates_and_opens_db_pool_without_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_pool = _FakePool()
    monkeypatch.setattr(app_module, "create_db_pool", lambda settings: fake_pool)
    app = app_module.create_app(settings=_fake_settings())

    with TestClient(app):
        assert app.state.db_pool is fake_pool
        assert fake_pool.opened_wait is False


def test_lifespan_creates_osrm_client(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_pool = _FakePool()
    monkeypatch.setattr(app_module, "create_db_pool", lambda settings: fake_pool)
    app = app_module.create_app(settings=_fake_settings())

    with TestClient(app):
        assert str(app.state.osrm_client.base_url) == "http://osrm.test"


def test_lifespan_closes_pool_and_client_on_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_pool = _FakePool()
    monkeypatch.setattr(app_module, "create_db_pool", lambda settings: fake_pool)
    app = app_module.create_app(settings=_fake_settings())

    with TestClient(app):
        osrm_client = app.state.osrm_client

    assert fake_pool.closed_called is True
    assert osrm_client.is_closed is True


def test_create_app_registers_health_route() -> None:
    # Since fastapi 0.137, `include_router()` appends a single `_IncludedRouter`
    # wrapper to `app.routes` instead of flattening the sub-routes; the wrapper has
    # no `.path`. The runtime-generated OpenAPI document is the stable way to check
    # what is actually registered.
    # Source: https://github.com/fastapi/fastapi/discussions/15791
    app = app_module.create_app(settings=_fake_settings())
    assert "/health" in app.openapi()["paths"]


def test_request_id_header_generated_when_absent() -> None:
    app = app_module.create_app(settings=_fake_settings())

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.headers["x-request-id"]


def test_request_id_header_echoed_when_provided() -> None:
    app = app_module.create_app(settings=_fake_settings())

    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "custom-id"})

    assert response.headers["x-request-id"] == "custom-id"


def test_request_id_header_rejects_invalid_value() -> None:
    app = app_module.create_app(settings=_fake_settings())

    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "not a valid id!"})

    request_id = response.headers["x-request-id"]
    assert request_id != "not a valid id!"
    assert app_module._SAFE_REQUEST_ID.fullmatch(request_id)


def test_http_request_finished_is_logged(capsys: pytest.CaptureFixture[str]) -> None:
    # `capture_logs()` can't be used here: entering `TestClient` runs `lifespan`,
    # which calls `configure_logging` — that replaces structlog's global config
    # (not just its processors, unlike `capture_logs`'s own swap) partway through
    # the `with`, so the request's own log never reaches the capture. Reading the
    # real (JSON) stderr output side-steps the conflict and matches what the app
    # actually emits.
    app = app_module.create_app(settings=_fake_settings())

    with TestClient(app) as client:
        client.get("/health")

    lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    events = [json.loads(line) for line in lines]
    finished = [e for e in events if e["event"] == "http_request_finished"]

    assert len(finished) == 1
    assert finished[0]["method"] == "GET"
    assert finished[0]["path"] == "/health"
    assert finished[0]["status"] == 200
    assert isinstance(finished[0]["duration_ms"], int)


def test_http_request_finished_is_logged_on_unhandled_exception(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # No exception handler is registered yet (`10-errors.md` adds one in a later
    # changeset), so an unhandled exception must still reach the access log —
    # otherwise a 5xx request disappears from observability entirely.
    app = app_module.create_app(settings=_fake_settings())

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500

    lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    events = [json.loads(line) for line in lines]
    finished = [e for e in events if e["event"] == "http_request_finished"]

    assert len(finished) == 1
    assert finished[0]["status"] == 500
    assert finished[0]["path"] == "/boom"
