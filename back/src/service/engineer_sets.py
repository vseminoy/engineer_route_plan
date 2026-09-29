"""Creating and deleting a region's additional engineer sets. The `default` set is not
managed here — it is created and kept in step with the loaded file by
`src.repository.region_data.replace_region_data`."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from psycopg import AsyncConnection

from src.domain import (
    EngineerDraft,
    EngineerSet,
    EngineerSetKind,
    EngineerSetWithRegion,
    Point,
    Ticket,
)
from src.errors import Conflict, InvalidInput, NotFound
from src.logging import get_logger
from src.repository.db import database_errors
from src.service.engineers_generator import generate_engineers
from src.service.loader import Connect
from src.service.regions import MIN_FULL_DAY_ENGINEERS, Regions

logger = get_logger(__name__)

GetRegionId = Callable[[AsyncConnection[Any], str], Awaitable[int | None]]
GetRegionOffice = Callable[[AsyncConnection[Any], int], Awaitable[Point]]
ListTickets = Callable[[AsyncConnection[Any], int], Awaitable[list[Ticket]]]
ListEngineerSets = Callable[[AsyncConnection[Any], int], Awaitable[list[EngineerSet]]]
InsertGeneratedEngineerSet = Callable[
    [AsyncConnection[Any], int, str, int, float, float, str, list[EngineerDraft]], Awaitable[int]
]
GetEngineerSet = Callable[[AsyncConnection[Any], int], Awaitable[EngineerSetWithRegion | None]]
DeleteEngineerSet = Callable[[AsyncConnection[Any], int], Awaitable[None]]


@dataclass(frozen=True)
class EngineerSets:
    regions: Regions
    connect: Connect
    get_region_id: GetRegionId
    get_region_office: GetRegionOffice
    list_tickets: ListTickets
    list_engineer_sets: ListEngineerSets
    insert_generated_engineer_set: InsertGeneratedEngineerSet
    get_engineer_set: GetEngineerSet
    delete_engineer_set: DeleteEngineerSet

    async def list(self, region_code: str) -> list[EngineerSet]:
        region = self.regions.get(region_code)
        async with database_errors("list_engineer_sets"), self.connect() as conn:
            region_id = await self.get_region_id(conn, region.code)
            if region_id is None:
                return []
            return await self.list_engineer_sets(conn, region_id)

    async def create(
        self,
        region_code: str,
        name: str,
        engineers: int,
        morning_share: float,
        evening_share: float,
        seed: str,
    ) -> EngineerSet:
        """Raises `InvalidInput` before touching the database if the region is not
        loaded or the shares would leave fewer than `MIN_FULL_DAY_ENGINEERS` full-day
        brigades — the same rule the region's own configuration is checked against."""
        region = self.regions.get(region_code)
        full_day = self.regions.shifts.split(engineers, morning_share, evening_share)[2]
        if full_day < MIN_FULL_DAY_ENGINEERS:
            raise InvalidInput(
                "insufficient_full_day_engineers",
                message="При таких параметрах бригад «на весь день» получилось бы меньше четырёх",
                params={"engineers": engineers, "full_day": full_day},
            )
        async with database_errors("create_engineer_set"), self.connect() as conn:
            region_id = await self.get_region_id(conn, region.code)
            if region_id is None:
                raise InvalidInput(
                    "region_not_loaded",
                    fields=[("region", "Нет загруженных данных региона")],
                    params={"region": region.code},
                )
            office = await self.get_region_office(conn, region_id)
            tickets = await self.list_tickets(conn, region_id)
            districts = {t.district for t in tickets if t.district}
            drafts = generate_engineers(
                self.regions, engineers, morning_share, evening_share, seed, office, districts
            )
            set_id = await self.insert_generated_engineer_set(
                conn, region_id, name, engineers, morning_share, evening_share, seed, drafts
            )
        logger.info(
            "engineer_set_created", region=region.code, engineer_set_id=set_id, engineers=engineers
        )
        return EngineerSet(
            id=set_id,
            name=name,
            kind=EngineerSetKind.GENERATED,
            engineers=engineers,
            morning_share=morning_share,
            evening_share=evening_share,
            seed=seed,
        )

    async def delete(self, engineer_set_id: int) -> None:
        async with database_errors("delete_engineer_set"), self.connect() as conn:
            existing = await self.get_engineer_set(conn, engineer_set_id)
            if existing is None:
                raise NotFound(
                    "engineer_set_not_found", params={"engineer_set_id": engineer_set_id}
                )
            if existing.kind is EngineerSetKind.DEMO:
                raise Conflict("demo_set", params={"engineer_set_id": engineer_set_id})
            await self.delete_engineer_set(conn, engineer_set_id)
        logger.info("engineer_set_deleted", engineer_set_id=engineer_set_id)
