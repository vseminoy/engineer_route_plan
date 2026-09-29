import pytest

from src.errors import DatabaseFailure, DependencyUnavailable, InvalidInput
from tests.api.region_fakes import FakeLists, client
from tests.log_records import events

UNKNOWN_REGION = InvalidInput(
    "unknown_region", fields=[("region", "Неизвестный регион")], params={"region": "north"}
)


def test_list_engineers() -> None:
    lists = FakeLists()
    response = client(lists).get("/api/v1/engineers", params={"region": "east"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 11,
            "name": "Бригада 1",
            "vehicle_type": "car",
            "skills": ["connection", "emergency"],
            "shift_start": "10:00",
            "shift_end": "23:30",
            "start": {"lat": 55.72, "lon": 37.74},
        }
    ]
    assert lists.calls == [("engineers", "east", None)]


def test_list_engineers_given_set() -> None:
    lists = FakeLists()
    response = client(lists).get(
        "/api/v1/engineers", params={"region": "east", "engineer_set_id": 9}
    )

    assert response.status_code == 200
    assert lists.calls == [("engineers", "east", 9)]


@pytest.mark.parametrize("engineer_set_id", ["0", "-1", "abc"])
def test_list_engineers_set_id_invalid(engineer_set_id: str) -> None:
    lists = FakeLists()
    response = client(lists).get(
        "/api/v1/engineers", params={"region": "east", "engineer_set_id": engineer_set_id}
    )

    assert response.status_code == 400
    assert [f["name"] for f in response.json()["fields"]] == ["engineer_set_id"]
    assert lists.calls == []


def test_list_engineers_set_not_in_region(capsys: pytest.CaptureFixture[str]) -> None:
    error = InvalidInput(
        "engineer_set_not_in_region",
        fields=[("engineer_set_id", "Набор не принадлежит региону")],
        params={"engineer_set_id": 9, "region": "east"},
    )
    response = client(FakeLists(error=error)).get(
        "/api/v1/engineers", params={"region": "east", "engineer_set_id": 9}
    )

    assert response.status_code == 400
    assert response.json() == {
        "fields": [{"name": "engineer_set_id", "message": "Набор не принадлежит региону"}]
    }


def test_list_engineers_empty() -> None:
    response = client(FakeLists(engineers=[])).get("/api/v1/engineers", params={"region": "east"})

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("params", [{}, {"region": "East!"}, {"region": "e" * 51}])
def test_list_engineers_region_invalid(params: dict[str, str]) -> None:
    lists = FakeLists()
    response = client(lists).get("/api/v1/engineers", params=params)

    assert response.status_code == 400
    assert [f["name"] for f in response.json()["fields"]] == ["region"]
    assert lists.calls == []


def test_list_engineers_unknown_region(capsys: pytest.CaptureFixture[str]) -> None:
    response = client(FakeLists(error=UNKNOWN_REGION)).get(
        "/api/v1/engineers", params={"region": "north"}
    )

    assert response.status_code == 400
    assert response.json() == {"fields": [{"name": "region", "message": "Неизвестный регион"}]}
    (record,) = events(capsys, "list_engineers_failed")
    assert record["level"] == "warning"
    assert (record["reason"], record["region"]) == ("unknown_region", "north")
    assert record["request_id"] == response.headers["X-Request-ID"]


def test_list_engineers_db_unavailable(capsys: pytest.CaptureFixture[str]) -> None:
    response = client(FakeLists(error=DependencyUnavailable(reason="db_unavailable"))).get(
        "/api/v1/engineers", params={"region": "east"}
    )

    assert response.status_code == 503
    assert response.content == b""
    (record,) = events(capsys, "list_engineers_failed")
    assert record["level"] == "error"
    assert record["reason"] == "db_unavailable"


def test_list_engineers_db_failure() -> None:
    response = client(FakeLists(error=DatabaseFailure(reason="db_query_failed"))).get(
        "/api/v1/engineers", params={"region": "east"}
    )

    assert response.status_code == 500
    assert response.content == b""
