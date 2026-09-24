import json
from collections.abc import Awaitable, Callable
from typing import Any

import psycopg
import pytest
from psycopg_pool import PoolTimeout

from src.config import LoggingSettings
from src.errors import DatabaseFailure, DependencyUnavailable
from src.logging import configure_logging
from src.repository.db import run_query


def _json_logs() -> None:
    # Called inside the test body: the handler binds `sys.stderr` when it is created,
    # and only there it is the stream `capsys` reads.
    configure_logging(LoggingSettings(log_format="json", log_level="INFO"))


def _records(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    """JSON log records from stderr; other lines (library warnings) are skipped."""
    records = []
    for line in capsys.readouterr().err.splitlines():
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return records


def _failing(exc: Exception) -> Callable[..., Awaitable[Any]]:
    async def call(**_params: object) -> Any:
        raise exc

    return call


async def test_run_returns_result(capsys: pytest.CaptureFixture[str]) -> None:
    _json_logs()

    async def call() -> list[dict[str, int]]:
        return [{"id": 1}]

    assert await run_query("list_regions", call) == [{"id": 1}]
    assert _records(capsys) == []


async def test_run_connection_error_is_dependency_unavailable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _json_logs()
    error = psycopg.errors.lookup("08006")("connection lost")

    with pytest.raises(DependencyUnavailable) as raised:
        await run_query("list_regions", _failing(error))

    assert raised.value.reason == "db_unavailable"
    assert raised.value.__cause__ is error
    [record] = _records(capsys)
    assert record["event"] == "db_query_failed"
    assert record["level"] == "error"
    assert record["query"] == "list_regions"
    assert record["sqlstate"] == "08006"


async def test_run_pool_timeout_is_dependency_unavailable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _json_logs()

    with pytest.raises(DependencyUnavailable) as raised:
        await run_query("list_regions", _failing(PoolTimeout("no free connection")))

    assert raised.value.reason == "db_unavailable"
    [record] = _records(capsys)
    assert record["event"] == "db_query_failed"
    assert record["sqlstate"] is None


async def test_run_other_db_error_is_database_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _json_logs()
    error = psycopg.errors.UniqueViolation("duplicate key")

    with pytest.raises(DatabaseFailure) as raised:
        await run_query("insert_region", _failing(error))

    assert raised.value.reason == "db_query_failed"
    assert raised.value.__cause__ is error
    [record] = _records(capsys)
    assert record["event"] == "db_query_failed"
    assert record["sqlstate"] == "23505"


async def test_run_logs_no_parameters(capsys: pytest.CaptureFixture[str]) -> None:
    _json_logs()
    address = "ул. Тверская, д. 7"
    call = _failing(psycopg.errors.lookup("08006")("connection lost"))

    with pytest.raises(DependencyUnavailable):
        await run_query("insert_ticket", lambda: call(address=address))

    [record] = _records(capsys)
    assert set(record) == {"event", "level", "logger", "timestamp", "query", "sqlstate"}
    assert address not in json.dumps(record, ensure_ascii=False)
