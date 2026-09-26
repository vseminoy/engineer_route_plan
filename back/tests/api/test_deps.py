import types
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from src.api.deps import create_db_pool, get_db_connection, get_osrm_client
from src.config import Settings


class _FakeConnection:
    pass


class _FakePool:
    def __init__(self) -> None:
        self.entered = False
        self.exited = False

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[_FakeConnection]:
        self.entered = True
        try:
            yield _FakeConnection()
        finally:
            self.exited = True


def _fake_request(**state: object) -> types.SimpleNamespace:
    app = types.SimpleNamespace(state=types.SimpleNamespace(**state))
    return types.SimpleNamespace(app=app)


async def test_get_db_connection_yields_and_releases() -> None:
    pool = _FakePool()
    request = _fake_request(db_pool=pool)

    agen = get_db_connection(request)  # type: ignore[arg-type]
    conn = await agen.__anext__()
    assert isinstance(conn, _FakeConnection)
    assert pool.entered is True
    assert pool.exited is False

    with pytest.raises(StopAsyncIteration):
        await agen.__anext__()
    assert pool.exited is True


def test_get_db_connection_pool_not_opened_at_import() -> None:
    settings = Settings(
        database_url="postgresql://test/test",
        osrm_url_car="http://localhost:5000",
        osrm_url_foot="http://localhost:5000",
        osrm_url_bike="http://localhost:5000",
    )
    pool = create_db_pool(settings)
    assert pool.closed is True


class _FakeOsrmClient:
    def __init__(self) -> None:
        self.aclose_calls = 0

    async def aclose(self) -> None:
        self.aclose_calls += 1


async def test_get_osrm_client_returns_shared_client() -> None:
    client = _FakeOsrmClient()
    request = _fake_request(osrm_client=client)
    agen = get_osrm_client(request)  # type: ignore[arg-type]
    assert await agen.__anext__() is client


async def test_get_osrm_client_not_closed_per_request() -> None:
    client = _FakeOsrmClient()
    request = _fake_request(osrm_client=client)
    agen = get_osrm_client(request)  # type: ignore[arg-type]
    await agen.__anext__()
    with pytest.raises(StopAsyncIteration):
        await agen.__anext__()
    assert client.aclose_calls == 0
