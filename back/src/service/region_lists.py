"""Regions of the configuration and the brigades and tickets stored for one of them."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from psycopg import AsyncConnection

from src.domain import Engineer, EngineerSetWithRegion, Ticket
from src.errors import InvalidInput
from src.repository.db import database_errors
from src.repository.plans import PlanSummaryRow
from src.service.loader import Connect
from src.service.regions import Region, Regions

T = TypeVar("T")

GetRegionId = Callable[[AsyncConnection[Any], str], Awaitable[int | None]]
GetDefaultEngineerSetId = Callable[[AsyncConnection[Any], int], Awaitable[int | None]]
GetEngineerSet = Callable[[AsyncConnection[Any], int], Awaitable[EngineerSetWithRegion | None]]
ListEngineers = Callable[[AsyncConnection[Any], int], Awaitable[list[Engineer]]]
ListByRegion = Callable[[AsyncConnection[Any], int], Awaitable[list[T]]]
ListPlans = Callable[[AsyncConnection[Any], int, int | None], Awaitable[list[PlanSummaryRow]]]


@dataclass(frozen=True)
class RegionLists:
    regions: Regions
    connect: Connect
    get_region_id: GetRegionId
    get_default_engineer_set_id: GetDefaultEngineerSetId
    get_engineer_set: GetEngineerSet
    list_engineers: ListEngineers
    list_tickets: ListByRegion[Ticket]
    list_plans: ListPlans

    def all_regions(self) -> list[Region]:
        """In the order of the configuration, whether or not the region's data is loaded."""
        return list(self.regions.regions.values())

    async def engineers(self, region_code: str, engineer_set_id: int | None) -> list[Engineer]:
        """Without `engineer_set_id` — the region's `default` set; with one, it must
        belong to `region_code`. Raises `InvalidInput` for a code outside the
        configuration, or a set that does not exist or belongs to another region, before
        touching brigade rows; a configured region whose data was never loaded has none."""
        region = self.regions.get(region_code)
        async with database_errors("list_engineers"), self.connect() as conn:
            region_id = await self.get_region_id(conn, region.code)
            if region_id is None:
                return []
            if engineer_set_id is None:
                resolved = await self.get_default_engineer_set_id(conn, region_id)
                if resolved is None:
                    return []
            else:
                owner = await self.get_engineer_set(conn, engineer_set_id)
                if owner is None or owner.region_id != region_id:
                    raise InvalidInput(
                        "engineer_set_not_in_region",
                        fields=[("engineer_set_id", "Набор не принадлежит региону")],
                        params={"engineer_set_id": engineer_set_id, "region": region.code},
                    )
                resolved = engineer_set_id
            return await self.list_engineers(conn, resolved)

    async def tickets(self, region_code: str) -> list[Ticket]:
        return await self._of_region(region_code, "list_tickets", self.list_tickets)

    async def plans(self, region_code: str, engineer_set_id: int | None) -> list[PlanSummaryRow]:
        """Without `engineer_set_id` — every plan of the region, any set; with one, it
        must belong to `region_code`. Unlike `engineers()`, no `engineer_set_id` does not
        mean the `default` set — a plan history is naturally the whole region's."""
        region = self.regions.get(region_code)
        async with database_errors("list_plans"), self.connect() as conn:
            region_id = await self.get_region_id(conn, region.code)
            if region_id is None:
                return []
            if engineer_set_id is not None:
                owner = await self.get_engineer_set(conn, engineer_set_id)
                if owner is None or owner.region_id != region_id:
                    raise InvalidInput(
                        "engineer_set_not_in_region",
                        fields=[("engineer_set_id", "Набор не принадлежит региону")],
                        params={"engineer_set_id": engineer_set_id, "region": region.code},
                    )
            return await self.list_plans(conn, region_id, engineer_set_id)

    async def _of_region(self, region_code: str, operation: str, read: ListByRegion[T]) -> list[T]:
        """Raises `InvalidInput` for a code outside the configuration before touching the
        database; a configured region whose data was never loaded has no rows."""
        region = self.regions.get(region_code)
        async with database_errors(operation), self.connect() as conn:
            region_id = await self.get_region_id(conn, region.code)
            if region_id is None:
                return []
            return await read(conn, region_id)
