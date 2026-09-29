import pytest

from src.errors import (
    AppError,
    Conflict,
    DatabaseFailure,
    DependencyUnavailable,
    InvalidInput,
    NotFound,
)
from src.service.plan_reader import MetricsRead, PlanRead
from src.service.replan import AssignmentChange, NewUrgentTicketEvent, PlanDiff, ReplanOutcome
from tests.api.region_fakes import FakePlanReader, FakeReplanner, client

REPLAN_URL = "/api/v1/plan/1/replan"

NEW_URGENT_TICKET_BODY = {
    "event_type": "new_urgent_ticket",
    "triggered_at": "2026-09-01T12:00:00",
    "ticket": {
        "external_id": "INC1",
        "type_bk": None,
        "type_hd": "Авария",
        "district": None,
        "address": "ул. Аварийная, 1",
        "location": {"lat": 55.7, "lon": 37.7},
        "required_vehicle": None,
    },
    "reaction_min": 90,
}

TICKET_CANCELLED_BODY = {
    "event_type": "ticket_cancelled",
    "triggered_at": "2026-09-01T12:00:00",
    "ticket_id": 21,
}


def test_replan_new_urgent_ticket_returns_the_new_plan() -> None:
    plan = PlanRead(
        plan_id=2,
        algorithm="or_tools",
        status="done",
        failed_reason=None,
        engineers=(),
        unassigned=(),
        metrics=MetricsRead(
            engineers_used=1,
            total_distance_km=5.0,
            distance_by_engineer={11: 5.0},
            assigned_count=1,
            unassigned_count=0,
            idle_time_by_engineer_min={11: 100},
        ),
    )
    outcome = ReplanOutcome(
        plan_id=2,
        parent_plan_id=1,
        algorithm="or_tools",
        diff=PlanDiff(
            changed_assignments=[
                AssignmentChange(
                    ticket_id=21,
                    before_engineer_id=11,
                    after_engineer_id=12,
                    before_sequence_no=1,
                    after_sequence_no=2,
                )
            ],
            newly_assigned=[99],
            newly_unassigned=[],
            plan_stability=2,
        ),
    )
    replanner = FakeReplanner(outcome=outcome)
    response = client(plan_reader=FakePlanReader(plan), replanner=replanner).post(
        REPLAN_URL, json=NEW_URGENT_TICKET_BODY
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plan_id"] == 2
    assert body["parent_plan_id"] == 1
    assert body["status"] == "done"
    assert body["diff"] == {
        "changed_assignments": [
            {
                "ticket_id": 21,
                "before_engineer_id": 11,
                "after_engineer_id": 12,
                "before_sequence_no": 1,
                "after_sequence_no": 2,
            }
        ],
        "newly_assigned": [99],
        "newly_unassigned": [],
        "reassigned_from_unavailable_engineer": [],
        "plan_stability": 2,
    }

    [(plan_id, event)] = replanner.calls
    assert plan_id == 1
    assert isinstance(event, NewUrgentTicketEvent)
    assert event.ticket.external_id == "INC1"
    assert event.reaction_min == 90


def test_replan_ticket_cancelled_reaches_the_service() -> None:
    replanner = FakeReplanner()
    response = client(replanner=replanner).post(REPLAN_URL, json=TICKET_CANCELLED_BODY)

    assert response.status_code == 200
    [(plan_id, event)] = replanner.calls
    assert plan_id == 1
    assert event.ticket_id == 21  # type: ignore[union-attr]


def test_replan_default_reaction_min_is_120() -> None:
    body = {**NEW_URGENT_TICKET_BODY}
    del body["reaction_min"]
    replanner = FakeReplanner()
    client(replanner=replanner).post(REPLAN_URL, json=body)

    [(_plan_id, event)] = replanner.calls
    assert isinstance(event, NewUrgentTicketEvent)
    assert event.reaction_min == 120


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"event_type": "unknown_event", "triggered_at": "2026-09-01T12:00:00"},
        {**NEW_URGENT_TICKET_BODY, "extra": 1},
        {**TICKET_CANCELLED_BODY, "ticket_id": 0},
    ],
)
def test_replan_rejects_malformed_body(body: dict[str, object]) -> None:
    response = client().post(REPLAN_URL, json=body)

    assert response.status_code == 400


def test_replan_invalid_triggered_at_date() -> None:
    body = {**NEW_URGENT_TICKET_BODY, "triggered_at": "2026-02-30T12:00:00"}
    response = client().post(REPLAN_URL, json=body)

    assert response.status_code == 400
    assert response.json() == {
        "fields": [{"name": "triggered_at", "message": "Несуществующие дата или время"}]
    }


def test_replan_plan_not_found() -> None:
    replanner = FakeReplanner(error=NotFound("plan_not_found", params={"plan_id": 1}))
    response = client(replanner=replanner).post(REPLAN_URL, json=NEW_URGENT_TICKET_BODY)

    assert response.status_code == 404


def test_replan_plan_not_ready() -> None:
    error = InvalidInput(
        "plan_not_ready", message="План-родитель ещё не готов для перепланирования"
    )
    replanner = FakeReplanner(error=error)
    response = client(replanner=replanner).post(REPLAN_URL, json=NEW_URGENT_TICKET_BODY)

    assert response.status_code == 400


def test_replan_ticket_not_cancelled_is_conflict() -> None:
    replanner = FakeReplanner(error=Conflict("ticket_not_cancelled", params={"ticket_id": 21}))
    response = client(replanner=replanner).post(REPLAN_URL, json=TICKET_CANCELLED_BODY)

    assert response.status_code == 409


@pytest.mark.parametrize(
    "error", [DependencyUnavailable(reason="osrm_unavailable"), DatabaseFailure(reason="db_query_failed")]
)
def test_replan_dependency_failure(error: AppError) -> None:
    replanner = FakeReplanner(error=error)
    response = client(replanner=replanner).post(REPLAN_URL, json=NEW_URGENT_TICKET_BODY)

    assert response.status_code == {DependencyUnavailable: 503, DatabaseFailure: 500}[type(error)]
    assert response.content == b""
