"""Log records of a test read as JSON lines from stderr.

Module loggers cache their configuration on first use, so `structlog.testing.capture_logs()`
misses a logger another test has already used; stderr sees every record.
"""

import json
from typing import Any

import pytest

from src.config import LoggingSettings
from src.logging import configure_logging


def json_logs(level: str = "INFO") -> None:
    """Call inside the test body: the handler binds `sys.stderr` when it is created, and
    only there it is the stream `capsys` reads."""
    configure_logging(LoggingSettings(log_format="json", log_level=level))


def records(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    """JSON log records from stderr; other lines (library warnings) are skipped."""
    found = []
    for line in capsys.readouterr().err.splitlines():
        try:
            found.append(json.loads(line))
        except ValueError:
            continue
    return found


def events(capsys: pytest.CaptureFixture[str], name: str) -> list[dict[str, Any]]:
    return [r for r in records(capsys) if r.get("event") == name]
