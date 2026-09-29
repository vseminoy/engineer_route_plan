"""Loading a region's data: a ticket file or the built-in demo set, into the database."""

import asyncio
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, Literal

import structlog
from psycopg import AsyncConnection

from src.domain import EngineerDraft, EngineerSetParams, RegionDraft, RegionWritten, TicketDraft
from src.errors import AppError, InvalidInput
from src.logging import get_logger
from src.repository.db import database_errors
from src.service.engineers_generator import generate_engineers
from src.service.geocoding import Geocoder, cache_key
from src.service.regions import Region, Regions
from src.service.ticket_file import (
    COL_ADDRESS,
    MAX_ADDRESS_LENGTH,
    FileFormat,
    FileRows,
    InvalidRow,
    ParsedTicket,
    parse_ticket,
    read_rows,
)
from src.service.ticket_types import TicketTypes

logger = get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEMO_DIR = DATA_DIR / "demo"

Source = Literal["csv", "json", "demo"]
Connect = Callable[[], AbstractAsyncContextManager[AsyncConnection[Any]]]
GenerateEngineers = Callable[[int, float, float, str], list[EngineerDraft]]
ReplaceRegionData = Callable[
    [AsyncConnection[Any], RegionDraft, EngineerSetParams, GenerateEngineers, list[TicketDraft]],
    Awaitable[RegionWritten],
]


def _since(started: float) -> int:
    """Milliseconds elapsed since `started`, a `time.monotonic()` reading."""
    return round((time.monotonic() - started) * 1000)


@dataclass(frozen=True)
class LoadResult:
    region: str
    engineers: int
    tickets: int
    rows_total: int
    rows_skipped: int
    rows_invalid: list[InvalidRow]


@dataclass(frozen=True)
class _Parsed:
    rows_total: int
    split: FileRows
    tickets: list[ParsedTicket]
    invalid: list[InvalidRow]


@dataclass(frozen=True)
class Loader:
    """`connect` opens a database connection (the pool's `connection`); the loader takes
    one only to write, after the file is read and geocoded, so a slow geocoder does not
    hold a pooled connection.

    Files are read one at a time: reading takes memory and CPU, the latter with the GIL
    held. Writes go one at a time too, so loads hold at most one pooled connection however
    many arrive at once; a write of a region would otherwise sit on a connection waiting
    for the region row lock of another. Geocoding is outside both turns: Nominatim
    requests are spaced by the client itself, and a load without cache misses does not
    wait for one with them."""

    regions: Regions
    types: TicketTypes
    geocoder: Geocoder
    connect: Connect
    replace_region_data: ReplaceRegionData
    _read_turn: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, compare=False)
    _write_turn: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, compare=False)

    async def load(self, region_code: str, source: Source, data: bytes | None = None) -> LoadResult:
        """Replaces the region's brigades and tickets with those of the file (`data`, for
        `csv`/`json`) or of the demo set. Rows that are not tickets are skipped; invalid
        ticket rows are left out and reported, not fatal. Raises `InvalidInput` for an
        unknown region, an unreadable or oversized file or a file without a single valid
        ticket, and passes on `DependencyUnavailable` from Nominatim and the database
        errors. Every failure is logged here as `data_load_failed`: a client's mistake at
        `warning`, a dependency's at `error`."""
        log = logger.bind(source=source, region=region_code[:50])
        started = time.monotonic()
        try:
            return await self._load(self.regions.get(region_code), source, data, log, started)
        except InvalidInput as e:
            log.warning(
                "data_load_failed", reason=e.reason, duration_ms=_since(started), **e.params
            )
            raise
        except AppError as e:
            log.error("data_load_failed", reason=e.reason, duration_ms=_since(started), **e.params)
            raise

    def _parse(self, source: Source, region: Region, data: bytes | None) -> _Parsed:
        fmt: FileFormat = "csv" if source == "demo" else source
        if source == "demo":
            data = (DEMO_DIR / f"{region.code}.csv").read_bytes()
        split = read_rows(data or b"", fmt)
        tickets: list[ParsedTicket] = []
        invalid: list[InvalidRow] = []
        for row in split.rows:
            outcome = parse_ticket(row, self.types)
            if isinstance(outcome, InvalidRow):
                invalid.append(outcome)
            else:
                tickets.append(outcome)
        return _Parsed(len(split.rows) + split.skipped, split, tickets, invalid)

    async def _load(
        self,
        region: Region,
        source: Source,
        data: bytes | None,
        log: structlog.stdlib.BoundLogger,
        started: float,
    ) -> LoadResult:
        # Parsing a file of up to the request body limit is CPU work; off the event loop.
        # `wait_ms` sums the time spent queued behind other loads for both turns.
        queued = time.monotonic()
        async with self._read_turn:
            wait_ms = _since(queued)
            parsed = await asyncio.to_thread(self._parse, source, region, data)
        invalid = list(parsed.invalid)
        office_address = parsed.split.office_address
        if office_address and len(office_address) > MAX_ADDRESS_LENGTH:
            office_address = None

        wanted = [(t.address, t.district) for t in parsed.tickets]
        if office_address:
            wanted.append((office_address, None))
        points = await self.geocoder.locate(wanted)

        tickets = []
        for t in parsed.tickets:
            point = points.get(cache_key(t.address))
            if point is None:
                invalid.append(InvalidRow(t.row, "address_not_found", COL_ADDRESS))
                continue
            tickets.append(
                TicketDraft(
                    external_id=t.external_id,
                    type_bk=t.type_bk,
                    type_hd=t.type_hd,
                    required_skill=t.required_skill,
                    priority=t.priority,
                    district=t.district,
                    address=t.address,
                    location=point,
                    window_start=t.window_start,
                    window_end=t.window_end,
                    duration_min=t.duration_min,
                    status=t.status,
                    received_at=t.received_at,
                )
            )
        invalid.sort(key=lambda r: r.row)
        if not tickets:
            raise InvalidInput(
                "no_valid_tickets",
                message="В файле нет ни одной заявки, которую можно загрузить",
                params={"rows_total": parsed.rows_total, "rows_invalid": len(invalid)},
            )

        office = points.get(cache_key(office_address)) if office_address else None
        draft = RegionDraft(
            code=region.code,
            name=region.name,
            office_address=office_address if office and office_address else region.name,
            office=office or region.center,
        )
        districts = {t.district for t in tickets if t.district}
        assert self.regions.shifts.morning.share is not None
        assert self.regions.shifts.evening.share is not None
        default_set_params = EngineerSetParams(
            engineers=region.engineers,
            morning_share=self.regions.shifts.morning.share,
            evening_share=self.regions.shifts.evening.share,
            seed=region.code,
        )
        generate = partial(generate_engineers, self.regions, office=draft.office, districts=districts)
        queued = time.monotonic()
        async with self._write_turn:
            wait_ms += _since(queued)
            async with database_errors("replace_region_data"), self.connect() as conn:
                written = await self.replace_region_data(
                    conn, draft, default_set_params, generate, tickets
                )

        result = LoadResult(
            region=region.code,
            engineers=written.engineers,
            tickets=len(tickets),
            rows_total=parsed.rows_total,
            rows_skipped=parsed.split.skipped,
            rows_invalid=invalid,
        )
        log.info(
            "data_load_finished",
            rows_total=result.rows_total,
            rows_skipped=result.rows_skipped,
            rows_invalid=len(invalid),
            invalid_by_reason=dict(Counter(r.reason for r in invalid)),
            engineers=result.engineers,
            engineers_kept=written.engineers_kept,
            tickets=result.tickets,
            wait_ms=wait_ms,
            duration_ms=_since(started),
        )
        return result
