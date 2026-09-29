from datetime import date, datetime

import pytest

from src.errors import AppError, DatabaseFailure, DependencyUnavailable, InvalidInput, NotFound
from src.service.plan_builder import QueuedPlan
from src.service.plan_reader import EngineerRouteRead, PlanRead, UnassignedRead, VisitRead
from tests.api.region_fakes import ENGINEER, TICKET, FakePlanBuilder, FakePlanReader, client

BUILD_URL = "/api/v1/plan/build"

UNKNOWN_REGION = InvalidInput(
    "unknown_region", fields=[("region", "Неизвестный регион")], params={"region": "north"}
)


def test_build_plan_returns_202_running() -> None:
    builder = FakePlanBuilder(
        queued=QueuedPlan(plan_id=42, algorithm="or_tools", tickets=[TICKET], engineers=[ENGINEER])
    )
    response = client(plan_builder=builder).post(
        BUILD_URL, json={"region": "east", "plan_date": "2026-09-01", "algorithm": "or_tools"}
    )

    assert response.status_code == 202
    assert response.json() == {
        "plan_id": 42,
        "algorithm": "or_tools",
        "status": "running",
        "engineers": None,
        "unassigned": None,
        "failed_reason": None,
    }
    assert builder.enqueue_calls == [("east", date(2026, 9, 1), "or_tools")]
    assert builder.build_calls == [(42, [TICKET], [ENGINEER], date(2026, 9, 1), "or_tools")]


def test_build_plan_invalid_date() -> None:
    response = client().post(
        BUILD_URL, json={"region": "east", "plan_date": "2026-02-30", "algorithm": "or_tools"}
    )

    assert response.status_code == 400
    assert response.json() == {"fields": [{"name": "plan_date", "message": "Несуществующая дата"}]}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"region": "east", "plan_date": "2026-09-01"},
        {"region": "east", "plan_date": "2026-09-01", "algorithm": "greedy"},
        {"region": "east", "plan_date": "2026-09-01", "algorithm": "or_tools", "extra": 1},
    ],
)
def test_build_plan_rejects_malformed_body(body: dict[str, object]) -> None:
    response = client().post(BUILD_URL, json=body)

    assert response.status_code == 400


def test_build_plan_unknown_region(capsys: pytest.CaptureFixture[str]) -> None:
    builder = FakePlanBuilder(error=UNKNOWN_REGION)
    response = client(plan_builder=builder).post(
        BUILD_URL, json={"region": "north", "plan_date": "2026-09-01", "algorithm": "or_tools"}
    )

    assert response.status_code == 400
    assert response.json() == {"fields": [{"name": "region", "message": "Неизвестный регион"}]}
    assert builder.build_calls == []


@pytest.mark.parametrize(
    "error",
    [DependencyUnavailable(reason="db_unavailable"), DatabaseFailure(reason="db_query_failed")],
)
def test_build_plan_dependency_failure(error: AppError) -> None:
    response = client(plan_builder=FakePlanBuilder(error=error)).post(
        BUILD_URL, json={"region": "east", "plan_date": "2026-09-01", "algorithm": "or_tools"}
    )

    assert response.status_code == {DependencyUnavailable: 503, DatabaseFailure: 500}[type(error)]
    assert response.content == b""


def test_get_running_plan() -> None:
    reader = FakePlanReader(
        PlanRead(
            plan_id=1,
            algorithm="or_tools",
            status="running",
            failed_reason=None,
            engineers=None,
            unassigned=None,
        )
    )
    response = client(plan_reader=reader).get("/api/v1/plan/1")

    assert response.status_code == 200
    assert response.json() == {
        "plan_id": 1,
        "algorithm": "or_tools",
        "status": "running",
        "engineers": None,
        "unassigned": None,
        "failed_reason": None,
    }


def test_get_failed_plan() -> None:
    reader = FakePlanReader(
        PlanRead(
            plan_id=1,
            algorithm="baseline_fcfs",
            status="failed",
            failed_reason="osrm_unavailable",
            engineers=None,
            unassigned=None,
        )
    )
    response = client(plan_reader=reader).get("/api/v1/plan/1")

    assert response.status_code == 200
    assert response.json() == {
        "plan_id": 1,
        "algorithm": "baseline_fcfs",
        "status": "failed",
        "failed_reason": "osrm_unavailable",
        "engineers": None,
        "unassigned": None,
    }


def test_get_done_plan() -> None:
    plan = PlanRead(
        plan_id=1,
        algorithm="or_tools",
        status="done",
        failed_reason=None,
        engineers=(
            EngineerRouteRead(
                engineer_id=11,
                name="Бригада 1",
                route=(
                    VisitRead(
                        ticket_id=21,
                        sequence_no=1,
                        planned_arrival=datetime(2026, 9, 1, 10, 30),
                        travel_time_min=15,
                        travel_distance_km=5.4,
                        explanation="назначено",
                    ),
                ),
                total_distance_km=5.4,
                total_travel_time_min=15,
                idle_time_min=100,
            ),
        ),
        unassigned=(
            UnassignedRead(ticket_id=22, reason_code="no_skill", explanation="нет навыка"),
        ),
    )
    response = client(plan_reader=FakePlanReader(plan)).get("/api/v1/plan/1")

    assert response.status_code == 200
    assert response.json() == {
        "plan_id": 1,
        "algorithm": "or_tools",
        "status": "done",
        "engineers": [
            {
                "engineer_id": 11,
                "name": "Бригада 1",
                "route": [
                    {
                        "ticket_id": 21,
                        "sequence_no": 1,
                        "planned_arrival": "2026-09-01T10:30:00",
                        "travel_time_min": 15,
                        "travel_distance_km": 5.4,
                        "explanation": "назначено",
                    }
                ],
                "total_distance_km": 5.4,
                "total_travel_time_min": 15,
                "idle_time_min": 100,
            }
        ],
        "unassigned": [{"ticket_id": 22, "reason_code": "no_skill", "explanation": "нет навыка"}],
        "failed_reason": None,
    }


def test_get_plan_not_found() -> None:
    response = client(plan_reader=FakePlanReader(error=NotFound("plan_not_found"))).get(
        "/api/v1/plan/1"
    )

    assert response.status_code == 404
    assert response.content == b""


def test_get_plan_invalid_id() -> None:
    response = client().get("/api/v1/plan/0")

    assert response.status_code == 400


@pytest.mark.parametrize(
    "error",
    [DependencyUnavailable(reason="db_unavailable"), DatabaseFailure(reason="db_query_failed")],
)
def test_get_plan_dependency_failure(error: AppError) -> None:
    response = client(plan_reader=FakePlanReader(error=error)).get("/api/v1/plan/1")

    assert response.status_code == {DependencyUnavailable: 503, DatabaseFailure: 500}[type(error)]
    assert response.content == b""


def test_build_and_get_failed_events_logged(capsys: pytest.CaptureFixture[str]) -> None:
    from tests.log_records import events, json_logs

    json_logs()
    client(plan_builder=FakePlanBuilder(error=UNKNOWN_REGION)).post(
        BUILD_URL, json={"region": "north", "plan_date": "2026-09-01", "algorithm": "or_tools"}
    )
    (record,) = events(capsys, "plan_build_failed")
    assert record["level"] == "warning"
    assert record["reason"] == "unknown_region"

    json_logs()
    client(plan_reader=FakePlanReader(error=NotFound("plan_not_found"))).get("/api/v1/plan/1")
    (record,) = events(capsys, "plan_get_failed")
    assert record["level"] == "warning"
    assert record["reason"] == "plan_not_found"
