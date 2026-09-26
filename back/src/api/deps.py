from collections.abc import AsyncIterator
from typing import Any

from fastapi import Request
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from src.clients.nominatim import NominatimClient
from src.clients.osrm import OsrmClient
from src.config import Settings
from src.repository.region_data import replace_region_data
from src.repository.region_lists import get_region_id, list_engineers, list_tickets
from src.repository.tickets import lock_ticket, update_ticket_status
from src.service.geocoding import GeoCache, Geocoder
from src.service.loader import DATA_DIR, Loader
from src.service.region_lists import RegionLists
from src.service.regions import Regions
from src.service.ticket_status import TicketStatuses
from src.service.ticket_types import TicketTypes


def create_db_pool(settings: Settings) -> AsyncConnectionPool:
    """Builds the pool without connecting: `open=False` performs no network I/O, so
    app startup does not depend on PostgreSQL being reachable yet.
    Source: https://www.psycopg.org/psycopg3/docs/api/pool.html (AsyncConnectionPool)
    """
    return AsyncConnectionPool(settings.database_url, open=False)


async def get_db_connection(request: Request) -> AsyncIterator[AsyncConnection[Any]]:
    pool: AsyncConnectionPool = request.app.state.db_pool
    async with pool.connection() as conn:
        yield conn


def create_data_services(
    settings: Settings, db_pool: AsyncConnectionPool, nominatim: NominatimClient | None
) -> tuple[Loader, RegionLists]:
    """Reads the region, ticket type and geocache files; a malformed one stops the
    startup instead of failing the first request."""
    regions = Regions.from_file(DATA_DIR / "regions.toml")
    geocoder = Geocoder(
        GeoCache.from_file(DATA_DIR / "geocache.csv"),
        nominatim,
        regions.remote_towns,
        settings.nominatim_max_lookups,
    )
    loader = Loader(
        regions,
        TicketTypes.from_file(DATA_DIR / "ticket_types.toml"),
        geocoder,
        db_pool.connection,
        replace_region_data,
    )
    lists = RegionLists(regions, db_pool.connection, get_region_id, list_engineers, list_tickets)
    return loader, lists


def create_ticket_statuses(db_pool: AsyncConnectionPool) -> TicketStatuses:
    return TicketStatuses(db_pool.connection, lock_ticket, update_ticket_status)


def get_loader(request: Request) -> Loader:
    loader: Loader = request.app.state.loader
    return loader


def get_region_lists(request: Request) -> RegionLists:
    lists: RegionLists = request.app.state.region_lists
    return lists


def get_ticket_statuses(request: Request) -> TicketStatuses:
    statuses: TicketStatuses = request.app.state.ticket_statuses
    return statuses


async def get_osrm_client(request: Request) -> AsyncIterator[OsrmClient]:
    """Returns the app-wide client created in `lifespan` — not closed per request,
    so keep-alive connections to OSRM are reused across requests."""
    yield request.app.state.osrm_client
