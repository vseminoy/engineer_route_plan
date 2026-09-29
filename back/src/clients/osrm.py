"""Travel time and distance over the road graph (OSRM).

Every profile has its own graph and its own `osrm-routed`: one server answers for exactly the
graph it loaded and ignores the profile named in the path. Public transport has no graph of
its own — it is the car graph with durations multiplied by a factor.
"""

import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar

import httpx

from src.config import Settings
from src.domain import Point, VehicleType
from src.errors import DependencyUnavailable
from src.logging import get_logger

logger = get_logger(__name__)

_T = TypeVar("_T")


class Graph(StrEnum):
    CAR = "car"
    FOOT = "foot"
    BIKE = "bike"


_GRAPH_OF = {
    VehicleType.CAR: Graph.CAR,
    VehicleType.FOOT: Graph.FOOT,
    VehicleType.BIKE: Graph.BIKE,
    VehicleType.PUBLIC_TRANSPORT: Graph.CAR,
}


@dataclass(frozen=True)
class TravelMatrix:
    """Row and column `i` are point `i` of the request; seconds and metres.
    `None` — the graph has no route between the pair."""

    durations_s: list[list[float | None]]
    distances_m: list[list[float | None]]


@dataclass(frozen=True)
class Leg:
    duration_s: float
    distance_m: float


@dataclass(frozen=True)
class Route:
    duration_s: float
    distance_m: float
    legs: list[Leg]
    geometry: list[Point]


class OsrmClient:
    """Any answer other than a result — network error, timeout, a `code` other than `Ok`,
    a body without the expected fields — is `DependencyUnavailable`; the one exception is
    `NoRoute` of `route`, which is `None`. A failure of one graph leaves the others usable.
    The logs never carry coordinates: a ticket's point is a client's address."""

    def __init__(
        self,
        graphs: Mapping[Graph, httpx.AsyncClient],
        *,
        public_transport_factor: float,
        max_table_size: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._graphs = dict(graphs)
        self._factor = public_transport_factor
        self._max_cells = max_table_size * max_table_size
        self._clock = clock

    async def aclose(self) -> None:
        for http in self._graphs.values():
            await http.aclose()

    def _factor_of(self, vehicle: VehicleType) -> float:
        return self._factor if vehicle is VehicleType.PUBLIC_TRANSPORT else 1.0

    async def table(self, vehicle: VehicleType, points: Sequence[Point]) -> TravelMatrix:
        n = len(points)
        # `osrm-routed` refuses a table of a single coordinate, and its answer is known.
        if n <= 1:
            return TravelMatrix(durations_s=[[0.0]] * n, distances_m=[[0.0]] * n)
        graph = _GRAPH_OF[vehicle]
        # `osrm-routed` refuses a table whose sources × destinations exceed the square of
        # its `--max-table-size`, so a large one is requested in strips of source rows.
        # Source: https://github.com/Project-OSRM/osrm-backend/blob/v6.0.0/src/engine/plugins/table.cpp
        strip = self._max_cells // n
        if strip < 1:
            raise ValueError(f"{n} points exceed the OSRM table limit even one row at a time")
        durations: list[list[float | None]] = []
        distances: list[list[float | None]] = []
        for first in range(0, n, strip):
            sources = range(first, min(first + strip, n))
            params = {"annotations": "duration,distance"}
            if len(sources) < n:
                params["sources"] = ";".join(str(i) for i in sources)

            def rows(body: Any, count: int = len(sources)) -> tuple[list[Any], list[Any]]:
                found = body["durations"], body["distances"]
                if any(len(m) != count or any(len(row) != n for row in m) for m in found):
                    raise ValueError("matrix size differs from the request")
                durations = [
                    [_cell(v, ceiling=_MAX_TABLE_SECONDS) for v in row] for row in found[0]
                ]
                distances = [
                    [_cell(v, ceiling=_MAX_TABLE_DISTANCE_M) for v in row] for row in found[1]
                ]
                # `osrm-routed` marks an unreachable pair `null` in both matrices together; a
                # cell missing in one but not the other is not a travel time or a distance,
                # only a malformed answer — and a caller that reads one matrix as the other's
                # "no route" flag must never see them disagree.
                if any(
                    (d is None) != (m is None)
                    for drow, mrow in zip(durations, distances, strict=True)
                    for d, m in zip(drow, mrow, strict=True)
                ):
                    raise ValueError(
                        "durations and distances disagree on which pairs have no route"
                    )
                return durations, distances

            strip_durations, strip_distances = await self._get(graph, "table", points, params, rows)
            durations += strip_durations
            distances += strip_distances
        factor = self._factor_of(vehicle)
        if factor != 1.0:
            durations = [[None if v is None else v * factor for v in row] for row in durations]
        return TravelMatrix(durations_s=durations, distances_m=distances)

    async def route(self, vehicle: VehicleType, points: Sequence[Point]) -> Route | None:
        if len(points) < 2:
            raise ValueError("a route needs at least two points")
        factor = self._factor_of(vehicle)

        def parse(body: Any) -> Route | None:
            found = body["routes"][0]
            legs = found["legs"]
            coordinates = found["geometry"]["coordinates"]
            if len(legs) != len(points) - 1 or len(coordinates) < 2:
                raise ValueError("route shape differs from the request")
            return Route(
                duration_s=_number(found["duration"]) * factor,
                distance_m=_number(found["distance"]),
                legs=[
                    Leg(
                        duration_s=_number(leg["duration"]) * factor,
                        distance_m=_number(leg["distance"]),
                    )
                    for leg in legs
                ],
                geometry=[Point(lat=_number(lat), lon=_number(lon)) for lon, lat in coordinates],
            )

        return await self._get(
            _GRAPH_OF[vehicle],
            "route",
            points,
            {"overview": "full", "geometries": "geojson"},
            parse,
            no_route=lambda: None,
        )

    async def _get(
        self,
        graph: Graph,
        endpoint: str,
        points: Sequence[Point],
        params: Mapping[str, str],
        parse: Callable[[Any], _T],
        *,
        no_route: Callable[[], _T] | None = None,
    ) -> _T:
        """`parse` of the body of an `Ok` answer; `no_route()` for `NoRoute` when given,
        otherwise `NoRoute` is a failure. A body `parse` rejects is a failed request, logged
        once as such."""
        # Five decimals are about a metre, and keep a day's matrix well inside the URL length
        # httpx accepts.
        coordinates = ";".join(f"{p.lon:.5f},{p.lat:.5f}" for p in points)
        fields = {"endpoint": endpoint, "profile": str(graph), "points": len(points)}
        started = self._clock()

        def elapsed_ms() -> int:
            return round((self._clock() - started) * 1000)

        def finished(status: int, **found: bool) -> None:
            logger.debug(
                "osrm_request_finished", **fields, status=status, duration_ms=elapsed_ms(), **found
            )

        def failed(status: int | None, error: str) -> DependencyUnavailable:
            logger.error(
                "osrm_request_failed",
                **fields,
                status=status,
                error=error,
                duration_ms=elapsed_ms(),
            )
            return DependencyUnavailable(reason="osrm_unavailable")

        try:
            response = await self._graphs[graph].get(
                f"/{endpoint}/v1/{graph}/{coordinates}", params=params
            )
        # `InvalidURL` (the URL is over the length httpx accepts) is not an `HTTPError`.
        except (httpx.HTTPError, httpx.InvalidURL) as e:
            raise failed(None, type(e).__name__) from e
        status = response.status_code
        try:
            body = response.json()
            code = body["code"] if isinstance(body, dict) else None
        # RecursionError — a body nested deeper than the parser's stack.
        except (ValueError, RecursionError):
            code = None
        if not isinstance(code, str):
            raise failed(status, "malformed_response" if status == 200 else "http_error")
        # Every answer but `Ok` comes with status 400, so the code in the body decides.
        # Source: https://github.com/Project-OSRM/osrm-backend/blob/v6.0.0/src/server/request_handler.cpp
        if no_route is not None and code == "NoRoute":
            finished(status, found=False)
            return no_route()
        if status != 200 or code != "Ok":
            raise failed(status, code)
        try:
            parsed = parse(body)
        # Not chained: a rejected value (a point of the geometry) would ride along in the
        # cause's text, and the error field already names the failure.
        except (KeyError, IndexError, TypeError, ValueError, OverflowError):
            raise failed(status, "malformed_response") from None
        if no_route is not None:
            finished(status, found=True)
        else:
            finished(status)
        return parsed


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("not a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("not a finite number")
    return number


# A day's matrix is at most ~530 points, and even the slowest of them is inside a region; a
# cell this far outside that range is a malformed answer, not a real travel time or distance.
_MAX_TABLE_SECONDS = 24 * 3600
_MAX_TABLE_DISTANCE_M = 2_000_000.0


def _cell(value: object, *, ceiling: float) -> float | None:
    if value is None:
        return None
    number = _number(value)
    if not (0 <= number <= ceiling):
        raise ValueError("table cell out of range")
    return number


def create_osrm_client(settings: Settings) -> OsrmClient:
    """Performs no network I/O: the app starts while the graphs are still being built.

    Proxy variables of the environment are ignored: OSRM is an internal service, and a
    proxy would receive the points of tickets, which are clients' addresses."""
    urls = {
        Graph.CAR: settings.osrm_url_car,
        Graph.FOOT: settings.osrm_url_foot,
        Graph.BIKE: settings.osrm_url_bike,
    }
    return OsrmClient(
        {
            graph: httpx.AsyncClient(
                base_url=url, timeout=httpx.Timeout(settings.osrm_timeout_s), trust_env=False
            )
            for graph, url in urls.items()
        },
        public_transport_factor=settings.public_transport_factor,
        max_table_size=settings.osrm_max_table_size,
    )
