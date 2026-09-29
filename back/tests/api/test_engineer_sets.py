import pytest

from src.domain import EngineerSet, EngineerSetKind
from src.errors import (
    AppError,
    Conflict,
    DatabaseFailure,
    DependencyUnavailable,
    InvalidInput,
    NotFound,
)
from tests.api.region_fakes import ENGINEER_SET, FakeEngineerSets, client
from tests.log_records import events, json_logs

LIST_URL = "/api/v1/engineer-sets"

VALID_BODY = {
    "region": "east",
    "name": "Вариант Б",
    "engineers": 15,
    "morning_share": 0.2,
    "evening_share": 0.2,
    "seed": "42",
}


def _unknown_region() -> AppError:
    return InvalidInput(
        "unknown_region", fields=[("region", "Неизвестный регион")], params={"region": "north"}
    )


def test_list_engineer_sets() -> None:
    other = ENGINEER_SET.model_copy(
        update={"id": 71, "name": "Вариант Б", "kind": EngineerSetKind.GENERATED}
    )
    sets = FakeEngineerSets(sets=[ENGINEER_SET, other])

    response = client(engineer_sets=sets).get(LIST_URL, params={"region": "east"})

    assert response.status_code == 200
    body = response.json()
    assert [s["id"] for s in body] == [70, 71]
    assert body[0]["kind"] == "demo"
    assert (
        body[0]["description"] == "Бригад: 13; утренняя смена: 25%; вечерняя смена: 25%; seed: east"
    )
    assert body[1]["kind"] == "generated"
    assert sets.list_calls == ["east"]


def test_list_engineer_sets_empty() -> None:
    response = client(engineer_sets=FakeEngineerSets(sets=[])).get(
        LIST_URL, params={"region": "east"}
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "params",
    [{}, {"region": "East!"}, {"region": "e" * 51}],
    ids=["missing", "invalid_chars", "too_long"],
)
def test_list_engineer_sets_region_invalid(params: dict[str, str]) -> None:
    sets = FakeEngineerSets()

    response = client(engineer_sets=sets).get(LIST_URL, params=params)

    assert response.status_code == 400
    assert sets.list_calls == []


def test_list_engineer_sets_unknown_region() -> None:
    sets = FakeEngineerSets(error=_unknown_region())

    response = client(engineer_sets=sets).get(LIST_URL, params={"region": "north"})

    assert response.status_code == 400
    assert response.json() == {"fields": [{"name": "region", "message": "Неизвестный регион"}]}


def test_create_engineer_set() -> None:
    created = EngineerSet(
        id=71,
        name="Вариант Б",
        kind=EngineerSetKind.GENERATED,
        engineers=15,
        morning_share=0.2,
        evening_share=0.2,
        seed="42",
    )
    sets = FakeEngineerSets(created=created)

    response = client(engineer_sets=sets).post(LIST_URL, json=VALID_BODY)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 71
    assert body["kind"] == "generated"
    assert body["description"] == "Бригад: 15; утренняя смена: 20%; вечерняя смена: 20%; seed: 42"
    assert sets.create_calls == [("east", "Вариант Б", 15, 0.2, 0.2, "42")]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {**VALID_BODY, "engineers": 0},
        {**VALID_BODY, "engineers": 31},
        {**VALID_BODY, "morning_share": -0.1},
        {**VALID_BODY, "morning_share": 1.1},
        {**VALID_BODY, "seed": ""},
        {**VALID_BODY, "name": ""},
        {**VALID_BODY, "extra": 1},
    ],
)
def test_create_engineer_set_body_invalid(body: dict[str, object]) -> None:
    sets = FakeEngineerSets()

    response = client(engineer_sets=sets).post(LIST_URL, json=body)

    assert response.status_code == 400
    assert sets.create_calls == []


def test_create_engineer_set_unknown_region() -> None:
    sets = FakeEngineerSets(error=_unknown_region())

    response = client(engineer_sets=sets).post(LIST_URL, json=VALID_BODY)

    assert response.status_code == 400
    assert response.json() == {"fields": [{"name": "region", "message": "Неизвестный регион"}]}


def test_create_engineer_set_region_not_loaded() -> None:
    error = InvalidInput(
        "region_not_loaded",
        fields=[("region", "Нет загруженных данных региона")],
        params={"region": "east"},
    )
    sets = FakeEngineerSets(error=error)

    response = client(engineer_sets=sets).post(LIST_URL, json=VALID_BODY)

    assert response.status_code == 400
    assert response.json() == {
        "fields": [{"name": "region", "message": "Нет загруженных данных региона"}]
    }


def test_create_engineer_set_insufficient_full_day() -> None:
    error = InvalidInput(
        "insufficient_full_day_engineers",
        message="При таких параметрах бригад «на весь день» получилось бы меньше четырёх",
        params={"engineers": 5, "full_day": 3},
    )
    sets = FakeEngineerSets(error=error)

    response = client(engineer_sets=sets).post(LIST_URL, json=VALID_BODY)

    assert response.status_code == 400
    assert response.json() == {
        "message": "При таких параметрах бригад «на весь день» получилось бы меньше четырёх"
    }


def test_create_engineer_set_name_conflict() -> None:
    sets = FakeEngineerSets(error=Conflict("name_taken"))

    response = client(engineer_sets=sets).post(LIST_URL, json=VALID_BODY)

    assert response.status_code == 409
    assert response.content == b""


@pytest.mark.parametrize(
    "error",
    [DependencyUnavailable(reason="db_unavailable"), DatabaseFailure(reason="db_query_failed")],
)
def test_create_engineer_set_dependency_failure(error: AppError) -> None:
    response = client(engineer_sets=FakeEngineerSets(error=error)).post(LIST_URL, json=VALID_BODY)

    assert response.status_code == {DependencyUnavailable: 503, DatabaseFailure: 500}[type(error)]
    assert response.content == b""


def test_delete_engineer_set() -> None:
    sets = FakeEngineerSets()

    response = client(engineer_sets=sets).delete("/api/v1/engineer-sets/71")

    assert response.status_code == 204
    assert response.content == b""
    assert sets.delete_calls == [71]


def test_delete_engineer_set_invalid_id() -> None:
    sets = FakeEngineerSets()

    response = client(engineer_sets=sets).delete("/api/v1/engineer-sets/0")

    assert response.status_code == 400
    assert sets.delete_calls == []


def test_delete_engineer_set_not_found() -> None:
    response = client(
        engineer_sets=FakeEngineerSets(error=NotFound("engineer_set_not_found"))
    ).delete("/api/v1/engineer-sets/71")

    assert response.status_code == 404
    assert response.content == b""


def test_delete_engineer_set_demo_conflict() -> None:
    response = client(engineer_sets=FakeEngineerSets(error=Conflict("demo_set"))).delete(
        "/api/v1/engineer-sets/70"
    )

    assert response.status_code == 409
    assert response.content == b""


@pytest.mark.parametrize(
    "error",
    [DependencyUnavailable(reason="db_unavailable"), DatabaseFailure(reason="db_query_failed")],
)
def test_delete_engineer_set_dependency_failure(error: AppError) -> None:
    response = client(engineer_sets=FakeEngineerSets(error=error)).delete(
        "/api/v1/engineer-sets/71"
    )

    assert response.status_code == {DependencyUnavailable: 503, DatabaseFailure: 500}[type(error)]
    assert response.content == b""


def test_engineer_sets_failed_logged(capsys: pytest.CaptureFixture[str]) -> None:
    json_logs()
    client(engineer_sets=FakeEngineerSets(error=_unknown_region())).get(
        LIST_URL, params={"region": "north"}
    )
    (record,) = events(capsys, "list_engineer_sets_failed")
    assert record["level"] == "warning"
    assert record["reason"] == "unknown_region"

    json_logs()
    client(engineer_sets=FakeEngineerSets(error=Conflict("name_taken"))).post(
        LIST_URL, json=VALID_BODY
    )
    (record,) = events(capsys, "engineer_set_create_failed")
    assert record["level"] == "warning"
    assert record["reason"] == "name_taken"

    json_logs()
    client(engineer_sets=FakeEngineerSets(error=NotFound("engineer_set_not_found"))).delete(
        "/api/v1/engineer-sets/71"
    )
    (record,) = events(capsys, "engineer_set_delete_failed")
    assert record["level"] == "warning"
    assert record["reason"] == "engineer_set_not_found"
