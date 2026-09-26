"""Reading a region's ticket file: encoding, rows, service rows, one ticket per row."""

import codecs
import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from src.domain import Skill, TicketStatus
from src.errors import InvalidInput
from src.service.ticket_types import TicketTypes

FileFormat = Literal["csv", "json"]

COL_ID = "Заявка"
COL_BK = "Тип заявки BK"
COL_HD = "Тип заявки HD"
COL_START = "Начало"
COL_END = "Окончание"
COL_DISTRICT = "Район"
COL_ADDRESS = "Адрес"
COL_STATUS = "Статус BK"
REQUIRED_COLUMNS = (COL_ID, COL_HD, COL_START, COL_END, COL_ADDRESS)
# Only these are kept from a row: the source files carry others, and work over a row must
# not grow with however many columns a file declares.
KNOWN_COLUMNS = frozenset((*REQUIRED_COLUMNS, COL_BK, COL_DISTRICT, COL_STATUS))

# The office address row closing every source file; the case of "офиса" differs between files.
SENTINEL_IDS = frozenset({"Адрес Офиса", "Адрес офиса"})

# Hour of one or two digits: emergency windows are written "17.08.2026 0:01".
_DATETIME = re.compile(r"(\d{2})\.(\d{2})\.(\d{4}) (\d{1,2}):(\d{2})")

# A file is one region's day, and the whole day goes into one travel matrix and one solver
# run, whose cost grows with the square of the points. 500 tickets are well above what the
# region's brigades can serve in a day, so a shortage of brigades still fits.
MAX_ROWS = 500
MAX_COLUMNS = 50
# Longer values are not addresses or ticket fields but junk; they are cut off before any
# pattern runs over them.
MAX_ADDRESS_LENGTH = 300
MAX_FIELD_LENGTH = 200

ENCODING_MESSAGE = (
    "Файл не удалось прочитать: CSV принимается в кодировке UTF-8 или Windows-1251, "
    "JSON — только в UTF-8"
)


@dataclass(frozen=True)
class Row:
    number: int
    """Line of the file for CSV (the header is line 1), position from 1 for JSON."""
    values: dict[str, str]


@dataclass(frozen=True)
class FileRows:
    """The tickets of a file, apart from the rows that are not tickets."""

    office_address: str | None
    rows: list[Row]
    skipped: int


@dataclass(frozen=True)
class InvalidRow:
    row: int
    reason: str
    """missing_field, field_too_long, bad_datetime, window_order, unknown_type,
    unknown_status, address_not_found."""
    column: str | None = None


@dataclass(frozen=True)
class ParsedTicket:
    """A valid ticket row, still without coordinates."""

    row: int
    external_id: str
    type_bk: str | None
    type_hd: str
    required_skill: Skill
    priority: int
    district: str | None
    address: str
    window_start: datetime
    window_end: datetime
    duration_min: int
    status: TicketStatus
    received_at: datetime


def _format_error(message: str) -> InvalidInput:
    return InvalidInput("file_format_invalid", message=f"Неверный формат файла: {message}")


def decode(data: bytes, fmt: FileFormat) -> str:
    """UTF-8 with a BOM, then strict UTF-8, then (CSV only) cp1251.

    cp1251 goes last because it decodes almost any byte sequence, while Cyrillic text in
    cp1251 is practically never valid UTF-8. A UTF-8 BOM in front of cp1251 bytes, left
    by some editors, is dropped as well.
    """
    body = data.removeprefix(codecs.BOM_UTF8)
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        if fmt == "json":
            raise InvalidInput("file_encoding_invalid", message=ENCODING_MESSAGE) from None
    try:
        return body.decode("cp1251")
    except UnicodeDecodeError:
        raise InvalidInput("file_encoding_invalid", message=ENCODING_MESSAGE) from None


def _check_columns(columns: set[str]) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise _format_error(f"нет колонок {', '.join(missing)}")


def _too_many_rows() -> InvalidInput:
    return InvalidInput(
        "too_many_rows",
        message=f"В файле больше {MAX_ROWS} заявок: план строится не больше чем по {MAX_ROWS} заявкам",
    )


class _Rows:
    """Keeps the tickets of a file and only counts the rows that are not tickets — blank
    rows and the office address row — so a file of blank lines costs no memory. Raises as
    soon as the file has more tickets than allowed."""

    def __init__(self) -> None:
        self.office: str | None = None
        self.tickets: list[Row] = []
        self.skipped = 0

    def add(self, row: Row) -> None:
        values = row.values
        if not any(values.values()):
            self.skipped += 1
        elif values.get(COL_ID, "") in SENTINEL_IDS:
            self.skipped += 1
            self.office = values.get(COL_BK) or self.office
        elif len(self.tickets) == MAX_ROWS:
            raise _too_many_rows()
        else:
            self.tickets.append(row)

    def result(self) -> FileRows:
        return FileRows(self.office, self.tickets, self.skipped)


def _csv_rows(text: str) -> FileRows:
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=";")
    try:
        header = [cell.strip() for cell in next(reader, [])]
        if len(header) < 2:
            raise _format_error("ожидается CSV с разделителем «;» и строкой заголовка")
        if len(header) > MAX_COLUMNS:
            raise _format_error(f"больше {MAX_COLUMNS} колонок")
        _check_columns(set(header))
        known = [(i, name) for i, name in enumerate(header) if name in KNOWN_COLUMNS]
        rows = _Rows()
        for cells in reader:
            if not "".join(cells).strip():
                # A row of empty or blank cells costs a counter, not a dict: a file of
                # blank lines stays cheap.
                rows.skipped += 1
                continue
            values = {name: (cells[i].strip() if i < len(cells) else "") for i, name in known}
            rows.add(Row(reader.line_num, values))
    except csv.Error:
        raise _format_error("CSV не разбирается") from None
    return rows.result()


def _json_rows(text: str) -> FileRows:
    try:
        items = json.loads(text)
    # ValueError also covers integers longer than the interpreter allows; RecursionError —
    # nesting deeper than the parser's stack.
    except (ValueError, RecursionError):
        raise _format_error("JSON не разбирается") from None
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        raise _format_error("ожидается JSON-массив объектов")
    columns: set[str] = set()
    rows = _Rows()
    for number, item in enumerate(items, start=1):
        if not item:
            # An empty object is a blank row: counted, not built.
            rows.skipped += 1
            continue
        values = {}
        for key, value in item.items():
            name = key.strip()
            if name not in KNOWN_COLUMNS:
                continue
            if isinstance(value, dict | list):
                raise _format_error(f"значение «{name}» должно быть строкой или числом")
            values[name] = "" if value is None else str(value).strip()
        columns |= values.keys()
        rows.add(Row(number, values))
    if items:
        _check_columns(columns)
    return rows.result()


def read_rows(data: bytes, fmt: FileFormat) -> FileRows:
    """Blank rows and the office address row are dropped before any field is checked."""
    text = decode(data, fmt)
    return _csv_rows(text) if fmt == "csv" else _json_rows(text)


def _datetime(value: str) -> datetime | None:
    m = _DATETIME.fullmatch(value)
    if m is None:
        return None
    day, month, year, hour, minute = (int(g) for g in m.groups())
    try:
        return datetime(year, month, day, hour, minute)
    except ValueError:
        return None


def parse_ticket(row: Row, types: TicketTypes) -> ParsedTicket | InvalidRow:
    v = row.values
    for column, value in v.items():
        limit = MAX_ADDRESS_LENGTH if column == COL_ADDRESS else MAX_FIELD_LENGTH
        if len(value) > limit:
            return InvalidRow(row.number, "field_too_long", column[:50])
    for column in REQUIRED_COLUMNS:
        if not v.get(column):
            return InvalidRow(row.number, "missing_field", column)
    start, end = _datetime(v[COL_START]), _datetime(v[COL_END])
    if start is None:
        return InvalidRow(row.number, "bad_datetime", COL_START)
    if end is None:
        return InvalidRow(row.number, "bad_datetime", COL_END)
    if start >= end:
        return InvalidRow(row.number, "window_order", COL_START)
    type_bk = v.get(COL_BK) or None
    kind = types.classify(type_bk, v[COL_HD])
    if kind is None:
        return InvalidRow(row.number, "unknown_type", COL_HD)
    status_value = v.get(COL_STATUS, "")
    status = types.status(status_value) if status_value else TicketStatus.SENT
    if status is None:
        return InvalidRow(row.number, "unknown_status", COL_STATUS)
    return ParsedTicket(
        row=row.number,
        external_id=v[COL_ID],
        type_bk=type_bk,
        type_hd=v[COL_HD],
        required_skill=kind.skill,
        priority=kind.priority,
        district=v.get(COL_DISTRICT) or None,
        address=v[COL_ADDRESS],
        window_start=start,
        window_end=end,
        duration_min=kind.duration_min,
        status=status,
        # Tickets of a file are all known at the start of their day.
        received_at=start.replace(hour=0, minute=0),
    )
