import json
from typing import Any

import pytest
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from src import app as app_module
from src.clients.osrm import OsrmClient
from src.config import Settings
from src.errors import AppError
from src.service.solver_pool import ProcessSolverPool


class _FakePool:
    def __init__(self) -> None:
        self.opened_wait: bool | str = "unset"
        self.closed_called = False

    async def open(self, wait: bool = True) -> None:
        self.opened_wait = wait

    async def close(self) -> None:
        self.closed_called = True

    def connection(self, timeout: float | None = None) -> None:
        raise AssertionError("the lifespan tests take no connection")


class _FakeOsrmClient:
    def __init__(self) -> None:
        self.aclose_calls = 0

    async def aclose(self) -> None:
        self.aclose_calls += 1


class _FakeSweep:
    """Stands in for `sweep_running_plans`: what it actually does (its behaviour under a
    missing/unreachable database, what it logs) is covered in
    `tests/service/test_plan_builder.py`. Here only the wiring matters — that `lifespan`
    calls it, once, before serving requests."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any]] = []

    async def __call__(self, connect: Any, mark_running_plans_failed: Any) -> list[int]:
        self.calls.append((connect, mark_running_plans_failed))
        return []


@pytest.fixture(autouse=True)
def _stub_sweep(monkeypatch: pytest.MonkeyPatch) -> _FakeSweep:
    fake = _FakeSweep()
    monkeypatch.setattr(app_module, "sweep_running_plans", fake)
    return fake


def _fake_settings() -> Settings:
    return Settings(
        database_url="postgresql://test/test",
        osrm_url_car="http://osrm.test",
        osrm_url_foot="http://osrm.test",
        osrm_url_bike="http://osrm.test",
    )


def test_lifespan_creates_and_opens_db_pool_without_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        assert isinstance(app.state.osrm_client, OsrmClient)


def test_lifespan_closes_pool_and_client_on_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_pool = _FakePool()
    monkeypatch.setattr(app_module, "create_db_pool", lambda settings: fake_pool)
    osrm_client = _FakeOsrmClient()
    monkeypatch.setattr(app_module, "create_osrm_client", lambda settings: osrm_client)
    app = app_module.create_app(settings=_fake_settings())

    with TestClient(app):
        pass

    assert fake_pool.closed_called is True
    assert osrm_client.aclose_calls == 1


def test_lifespan_closes_pool_when_data_files_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_pool = _FakePool()
    osrm_client = _FakeOsrmClient()
    monkeypatch.setattr(app_module, "create_db_pool", lambda settings: fake_pool)
    monkeypatch.setattr(app_module, "create_osrm_client", lambda settings: osrm_client)

    def broken(*args: object) -> None:
        raise ValueError("malformed regions.toml")

    monkeypatch.setattr(app_module, "create_data_services", broken)
    app = app_module.create_app(settings=_fake_settings())

    with pytest.raises(ValueError, match="regions.toml"), TestClient(app):
        pass
    assert fake_pool.closed_called is True
    assert osrm_client.aclose_calls == 1


def test_lifespan_calls_startup_sweep_before_serving(
    monkeypatch: pytest.MonkeyPatch, _stub_sweep: _FakeSweep
) -> None:
    fake_pool = _FakePool()
    monkeypatch.setattr(app_module, "create_db_pool", lambda settings: fake_pool)
    app = app_module.create_app(settings=_fake_settings())

    with TestClient(app):
        assert len(_stub_sweep.calls) == 1


def test_lifespan_uses_process_solver_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_pool = _FakePool()
    monkeypatch.setattr(app_module, "create_db_pool", lambda settings: fake_pool)
    app = app_module.create_app(settings=_fake_settings())

    with TestClient(app):
        assert isinstance(app.state.plan_builder.pool, ProcessSolverPool)


def test_lifespan_shutdown_stops_solver_pool_without_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pool = _FakePool()
    monkeypatch.setattr(app_module, "create_db_pool", lambda settings: fake_pool)
    calls: list[dict[str, Any]] = []
    original_shutdown = ProcessSolverPool.shutdown

    def spy_shutdown(self: ProcessSolverPool, *, cancel_futures: bool = False) -> None:
        calls.append({"cancel_futures": cancel_futures})
        original_shutdown(self, cancel_futures=cancel_futures)

    monkeypatch.setattr(ProcessSolverPool, "shutdown", spy_shutdown)
    app = app_module.create_app(settings=_fake_settings())

    with TestClient(app):
        pass

    assert calls == [{"cancel_futures": True}]


def test_create_app_registers_health_route() -> None:
    # Since fastapi 0.137, `include_router()` appends a single `_IncludedRouter`
    # wrapper to `app.routes` instead of flattening the sub-routes; the wrapper has
    # no `.path`. The runtime-generated OpenAPI document is the stable way to check
    # what is actually registered.
    # Source: https://github.com/fastapi/fastapi/discussions/15791
    app = app_module.create_app(settings=_fake_settings())
    assert "/health" in app.openapi()["paths"]


def test_create_app_registers_not_implemented_stub_last() -> None:
    app = app_module.create_app(settings=_fake_settings())

    assert getattr(app.routes[-1], "path", None) == "/api/v1/{path:path}"


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
    # Reads the real (JSON) stderr rather than `capture_logs()`: `create_app` calls
    # `configure_logging`, which replaces structlog's global config, and what the
    # app actually emits is what the check is about. DEBUG: a successful health
    # probe is logged at that level.
    settings = Settings(
        database_url="postgresql://test/test",
        osrm_url_car="http://osrm.test",
        osrm_url_foot="http://osrm.test",
        osrm_url_bike="http://osrm.test",
        log_level="DEBUG",
    )
    app = app_module.create_app(settings=settings)

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


def test_successful_health_probe_is_not_logged_at_info(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = app_module.create_app(settings=_fake_settings())

    with TestClient(app) as client:
        client.get("/health")

    lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    events = [json.loads(line) for line in lines]
    assert not [e for e in events if e["event"] == "http_request_finished"]


def test_http_request_finished_is_logged_on_unhandled_exception(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The `500` is built by the `Exception` handler outside the request
    # middleware; the request must still reach the access log.
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


def test_create_app_registers_error_handlers() -> None:
    handlers = app_module.create_app(settings=_fake_settings()).exception_handlers

    for exc_class in (AppError, RequestValidationError, StarletteHTTPException, Exception):
        assert exc_class in handlers
