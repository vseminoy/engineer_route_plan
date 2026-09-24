"""The boundary between a repository and the database driver."""

from collections.abc import Awaitable, Callable
from typing import TypeVar

import psycopg

from src.errors import DatabaseFailure, DependencyUnavailable
from src.logging import get_logger

T = TypeVar("T")

logger = get_logger(__name__)


async def run_query(query: str, call: Callable[[], Awaitable[T]]) -> T:
    """Awaits `call`, the aiosql query named `query`, and logs its failure.

    An `OperationalError` — the connection lost, no free connection in the pool
    (`PoolTimeout`), a statement timeout, a deadlock, the server out of resources —
    becomes `DependencyUnavailable`: the request may be retried. Any other driver
    error becomes `DatabaseFailure`: a retry would fail the same way.
    The log record names the query and SQLSTATE only: parameters and the driver's
    DETAIL may carry personal data, and the SQL text is in the query file.
    """
    try:
        return await call()
    except psycopg.OperationalError as e:
        logger.error("db_query_failed", query=query, sqlstate=e.sqlstate)
        raise DependencyUnavailable(reason="db_unavailable") from e
    except psycopg.Error as e:
        logger.error("db_query_failed", query=query, sqlstate=e.sqlstate)
        raise DatabaseFailure(reason="db_query_failed") from e
