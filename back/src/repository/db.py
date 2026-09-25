"""The boundary between a repository and the database driver."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TypeVar

import psycopg

from src.errors import DatabaseFailure, DependencyUnavailable
from src.logging import get_logger

T = TypeVar("T")

logger = get_logger(__name__)


@asynccontextmanager
async def database_errors(operation: str) -> AsyncIterator[None]:
    """Turns a driver error raised in the block into a domain error and logs it once.

    An `OperationalError` — the connection lost, no free connection in the pool
    (`PoolTimeout`), a statement timeout, a deadlock, the server out of resources —
    becomes `DependencyUnavailable`: the request may be retried. Any other driver
    error becomes `DatabaseFailure`: a retry would fail the same way.
    The log record names `operation` (the aiosql query, or a block such as taking a
    connection and committing) and SQLSTATE only: parameters and the driver's DETAIL may
    carry personal data, and the SQL text is in the query file.
    """
    try:
        yield
    except psycopg.OperationalError as e:
        logger.error("db_query_failed", query=operation, sqlstate=e.sqlstate)
        raise DependencyUnavailable(reason="db_unavailable") from e
    except psycopg.Error as e:
        logger.error("db_query_failed", query=operation, sqlstate=e.sqlstate)
        raise DatabaseFailure(reason="db_query_failed") from e


async def run_query(query: str, call: Callable[[], Awaitable[T]]) -> T:
    """Awaits `call`, the aiosql query named `query`, translating its failure as
    `database_errors` does."""
    async with database_errors(query):
        return await call()
