import codecs
import json
import time
from datetime import datetime
from pathlib import Path

import pytest

from src.domain import Skill, TicketStatus
from src.errors import InvalidInput
from src.service.ticket_file import (
    InvalidRow,
    ParsedTicket,
    Row,
    parse_ticket,
    read_rows,
    split_rows,
)
from src.service.ticket_types import TicketTypes

BACK_DIR = Path(__file__).resolve().parents[2]
DOCS_DIR = BACK_DIR.parent / "docs"

HEADER = "Заявка;Тип заявки BK;Тип заявки HD;Начало;Окончание;Район;Адрес;Подключение"
TICKET = (
    "74198;Подключение;Конвергенция абонента;17.08.2026 20:00;17.08.2026 22:00;"
    "Кузьминки;Город Москва, пр-кт.Волгоградский, д. 128 к 5;FMC"
)
SENTINEL = "Адрес Офиса;г. Москва, ул Юных Ленинцев, д 83с 4;;;;;;"
CSV_TEXT = f"{HEADER}\r\n{TICKET}\r\n;;;;;;;\r\n{SENTINEL}\r\n"
JSON_ROWS = [
    dict(zip(HEADER.split(";"), TICKET.split(";"), strict=True)),
    dict(zip(HEADER.split(";"), SENTINEL.split(";"), strict=True)),
]


@pytest.fixture(scope="module")
def types() -> TicketTypes:
    return TicketTypes.from_file(BACK_DIR / "data" / "ticket_types.toml")


def _read(data: bytes, fmt: str = "csv") -> tuple[str | None, list[Row], int]:
    split = split_rows(read_rows(data, fmt))  # type: ignore[arg-type]  # test passes literals
    return split.office_address, split.rows, split.skipped


def _row(**values: str) -> Row:
    base = dict(zip(HEADER.split(";"), TICKET.split(";"), strict=True))
    base.update(values)
    return Row(2, base)


EXPECTED = ("г. Москва, ул Юных Ленинцев, д 83с 4", "Город Москва, пр-кт.Волгоградский, д. 128 к 5")


def _check(office: str | None, rows: list[Row]) -> None:
    assert office == EXPECTED[0]
    assert len(rows) == 1
    assert rows[0].values["Заявка"] == "74198"
    assert rows[0].values["Адрес"] == EXPECTED[1]


def test_csv_utf8() -> None:
    office, rows, _ = _read(CSV_TEXT.encode("utf-8"))
    _check(office, rows)


def test_csv_utf8_bom() -> None:
    office, rows, _ = _read(codecs.BOM_UTF8 + CSV_TEXT.encode("utf-8"))
    _check(office, rows)
    assert "Заявка" in rows[0].values


def test_csv_cp1251() -> None:
    office, rows, _ = _read(CSV_TEXT.encode("cp1251"))
    _check(office, rows)


def test_csv_cp1251_after_utf8_bom() -> None:
    office, rows, _ = _read(codecs.BOM_UTF8 + CSV_TEXT.encode("cp1251"))
    _check(office, rows)


def test_csv_source_files_read() -> None:
    counts = {}
    for path in sorted((DOCS_DIR / "synthetic_data").glob("*.csv")):
        office, rows, _ = _read(path.read_bytes())
        assert office
        counts[path.name.split()[0]] = len(rows)
    assert counts == {"Восток": 66, "Юго-восток": 83, "Югоцентр": 56}


def test_csv_undecodable_rejected() -> None:
    # 0x98 is undefined in cp1251 and cannot start a UTF-8 sequence.
    data = HEADER.encode("cp1251") + b"\r\n1;\x98"
    with pytest.raises(InvalidInput) as e:
        read_rows(data, "csv")
    assert e.value.reason == "file_encoding_invalid"
    assert e.value.message


@pytest.mark.parametrize("bom", [b"", codecs.BOM_UTF8])
def test_json_utf8_with_and_without_bom(bom: bytes) -> None:
    office, rows, _ = _read(bom + json.dumps(JSON_ROWS, ensure_ascii=False).encode("utf-8"), "json")
    _check(office, rows)


def test_json_cp1251_rejected() -> None:
    with pytest.raises(InvalidInput) as e:
        read_rows(json.dumps(JSON_ROWS, ensure_ascii=False).encode("cp1251"), "json")
    assert e.value.reason == "file_encoding_invalid"


def test_csv_columns_by_header() -> None:
    header = "Заявка;Тип заявки BK;Статус BK;Тип заявки HD;Начало;Окончание;Район;Адрес;Бригада"
    line = (
        "1;Подключение;Выполнена;Заявка на подключение;17.08.2026 10:00;17.08.2026 12:00;"
        "Выхино;Город Москва, ул.Ташкентская, д. 1;Бригада А"
    )
    _, rows, _ = _read(f"{header}\n{line}\n".encode())
    assert rows[0].values["Статус BK"] == "Выполнена"
    assert rows[0].values["Адрес"] == "Город Москва, ул.Ташкентская, д. 1"


def test_csv_missing_required_column() -> None:
    with pytest.raises(InvalidInput) as e:
        read_rows("Заявка;Тип заявки HD;Начало;Окончание\n1;x;y;z\n".encode(), "csv")
    assert e.value.reason == "file_format_invalid"
    assert e.value.message is not None and "Адрес" in e.value.message


@pytest.mark.parametrize("body", ['{"Заявка": "1"}', "5", '["a", "b"]'])
def test_json_not_array_of_objects(body: str) -> None:
    with pytest.raises(InvalidInput) as e:
        read_rows(body.encode(), "json")
    assert e.value.reason == "file_format_invalid"


def test_json_invalid_syntax() -> None:
    with pytest.raises(InvalidInput) as e:
        read_rows(b'[{"a": ', "json")
    assert e.value.reason == "file_format_invalid"


def test_blank_rows_skipped() -> None:
    text = f"{HEADER}\n{TICKET}\n\n\n;;;;;;;\n{TICKET}\n"
    _, rows, skipped = _read(text.encode())
    assert len(rows) == 2
    assert skipped == 3


@pytest.mark.parametrize("marker", ["Адрес Офиса", "Адрес офиса"])
def test_sentinel_row_gives_office_address(marker: str) -> None:
    text = "\n".join([HEADER, TICKET, f"{marker};г.Москва проезд Симферопольский, д.7;;;;;;"])
    office, rows, skipped = _read(text.encode())
    assert office == "г.Москва проезд Симферопольский, д.7"
    assert len(rows) == 1
    assert skipped == 1


def test_no_sentinel_row() -> None:
    office, rows, _ = _read(f"{HEADER}\n{TICKET}\n".encode())
    assert office is None
    assert len(rows) == 1


def test_row_parsed(types: TicketTypes) -> None:
    t = parse_ticket(_row(Начало="17.08.2026 10:00", Окончание="17.08.2026 12:00"), types)
    assert isinstance(t, ParsedTicket)
    assert (t.external_id, t.type_bk, t.type_hd) == (
        "74198",
        "Подключение",
        "Конвергенция абонента",
    )
    assert (t.required_skill, t.priority, t.duration_min) == (Skill.CONNECTION, 2, 70)
    assert t.district == "Кузьминки"
    assert t.window_start == datetime(2026, 8, 17, 10, 0)
    assert t.window_end == datetime(2026, 8, 17, 12, 0)
    assert t.window_start.tzinfo is None


def test_row_single_digit_hour(types: TicketTypes) -> None:
    t = parse_ticket(_row(Начало="17.08.2026 0:01", Окончание="17.08.2026 23:59"), types)
    assert isinstance(t, ParsedTicket)
    assert (t.window_start, t.window_end) == (
        datetime(2026, 8, 17, 0, 1),
        datetime(2026, 8, 17, 23, 59),
    )


@pytest.mark.parametrize("column", ["Заявка", "Тип заявки HD", "Начало", "Окончание", "Адрес"])
def test_row_missing_required_field(types: TicketTypes, column: str) -> None:
    assert parse_ticket(_row(**{column: ""}), types) == InvalidRow(2, "missing_field", column)


@pytest.mark.parametrize("value", ["2026-08-17 10:00", "17.08.2026", "32.08.2026 10:00"])
def test_row_bad_datetime(types: TicketTypes, value: str) -> None:
    result = parse_ticket(_row(Начало=value), types)
    assert isinstance(result, InvalidRow) and result.reason == "bad_datetime"


@pytest.mark.parametrize("start", ["17.08.2026 22:00", "17.08.2026 23:00"])
def test_row_window_not_ordered(types: TicketTypes, start: str) -> None:
    result = parse_ticket(_row(Начало=start), types)
    assert isinstance(result, InvalidRow) and result.reason == "window_order"


def test_row_unknown_type(types: TicketTypes) -> None:
    result = parse_ticket(_row(**{"Тип заявки HD": "Неизвестный тип"}), types)
    assert result == InvalidRow(2, "unknown_type", "Тип заявки HD")


@pytest.mark.parametrize(
    ("value", "status"),
    [
        ("Не отправлена", TicketStatus.NOT_SENT),
        ("Отправлена", TicketStatus.SENT),
        ("В пути", TicketStatus.EN_ROUTE),
        ("В работе", TicketStatus.IN_PROGRESS),
        ("Выполнена", TicketStatus.COMPLETED),
        ("Отменена", TicketStatus.CANCELLED),
        ("Просрочена", TicketStatus.OVERDUE),
    ],
)
def test_row_status_from_column(types: TicketTypes, value: str, status: TicketStatus) -> None:
    t = parse_ticket(_row(**{"Статус BK": value}), types)
    assert isinstance(t, ParsedTicket) and t.status == status


def test_row_status_default_sent(types: TicketTypes) -> None:
    t = parse_ticket(_row(), types)
    assert isinstance(t, ParsedTicket) and t.status == TicketStatus.SENT


def test_row_unknown_status(types: TicketTypes) -> None:
    result = parse_ticket(_row(**{"Статус BK": "Неизвестно"}), types)
    assert result == InvalidRow(2, "unknown_status", "Статус BK")


def test_row_received_at_start_of_day(types: TicketTypes) -> None:
    t = parse_ticket(_row(), types)
    assert isinstance(t, ParsedTicket)
    assert t.received_at == datetime(2026, 8, 17, 0, 0)
    assert t.received_at.tzinfo is None


def test_invalid_row_does_not_stop_others(types: TicketTypes) -> None:
    bad = TICKET.replace("17.08.2026 20:00", "не дата")
    _, rows, _ = _read(f"{HEADER}\n{TICKET}\n{bad}\n{TICKET}\n".encode())
    results = [parse_ticket(r, types) for r in rows]
    assert [type(r) for r in results] == [ParsedTicket, InvalidRow, ParsedTicket]
    assert isinstance(results[1], InvalidRow) and results[1].row == 3


def test_field_too_long(types: TicketTypes) -> None:
    long_address = "Город Москва, ул." + "а" * 300
    assert parse_ticket(_row(Адрес=long_address), types) == InvalidRow(2, "field_too_long", "Адрес")
    assert parse_ticket(_row(Район="р" * 201), types) == InvalidRow(2, "field_too_long", "Район")


def test_too_many_rows() -> None:
    rows = "\n".join([TICKET] * 10_001)
    with pytest.raises(InvalidInput) as e:
        read_rows(f"{HEADER}\n{rows}\n".encode(), "csv")
    assert e.value.reason == "too_many_rows"
    items = [JSON_ROWS[0]] * 10_001
    with pytest.raises(InvalidInput) as e:
        read_rows(json.dumps(items, ensure_ascii=False).encode(), "json")
    assert e.value.reason == "too_many_rows"
    assert (
        len(read_rows(f"{HEADER}\n{chr(10).join([TICKET] * 10_000)}\n".encode(), "csv")) == 10_000
    )


@pytest.mark.parametrize(
    ("data", "fmt"),
    [
        ((HEADER + "\n1;" + "x" * 200_000 + "\n").encode(), "csv"),
        (b"[" * 200_000, "json"),
        (b'[{"a": ' + b"1" * 5000 + b"}]", "json"),
    ],
    ids=["csv_field_over_limit", "json_too_deep", "json_int_too_long"],
)
def test_unparsable_file_is_format_error(data: bytes, fmt: str) -> None:
    with pytest.raises(InvalidInput) as e:
        read_rows(data, fmt)  # type: ignore[arg-type]  # test passes literals
    assert e.value.reason == "file_format_invalid"


def test_json_bad_value_in_known_column() -> None:
    item = dict(JSON_ROWS[0]) | {"Адрес": {"nested": 1}}
    with pytest.raises(InvalidInput) as e:
        read_rows(json.dumps([item], ensure_ascii=False).encode(), "json")
    assert e.value.reason == "file_format_invalid"
    assert e.value.message is not None and "Адрес" in e.value.message


def test_unknown_columns_dropped() -> None:
    item = dict(JSON_ROWS[0]) | {"k" * 1000: {"nested": 1}, "Бригада": "Бригада А"}
    (row,) = read_rows(json.dumps([item], ensure_ascii=False).encode(), "json")
    assert set(row.values) <= {
        "Заявка",
        "Тип заявки BK",
        "Тип заявки HD",
        "Начало",
        "Окончание",
        "Район",
        "Адрес",
        "Статус BK",
    }
    header = HEADER + ";Бригада"
    (row,) = read_rows(f"{header}\n{TICKET};Бригада А\n".encode(), "csv")
    assert "Бригада" not in row.values and "Подключение" not in row.values


def test_too_many_columns() -> None:
    header = HEADER + ";" + ";".join(str(i) for i in range(20_000))
    started = time.perf_counter()
    with pytest.raises(InvalidInput) as e:
        read_rows((header + "\n" * 1000).encode(), "csv")
    assert time.perf_counter() - started < 0.1
    assert e.value.reason == "file_format_invalid"
