from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

from fastapi import Request
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from src.clients.nominatim import NominatimClient
from src.clients.osrm import OsrmClient
from src.config import Settings
from src.repository.plans import (
    get_plan,
    insert_replanned_plan,
    insert_running_plan,
    list_plan_assignments,
    mark_plan_done,
    mark_plan_failed,
)
from src.repository.region_data import replace_region_data
from src.repository.region_lists import (
    get_region_id,
    list_engineers,
    list_open_tickets,
    list_tickets,
)
from src.repository.tickets import insert_ticket, lock_ticket, update_ticket_status
from src.service.geocoding import GeoCache, Geocoder
from src.service.loader import DATA_DIR, Loader
from src.service.plan_builder import PlanBuilder
from src.service.plan_reader import PlanReader
from src.service.region_lists import RegionLists
from src.service.regions import Regions
from src.service.replan import Replanner
from src.service.solver_pool import SolverPool
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
) -> tuple[Loader, RegionLists, TicketTypes]:
    """Reads the region, ticket type and geocache files; a malformed one stops the
    startup instead of failing the first request. `TicketTypes` is also returned for
    `create_plan_services`: `replan`'s `new_ticket` event classifies a ticket by the same
    table the loader uses, not a second copy of it."""
    regions = Regions.from_file(DATA_DIR / "regions.toml")
    geocoder = Geocoder(
        GeoCache.from_file(DATA_DIR / "geocache.csv"),
        nominatim,
        regions.remote_towns,
        settings.nominatim_max_lookups,
    )
    ticket_types = TicketTypes.from_file(DATA_DIR / "ticket_types.toml")
    loader = Loader(regions, ticket_types, geocoder, db_pool.connection, replace_region_data)
    lists = RegionLists(regions, db_pool.connection, get_region_id, list_engineers, list_tickets)
    return loader, lists, ticket_types


def create_ticket_statuses(db_pool: AsyncConnectionPool) -> TicketStatuses:
    return TicketStatuses(db_pool.connection, lock_ticket, update_ticket_status)


def create_plan_services(
    settings: Settings,
    db_pool: AsyncConnectionPool,
    regions: Regions,
    osrm: OsrmClient,
    pool: SolverPool,
    ticket_types: TicketTypes,
) -> tuple[PlanBuilder, PlanReader, Replanner]:
    builder = PlanBuilder(
        regions=regions,
        connect=db_pool.connection,
        get_region_id=get_region_id,
        list_open_tickets=list_open_tickets,
        list_engineers=list_engineers,
        insert_running_plan=insert_running_plan,
        mark_plan_done=mark_plan_done,
        mark_plan_failed=mark_plan_failed,
        osrm=osrm,
        pool=pool,
        max_table_size=settings.osrm_max_table_size,
        solver_time_limit=timedelta(seconds=settings.solver_time_limit_s),
        solver_watchdog_margin_s=settings.solver_watchdog_margin_s,
    )
    reader = PlanReader(
        connect=db_pool.connection,
        get_plan=get_plan,
        list_engineers=list_engineers,
        list_plan_assignments=list_plan_assignments,
    )
    replanner = Replanner(
        connect=db_pool.connection,
        get_plan=get_plan,
        list_engineers=list_engineers,
        list_tickets=list_tickets,
        list_plan_assignments=list_plan_assignments,
        insert_ticket=insert_ticket,
        insert_replanned_plan=insert_replanned_plan,
        osrm=osrm,
        ticket_types=ticket_types,
    )
    return builder, reader, replanner


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


def get_plan_builder(request: Request) -> PlanBuilder:
    builder: PlanBuilder = request.app.state.plan_builder
    return builder


def get_plan_reader(request: Request) -> PlanReader:
    reader: PlanReader = request.app.state.plan_reader
    return reader


def get_replanner(request: Request) -> Replanner:
    replanner: Replanner = request.app.state.replanner
    return replanner
