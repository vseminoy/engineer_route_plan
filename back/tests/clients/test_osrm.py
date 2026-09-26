import json
import traceback
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from src.clients.osrm import Graph, Leg, OsrmClient, Route, TravelMatrix, create_osrm_client
from src.config import Settings
from src.domain import Point, VehicleType
from src.errors import DependencyUnavailable
from tests.log_records import events, json_logs, records

A = Point(lat=55.751244, lon=37.618423)
B = Point(lat=55.733842, lon=37.588144)
C = Point(lat=55.700846, lon=37.782219)
D = Point(lat=55.796127, lon=37.537434)

Handler = Callable[[httpx.Request], httpx.Response]


def _ok_table(request: httpx.Request) -> httpx.Response:
    """A consistent answer for any request: cell (i, j) = 100·i + j seconds, 10× metres."""
    n = len(request.url.path.rsplit("/", 1)[1].split(";"))
    sources_param = request.url.params.get("sources")
    sources = [int(i) for i in sources_param.split(";")] if sources_param else list(range(n))
    return httpx.Response(
        200,
        json={
            "code": "Ok",
            "durations": [[100.0 * i + j for j in range(n)] for i in sources],
            "distances": [[1000.0 * i + 10 * j for j in range(n)] for i in sources],
        },
    )


class Graphs:
    """One mock transport per graph; each keeps the requests it received."""

    def __init__(self, **handlers: Handler) -> None:
        self.seen: dict[Graph, list[httpx.Request]] = {g: [] for g in Graph}
        self.http: dict[Graph, httpx.AsyncClient] = {}
        for graph in Graph:
            handler = handlers.get(graph.value, _ok_table)

            def record(
                request: httpx.Request, graph: Graph = graph, handler: Handler = handler
            ) -> httpx.Response:
                self.seen[graph].append(request)
                return handler(request)

            self.http[graph] = httpx.AsyncClient(
                base_url=f"http://osrm-{graph}.test", transport=httpx.MockTransport(record)
            )

    def client(self, *, max_table_size: int = 1000) -> OsrmClient:
        return OsrmClient(self.http, public_transport_factor=1.5, max_table_size=max_table_size)


def _reply(status: int, body: Any) -> Handler:
    return lambda _: httpx.Response(status, json=body)


def _raise(error: Exception) -> Handler:
    def handler(_: httpx.Request) -> httpx.Response:
        raise error

    return handler


def _url(*points: Point) -> str:
    """Coordinates as the client writes them: `lon,lat`, five decimals (about a metre)."""
    return ";".join(f"{p.lon:.5f},{p.lat:.5f}" for p in points)


def _coordinates(request: httpx.Request) -> str:
    return request.url.path.rsplit("/", 1)[1]


# --- table ---------------------------------------------------------------------------


async def test_table_car(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs("DEBUG")
    graphs = Graphs(
        car=_reply(
            200,
            {
                "code": "Ok",
                "durations": [[0, 612.4], [655.1, 0]],
                "distances": [[0, 5010.2], [5230.7, 0]],
            },
        )
    )
    matrix = await graphs.client().table(VehicleType.CAR, [A, B])

    assert matrix == TravelMatrix(
        durations_s=[[0.0, 612.4], [655.1, 0.0]], distances_m=[[0.0, 5010.2], [5230.7, 0.0]]
    )
    (request,) = graphs.seen[Graph.CAR]
    assert request.url.path == f"/table/v1/car/{_url(A, B)}"
    assert str(A.lat) not in request.url.path  # 55.751244 goes out as 55.75124
    assert dict(request.url.params) == {"annotations": "duration,distance"}
    (record,) = events(capsys, "osrm_request_finished")
    assert record["level"] == "debug"
    assert record["endpoint"] == "table"
    assert record["profile"] == "car"
    assert record["points"] == 2
    assert record["status"] == 200
    assert isinstance(record["duration_ms"], int)


@pytest.mark.parametrize("vehicle", [VehicleType.CAR, VehicleType.FOOT, VehicleType.BIKE])
async def test_table_uses_graph_of_vehicle(vehicle: VehicleType) -> None:
    graphs = Graphs()
    matrix = await graphs.client().table(vehicle, [A, B])

    graph = Graph(vehicle.value)
    (request,) = graphs.seen[graph]
    assert request.url.path.startswith(f"/table/v1/{graph}/")
    assert all(not graphs.seen[other] for other in Graph if other is not graph)
    assert matrix.durations_s == [[0.0, 1.0], [100.0, 101.0]]


async def test_table_public_transport_is_car_times_factor(
    capsys: pytest.CaptureFixture[str],
) -> None:
    json_logs("DEBUG")
    graphs = Graphs(
        car=_reply(
            200,
            {"code": "Ok", "durations": [[0, 600], [700, 0]], "distances": [[0, 5000], [5200, 0]]},
        )
    )
    matrix = await graphs.client().table(VehicleType.PUBLIC_TRANSPORT, [A, B])

    assert len(graphs.seen[Graph.CAR]) == 1
    assert matrix.durations_s == [[0.0, 900.0], [1050.0, 0.0]]
    assert matrix.distances_m == [[0.0, 5000.0], [5200.0, 0.0]]
    (record,) = events(capsys, "osrm_request_finished")
    assert record["profile"] == "car"


async def test_table_empty_points() -> None:
    graphs = Graphs()
    assert await graphs.client().table(VehicleType.CAR, []) == TravelMatrix([], [])
    assert all(not seen for seen in graphs.seen.values())


@pytest.mark.parametrize("vehicle", [VehicleType.CAR, VehicleType.PUBLIC_TRANSPORT])
async def test_table_single_point(vehicle: VehicleType) -> None:
    graphs = Graphs(car=_reply(400, {"code": "InvalidOptions"}))
    assert await graphs.client().table(vehicle, [A]) == TravelMatrix([[0.0]], [[0.0]])
    assert all(not seen for seen in graphs.seen.values())


@pytest.mark.parametrize("vehicle", [VehicleType.CAR, VehicleType.PUBLIC_TRANSPORT])
async def test_table_null_cell_is_none(vehicle: VehicleType) -> None:
    graphs = Graphs(
        car=_reply(
            200,
            {"code": "Ok", "durations": [[0, None], [700, 0]], "distances": [[0, None], [5200, 0]]},
        )
    )
    matrix = await graphs.client().table(vehicle, [A, B])

    assert matrix.durations_s[0][1] is None
    assert matrix.distances_m[0][1] is None


async def test_table_in_strips_over_limit(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs("DEBUG")
    graphs = Graphs()
    matrix = await graphs.client(max_table_size=3).table(VehicleType.CAR, [A, B, C, D])

    first, second = graphs.seen[Graph.CAR]
    assert _coordinates(first) == _coordinates(second) == _url(A, B, C, D)
    assert first.url.params["sources"] == "0;1"
    assert second.url.params["sources"] == "2;3"
    assert matrix.durations_s == [[100.0 * i + j for j in range(4)] for i in range(4)]
    assert matrix.distances_m == [[1000.0 * i + 10 * j for j in range(4)] for i in range(4)]
    assert len(events(capsys, "osrm_request_finished")) == 2


async def test_table_strip_failure_fails_whole_matrix() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _ok_table(request) if calls == 1 else httpx.Response(503)

    graphs = Graphs(car=handler)
    with pytest.raises(DependencyUnavailable) as raised:
        await graphs.client(max_table_size=3).table(VehicleType.CAR, [A, B, C, D])
    assert raised.value.reason == "osrm_unavailable"


async def test_table_server_error(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    graphs = Graphs(foot=lambda _: httpx.Response(503, text="Service Unavailable"))
    with pytest.raises(DependencyUnavailable) as raised:
        await graphs.client().table(VehicleType.FOOT, [A, B])

    assert raised.value.reason == "osrm_unavailable"
    (record,) = events(capsys, "osrm_request_failed")
    assert record["level"] == "error"
    assert record["endpoint"] == "table"
    assert record["profile"] == "foot"
    assert record["points"] == 2
    assert record["status"] == 503
    assert record["error"] == "http_error"
    assert isinstance(record["duration_ms"], int)


@pytest.mark.parametrize("code", ["TooBig", "NoSegment", "InvalidQuery"])
async def test_table_error_code(capsys: pytest.CaptureFixture[str], code: str) -> None:
    json_logs()
    graphs = Graphs(car=_reply(400, {"code": code, "message": "details"}))
    with pytest.raises(DependencyUnavailable):
        await graphs.client().table(VehicleType.CAR, [A, B])

    (record,) = events(capsys, "osrm_request_failed")
    assert record["status"] == 400
    assert record["error"] == code


@pytest.mark.parametrize("error", [httpx.ReadTimeout("timed out"), httpx.ConnectError("refused")])
async def test_table_timeout_and_network_error(
    capsys: pytest.CaptureFixture[str], error: Exception
) -> None:
    json_logs()
    graphs = Graphs(car=_raise(error))
    with pytest.raises(DependencyUnavailable):
        await graphs.client().table(VehicleType.CAR, [A, B])

    (record,) = events(capsys, "osrm_request_failed")
    assert record["status"] is None
    assert record["error"] == type(error).__name__


async def test_table_url_too_long(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    points = [Point(lat=55.5 + i * 1e-5, lon=37.5 + i * 1e-5) for i in range(4000)]
    graphs = Graphs()
    with pytest.raises(DependencyUnavailable):
        await graphs.client(max_table_size=4000).table(VehicleType.CAR, points)

    (record,) = events(capsys, "osrm_request_failed")
    assert record["error"] == "InvalidURL"
    assert record["points"] == 4000


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(200, text="not json"), "malformed_response"),
        (httpx.Response(200, json={"code": "Ok"}), "malformed_response"),
        (
            httpx.Response(200, json={"code": "Ok", "durations": [[0, 1]], "distances": [[0, 1]]}),
            "malformed_response",
        ),
        (httpx.Response(200, json={"code": "NoTable"}), "NoTable"),
        (
            httpx.Response(
                200,
                text='{"code": "Ok", "durations": [[0, Infinity], [1, 0]], "distances": [[0, 1], [1, 0]]}',
            ),
            "malformed_response",
        ),
        (
            httpx.Response(
                200,
                text='{"code": "Ok", "durations": [[0, NaN], [1, 0]], "distances": [[0, 1], [1, 0]]}',
            ),
            "malformed_response",
        ),
        (
            httpx.Response(
                200,
                text='{"code": "Ok", "durations": [[0, 1%s], [1, 0]], "distances": [[0, 1], [1, 0]]}'
                % ("0" * 400),
            ),
            "malformed_response",
        ),
        (httpx.Response(502, text="Bad Gateway"), "http_error"),
        (httpx.Response(200, text="[" * 200_000), "malformed_response"),
    ],
    ids=[
        "not-json",
        "no-durations",
        "too-few-rows",
        "code-not-ok",
        "infinity",
        "nan",
        "number-overflow",
        "non-json-error-status",
        "deep-nesting",
    ],
)
async def test_table_malformed_response(
    capsys: pytest.CaptureFixture[str], response: httpx.Response, error: str
) -> None:
    json_logs("DEBUG")
    graphs = Graphs(car=lambda _: response)
    with pytest.raises(DependencyUnavailable):
        await graphs.client().table(VehicleType.CAR, [A, B])

    logged = records(capsys)
    (record,) = [r for r in logged if r["event"] == "osrm_request_failed"]
    assert record["error"] == error
    assert isinstance(record["duration_ms"], int)
    # One record per request: a rejected body is a failure, not a finished request.
    assert [r for r in logged if r["event"] == "osrm_request_finished"] == []


async def test_graph_failure_does_not_affect_other_graphs() -> None:
    graphs = Graphs(foot=lambda _: httpx.Response(503))
    client = graphs.client()
    with pytest.raises(DependencyUnavailable):
        await client.table(VehicleType.FOOT, [A, B])
    matrix = await client.table(VehicleType.CAR, [A, B])
    assert matrix.durations_s == [[0.0, 1.0], [100.0, 101.0]]


# --- route ---------------------------------------------------------------------------

_ROUTE = {
    "code": "Ok",
    "routes": [
        {
            "duration": 1500.5,
            "distance": 12000.0,
            "legs": [
                {"duration": 600.0, "distance": 5000.0},
                {"duration": 900.5, "distance": 7000.0},
            ],
            "geometry": {
                "type": "LineString",
                "coordinates": [[A.lon, A.lat], [37.6, 55.74], [B.lon, B.lat], [C.lon, C.lat]],
            },
        }
    ],
}


def _route_body(
    *, legs: int = 1, coordinates: list[list[float]] | None = None, duration: object = 600.0
) -> dict[str, Any]:
    """A two-point route answer with one part changed."""
    return {
        "code": "Ok",
        "routes": [
            {
                "duration": duration,
                "distance": 5000.0,
                "legs": [{"duration": 600.0, "distance": 5000.0}] * legs,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[A.lon, A.lat], [B.lon, B.lat]]
                    if coordinates is None
                    else coordinates,
                },
            }
        ],
    }


async def test_route_found(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs("DEBUG")
    graphs = Graphs(car=_reply(200, _ROUTE))
    route = await graphs.client().route(VehicleType.CAR, [A, B, C])

    assert route == Route(
        duration_s=1500.5,
        distance_m=12000.0,
        legs=[Leg(duration_s=600.0, distance_m=5000.0), Leg(duration_s=900.5, distance_m=7000.0)],
        geometry=[A, Point(lat=55.74, lon=37.6), B, C],
    )
    (request,) = graphs.seen[Graph.CAR]
    assert request.url.path.startswith("/route/v1/car/")
    assert dict(request.url.params) == {"overview": "full", "geometries": "geojson"}
    (record,) = events(capsys, "osrm_request_finished")
    assert record["endpoint"] == "route"
    assert record["found"] is True


async def test_route_public_transport_is_car_times_factor() -> None:
    body = {
        "code": "Ok",
        "routes": [
            {
                "duration": 600.0,
                "distance": 5000.0,
                "legs": [{"duration": 600.0, "distance": 5000.0}],
                "geometry": {"type": "LineString", "coordinates": [[A.lon, A.lat], [B.lon, B.lat]]},
            }
        ],
    }
    graphs = Graphs(car=_reply(200, body))
    route = await graphs.client().route(VehicleType.PUBLIC_TRANSPORT, [A, B])

    assert len(graphs.seen[Graph.CAR]) == 1
    assert route is not None
    assert route.duration_s == 900.0
    assert route.legs == [Leg(duration_s=900.0, distance_m=5000.0)]
    assert route.distance_m == 5000.0
    assert route.geometry == [A, B]


async def test_route_no_route(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs("DEBUG")
    graphs = Graphs(car=_reply(400, {"code": "NoRoute", "message": "Impossible route"}))
    assert await graphs.client().route(VehicleType.CAR, [A, B]) is None

    (record,) = events(capsys, "osrm_request_finished")
    assert record["status"] == 400
    assert record["found"] is False
    assert events(capsys, "osrm_request_failed") == []


@pytest.mark.parametrize(
    "handler",
    [
        lambda _: httpx.Response(503),
        _reply(400, {"code": "NoSegment"}),
        _raise(httpx.ConnectError("refused")),
        _reply(200, {"code": "Ok"}),
        _reply(200, {"code": "Ok", "routes": [{"duration": 1, "distance": 1, "legs": []}]}),
        _reply(200, _route_body(legs=0)),
        _reply(200, _route_body(coordinates=[])),
        _reply(200, _route_body(duration=True)),
    ],
    ids=[
        "503",
        "no-segment",
        "network",
        "no-routes",
        "no-geometry",
        "legs-differ",
        "empty-geometry",
        "duration-not-number",
    ],
)
async def test_route_errors(capsys: pytest.CaptureFixture[str], handler: Handler) -> None:
    json_logs("DEBUG")
    graphs = Graphs(car=handler)
    with pytest.raises(DependencyUnavailable) as raised:
        await graphs.client().route(VehicleType.CAR, [A, B])

    assert raised.value.reason == "osrm_unavailable"
    logged = records(capsys)
    (record,) = [r for r in logged if r["event"] == "osrm_request_failed"]
    assert record["endpoint"] == "route"
    assert [r for r in logged if r["event"] == "osrm_request_finished"] == []


@pytest.mark.parametrize("points", [[], [A]], ids=["none", "one"])
async def test_route_needs_two_points(points: list[Point]) -> None:
    graphs = Graphs()
    with pytest.raises(ValueError):
        await graphs.client().route(VehicleType.CAR, points)
    assert all(not seen for seen in graphs.seen.values())


# --- creation, closing, logs ---------------------------------------------------------


async def test_create_osrm_client_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.test:3128")
    monkeypatch.setenv("ALL_PROXY", "http://proxy.test:3128")
    settings = Settings(
        database_url="postgresql://test/test",
        osrm_url_car="http://osrm-car:5000",
        osrm_url_foot="http://osrm-foot:5000",
        osrm_url_bike="http://osrm-bike:5000",
        public_transport_factor=2.0,
        osrm_max_table_size=500,
        osrm_timeout_s=45,
    )
    client = create_osrm_client(settings)
    try:
        http = client._graphs
        assert {g: str(h.base_url) for g, h in http.items()} == {
            Graph.CAR: "http://osrm-car:5000",
            Graph.FOOT: "http://osrm-foot:5000",
            Graph.BIKE: "http://osrm-bike:5000",
        }
        assert all(h.timeout == httpx.Timeout(45.0) for h in http.values())
        # The proxy of the environment is not used: every graph connects directly.
        assert all(h.trust_env is False for h in http.values())
        assert client._factor == 2.0
        assert client._max_cells == 500 * 500
    finally:
        await client.aclose()


async def test_aclose_closes_every_graph() -> None:
    graphs = Graphs()
    await graphs.client().aclose()
    assert all(http.is_closed for http in graphs.http.values())


async def test_logs_no_coordinates(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs("DEBUG")
    await Graphs().client().table(VehicleType.CAR, [A, B])
    await Graphs(car=_reply(200, _ROUTE)).client().route(VehicleType.CAR, [A, B, C])
    with pytest.raises(DependencyUnavailable):
        await Graphs(car=lambda _: httpx.Response(503)).client().table(VehicleType.CAR, [A, B])
    with pytest.raises(DependencyUnavailable):
        await (
            Graphs(car=_raise(httpx.ConnectError("refused")))
            .client()
            .route(VehicleType.CAR, [A, B])
        )

    logged = records(capsys)
    assert {r["event"] for r in logged} >= {"osrm_request_finished", "osrm_request_failed"}
    text = json.dumps(logged)
    for point in (A, B, C):
        assert str(point.lat) not in text
        assert str(point.lon) not in text


async def test_route_error_carries_no_coordinates() -> None:
    body = _route_body(coordinates=[[37.61234, 95.43219], [B.lon, B.lat]])
    graphs = Graphs(car=_reply(200, body))
    with pytest.raises(DependencyUnavailable) as raised:
        await graphs.client().route(VehicleType.CAR, [A, B])

    chain = "".join(traceback.format_exception(raised.value))
    assert "95.43219" not in chain
    assert "37.61234" not in chain
