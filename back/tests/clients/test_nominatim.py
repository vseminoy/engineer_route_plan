import asyncio
from collections.abc import Callable

import httpx
import pytest

from src.clients.nominatim import NominatimClient
from src.domain import Point
from src.errors import DependencyUnavailable
from tests.log_records import events, json_logs, records

QUERY = "Волгоградский проспект 128к5, Москва"


class FakeClock:
    """Time that moves only when the client sleeps, plus 0.2 s per request."""

    def __init__(self) -> None:
        self.now = 100.0
        self.starts: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


def _client(
    handler: Callable[[httpx.Request], httpx.Response], clock: FakeClock | None = None
) -> tuple[NominatimClient, list[httpx.Request], FakeClock]:
    seen: list[httpx.Request] = []
    clock = clock or FakeClock()

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        clock.starts.append(clock.now)
        clock.now += 0.2
        return handler(request)

    http = httpx.AsyncClient(
        base_url="https://nominatim.test",
        headers={"User-Agent": "engineer-route-plan/test"},
        transport=httpx.MockTransport(record),
    )
    return NominatimClient(http, clock=clock, sleep=clock.sleep), seen, clock


async def test_search_found(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs("DEBUG")
    client, seen, _ = _client(
        lambda _: httpx.Response(200, json=[{"lat": "55.7008460", "lon": "37.7822191"}])
    )
    assert await client.search(QUERY) == Point(lat=55.700846, lon=37.7822191)
    (request,) = seen
    assert request.url.path == "/search"
    assert dict(request.url.params) == {
        "q": QUERY,
        "format": "jsonv2",
        "countrycodes": "ru",
        "limit": "1",
    }
    assert request.headers["User-Agent"] == "engineer-route-plan/test"
    (record,) = events(capsys, "nominatim_request_finished")
    assert record["level"] == "debug"
    assert record["status"] == 200
    assert record["found"] is True
    assert "duration_ms" in record


async def test_search_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs("DEBUG")
    client, _, _ = _client(lambda _: httpx.Response(200, json=[]))
    assert await client.search(QUERY) is None
    (record,) = events(capsys, "nominatim_request_finished")
    assert record["found"] is False


async def test_rate_limit() -> None:
    client, _, clock = _client(lambda _: httpx.Response(200, json=[]))
    for _ in range(3):
        await client.search(QUERY)
    gaps = [b - a for a, b in zip(clock.starts, clock.starts[1:], strict=False)]
    assert len(gaps) == 2
    assert all(gap >= 1.0 for gap in gaps)


async def test_rate_limit_concurrent() -> None:
    client, _, clock = _client(lambda _: httpx.Response(200, json=[]))
    await asyncio.gather(*(client.search(QUERY) for _ in range(3)))
    gaps = [b - a for a, b in zip(clock.starts, clock.starts[1:], strict=False)]
    assert len(gaps) == 2
    assert all(gap >= 1.0 for gap in gaps)


async def test_server_error(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    client, _, _ = _client(lambda _: httpx.Response(503))
    with pytest.raises(DependencyUnavailable) as e:
        await client.search(QUERY)
    assert e.value.reason == "geocoder_unavailable"
    (record,) = events(capsys, "nominatim_request_failed")
    assert record["status"] == 503
    assert "duration_ms" in record


@pytest.mark.parametrize("status", [429, 403])
async def test_rate_limited_or_forbidden(capsys: pytest.CaptureFixture[str], status: int) -> None:
    json_logs()
    client, _, _ = _client(lambda _: httpx.Response(status))
    with pytest.raises(DependencyUnavailable):
        await client.search(QUERY)
    assert events(capsys, "nominatim_request_failed")[0]["status"] == status


@pytest.mark.parametrize("error", [httpx.ConnectTimeout, httpx.ConnectError])
async def test_timeout_and_network_error(
    capsys: pytest.CaptureFixture[str], error: type[httpx.TransportError]
) -> None:
    json_logs()

    def fail(request: httpx.Request) -> httpx.Response:
        raise error("boom", request=request)

    client, _, _ = _client(fail)
    with pytest.raises(DependencyUnavailable):
        await client.search(QUERY)
    assert events(capsys, "nominatim_request_failed")[0]["status"] is None


@pytest.mark.parametrize(
    "response",
    [httpx.Response(200, text="<html>"), httpx.Response(200, json=[{"lon": "37.7"}])],
)
async def test_malformed_response(
    capsys: pytest.CaptureFixture[str], response: httpx.Response
) -> None:
    json_logs()
    client, _, _ = _client(lambda _: response)
    with pytest.raises(DependencyUnavailable):
        await client.search(QUERY)
    assert events(capsys, "nominatim_request_failed")


async def test_logs_no_address(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    client, _, _ = _client(lambda _: httpx.Response(200, json=[]))
    await client.search(QUERY)
    client, _, _ = _client(lambda _: httpx.Response(503))
    with pytest.raises(DependencyUnavailable):
        await client.search(QUERY)
    logged = str(records(capsys))
    assert "Волгоградский" not in logged
    assert "128к5" not in logged


@pytest.fixture(autouse=True)
def _info_level_after() -> object:
    """Leaves the process at INFO: a DEBUG handler bound to a closed capture stream would
    fail on the debug records other libraries write later in the session."""
    yield
    json_logs()
