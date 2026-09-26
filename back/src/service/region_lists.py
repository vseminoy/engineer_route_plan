"""Regions of the configuration and the brigades and tickets stored for one of them."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from psycopg import AsyncConnection

from src.domain import Engineer, Ticket
from src.repository.db import database_errors
from src.service.loader import Connect
from src.service.regions import Region, Regions

T = TypeVar("T")

GetRegionId = Callable[[AsyncConnection[Any], str], Awaitable[int | None]]
ListByRegion = Callable[[AsyncConnection[Any], int], Awaitable[list[T]]]


@dataclass(frozen=True)
class RegionLists:
    regions: Regions
    connect: Connect
    get_region_id: GetRegionId
    list_engineers: ListByRegion[Engineer]
    list_tickets: ListByRegion[Ticket]

    def all_regions(self) -> list[Region]:
        """In the order of the configuration, whether or not the region's data is loaded."""
        return list(self.regions.regions.values())

    async def engineers(self, region_code: str) -> list[Engineer]:
        return await self._of_region(region_code, "list_engineers", self.list_engineers)

    async def tickets(self, region_code: str) -> list[Ticket]:
        return await self._of_region(region_code, "list_tickets", self.list_tickets)

    async def _of_region(self, region_code: str, operation: str, read: ListByRegion[T]) -> list[T]:
        """Raises `InvalidInput` for a code outside the configuration before touching the
        database; a configured region whose data was never loaded has no rows."""
        region = self.regions.get(region_code)
        async with database_errors(operation), self.connect() as conn:
            region_id = await self.get_region_id(conn, region.code)
            if region_id is None:
                return []
            return await read(conn, region_id)
