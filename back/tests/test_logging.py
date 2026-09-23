import json
import logging

import pytest
import structlog
from structlog.testing import capture_logs

from src.config import Settings
from src.logging import configure_logging, get_logger, new_run_id, run_id_context


def test_new_run_id_is_unique() -> None:
    assert new_run_id() != new_run_id()


# `capture_logs()` replaces the whole configured processor chain for its duration
# (structlog.testing docs) — `merge_contextvars` has to be passed explicitly or
# `run_id`/`request_id` bound via contextvars never reach the captured event.
_CONTEXTVARS_PROCESSOR = [structlog.contextvars.merge_contextvars]


def test_run_id_context_binds_run_id_to_log_events() -> None:
    log = get_logger("test.logging.run_id")

    with capture_logs(processors=_CONTEXTVARS_PROCESSOR) as entries, run_id_context("abc123"):
        log.info("inside_context")

    assert entries[-1]["run_id"] == "abc123"


def test_run_id_context_unbinds_on_exit() -> None:
    log = get_logger("test.logging.run_id")

    with capture_logs(processors=_CONTEXTVARS_PROCESSOR) as entries:
        with run_id_context("abc123"):
            log.info("inside_context")
        log.info("after_context")

    assert "run_id" not in entries[-1]


def test_log_event_without_context_has_no_run_id_field() -> None:
    log = get_logger("test.logging.no_context")

    with capture_logs(processors=_CONTEXTVARS_PROCESSOR) as entries:
        log.info("outside_context")

    assert "run_id" not in entries[-1]


def test_configure_logging_json_format_produces_one_json_line_per_record(
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(
        database_url="postgresql://test/test",
        osrm_url="http://osrm.test",
        log_format="json",
    )
    configure_logging(settings)

    structlog.get_logger("test.logging.json").info("structlog_event", field=1)
    logging.getLogger("uvicorn.error").warning("stdlib_event")

    lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]

    assert len(lines) == 2
    for line in lines:
        json.loads(line)  # each line is one valid JSON object


def test_configure_logging_console_format_is_human_readable_not_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(
        database_url="postgresql://test/test",
        osrm_url="http://osrm.test",
        log_format="console",
    )
    configure_logging(settings)

    structlog.get_logger("test.logging.console").info("structlog_event", field=1)

    output = capsys.readouterr().err
    assert "structlog_event" in output
    with pytest.raises(json.JSONDecodeError):
        json.loads(output.strip().splitlines()[0])
