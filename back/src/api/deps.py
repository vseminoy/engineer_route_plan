from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import Request
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from src.config import Settings


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


def create_osrm_client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=settings.osrm_url)


async def get_osrm_client(request: Request) -> AsyncIterator[httpx.AsyncClient]:
    """Returns the app-wide client created in `lifespan` — not closed per request,
    so keep-alive connections to OSRM are reused across requests."""
    yield request.app.state.osrm_client
