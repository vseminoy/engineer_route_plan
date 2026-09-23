import json
import logging
import logging.config

import pytest
import structlog
import uvicorn.config
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


def _apply_uvicorn_default_logging() -> None:
    # What uvicorn applies before importing the app: plain-text handlers on
    # `uvicorn` and `uvicorn.access`, both with `propagate=False`.
    logging.config.dictConfig(uvicorn.config.LOGGING_CONFIG)


def _json_settings() -> Settings:
    return Settings(
        database_url="postgresql://test/test", osrm_url="http://osrm.test", log_format="json"
    )


def test_configure_logging_routes_uvicorn_loggers_to_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _apply_uvicorn_default_logging()

    configure_logging(_json_settings())
    logging.getLogger("uvicorn.error").info("Started server process")

    lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "Started server process"


def test_configure_logging_keeps_uvicorn_access_log_off(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _apply_uvicorn_default_logging()

    configure_logging(_json_settings())
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.info('127.0.0.1:5000 - "GET /api/v1/tickets/42?x=1 HTTP/1.1" 501')

    # uvicorn switches its access log on by exactly this check.
    assert access_logger.hasHandlers() is False
    assert capsys.readouterr().err == ""
