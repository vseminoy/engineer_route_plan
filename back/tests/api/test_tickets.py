import pytest

from src.errors import DatabaseFailure, DependencyUnavailable, InvalidInput
from tests.api.region_fakes import FakeLists, client
from tests.log_records import events

UNKNOWN_REGION = InvalidInput(
    "unknown_region", fields=[("region", "Неизвестный регион")], params={"region": "north"}
)
TICKET_JSON = {
    "id": 21,
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
    "status": "sent",
    "received_at": "2026-08-17T00:00:00",
}


def test_list_tickets() -> None:
    lists = FakeLists()
    response = client(lists).get("/api/v1/tickets", params={"region": "east"})

    assert response.status_code == 200
    assert response.json() == [TICKET_JSON]
    assert lists.calls == [("tickets", "east")]


def test_list_tickets_empty() -> None:
    response = client(FakeLists(tickets=[])).get("/api/v1/tickets", params={"region": "east"})

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("params", [{}, {"region": "East!"}, {"region": "e" * 51}])
def test_list_tickets_region_invalid(params: dict[str, str]) -> None:
    lists = FakeLists()
    response = client(lists).get("/api/v1/tickets", params=params)

    assert response.status_code == 400
    assert [f["name"] for f in response.json()["fields"]] == ["region"]
    assert lists.calls == []


def test_list_tickets_plan_id_ignored() -> None:
    response = client().get("/api/v1/tickets", params={"region": "east", "plan_id": "1"})

    assert response.status_code == 200
    assert response.json() == [TICKET_JSON]


def test_list_tickets_unknown_region(capsys: pytest.CaptureFixture[str]) -> None:
    response = client(FakeLists(error=UNKNOWN_REGION)).get(
        "/api/v1/tickets", params={"region": "north"}
    )

    assert response.status_code == 400
    assert [f["name"] for f in response.json()["fields"]] == ["region"]
    (record,) = events(capsys, "list_tickets_failed")
    assert record["level"] == "warning"


def test_list_tickets_db_unavailable(capsys: pytest.CaptureFixture[str]) -> None:
    response = client(FakeLists(error=DependencyUnavailable(reason="db_unavailable"))).get(
        "/api/v1/tickets", params={"region": "east"}
    )

    assert response.status_code == 503
    assert response.content == b""
    (record,) = events(capsys, "list_tickets_failed")
    assert record["level"] == "error"


def test_list_tickets_db_failure() -> None:
    response = client(FakeLists(error=DatabaseFailure(reason="db_query_failed"))).get(
        "/api/v1/tickets", params={"region": "east"}
    )

    assert response.status_code == 500
    assert response.content == b""
