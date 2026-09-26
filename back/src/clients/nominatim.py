"""Geocoding client for Nominatim (OpenStreetMap)."""

import asyncio
import time
from collections.abc import Awaitable, Callable

import httpx

from src.domain import Point
from src.errors import DependencyUnavailable
from src.logging import get_logger

logger = get_logger(__name__)

# The public instance allows at most one request per second.
# Source: https://operations.osmfoundation.org/policies/nominatim/
MIN_INTERVAL_S = 1.0


class NominatimClient:
    """`search` returns the best match or `None`; any answer other than a search result —
    network error, timeout, a status other than 200 (including 403 and 429), a body
    without coordinates — is `DependencyUnavailable`. Requests start at least
    `MIN_INTERVAL_S` apart across every caller sharing the client, so one client serves
    the whole process. The logs never carry the address: it is personal data."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._http = http
        self._clock = clock
        self._sleep = sleep
        self._last_start: float | None = None
        self._turn = asyncio.Lock()

    async def _wait_turn(self) -> None:
        # Concurrent loads would otherwise read the same last start and fire together.
        async with self._turn:
            if self._last_start is not None:
                wait = self._last_start + MIN_INTERVAL_S - self._clock()
                if wait > 0:
                    await self._sleep(wait)
            self._last_start = self._clock()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def search(self, query: str) -> Point | None:
        await self._wait_turn()
        started = self._clock()

        def failed(status: int | None, error: str | None = None) -> DependencyUnavailable:
            logger.error(
                "nominatim_request_failed",
                status=status,
                error=error,
                duration_ms=round((self._clock() - started) * 1000),
            )
            return DependencyUnavailable(reason="geocoder_unavailable")

        try:
            response = await self._http.get(
                "/search",
                params={"q": query, "format": "jsonv2", "countrycodes": "ru", "limit": 1},
            )
        except httpx.HTTPError as e:
            raise failed(None, type(e).__name__) from e
        if response.status_code != 200:
            raise failed(response.status_code)
        try:
            found = response.json()
            point = Point(lat=float(found[0]["lat"]), lon=float(found[0]["lon"])) if found else None
        except (ValueError, TypeError, KeyError, IndexError) as e:
            raise failed(response.status_code, "malformed_response") from e
        logger.debug(
            "nominatim_request_finished",
            status=response.status_code,
            found=point is not None,
            duration_ms=round((self._clock() - started) * 1000),
        )
        return point


def create_nominatim_client(url: str, user_agent: str) -> NominatimClient | None:
    """`None` when `url` is empty: the external geocoder is switched off."""
    if not url:
        return None
    http = httpx.AsyncClient(
        base_url=url, headers={"User-Agent": user_agent}, timeout=httpx.Timeout(10.0)
    )
    return NominatimClient(http)
