import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import structlog

from src.config import Settings


def new_run_id() -> str:
    """A short opaque id for one traced operation (data load, plan build, replan)."""
    return uuid.uuid4().hex[:12]


@contextmanager
def run_id_context(run_id: str) -> Iterator[None]:
    """Log events emitted while this context is active carry `run_id`."""
    with structlog.contextvars.bound_contextvars(run_id=run_id):
        yield


def configure_logging(settings: Settings) -> None:
    """Wires structlog on top of stdlib `logging`, once, at app startup.
    Source: https://www.structlog.org/en/stable/standard-library.html
    (ProcessorFormatter + foreign_pre_chain recipe).
    """
    # This project stores and serves all datetimes as naive local time, with no
    # UTC conversion anywhere in the stack — log timestamps follow the same
    # policy (`TimeStamper(fmt="iso", utc=False)`) so they never disagree with
    # the times in the database or the API.
    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=False),
        structlog.processors.StackInfoRenderer(),
    ]
    if settings.log_format == "json":
        # ConsoleRenderer renders exceptions itself; format_exc_info is only
        # needed ahead of a renderer that can't.
        shared.append(structlog.processors.format_exc_info)
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
