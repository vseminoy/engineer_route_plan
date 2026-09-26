from collections.abc import Iterator
from typing import Any

import pytest

from src.errors import DatabaseFailure, DependencyUnavailable, InvalidInput
from src.service.loader import LoadResult
from src.service.ticket_file import InvalidRow
from tests.api.region_fakes import FakeLoader, client
from tests.log_records import events

CONTENT = "Заявка;Тип заявки HD\n".encode("cp1251")
RESULT_JSON = {
    "region": "east",
    "engineers": 13,
    "tickets": 65,
    "rows_total": 70,
    "rows_skipped": 3,
    "rows_invalid": [{"row": 5, "reason": "bad_datetime", "column": "Начало"}],
}


def _upload(loader: FakeLoader, filename: str = "tickets.CSV", **kw: Any) -> Any:
    return client(loader=loader).post(
        "/api/v1/data/upload",
        data={"region": "east"},
        files={"tickets_file": (filename, CONTENT, "text/csv")},
        **kw,
    )


def test_upload_csv() -> None:
    loader = FakeLoader()
    response = _upload(loader)

    assert response.status_code == 200
    assert response.json() == RESULT_JSON
    assert loader.calls == [("east", "csv", CONTENT)]


def test_upload_json() -> None:
    loader = FakeLoader()
    response = _upload(loader, "tickets.json")

    assert response.status_code == 200
    assert loader.calls == [("east", "json", CONTENT)]


def test_upload_invalid_row_without_column() -> None:
    result = LoadResult("east", 13, 1, 2, 0, [InvalidRow(2, "missing_field", None)])
    response = _upload(FakeLoader(result))

    assert response.status_code == 200
    assert response.json()["rows_invalid"] == [
        {"row": 2, "reason": "missing_field", "column": None}
    ]


@pytest.mark.parametrize("filename", ["tickets.xlsx", "tickets", "tickets.csv.txt"])
def test_upload_bad_extension(filename: str, capsys: pytest.CaptureFixture[str]) -> None:
    loader = FakeLoader()
    response = _upload(loader, filename)

    assert response.status_code == 400
    assert response.json() == {
        "fields": [{"name": "tickets_file", "message": "Файл должен быть .csv или .json"}]
    }
    assert loader.calls == []
    (record,) = events(capsys, "data_upload_failed")
    assert record["level"] == "warning"
    assert (record["reason"], record["region"]) == ("file_type_invalid", "east")
    assert filename not in str(record)


@pytest.mark.parametrize(
    ("data", "files", "field"),
    [
        ({"region": "east"}, {}, "tickets_file"),
        ({}, {"tickets_file": ("t.csv", CONTENT)}, "region"),
        ({"region": "East!"}, {"tickets_file": ("t.csv", CONTENT)}, "region"),
        (
            {"region": "east"},
            {"tickets_file": ("t.csv", CONTENT), "engineers_file": ("e.csv", CONTENT)},
            "engineers_file",
        ),
    ],
    ids=["no_file", "no_region", "region_pattern", "extra_field"],
)
def test_upload_form_invalid(data: dict[str, str], files: dict[str, Any], field: str) -> None:
    loader = FakeLoader()
    response = client(loader=loader).post("/api/v1/data/upload", data=data, files=files or None)

    assert response.status_code == 400
    assert field in [f["name"] for f in response.json()["fields"]]
    assert loader.calls == []


def test_upload_broken_multipart(capsys: pytest.CaptureFixture[str]) -> None:
    loader = FakeLoader()
    body = (
        b'--b\r\nContent-Disposition: form-data; name="region"\r\nX\rY: z\r\n\r\neast\r\n--b--\r\n'
    )
    response = client(loader=loader).post(
        "/api/v1/data/upload",
        content=body,
        headers={"Content-Type": "multipart/form-data; boundary=b"},
    )

    assert response.status_code == 400
    assert set(response.json()) == {"message"}
    assert loader.calls == []
    (record,) = events(capsys, "data_upload_failed")
    assert (record["level"], record["reason"]) == ("warning", "form_invalid")


def test_upload_form_over_limits(capsys: pytest.CaptureFixture[str]) -> None:
    loader = FakeLoader()
    files = [("tickets_file", (f"t{i}.csv", CONTENT)) for i in range(3)]
    response = client(loader=loader).post(
        "/api/v1/data/upload", data={"region": "east"}, files=files
    )

    assert response.status_code == 400
    assert set(response.json()) == {"message"}
    assert loader.calls == []
    (record,) = events(capsys, "data_upload_failed")
    assert record["reason"] == "form_invalid"


def test_upload_too_large(capsys: pytest.CaptureFixture[str]) -> None:
    loader = FakeLoader()
    response = client(loader=loader, max_body=1024).post(
        "/api/v1/data/upload",
        data={"region": "east"},
        files={"tickets_file": ("t.csv", b"x" * 2000)},
    )

    assert response.status_code == 413
    assert response.content == b""
    assert loader.calls == []
    assert events(capsys, "data_upload_failed") == []


def test_upload_too_large_without_content_length(capsys: pytest.CaptureFixture[str]) -> None:
    loader = FakeLoader()
    part = (
        b'--b\r\nContent-Disposition: form-data; name="tickets_file"; filename="t.csv"\r\n\r\n'
        + b"x" * 2000
        + b"\r\n--b--\r\n"
    )

    def chunks() -> Iterator[bytes]:
        for i in range(0, len(part), 256):
            yield part[i : i + 256]

    response = client(loader=loader, max_body=1024).post(
        "/api/v1/data/upload",
        content=chunks(),
        headers={"Content-Type": "multipart/form-data; boundary=b"},
    )

    assert response.status_code == 413
    assert response.content == b""
    assert loader.calls == []
    assert events(capsys, "data_upload_failed") == []


def test_demo_load() -> None:
    loader = FakeLoader()
    response = client(loader=loader).post("/api/v1/data/demo", json={"region": "east"})

    assert response.status_code == 200
    assert response.json() == RESULT_JSON
    assert loader.calls == [("east", "demo", None)]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({}, "region"),
        ({"region": "East!"}, "region"),
        ({"region": "e" * 51}, "region"),
        ({"region": "east", "date": "2026-08-17"}, "date"),
    ],
    ids=["no_region", "pattern", "too_long", "extra_field"],
)
def test_demo_body_invalid(body: dict[str, str], field: str) -> None:
    loader = FakeLoader()
    response = client(loader=loader).post("/api/v1/data/demo", json=body)

    assert response.status_code == 400
    assert [f["name"] for f in response.json()["fields"]] == [field]
    assert loader.calls == []


def test_demo_body_not_json() -> None:
    loader = FakeLoader()
    response = client(loader=loader).post(
        "/api/v1/data/demo",
        content=b"region=east",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert set(response.json()) == {"message"}
    assert loader.calls == []


def test_demo_region_in_query_not_accepted() -> None:
    loader = FakeLoader()
    response = client(loader=loader).post("/api/v1/data/demo", params={"region": "east"})

    assert response.status_code == 400
    assert loader.calls == []


def test_demo_too_large() -> None:
    loader = FakeLoader()
    response = client(loader=loader, max_body=1024).post(
        "/api/v1/data/demo", json={"region": "east", "pad": "x" * 2000}
    )

    assert response.status_code == 413
    assert response.content == b""
    assert loader.calls == []


def test_demo_get_does_not_load() -> None:
    loader = FakeLoader()
    response = client(loader=loader).get("/api/v1/data/demo", params={"region": "east"})

    assert response.status_code == 501
    assert response.content == b""
    assert loader.calls == []


ERRORS = [
    (
        InvalidInput("unknown_region", fields=[("region", "Неизвестный регион")]),
        400,
        {"fields": [{"name": "region", "message": "Неизвестный регион"}]},
    ),
    (InvalidInput("no_valid_tickets", message="Нет заявок"), 400, {"message": "Нет заявок"}),
    (DependencyUnavailable(reason="db_unavailable"), 503, None),
    (DatabaseFailure(reason="db_query_failed"), 500, None),
]


@pytest.mark.parametrize("operation", ["upload", "demo"])
@pytest.mark.parametrize(("error", "status", "body"), ERRORS)
def test_load_errors_map_to_status(
    operation: str,
    error: Exception,
    status: int,
    body: dict[str, Any] | None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    loader = FakeLoader(error=error)
    if operation == "upload":
        response = _upload(loader)
    else:
        response = client(loader=loader).post("/api/v1/data/demo", json={"region": "east"})

    assert response.status_code == status
    if body is None:
        assert response.content == b""
    else:
        assert response.json() == body
    assert events(capsys, "data_upload_failed") == []
