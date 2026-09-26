from typing import Any

import pytest

from src.domain import TicketStatus
from src.errors import DatabaseFailure, DependencyUnavailable, InvalidInput, NotFound
from tests.api.region_fakes import FakeStatuses, client
from tests.log_records import events, json_logs

URL = "/api/v1/tickets/87/status"
NOT_ALLOWED = InvalidInput(
    "transition_not_allowed",
    message="Статус заявки нельзя изменить с «Выполнена» на «В пути»",
    params={"ticket_id": 87, "status_from": "completed", "status_to": "en_route"},
)


def test_change_ticket_status() -> None:
    statuses = FakeStatuses()
    response = client(statuses=statuses).patch(URL, json={"status": "completed"})

    assert response.status_code == 200
    assert response.json() == {
        "id": 87,
        "external_id": "74198",
        "type_bk": None,
        "type_hd": "Авария",
        "required_skill": "emergency",
        "required_vehicle": None,
        "priority": 1,
        "district": None,
        "address": "Город Москва, ул.Тестовая, д. 1",
        "location": {"lat": 55.71, "lon": 37.75},
        "window_start": "2026-08-17T10:00:00",
        "window_end": "2026-08-17T12:00:00",
        "duration_min": 80,
        "status": "completed",
        "received_at": "2026-08-17T00:00:00",
    }
    assert statuses.calls == [(87, TicketStatus.COMPLETED)]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({}, "status"),
        ({"status": "done"}, "status"),
        ({"status": None}, "status"),
        ({"status": "completed", "comment": "x"}, "comment"),
    ],
)
def test_change_ticket_status_body_invalid(body: dict[str, Any], field: str) -> None:
    statuses = FakeStatuses()
    response = client(statuses=statuses).patch(URL, json=body)

    assert response.status_code == 400
    assert [f["name"] for f in response.json()["fields"]] == [field]
    assert statuses.calls == []


def test_change_ticket_status_body_not_json() -> None:
    statuses = FakeStatuses()
    response = client(statuses=statuses).patch(
        URL, content=b"status=completed", headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 400
    assert "message" in response.json()
    assert statuses.calls == []


@pytest.mark.parametrize("ticket_id", ["0", "-1", "abc", "9223372036854775808"])
def test_change_ticket_status_id_invalid(ticket_id: str) -> None:
    statuses = FakeStatuses()
    response = client(statuses=statuses).patch(
        f"/api/v1/tickets/{ticket_id}/status", json={"status": "completed"}
    )

    assert response.status_code == 400
    assert [f["name"] for f in response.json()["fields"]] == ["ticket_id"]
    assert statuses.calls == []


def test_change_ticket_status_transition_not_allowed(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    response = client(statuses=FakeStatuses(NOT_ALLOWED)).patch(URL, json={"status": "en_route"})

    assert response.status_code == 400
    assert response.json() == {"message": "Статус заявки нельзя изменить с «Выполнена» на «В пути»"}
    (record,) = events(capsys, "ticket_status_change_failed")
    assert record["level"] == "warning"
    assert (record["reason"], record["ticket_id"]) == ("transition_not_allowed", 87)
    assert (record["status_from"], record["status_to"]) == ("completed", "en_route")
    assert record["request_id"] == response.headers["X-Request-ID"]


def test_change_ticket_status_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    error = NotFound("ticket_not_found", params={"ticket_id": 87})
    response = client(statuses=FakeStatuses(error)).patch(URL, json={"status": "completed"})

    assert response.status_code == 404
    assert response.content == b""
    (record,) = events(capsys, "ticket_status_change_failed")
    assert record["level"] == "warning"
    assert (record["reason"], record["ticket_id"]) == ("ticket_not_found", 87)


def test_change_ticket_status_db_unavailable(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    error = DependencyUnavailable("db_unavailable")
    response = client(statuses=FakeStatuses(error)).patch(URL, json={"status": "completed"})

    assert response.status_code == 503
    assert response.content == b""
    (record,) = events(capsys, "ticket_status_change_failed")
    assert record["level"] == "error"


def test_change_ticket_status_db_failure() -> None:
    error = DatabaseFailure("db_query_failed")
    response = client(statuses=FakeStatuses(error)).patch(URL, json={"status": "completed"})

    assert response.status_code == 500
    assert response.content == b""


def test_change_ticket_status_too_large() -> None:
    statuses = FakeStatuses()
    response = client(statuses=statuses, max_body=1024).patch(
        URL, json={"status": "completed", "pad": "x" * 2000}
    )

    assert response.status_code == 413
    assert response.content == b""
    assert statuses.calls == []


def test_ticket_status_get_not_implemented() -> None:
    statuses = FakeStatuses()
    response = client(statuses=statuses).get(URL)

    assert response.status_code == 501
    assert response.content == b""
    assert statuses.calls == []
