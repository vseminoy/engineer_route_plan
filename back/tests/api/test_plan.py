from datetime import date, datetime

import pytest

from src.errors import (
    AppError,
    Conflict,
    DatabaseFailure,
    DependencyUnavailable,
    InvalidInput,
    NotFound,
)
from src.service.plan_builder import QueuedPlan
from src.service.plan_reader import (
    ComparisonEntryRead,
    EngineerRouteRead,
    MetricsRead,
    PlanRead,
    UnassignedRead,
    VisitRead,
)
from tests.api.region_fakes import (
    ENGINEER,
    PLAN_SUMMARY,
    TICKET,
    FakeLists,
    FakePlanBuilder,
    FakePlanReader,
    client,
)
from tests.log_records import events

LIST_URL = "/api/v1/plan"

COMPARE_URL = "/api/v1/plan/1/compare"

BUILD_URL = "/api/v1/plan/build"

UNKNOWN_REGION = InvalidInput(
    "unknown_region", fields=[("region", "Неизвестный регион")], params={"region": "north"}
)


def test_list_plans() -> None:
    lists = FakeLists(plans=[PLAN_SUMMARY])
    response = client(lists).get(LIST_URL, params={"region": "east"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "plan_id": 1,
            "region": "east",
            "engineer_set_id": 70,
            "plan_date": "2026-08-17",
            "algorithm": "or_tools",
            "status": "done",
            "created_at": "2026-08-17T09:00:00",
            "parent_plan_id": None,
            "failed_reason": None,
        }
    ]
    assert lists.calls == [("plans", "east", None)]


def test_list_plans_given_set() -> None:
    lists = FakeLists()
    response = client(lists).get(LIST_URL, params={"region": "east", "engineer_set_id": 9})

    assert response.status_code == 200
    assert lists.calls == [("plans", "east", 9)]


def test_list_plans_empty() -> None:
    response = client(FakeLists(plans=[])).get(LIST_URL, params={"region": "east"})

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("params", [{}, {"region": "East!"}, {"region": "e" * 51}])
def test_list_plans_region_invalid(params: dict[str, str]) -> None:
    lists = FakeLists()
    response = client(lists).get(LIST_URL, params=params)

    assert response.status_code == 400
    assert [f["name"] for f in response.json()["fields"]] == ["region"]
    assert lists.calls == []


@pytest.mark.parametrize("engineer_set_id", ["0", "-1", "abc"])
def test_list_plans_set_id_invalid(engineer_set_id: str) -> None:
    lists = FakeLists()
    response = client(lists).get(
        LIST_URL, params={"region": "east", "engineer_set_id": engineer_set_id}
    )

    assert response.status_code == 400
    assert [f["name"] for f in response.json()["fields"]] == ["engineer_set_id"]
    assert lists.calls == []


def test_list_plans_unknown_region(capsys: pytest.CaptureFixture[str]) -> None:
    response = client(FakeLists(error=UNKNOWN_REGION)).get(LIST_URL, params={"region": "north"})

    assert response.status_code == 400
    assert response.json() == {"fields": [{"name": "region", "message": "Неизвестный регион"}]}
    (record,) = events(capsys, "list_plans_failed")
    assert record["level"] == "warning"
    assert record["reason"] == "unknown_region"


def test_list_plans_set_not_in_region() -> None:
    error = InvalidInput(
        "engineer_set_not_in_region",
        fields=[("engineer_set_id", "Набор не принадлежит региону")],
        params={"engineer_set_id": 9, "region": "east"},
    )
    response = client(FakeLists(error=error)).get(
        LIST_URL, params={"region": "east", "engineer_set_id": 9}
    )

    assert response.status_code == 400
    assert response.json() == {
        "fields": [{"name": "engineer_set_id", "message": "Набор не принадлежит региону"}]
    }


def test_list_plans_db_unavailable(capsys: pytest.CaptureFixture[str]) -> None:
    response = client(FakeLists(error=DependencyUnavailable(reason="db_unavailable"))).get(
        LIST_URL, params={"region": "east"}
    )

    assert response.status_code == 503
    assert response.content == b""
    (record,) = events(capsys, "list_plans_failed")
    assert record["level"] == "error"


def test_list_plans_db_failure() -> None:
    response = client(FakeLists(error=DatabaseFailure(reason="db_query_failed"))).get(
        LIST_URL, params={"region": "east"}
    )

    assert response.status_code == 500
    assert response.content == b""


def test_build_plan_returns_202_running() -> None:
    builder = FakePlanBuilder(
        queued=QueuedPlan(
            plan_id=42,
            algorithm="or_tools",
            engineer_set_id=70,
            tickets=[TICKET],
            engineers=[ENGINEER],
        )
    )
    response = client(plan_builder=builder).post(
        BUILD_URL, json={"region": "east", "plan_date": "2026-09-01", "algorithm": "or_tools"}
    )

    assert response.status_code == 202
    assert response.json() == {
        "plan_id": 42,
        "algorithm": "or_tools",
        "status": "running",
        "region": "east",
        "engineer_set_id": 70,
        "engineers": None,
        "unassigned": None,
        "metrics": None,
        "failed_reason": None,
    }
    assert builder.enqueue_calls == [("east", date(2026, 9, 1), "or_tools", None)]
    assert builder.build_calls == [(42, [TICKET], [ENGINEER], date(2026, 9, 1), "or_tools")]


def test_build_plan_given_engineer_set() -> None:
    builder = FakePlanBuilder(
        queued=QueuedPlan(
            plan_id=42,
            algorithm="or_tools",
            engineer_set_id=9,
            tickets=[TICKET],
            engineers=[ENGINEER],
        )
    )
    response = client(plan_builder=builder).post(
        BUILD_URL,
        json={
            "region": "east",
            "plan_date": "2026-09-01",
            "algorithm": "or_tools",
            "engineer_set_id": 9,
        },
    )

    assert response.status_code == 202
    assert response.json()["engineer_set_id"] == 9
    assert builder.enqueue_calls == [("east", date(2026, 9, 1), "or_tools", 9)]


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


def test_build_plan_engineer_set_not_in_region() -> None:
    error = InvalidInput(
        "engineer_set_not_in_region",
        fields=[("engineer_set_id", "Набор не принадлежит региону")],
        params={"engineer_set_id": 9, "region": "east"},
    )
    builder = FakePlanBuilder(error=error)
    response = client(plan_builder=builder).post(
        BUILD_URL,
        json={
            "region": "east",
            "plan_date": "2026-09-01",
            "algorithm": "or_tools",
            "engineer_set_id": 9,
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "fields": [{"name": "engineer_set_id", "message": "Набор не принадлежит региону"}]
    }
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
            region_code="east",
            engineer_set_id=70,
            status="running",
            failed_reason=None,
            engineers=None,
            unassigned=None,
            metrics=None,
        )
    )
    response = client(plan_reader=reader).get("/api/v1/plan/1")

    assert response.status_code == 200
    assert response.json() == {
        "plan_id": 1,
        "algorithm": "or_tools",
        "status": "running",
        "region": "east",
        "engineer_set_id": 70,
        "engineers": None,
        "unassigned": None,
        "metrics": None,
        "failed_reason": None,
    }


def test_get_failed_plan() -> None:
    reader = FakePlanReader(
        PlanRead(
            plan_id=1,
            algorithm="baseline_fcfs",
            region_code="east",
            engineer_set_id=70,
            status="failed",
            failed_reason="osrm_unavailable",
            engineers=None,
            unassigned=None,
            metrics=None,
        )
    )
    response = client(plan_reader=reader).get("/api/v1/plan/1")

    assert response.status_code == 200
    assert response.json() == {
        "plan_id": 1,
        "algorithm": "baseline_fcfs",
        "status": "failed",
        "region": "east",
        "engineer_set_id": 70,
        "failed_reason": "osrm_unavailable",
        "engineers": None,
        "unassigned": None,
        "metrics": None,
    }


def test_get_done_plan() -> None:
    plan = PlanRead(
        plan_id=1,
        algorithm="or_tools",
        region_code="east",
        engineer_set_id=70,
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
        metrics=MetricsRead(
            engineers_used=1,
            total_distance_km=5.4,
            distance_by_engineer={11: 5.4},
            assigned_count=1,
            unassigned_count=1,
            idle_time_by_engineer_min={11: 100},
        ),
    )
    response = client(plan_reader=FakePlanReader(plan)).get("/api/v1/plan/1")

    assert response.status_code == 200
    assert response.json() == {
        "plan_id": 1,
        "algorithm": "or_tools",
        "status": "done",
        "region": "east",
        "engineer_set_id": 70,
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
        "metrics": {
            "engineers_used": 1,
            "total_distance_km": 5.4,
            "distance_by_engineer": {"11": 5.4},
            "assigned_count": 1,
            "unassigned_count": 1,
            "idle_time_by_engineer_min": {"11": 100},
        },
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


def test_delete_plan_returns_204() -> None:
    reader = FakePlanReader()
    response = client(plan_reader=reader).delete("/api/v1/plan/1")

    assert response.status_code == 204
    assert response.content == b""
    assert reader.delete_calls == [1]


@pytest.mark.parametrize("plan_id", ["0", "-1", "abc"])
def test_delete_plan_invalid_id(plan_id: str) -> None:
    reader = FakePlanReader()
    response = client(plan_reader=reader).delete(f"/api/v1/plan/{plan_id}")

    assert response.status_code == 400
    assert [f["name"] for f in response.json()["fields"]] == ["plan_id"]
    assert reader.delete_calls == []


def test_delete_plan_not_found() -> None:
    response = client(plan_reader=FakePlanReader(delete_error=NotFound("plan_not_found"))).delete(
        "/api/v1/plan/1"
    )

    assert response.status_code == 404
    assert response.content == b""


def test_delete_plan_running_conflict() -> None:
    error = Conflict("plan_running", params={"plan_id": 1})
    response = client(plan_reader=FakePlanReader(delete_error=error)).delete("/api/v1/plan/1")

    assert response.status_code == 409
    assert response.content == b""


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (DependencyUnavailable(reason="db_unavailable"), 503),
        (DatabaseFailure(reason="db_query_failed"), 500),
    ],
)
def test_delete_plan_dependency_failure(error: Exception, status: int) -> None:
    response = client(plan_reader=FakePlanReader(delete_error=error)).delete("/api/v1/plan/1")

    assert response.status_code == status
    assert response.content == b""


def test_delete_plan_failed_logged(capsys: pytest.CaptureFixture[str]) -> None:
    from tests.log_records import events, json_logs

    json_logs()
    client(plan_reader=FakePlanReader(delete_error=NotFound("plan_not_found"))).delete(
        "/api/v1/plan/1"
    )
    (record,) = events(capsys, "plan_delete_failed")
    assert record["level"] == "warning"
    assert record["reason"] == "plan_not_found"


def test_compare_plan_returns_entries() -> None:
    reader = FakePlanReader(
        compare_result=(
            ComparisonEntryRead(metric="engineers_used", main=9, baseline=13, delta=-4),
            ComparisonEntryRead(
                metric="total_distance_km", main=187.3, baseline=244.9, delta=-57.6
            ),
        )
    )

    response = client(plan_reader=reader).get(COMPARE_URL, params={"baseline_plan_id": 2})

    assert response.status_code == 200
    assert response.json() == [
        {"metric": "engineers_used", "main": 9, "baseline": 13, "delta": -4},
        {"metric": "total_distance_km", "main": 187.3, "baseline": 244.9, "delta": -57.6},
    ]
    assert reader.compare_calls == [(1, 2)]


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/v1/plan/0/compare", {"baseline_plan_id": 2}),
        ("/api/v1/plan/1/compare", {"baseline_plan_id": 0}),
    ],
    ids=["plan_id", "baseline_plan_id"],
)
def test_compare_plan_invalid_ids(path: str, params: dict[str, int]) -> None:
    response = client().get(path, params=params)

    assert response.status_code == 400


def test_compare_plan_missing_baseline_query() -> None:
    response = client().get(COMPARE_URL)

    assert response.status_code == 400


def test_compare_plan_not_found() -> None:
    reader = FakePlanReader(compare_error=NotFound("plan_not_found", params={"plan_id": 2}))

    response = client(plan_reader=reader).get(COMPARE_URL, params={"baseline_plan_id": 2})

    assert response.status_code == 404
    assert response.content == b""


def test_compare_plan_not_ready() -> None:
    reader = FakePlanReader(
        compare_error=InvalidInput(
            "plan_not_ready", message="План ещё не готов для сравнения", params={"plan_id": 1}
        )
    )

    response = client(plan_reader=reader).get(COMPARE_URL, params={"baseline_plan_id": 2})

    assert response.status_code == 400
    assert response.json() == {"message": "План ещё не готов для сравнения"}


def test_compare_plan_engineer_set_mismatch() -> None:
    reader = FakePlanReader(
        compare_error=InvalidInput(
            "engineer_set_mismatch",
            message="Планы построены для разных наборов бригад",
            params={"plan_id": 1, "baseline_plan_id": 2},
        )
    )

    response = client(plan_reader=reader).get(COMPARE_URL, params={"baseline_plan_id": 2})

    assert response.status_code == 400
    assert response.json() == {"message": "Планы построены для разных наборов бригад"}


@pytest.mark.parametrize(
    "error",
    [DependencyUnavailable(reason="db_unavailable"), DatabaseFailure(reason="db_query_failed")],
)
def test_compare_plan_dependency_failure(error: AppError) -> None:
    response = client(plan_reader=FakePlanReader(compare_error=error)).get(
        COMPARE_URL, params={"baseline_plan_id": 2}
    )

    assert response.status_code == {DependencyUnavailable: 503, DatabaseFailure: 500}[type(error)]
    assert response.content == b""


def test_compare_plan_failed_logged(capsys: pytest.CaptureFixture[str]) -> None:
    from tests.log_records import events, json_logs

    json_logs()
    reader = FakePlanReader(compare_error=NotFound("plan_not_found", params={"plan_id": 2}))
    client(plan_reader=reader).get(COMPARE_URL, params={"baseline_plan_id": 2})

    (record,) = events(capsys, "plan_compare_failed")
    assert record["level"] == "warning"
    assert record["reason"] == "plan_not_found"
    assert (record["plan_id"], record["baseline_plan_id"]) == (1, 2)
