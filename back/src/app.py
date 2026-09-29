import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response

from src.api.body_limit import BodyLimitMiddleware
from src.api.deps import (
    create_data_services,
    create_db_pool,
    create_engineer_sets_service,
    create_plan_services,
    create_ticket_statuses,
)
from src.api.errors import REQUEST_ID_HEADER, register_error_handlers, route_path
from src.api.routes.data import router as data_router
from src.api.routes.engineer_sets import router as engineer_sets_router
from src.api.routes.health import router as health_router
from src.api.routes.not_implemented import add_not_implemented_stub
from src.api.routes.plan import router as plan_router
from src.api.routes.regions import router as regions_router
from src.clients.nominatim import NominatimClient, create_nominatim_client
from src.clients.osrm import OsrmClient, create_osrm_client
from src.config import Settings, get_settings
from src.logging import configure_logging, get_logger
from src.repository.plans import mark_running_plans_failed
from src.service.plan_builder import sweep_running_plans
from src.service.solver_pool import ProcessSolverPool

logger = get_logger(__name__)
access_logger = get_logger("http")

# Accepts a uuid4().hex-shaped id or a typical client/proxy trace id; anything
# else is replaced rather than echoed — an unvalidated header value would go
# straight into a response header and every log line of the request.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# Polled by the container healthcheck every few seconds: a successful probe is
# logged at debug so it does not drown out real traffic at the default level.
_PROBE_PATHS = frozenset({"/health"})
# The startup sweep's own connection timeout, shorter than the pool's default: an
# unreachable database should not hold up the app coming up at all.
_STARTUP_SWEEP_TIMEOUT_S = 5.0


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    # Configured when the app is built, not in `lifespan`: uvicorn imports the app
    # before logging its own startup lines, so those come out in the same format.
    configure_logging(app_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db_pool = create_db_pool(app_settings)
        await db_pool.open(wait=False)
        app.state.db_pool = db_pool
        osrm_client: OsrmClient | None = None
        nominatim: NominatimClient | None = None
        # One process for the whole app: `or_tools.solve_day` does not release the GIL for
        # the length of its search, so a thread pool would not free the event loop either —
        # only a separate process does. A single worker means the server never builds more
        # than one `or_tools` plan at a time; a concurrent build waits in the executor's queue.
        plan_pool = ProcessSolverPool(max_workers=1)
        try:
            # Inside `try`: a client that fails to build or a malformed data file stops
            # the startup, and whatever was opened before it still gets closed.
            app.state.osrm_client = osrm_client = create_osrm_client(app_settings)
            nominatim = create_nominatim_client(
                app_settings.nominatim_url, app_settings.nominatim_user_agent
            )
            app.state.loader, app.state.region_lists, ticket_types = create_data_services(
                app_settings, db_pool, nominatim
            )
            app.state.engineer_sets = create_engineer_sets_service(
                app.state.region_lists.regions, db_pool
            )
            app.state.ticket_statuses = create_ticket_statuses(db_pool)
            app.state.plan_builder, app.state.plan_reader, app.state.replanner = (
                create_plan_services(
                    app_settings,
                    db_pool,
                    app.state.region_lists.regions,
                    osrm_client,
                    plan_pool,
                    ticket_types,
                )
            )
            # Before yield: no request is served until any plan an earlier, ungraceful
            # stop left `running` is closed. A short connection timeout of its own — an
            # unreachable database must not hold up startup by the pool's full default
            # wait; the sweep just runs again next restart.
            await sweep_running_plans(
                lambda: db_pool.connection(timeout=_STARTUP_SWEEP_TIMEOUT_S),
                mark_running_plans_failed,
            )
            logger.info("app_started", mode=app_settings.app_mode)
            yield
        finally:
            plan_pool.shutdown(cancel_futures=True)
            if nominatim is not None:
                await nominatim.aclose()
            if osrm_client is not None:
                await osrm_client.aclose()
            await db_pool.close()

    app = FastAPI(title="Engineer Route Plan API", version="0.1.0", lifespan=lifespan)
    register_error_handlers(app)
    # Added before the request middleware below, so it runs inside it: a `413`
    # still gets an `X-Request-ID` and an access-log record.
    app.add_middleware(BodyLimitMiddleware, max_bytes=app_settings.max_request_body_bytes)

    @app.middleware("http")
    async def log_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Replaces uvicorn's access log (run with `--no-access-log`): one
        # structured record per request instead of two differently-shaped ones.
        structlog.contextvars.clear_contextvars()
        raw_request_id = request.headers.get(REQUEST_ID_HEADER)
        request_id = (
            raw_request_id
            if raw_request_id and _SAFE_REQUEST_ID.fullmatch(raw_request_id)
            else uuid.uuid4().hex
        )
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started_at = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            # Only the `Exception` handler is left to answer it, from outside this
            # middleware: it logs `unhandled_error` with the stack and sets the
            # `X-Request-ID` itself. This record keeps the request in the access log.
            access_logger.error(
                "http_request_finished",
                method=request.method,
                path=route_path(request),
                status=500,
                duration_ms=round((time.monotonic() - started_at) * 1000),
            )
            raise

        path = route_path(request)
        log = (
            access_logger.debug
            if path in _PROBE_PATHS and response.status_code < 400
            else access_logger.info
        )
        log(
            "http_request_finished",
            method=request.method,
            path=path,
            status=response.status_code,
            duration_ms=round((time.monotonic() - started_at) * 1000),
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    app.include_router(health_router)
    app.include_router(regions_router)
    app.include_router(engineer_sets_router)
    app.include_router(data_router)
    app.include_router(plan_router)
    add_not_implemented_stub(app)
    return app
