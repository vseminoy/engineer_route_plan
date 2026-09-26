import json
import os
import subprocess
import sys
from typing import Any

import pytest

from tests.conftest import BACK_DIR, RO_PASSWORD, RW_PASSWORD, Database, applied_revisions

pytestmark = pytest.mark.integration


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Runs the alembic command line with only the variables the container sets."""
    env = {
        "PATH": os.environ["PATH"],
        "MIGRATION_DATABASE_URL": url,
        "APP_RW_PASSWORD": RW_PASSWORD,
        "APP_RO_PASSWORD": RO_PASSWORD,
        "LOG_FORMAT": "json",
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACK_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _output(result: subprocess.CompletedProcess[str]) -> list[str]:
    return [line for line in (result.stdout + result.stderr).splitlines() if line]


def _json_lines(result: subprocess.CompletedProcess[str]) -> list[dict[str, Any]]:
    return [json.loads(line) for line in _output(result)]


def test_env_uses_migration_url(empty_db: Database) -> None:
    url = empty_db.url.replace("postgresql://", "postgresql+psycopg://", 1)

    result = _alembic(url, "upgrade", "head")

    assert result.returncode == 0, result.stderr
    assert applied_revisions(empty_db) == [("cb3db41d521a",)]


def test_env_accepts_plain_postgresql_url(empty_db: Database) -> None:
    result = _alembic(empty_db.url, "upgrade", "head")

    assert result.returncode == 0, result.stderr
    assert applied_revisions(empty_db) == [("cb3db41d521a",)]


def test_env_logs_are_json(empty_db: Database) -> None:
    result = _alembic(empty_db.url, "upgrade", "head")

    records = _json_lines(result)
    for revision in ("5d23f2956ce7", "cb3db41d521a"):
        assert any(revision in record["event"] for record in records)
    output = "\n".join(_output(result))
    for secret in (RW_PASSWORD, RO_PASSWORD, empty_db.owner_password):
        assert secret not in output


def test_env_failure_exits_nonzero(empty_db: Database) -> None:
    unreachable = f"postgresql://owner:{empty_db.owner_password}@127.0.0.1:1/plan"

    result = _alembic(unreachable, "upgrade", "head")

    assert result.returncode != 0
    last = _json_lines(result)[-1]
    assert last["level"] == "error"
    assert last["event"] == "migration_failed"
    output = "\n".join(_output(result))
    for secret in (RW_PASSWORD, RO_PASSWORD, empty_db.owner_password):
        assert secret not in output


def test_env_refuses_offline_mode(empty_db: Database) -> None:
    result = _alembic(empty_db.url, "upgrade", "head", "--sql")

    assert result.returncode != 0
    last = _json_lines(result)[-1]
    assert last["event"] == "migration_failed"
    assert "offline mode is not supported" in last["exception"]
