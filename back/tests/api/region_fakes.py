"""Stand-ins for the data services behind the routes, set through `dependency_overrides`."""

from datetime import date, datetime, time
from typing import Any

from fastapi.testclient import TestClient

from src.api.deps import (
    get_loader,
    get_plan_builder,
    get_plan_reader,
    get_region_lists,
    get_ticket_statuses,
)
from src.app import create_app
from src.config import Settings
from src.domain import Engineer, Point, Skill, Ticket, TicketStatus, VehicleType
from src.service.loader import LoadResult
from src.service.plan_builder import QueuedPlan
from src.service.plan_reader import ComparisonEntryRead, MetricsRead, PlanRead
from src.service.regions import Region
from src.service.ticket_file import InvalidRow

ENGINEER = Engineer(
    id=11,
    name="Бригада 1",
    start=Point(lat=55.72, lon=37.74),
    shift_start=time(10, 0),
    shift_end=time(23, 30),
    vehicle_type=VehicleType.CAR,
    skills=(Skill.CONNECTION, Skill.EMERGENCY),
)
TICKET = Ticket(
    id=21,
    external_id="74198",
    type_bk=None,
    type_hd="Авария",
    required_skill=Skill.EMERGENCY,
    required_vehicle=None,
    priority=1,
    district=None,
    address="Город Москва, ул.Тестовая, д. 1",
    location=Point(lat=55.71, lon=37.75),
    window_start=datetime(2026, 8, 17, 10, 0),
    window_end=datetime(2026, 8, 17, 12, 0),
    duration_min=80,
    status=TicketStatus.SENT,
    received_at=datetime(2026, 8, 17, 0, 0),
)
RESULT = LoadResult(
    region="east",
    engineers=13,
    tickets=65,
    rows_total=70,
    rows_skipped=3,
    rows_invalid=[InvalidRow(5, "bad_datetime", "Начало")],
)


class FakeLists:
    def __init__(
        self,
        engineers: list[Engineer] | None = None,
        tickets: list[Ticket] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._engineers = [ENGINEER] if engineers is None else engineers
        self._tickets = [TICKET] if tickets is None else tickets
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def all_regions(self) -> list[Region]:
        return [
            Region(code="east", name="Восток", center=Point(lat=55.7, lon=37.7), engineers=13),
            Region(
                code="south_east", name="Юго-Восток", center=Point(lat=55.6, lon=37.7), engineers=12
            ),
        ]

    async def engineers(self, region: str) -> list[Engineer]:
        self.calls.append(("engineers", region))
        if self.error:
            raise self.error
        return self._engineers

    async def tickets(self, region: str) -> list[Ticket]:
        self.calls.append(("tickets", region))
        if self.error:
            raise self.error
        return self._tickets


class FakeLoader:
    def __init__(self, result: LoadResult = RESULT, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[Any, ...]] = []

    async def load(self, region: str, source: str, data: bytes | None = None) -> LoadResult:
        self.calls.append((region, source, data))
        if self.error:
            raise self.error
        return self.result


class FakeStatuses:
    """Returns `TICKET` with the requested status, or raises `error`."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[int, TicketStatus]] = []

    async def change(self, ticket_id: int, status: TicketStatus) -> Ticket:
        self.calls.append((ticket_id, status))
        if self.error:
            raise self.error
        return TICKET.model_copy(update={"id": ticket_id, "status": status})


class FakePlanBuilder:
    def __init__(self, queued: "QueuedPlan | None" = None, error: Exception | None = None) -> None:
        self.queued = queued or QueuedPlan(
            plan_id=1, algorithm="or_tools", tickets=[TICKET], engineers=[ENGINEER]
        )
        self.error = error
        self.enqueue_calls: list[tuple[str, date, str]] = []
        self.build_calls: list[tuple[Any, ...]] = []

    async def enqueue(self, region: str, plan_date: date, algorithm: str) -> QueuedPlan:
        self.enqueue_calls.append((region, plan_date, algorithm))
        if self.error:
            raise self.error
        return self.queued

    async def build(
        self,
        plan_id: int,
        tickets: list[Ticket],
        engineers: list[Engineer],
        plan_date: date,
        algorithm: str,
    ) -> None:
        self.build_calls.append((plan_id, tickets, engineers, plan_date, algorithm))


class FakePlanReader:
    def __init__(
        self,
        plan: "PlanRead | None" = None,
        error: Exception | None = None,
        compare_result: "tuple[ComparisonEntryRead, ...] | None" = None,
        compare_error: Exception | None = None,
    ) -> None:
        self.plan = plan or PlanRead(
            plan_id=1,
            algorithm="or_tools",
            status="done",
            failed_reason=None,
            engineers=(),
            unassigned=(),
            metrics=MetricsRead(
                engineers_used=0,
                total_distance_km=0,
                distance_by_engineer={},
                assigned_count=0,
                unassigned_count=0,
                idle_time_by_engineer_min={},
            ),
        )
        self.error = error
        self.compare_result = compare_result or (
            ComparisonEntryRead(metric="engineers_used", main=9, baseline=13, delta=-4),
            ComparisonEntryRead(
                metric="total_distance_km", main=187.3, baseline=244.9, delta=-57.6
            ),
        )
        self.compare_error = compare_error
        self.calls: list[int] = []
        self.compare_calls: list[tuple[int, int]] = []

    async def get(self, plan_id: int) -> PlanRead:
        self.calls.append(plan_id)
        if self.error:
            raise self.error
        return self.plan

    async def compare(self, plan_id: int, baseline_plan_id: int) -> tuple[ComparisonEntryRead, ...]:
        self.compare_calls.append((plan_id, baseline_plan_id))
        if self.compare_error:
            raise self.compare_error
        return self.compare_result


def client(
    lists: FakeLists | None = None,
    loader: FakeLoader | None = None,
    max_body: int | None = None,
    statuses: FakeStatuses | None = None,
    plan_builder: FakePlanBuilder | None = None,
    plan_reader: FakePlanReader | None = None,
) -> TestClient:
    """The application with fake data services; built inside the test, so its JSON logs go
    to the stderr `capsys` reads."""
    extra: dict[str, Any] = {} if max_body is None else {"max_request_body_bytes": max_body}
    app = create_app(
        settings=Settings(
            database_url="postgresql://test/test",
            osrm_url_car="http://osrm.test",
            osrm_url_foot="http://osrm.test",
            osrm_url_bike="http://osrm.test",
            **extra,
        )
    )
    app.dependency_overrides[get_region_lists] = lambda: lists or FakeLists()
    app.dependency_overrides[get_loader] = lambda: loader or FakeLoader()
    app.dependency_overrides[get_ticket_statuses] = lambda: statuses or FakeStatuses()
    app.dependency_overrides[get_plan_builder] = lambda: plan_builder or FakePlanBuilder()
    app.dependency_overrides[get_plan_reader] = lambda: plan_reader or FakePlanReader()
    return TestClient(app)
