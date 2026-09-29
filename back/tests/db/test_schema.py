import itertools
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import psycopg
import pytest
from alembic import command
from psycopg import errors
from sqlalchemy.exc import ProgrammingError

from tests.conftest import RO_PASSWORD, RW_PASSWORD, Database, alembic_config, applied_revisions

pytestmark = pytest.mark.integration

TABLES = [
    "regions",
    "engineer_sets",
    "engineers",
    "tickets",
    "plans",
    "assignments",
    "replan_events",
]
POINT = "ST_SetSRID(ST_MakePoint(37.62, 55.75), 4326)"
INITIAL = "5d23f2956ce7"
PRE_ENGINEER_SETS = "c124884e0c63"
HEAD = "1b0ce84eb128"


def _tables(db: Database) -> set[str]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables"
            " WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        ).fetchall()
    return {r[0] for r in rows}


def _roles(db: Database) -> set[str]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT rolname FROM pg_roles WHERE rolname IN ('app_rw', 'app_ro') AND rolcanlogin"
        ).fetchall()
    return {r[0] for r in rows}


@pytest.fixture
def rw(migrated_db: Database) -> Iterator[psycopg.Connection]:
    """A connection as `app_rw` inside one transaction, rolled back after the test."""
    conn = migrated_db.connect("app_rw", RW_PASSWORD)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _violation(conn: psycopg.Connection, sql: str, params: Any = None) -> psycopg.Error:
    """Runs `sql` in a savepoint and returns the error it must raise."""
    with pytest.raises(psycopg.Error) as raised, conn.transaction():
        conn.execute(sql, params)
    return raised.value


def _region(conn: psycopg.Connection, code: str = "east") -> int:
    row = conn.execute(
        f"INSERT INTO regions (code, name, office_address, office_geom) "
        f"VALUES (%s, 'Восток', 'адрес офиса', {POINT}) RETURNING id",
        (code,),
    ).fetchone()
    assert row
    return int(row[0])


_ENGINEER_SET_NAMES = itertools.count(1)


def _engineer_set(conn: psycopg.Connection, region_id: int, **overrides: Any) -> int:
    """A throwaway set of the region — a fresh, uniquely named row each call, since
    tests only need a valid `engineer_set_id` to point brigades and plans at, not a
    particular set."""
    params = {
        "region_id": region_id,
        "name": f"set-{next(_ENGINEER_SET_NAMES)}",
        "kind": "demo",
        "engineers": 1,
        "morning_share": 0.0,
        "evening_share": 0.0,
        "seed": "east",
        **overrides,
    }
    row = conn.execute(
        "INSERT INTO engineer_sets"
        " (region_id, name, kind, engineers, morning_share, evening_share, seed)"
        " VALUES (%(region_id)s, %(name)s, %(kind)s, %(engineers)s, %(morning_share)s,"
        " %(evening_share)s, %(seed)s) RETURNING id",
        params,
    ).fetchone()
    assert row
    return int(row[0])


ENGINEER_SQL = (
    "INSERT INTO engineers (engineer_set_id, name, start_geom, shift_start, shift_end,"
    " vehicle_type, skills)"
    f" VALUES (%(engineer_set_id)s, 'Бригада 1', {POINT}, %(shift_start)s, %(shift_end)s,"
    " %(vehicle_type)s, %(skills)s) RETURNING id"
)


def _engineer_params(engineer_set_id: int, **overrides: Any) -> dict[str, Any]:
    return {
        "engineer_set_id": engineer_set_id,
        "shift_start": "09:00",
        "shift_end": "18:00",
        "vehicle_type": "car",
        "skills": ["local_work"],
        **overrides,
    }


def _engineer(conn: psycopg.Connection, region_id: int, **overrides: Any) -> int:
    engineer_set_id = overrides.pop("engineer_set_id", None) or _engineer_set(conn, region_id)
    row = conn.execute(ENGINEER_SQL, _engineer_params(engineer_set_id, **overrides)).fetchone()
    assert row
    return int(row[0])


TICKET_SQL = (
    "INSERT INTO tickets (region_id, external_id, type_hd, required_skill, required_vehicle,"
    " priority, address, geom, window_start, window_end, duration_min, status, received_at)"
    " VALUES (%(region_id)s, 'T-1', %(type_hd)s, %(required_skill)s, %(required_vehicle)s,"
    " %(priority)s,"
    " 'адрес', " + POINT + ", %(window_start)s, %(window_end)s, %(duration_min)s,"
    " %(status)s, %(received_at)s) RETURNING id"
)


def _ticket_params(region_id: int, **overrides: Any) -> dict[str, Any]:
    return {
        "region_id": region_id,
        "type_hd": "Локальная заявка",
        "required_skill": "local_work",
        "required_vehicle": None,
        "priority": 3,
        "window_start": datetime(2026, 9, 23, 10, 0),
        "window_end": datetime(2026, 9, 23, 12, 0),
        "duration_min": 30,
        "status": "sent",
        "received_at": datetime(2026, 9, 22, 18, 0),
        **overrides,
    }


def _ticket(conn: psycopg.Connection, region_id: int, **overrides: Any) -> int:
    row = conn.execute(TICKET_SQL, _ticket_params(region_id, **overrides)).fetchone()
    assert row
    return int(row[0])


def _plan(conn: psycopg.Connection, region_id: int, **overrides: Any) -> int:
    engineer_set_id = overrides.pop("engineer_set_id", None) or _engineer_set(conn, region_id)
    params = {
        "region_id": region_id,
        "engineer_set_id": engineer_set_id,
        "status": "done",
        "failed_reason": None,
        **overrides,
    }
    row = conn.execute(
        "INSERT INTO plans (region_id, engineer_set_id, plan_date, algorithm, status,"
        " failed_reason, created_at)"
        " VALUES (%(region_id)s, %(engineer_set_id)s, '2026-09-23', 'or_tools', %(status)s,"
        " %(failed_reason)s, '2026-09-22 20:00') RETURNING id",
        params,
    ).fetchone()
    assert row
    return int(row[0])


ASSIGNMENT_SQL = (
    "INSERT INTO assignments (plan_id, ticket_id, engineer_id, sequence_no, planned_arrival,"
    " travel_time_min, travel_distance_m, unassigned_reason, explanation)"
    " VALUES (%(plan_id)s, %(ticket_id)s, %(engineer_id)s, %(sequence_no)s,"
    " %(planned_arrival)s, %(travel_time_min)s, %(travel_distance_m)s, %(unassigned_reason)s,"
    " 'объяснение')"
)


def _assigned(plan_id: int, ticket_id: int, engineer_id: int, **overrides: Any) -> dict[str, Any]:
    return {
        "plan_id": plan_id,
        "ticket_id": ticket_id,
        "engineer_id": engineer_id,
        "sequence_no": 1,
        "planned_arrival": datetime(2026, 9, 23, 10, 30),
        "travel_time_min": 15,
        "travel_distance_m": 5400,
        "unassigned_reason": None,
        **overrides,
    }


def _unassigned(plan_id: int, ticket_id: int, **overrides: Any) -> dict[str, Any]:
    return {
        "plan_id": plan_id,
        "ticket_id": ticket_id,
        "engineer_id": None,
        "sequence_no": None,
        "planned_arrival": None,
        "travel_time_min": None,
        "travel_distance_m": None,
        "unassigned_reason": "no_skill",
        **overrides,
    }


# --- revision lifecycle -------------------------------------------------------------


def test_upgrade_creates_schema(empty_db: Database) -> None:
    command.upgrade(alembic_config(), "head")

    assert set(TABLES) <= _tables(empty_db)
    assert applied_revisions(empty_db) == [(HEAD,)]
    assert _roles(empty_db) == {"app_rw", "app_ro"}


def test_downgrade_then_upgrade(migrated_db: Database) -> None:
    command.downgrade(alembic_config(), "base")

    assert not set(TABLES) & _tables(migrated_db)
    assert _roles(migrated_db) == set()
    with migrated_db.connect() as conn:
        postgis = conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'postgis'").fetchone()
    assert postgis == (1,)

    command.upgrade(alembic_config(), "head")
    assert set(TABLES) <= _tables(migrated_db)


def test_upgrade_requires_role_passwords(
    empty_db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("APP_RW_PASSWORD")

    with pytest.raises(RuntimeError, match="APP_RW_PASSWORD"):
        command.upgrade(alembic_config(), "head")

    assert not set(TABLES) & _tables(empty_db)
    assert applied_revisions(empty_db) == []


def test_failed_ddl_rolls_back_whole_revision(empty_db: Database) -> None:
    with empty_db.connect() as conn:
        conn.execute("CREATE TABLE plans (id int)")
        conn.commit()
    try:
        with pytest.raises(ProgrammingError) as raised:
            command.upgrade(alembic_config(), "head")

        assert isinstance(raised.value.orig, errors.DuplicateTable)
        assert set(TABLES) & _tables(empty_db) == {"plans"}
        assert applied_revisions(empty_db) == []
        assert _roles(empty_db) == set()
    finally:
        with empty_db.connect() as conn:
            conn.execute("DROP TABLE plans")
            conn.commit()


def test_role_password_is_not_sql(empty_db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    password = "rw'pa ss; DROP TABLE x"
    monkeypatch.setenv("APP_RW_PASSWORD", password)

    try:
        command.upgrade(alembic_config(), "head")

        with empty_db.connect("app_rw", password) as conn:
            assert conn.execute("SELECT current_user").fetchone() == ("app_rw",)
    finally:
        command.downgrade(alembic_config(), "base")


def test_existing_role_is_reset(empty_db: Database) -> None:
    with empty_db.connect() as conn:
        conn.execute("CREATE ROLE app_rw LOGIN CREATEROLE CREATEDB PASSWORD 'old'")
        conn.commit()

    command.upgrade(alembic_config(), "head")

    with empty_db.connect() as conn:
        row = conn.execute(
            "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls"
            " FROM pg_roles WHERE rolname = 'app_rw'"
        ).fetchone()
    assert row == (False, False, False, False, False)
    with empty_db.connect("app_rw", RW_PASSWORD) as conn:
        assert conn.execute("SELECT current_user").fetchone() == ("app_rw",)


# --- roles ----------------------------------------------------------------------------


def test_app_rw_changes_data(rw: psycopg.Connection) -> None:
    region_id = _region(rw)
    rw.execute("UPDATE regions SET name = 'Восток-2' WHERE id = %s", (region_id,))
    assert rw.execute("SELECT name FROM regions WHERE id = %s", (region_id,)).fetchone() == (
        "Восток-2",
    )
    rw.execute("DELETE FROM regions WHERE id = %s", (region_id,))
    assert rw.execute("SELECT count(*) FROM regions WHERE id = %s", (region_id,)).fetchone() == (0,)


@pytest.mark.parametrize(
    "sql",
    ["CREATE TABLE x (id int)", "ALTER TABLE tickets ADD COLUMN y int", "DROP TABLE plans"],
)
def test_app_rw_cannot_change_schema(rw: psycopg.Connection, sql: str) -> None:
    assert isinstance(_violation(rw, sql), errors.InsufficientPrivilege)


def test_app_ro_is_read_only(migrated_db: Database) -> None:
    with migrated_db.connect("app_ro", RO_PASSWORD) as conn:
        for table in TABLES:
            conn.execute(f"SELECT count(*) FROM {table}")
        error = _violation(
            conn,
            f"INSERT INTO regions (code, name, office_address, office_geom)"
            f" VALUES ('x', 'x', 'x', {POINT})",
        )
    assert isinstance(error, errors.InsufficientPrivilege)


# --- time -------------------------------------------------------------------------------


def test_timestamps_are_naive_without_default(migrated_db: Database) -> None:
    with migrated_db.connect() as conn:
        rows = conn.execute(
            "SELECT table_name, column_name, data_type, column_default, datetime_precision"
            " FROM information_schema.columns"
            " WHERE table_schema = 'public' AND data_type LIKE 'timestamp%%'"
        ).fetchall()
        zoned = conn.execute(
            "SELECT table_name, column_name FROM information_schema.columns"
            " WHERE table_schema = 'public' AND data_type LIKE '%%with time zone'"
        ).fetchall()
    columns = {(r[0], r[1]) for r in rows}
    assert columns == {
        ("tickets", "window_start"),
        ("tickets", "window_end"),
        ("tickets", "received_at"),
        ("plans", "created_at"),
        ("assignments", "planned_arrival"),
        ("replan_events", "triggered_at"),
    }
    assert {r[2] for r in rows} == {"timestamp without time zone"}
    assert all(r[3] is None for r in rows)
    assert {r[4] for r in rows} == {0}
    assert zoned == []


def test_timestamp_keeps_whole_seconds(rw: psycopg.Connection) -> None:
    ticket_id = _ticket(rw, _region(rw), received_at=datetime(2026, 9, 22, 18, 0, 5, 700000))

    row = rw.execute("SELECT received_at FROM tickets WHERE id = %s", (ticket_id,)).fetchone()

    assert row == (datetime(2026, 9, 22, 18, 0, 6),)


def test_naive_time_roundtrips_unchanged(rw: psycopg.Connection) -> None:
    rw.execute("SET TIME ZONE 'America/New_York'")
    ticket_id = _ticket(
        rw,
        _region(rw),
        window_start=datetime(2026, 9, 23, 13, 20),
        window_end=datetime(2026, 9, 23, 15, 0),
    )
    rw.execute("SET TIME ZONE 'UTC'")

    row = rw.execute("SELECT window_start FROM tickets WHERE id = %s", (ticket_id,)).fetchone()

    assert row == (datetime(2026, 9, 23, 13, 20),)
    assert row[0].tzinfo is None


# --- engineers --------------------------------------------------------------------------


@pytest.mark.parametrize("skills", [["emergency"], ["local_work", "connection", "emergency"]])
def test_engineer_skills_valid(rw: psycopg.Connection, skills: list[str]) -> None:
    _engineer(rw, _region(rw), skills=skills)


@pytest.mark.parametrize(
    "skills",
    [
        [],
        ["local_work", "connection", "emergency", "local_work"],
        ["cooking"],
        ["local_work", None],
        [["local_work"], ["connection"]],
    ],
    ids=["empty", "four", "unknown", "null", "two_dimensional"],
)
def test_engineer_skills_rejected(rw: psycopg.Connection, skills: list[Any]) -> None:
    error = _engineer_violation(rw, skills=skills)
    assert isinstance(error, errors.CheckViolation)
    assert error.diag.constraint_name == "ck_engineers__skills"


def _engineer_violation(rw: psycopg.Connection, **overrides: Any) -> psycopg.Error:
    engineer_set_id = _engineer_set(rw, _region(rw))
    return _violation(rw, ENGINEER_SQL, _engineer_params(engineer_set_id, **overrides))


def test_engineer_shift_order(rw: psycopg.Connection) -> None:
    error = _engineer_violation(rw, shift_start="18:00", shift_end="09:00")
    assert error.diag.constraint_name == "ck_engineers__shift_order"


def test_engineer_vehicle_type(rw: psycopg.Connection) -> None:
    error = _engineer_violation(rw, vehicle_type="truck")
    assert error.diag.constraint_name == "ck_engineers__vehicle_type"


# --- tickets ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "start",
    [datetime(2026, 9, 23, 12, 0), datetime(2026, 9, 23, 13, 0)],
    ids=["equal", "later"],
)
def test_ticket_window_order(rw: psycopg.Connection, start: datetime) -> None:
    params = _ticket_params(_region(rw), window_start=start, window_end=datetime(2026, 9, 23, 12))
    error = _violation(rw, TICKET_SQL, params)
    assert error.diag.constraint_name == "ck_tickets__window_order"


@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [
        ("required_skill", "cooking", "ck_tickets__required_skill"),
        ("required_vehicle", "truck", "ck_tickets__required_vehicle"),
        ("priority", 0, "ck_tickets__priority_rank"),
        ("status", "lost", "ck_tickets__status"),
        ("duration_min", 0, "ck_tickets__duration_positive"),
    ],
)
def test_ticket_closed_sets(
    rw: psycopg.Connection, field: str, value: object, constraint: str
) -> None:
    error = _violation(rw, TICKET_SQL, _ticket_params(_region(rw), **{field: value}))
    assert isinstance(error, errors.CheckViolation)
    assert error.diag.constraint_name == constraint


@pytest.mark.parametrize("rank", [1, 2, 3, 7])
def test_ticket_priority_rank(rw: psycopg.Connection, rank: int) -> None:
    _ticket(rw, _region(rw), priority=rank)


def test_ticket_vehicle_may_be_absent(rw: psycopg.Connection) -> None:
    _ticket(rw, _region(rw), required_vehicle=None)


def test_ticket_requires_location(rw: psycopg.Connection) -> None:
    sql = TICKET_SQL.replace(POINT, "NULL")
    error = _violation(rw, sql, _ticket_params(_region(rw)))
    assert isinstance(error, errors.NotNullViolation)
    assert error.diag.column_name == "geom"


# --- tickets.type_hd ------------------------------------------------------------------


def _type_hd_comment(conn: psycopg.Connection) -> str:
    row = conn.execute(
        "SELECT col_description('tickets'::regclass, attnum) FROM pg_attribute"
        " WHERE attrelid = 'tickets'::regclass AND attname = 'type_hd'"
    ).fetchone()
    assert row
    return str(row[0])


def _owner_ticket(db: Database, type_hd: str | None) -> None:
    """A ticket written by the schema owner, outside the application."""
    with db.connect() as conn:
        region_id = _region(conn)
        conn.execute(TICKET_SQL, _ticket_params(region_id, type_hd=type_hd))
        conn.commit()


def test_ticket_type_hd_required(rw: psycopg.Connection) -> None:
    error = _violation(rw, TICKET_SQL, _ticket_params(_region(rw), type_hd=None))
    assert isinstance(error, errors.NotNullViolation)
    assert error.diag.column_name == "type_hd"


def test_type_hd_upgrade_keeps_tickets(empty_db: Database) -> None:
    command.upgrade(alembic_config(), INITIAL)
    _owner_ticket(empty_db, "Локальная заявка")

    command.upgrade(alembic_config(), "head")

    with empty_db.connect() as conn:
        assert conn.execute("SELECT type_hd FROM tickets").fetchall() == [("Локальная заявка",)]
        assert "обязателен" in _type_hd_comment(conn)


def test_type_hd_upgrade_fails_on_null(empty_db: Database) -> None:
    command.upgrade(alembic_config(), INITIAL)
    _owner_ticket(empty_db, None)
    try:
        with pytest.raises(Exception) as raised:
            command.upgrade(alembic_config(), "head")

        assert isinstance(getattr(raised.value, "orig", None), errors.NotNullViolation)
        assert applied_revisions(empty_db) == [(INITIAL,)]
        with empty_db.connect() as conn:
            assert conn.execute("SELECT type_hd FROM tickets").fetchall() == [(None,)]
    finally:
        # The next test migrates this database to head, which the row would block.
        command.downgrade(alembic_config(), "base")


def test_type_hd_downgrade(migrated_db: Database) -> None:
    command.downgrade(alembic_config(), INITIAL)
    try:
        with migrated_db.connect() as conn:
            assert "NULL — поле пусто" in _type_hd_comment(conn)
        _owner_ticket(migrated_db, None)
        with migrated_db.connect() as conn:
            conn.execute("DELETE FROM tickets")
            conn.execute("DELETE FROM regions")
            conn.commit()
    finally:
        command.upgrade(alembic_config(), "head")
    assert applied_revisions(migrated_db) == [(HEAD,)]


# --- engineer_sets ------------------------------------------------------------------------


def _owner_engineer_pre_engineer_sets(
    conn: psycopg.Connection, region_id: int, name: str = "Бригада 1"
) -> int:
    """A brigade written directly against the pre-migration schema, where a brigade still
    belongs to a region directly (`engineers.region_id`), not to a set."""
    row = conn.execute(
        "INSERT INTO engineers (region_id, name, start_geom, shift_start, shift_end,"
        f" vehicle_type, skills) VALUES (%s, %s, {POINT}, '09:00', '18:00', 'car',"
        " ARRAY['local_work']) RETURNING id",
        (region_id, name),
    ).fetchone()
    assert row
    return int(row[0])


def test_upgrade_backfills_default_set_from_config(empty_db: Database) -> None:
    """`east` is in the repository's own `data/regions.toml` with `engineers=13` and
    morning/evening shares 0.25 — the values this backfill must read from there."""
    command.upgrade(alembic_config(), PRE_ENGINEER_SETS)
    with empty_db.connect() as conn:
        region_id = _region(conn, "east")
        for i in range(13):
            _owner_engineer_pre_engineer_sets(conn, region_id, f"Бригада {i}")
        conn.commit()

    command.upgrade(alembic_config(), "head")

    with empty_db.connect() as conn:
        rows = conn.execute(
            "SELECT id, name, kind, engineers, morning_share, evening_share, seed"
            " FROM engineer_sets WHERE region_id = %s",
            (region_id,),
        ).fetchall()
        assert len(rows) == 1
        set_id, name, kind, engineers, morning_share, evening_share, seed = rows[0]
        assert (name, kind, engineers, morning_share, evening_share, seed) == (
            "default",
            "demo",
            13,
            0.25,
            0.25,
            "east",
        )
        count = conn.execute(
            "SELECT count(*) FROM engineers WHERE engineer_set_id = %s", (set_id,)
        ).fetchone()
        assert count == (13,)
        no_region_id = conn.execute(
            "SELECT 1 FROM information_schema.columns"
            " WHERE table_name = 'engineers' AND column_name = 'region_id'"
        ).fetchone()
        assert no_region_id is None


def test_upgrade_backfills_unknown_region_from_db(empty_db: Database) -> None:
    """`west` has no entry in `data/regions.toml` — the backfill falls back to the
    region's current brigade count and its own code as `seed`, with both shares 0."""
    command.upgrade(alembic_config(), PRE_ENGINEER_SETS)
    with empty_db.connect() as conn:
        region_id = _region(conn, "west")
        for i in range(5):
            _owner_engineer_pre_engineer_sets(conn, region_id, f"Бригада {i}")
        conn.commit()

    command.upgrade(alembic_config(), "head")

    with empty_db.connect() as conn:
        row = conn.execute(
            "SELECT id, engineers, morning_share, evening_share, seed FROM engineer_sets"
            " WHERE region_id = %s",
            (region_id,),
        ).fetchone()
        assert row is not None
        set_id, engineers, morning_share, evening_share, seed = row
        assert (engineers, morning_share, evening_share, seed) == (5, 0.0, 0.0, "west")
        count = conn.execute(
            "SELECT count(*) FROM engineers WHERE engineer_set_id = %s", (set_id,)
        ).fetchone()
        assert count == (5,)


def test_upgrade_plans_get_default_engineer_set_id(empty_db: Database) -> None:
    command.upgrade(alembic_config(), PRE_ENGINEER_SETS)
    with empty_db.connect() as conn:
        region_id = _region(conn, "east")
        row = conn.execute(
            "INSERT INTO plans (region_id, plan_date, algorithm, status, created_at)"
            " VALUES (%s, '2026-09-23', 'or_tools', 'done', '2026-09-22 20:00') RETURNING id",
            (region_id,),
        ).fetchone()
        assert row
        plan_id = int(row[0])
        conn.commit()

    command.upgrade(alembic_config(), "head")

    with empty_db.connect() as conn:
        default_row = conn.execute(
            "SELECT id FROM engineer_sets WHERE region_id = %s AND kind = 'demo'", (region_id,)
        ).fetchone()
        assert default_row
        plan_row = conn.execute(
            "SELECT engineer_set_id FROM plans WHERE id = %s", (plan_id,)
        ).fetchone()
        assert plan_row == default_row


def test_upgrade_keeps_engineer_and_plan_ids(empty_db: Database) -> None:
    command.upgrade(alembic_config(), PRE_ENGINEER_SETS)
    with empty_db.connect() as conn:
        region_id = _region(conn, "east")
        e1 = _owner_engineer_pre_engineer_sets(conn, region_id, "Бригада 1")
        e2 = _owner_engineer_pre_engineer_sets(conn, region_id, "Бригада 2")
        row = conn.execute(
            "INSERT INTO plans (region_id, plan_date, algorithm, status, created_at)"
            " VALUES (%s, '2026-09-23', 'or_tools', 'done', '2026-09-22 20:00') RETURNING id",
            (region_id,),
        ).fetchone()
        assert row
        p1 = int(row[0])
        conn.commit()

    command.upgrade(alembic_config(), "head")

    with empty_db.connect() as conn:
        engineer_ids = [
            r[0] for r in conn.execute("SELECT id FROM engineers ORDER BY id").fetchall()
        ]
        plan_ids = [r[0] for r in conn.execute("SELECT id FROM plans").fetchall()]
    assert engineer_ids == [e1, e2]
    assert plan_ids == [p1]


def test_engineer_set_kind_closed_set(rw: psycopg.Connection) -> None:
    region_id = _region(rw)
    error = _violation(
        rw,
        "INSERT INTO engineer_sets (region_id, name, kind, engineers, morning_share,"
        " evening_share, seed) VALUES (%s, 'x', 'bogus', 1, 0, 0, 'seed')",
        (region_id,),
    )
    assert isinstance(error, errors.CheckViolation)
    assert error.diag.constraint_name == "ck_engineer_sets__kind"


@pytest.mark.parametrize(
    ("engineers", "ok"), [(0, False), (31, False), (1, True), (30, True)], ids=str
)
def test_engineer_set_engineers_bounds(rw: psycopg.Connection, engineers: int, ok: bool) -> None:
    region_id = _region(rw)
    sql = (
        "INSERT INTO engineer_sets (region_id, name, kind, engineers, morning_share,"
        " evening_share, seed) VALUES (%s, 'x', 'demo', %s, 0, 0, 'seed')"
    )
    if ok:
        rw.execute(sql, (region_id, engineers))
    else:
        error = _violation(rw, sql, (region_id, engineers))
        assert isinstance(error, errors.CheckViolation)
        assert error.diag.constraint_name == "ck_engineer_sets__engineers"


@pytest.mark.parametrize(
    ("morning_share", "evening_share", "ok"),
    [
        (-0.1, 0.0, False),
        (1.1, 0.0, False),
        (0.0, -0.1, False),
        (0.0, 1.1, False),
        (0.0, 0.0, True),
        (1.0, 1.0, True),
    ],
    ids=["morning_low", "morning_high", "evening_low", "evening_high", "zero", "one"],
)
def test_engineer_set_share_bounds(
    rw: psycopg.Connection, morning_share: float, evening_share: float, ok: bool
) -> None:
    region_id = _region(rw)
    sql = (
        "INSERT INTO engineer_sets (region_id, name, kind, engineers, morning_share,"
        " evening_share, seed) VALUES (%s, 'x', 'demo', 1, %s, %s, 'seed')"
    )
    if ok:
        rw.execute(sql, (region_id, morning_share, evening_share))
    else:
        assert isinstance(
            _violation(rw, sql, (region_id, morning_share, evening_share)), errors.CheckViolation
        )


def test_engineer_set_seed_not_blank(rw: psycopg.Connection) -> None:
    region_id = _region(rw)
    error = _violation(
        rw,
        "INSERT INTO engineer_sets (region_id, name, kind, engineers, morning_share,"
        " evening_share, seed) VALUES (%s, 'x', 'demo', 1, 0, 0, '')",
        (region_id,),
    )
    assert isinstance(error, errors.CheckViolation)
    assert error.diag.constraint_name == "ck_engineer_sets__seed"


def test_engineer_set_name_unique_per_region(rw: psycopg.Connection) -> None:
    region_id = _region(rw)
    other_region_id = _region(rw, "south_east")
    sql = (
        "INSERT INTO engineer_sets (region_id, name, kind, engineers, morning_share,"
        " evening_share, seed) VALUES (%s, 'default', 'demo', 1, 0, 0, 'seed')"
    )
    rw.execute(sql, (region_id,))

    error = _violation(rw, sql, (region_id,))

    assert isinstance(error, errors.UniqueViolation)
    assert error.diag.constraint_name == "ux_engineer_sets__region_id_name"
    rw.execute(sql, (other_region_id,))


def test_engineers_engineer_set_id_required(rw: psycopg.Connection) -> None:
    error = _violation(
        rw,
        f"INSERT INTO engineers (engineer_set_id, name, start_geom, shift_start, shift_end,"
        f" vehicle_type, skills) VALUES (NULL, 'x', {POINT}, '09:00', '18:00', 'car',"
        " ARRAY['local_work'])",
    )
    assert isinstance(error, errors.NotNullViolation)
    assert error.diag.column_name == "engineer_set_id"


def test_engineers_engineer_set_id_foreign_key(rw: psycopg.Connection) -> None:
    error = _violation(
        rw,
        f"INSERT INTO engineers (engineer_set_id, name, start_geom, shift_start, shift_end,"
        f" vehicle_type, skills) VALUES (999999, 'x', {POINT}, '09:00', '18:00', 'car',"
        " ARRAY['local_work'])",
    )
    assert isinstance(error, errors.ForeignKeyViolation)


def test_plans_engineer_set_id_required_and_fk(rw: psycopg.Connection) -> None:
    region_id = _region(rw)
    required = _violation(
        rw,
        "INSERT INTO plans (region_id, plan_date, algorithm, status, created_at)"
        " VALUES (%s, '2026-09-23', 'or_tools', 'done', '2026-09-22 20:00')",
        (region_id,),
    )
    assert isinstance(required, errors.NotNullViolation)
    assert required.diag.column_name == "engineer_set_id"

    fk = _violation(
        rw,
        "INSERT INTO plans (region_id, engineer_set_id, plan_date, algorithm, status,"
        " created_at) VALUES (%s, 999999, '2026-09-23', 'or_tools', 'done', '2026-09-22 20:00')",
        (region_id,),
    )
    assert isinstance(fk, errors.ForeignKeyViolation)


def test_engineer_sets_downgrade_then_upgrade(migrated_db: Database) -> None:
    with migrated_db.connect() as conn:
        region_id = _region(conn, "east")
        set_id = _engineer_set(conn, region_id, name="default", kind="demo", engineers=1)
        engineer_id = conn.execute(
            "INSERT INTO engineers (engineer_set_id, name, start_geom, shift_start, shift_end,"
            f" vehicle_type, skills) VALUES (%s, 'Бригада 1', {POINT}, '09:00', '18:00', 'car',"
            " ARRAY['local_work']) RETURNING id",
            (set_id,),
        ).fetchone()
        assert engineer_id
        engineer_id = engineer_id[0]
        conn.commit()

    command.downgrade(alembic_config(), PRE_ENGINEER_SETS)
    try:
        assert "engineer_sets" not in _tables(migrated_db)
        with migrated_db.connect() as conn:
            restored = conn.execute(
                "SELECT region_id FROM engineers WHERE id = %s", (engineer_id,)
            ).fetchone()
            assert restored == (region_id,)
            no_engineer_set_id = conn.execute(
                "SELECT 1 FROM information_schema.columns"
                " WHERE table_name = 'engineers' AND column_name = 'engineer_set_id'"
            ).fetchone()
            assert no_engineer_set_id is None
            no_plan_engineer_set_id = conn.execute(
                "SELECT 1 FROM information_schema.columns"
                " WHERE table_name = 'plans' AND column_name = 'engineer_set_id'"
            ).fetchone()
            assert no_plan_engineer_set_id is None
    finally:
        command.upgrade(alembic_config(), "head")

    with migrated_db.connect() as conn:
        recreated = conn.execute(
            "SELECT kind FROM engineer_sets WHERE region_id = %s", (region_id,)
        ).fetchone()
    assert recreated == ("demo",)


def test_engineer_sets_grants(rw: psycopg.Connection, migrated_db: Database) -> None:
    region_id = _region(rw)
    row = rw.execute(
        "INSERT INTO engineer_sets (region_id, name, kind, engineers, morning_share,"
        " evening_share, seed) VALUES (%s, 'x', 'demo', 1, 0, 0, 'seed') RETURNING id",
        (region_id,),
    ).fetchone()
    assert row
    set_id = row[0]
    rw.execute("UPDATE engineer_sets SET name = 'y' WHERE id = %s", (set_id,))
    rw.execute("DELETE FROM engineer_sets WHERE id = %s", (set_id,))

    with migrated_db.connect("app_ro", RO_PASSWORD) as conn:
        conn.execute("SELECT count(*) FROM engineer_sets")


# --- plans.status -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "failed_reason", ["osrm_unavailable", "db_unavailable", "build_error", "timeout", "shutdown"]
)
def test_plan_failed_reason_valid(rw: psycopg.Connection, failed_reason: str) -> None:
    region_id = _region(rw)
    _plan(rw, region_id, status="failed", failed_reason=failed_reason)


@pytest.mark.parametrize("status", ["running", "done", "failed"])
def test_plan_status_valid(rw: psycopg.Connection, status: str) -> None:
    region_id = _region(rw)
    failed_reason = "build_error" if status == "failed" else None
    _plan(rw, region_id, status=status, failed_reason=failed_reason)


def test_plan_status_closed_set(rw: psycopg.Connection) -> None:
    region_id = _region(rw)
    with pytest.raises(psycopg.Error) as raised, rw.transaction():
        _plan(rw, region_id, status="queued")
    assert raised.value.diag.constraint_name == "ck_plans__status"


def test_plan_failed_reason_closed_set(rw: psycopg.Connection) -> None:
    region_id = _region(rw)
    with pytest.raises(psycopg.Error) as raised, rw.transaction():
        _plan(rw, region_id, status="failed", failed_reason="bogus_reason")
    assert raised.value.diag.constraint_name == "ck_plans__failed_reason"


@pytest.mark.parametrize(
    ("status", "failed_reason"),
    [("failed", None), ("done", "build_error"), ("running", "build_error")],
    ids=["failed_without_reason", "done_with_reason", "running_with_reason"],
)
def test_plan_status_failed_reason_shape(
    rw: psycopg.Connection, status: str, failed_reason: str | None
) -> None:
    region_id = _region(rw)
    with pytest.raises(psycopg.Error) as raised, rw.transaction():
        _plan(rw, region_id, status=status, failed_reason=failed_reason)
    assert raised.value.diag.constraint_name == "ck_plans__status_failed_reason"


# --- assignments ------------------------------------------------------------------------


@pytest.fixture
def plan_rows(rw: psycopg.Connection) -> dict[str, int]:
    region_id = _region(rw)
    return {
        "plan": _plan(rw, region_id),
        "other_plan": _plan(rw, region_id),
        "ticket": _ticket(rw, region_id),
        "ticket2": _ticket(rw, region_id),
        "engineer": _engineer(rw, region_id),
    }


def test_assignment_shapes_valid(rw: psycopg.Connection, plan_rows: dict[str, int]) -> None:
    rw.execute(
        ASSIGNMENT_SQL, _assigned(plan_rows["plan"], plan_rows["ticket"], plan_rows["engineer"])
    )
    rw.execute(ASSIGNMENT_SQL, _unassigned(plan_rows["plan"], plan_rows["ticket2"]))


@pytest.mark.parametrize(
    "shape",
    ["assigned_without_travel", "assigned_with_reason", "unassigned_with_engineer", "neither"],
)
def test_assignment_shapes_rejected(
    rw: psycopg.Connection, plan_rows: dict[str, int], shape: str
) -> None:
    plan, ticket, engineer = plan_rows["plan"], plan_rows["ticket"], plan_rows["engineer"]
    params = {
        "assigned_without_travel": _assigned(plan, ticket, engineer, travel_time_min=None),
        "assigned_with_reason": _assigned(plan, ticket, engineer, unassigned_reason="no_skill"),
        "unassigned_with_engineer": _unassigned(plan, ticket, engineer_id=engineer),
        "neither": _unassigned(plan, ticket, unassigned_reason=None),
    }[shape]
    error = _violation(rw, ASSIGNMENT_SQL, params)
    assert isinstance(error, errors.CheckViolation)
    assert error.diag.constraint_name == "ck_assignments__assigned_or_reason"


def test_assignment_ticket_once_per_plan(rw: psycopg.Connection, plan_rows: dict[str, int]) -> None:
    rw.execute(ASSIGNMENT_SQL, _unassigned(plan_rows["plan"], plan_rows["ticket"]))

    error = _violation(rw, ASSIGNMENT_SQL, _unassigned(plan_rows["plan"], plan_rows["ticket"]))

    assert isinstance(error, errors.UniqueViolation)
    assert error.diag.constraint_name == "ux_assignments__plan_id_ticket_id"
    rw.execute(ASSIGNMENT_SQL, _unassigned(plan_rows["other_plan"], plan_rows["ticket"]))


def test_assignment_sequence_unique_per_engineer(
    rw: psycopg.Connection, plan_rows: dict[str, int]
) -> None:
    plan, engineer = plan_rows["plan"], plan_rows["engineer"]
    rw.execute(ASSIGNMENT_SQL, _assigned(plan, plan_rows["ticket"], engineer))

    duplicate = _violation(rw, ASSIGNMENT_SQL, _assigned(plan, plan_rows["ticket2"], engineer))
    zero = _violation(
        rw, ASSIGNMENT_SQL, _assigned(plan, plan_rows["ticket2"], engineer, sequence_no=0)
    )

    assert isinstance(duplicate, errors.UniqueViolation)
    assert duplicate.diag.constraint_name == "ux_assignments__plan_id_engineer_id_sequence_no"
    assert zero.diag.constraint_name == "ck_assignments__sequence_no_positive"


def test_assignment_arrival_whole_minute(rw: psycopg.Connection, plan_rows: dict[str, int]) -> None:
    params = _assigned(
        plan_rows["plan"],
        plan_rows["ticket"],
        plan_rows["engineer"],
        planned_arrival=datetime(2026, 9, 23, 10, 30, 15),
    )
    error = _violation(rw, ASSIGNMENT_SQL, params)
    assert error.diag.constraint_name == "ck_assignments__planned_arrival_whole_minute"


def test_assignment_reason_set(rw: psycopg.Connection, plan_rows: dict[str, int]) -> None:
    params = _unassigned(plan_rows["plan"], plan_rows["ticket"], unassigned_reason="busy")
    error = _violation(rw, ASSIGNMENT_SQL, params)
    assert error.diag.constraint_name == "ck_assignments__unassigned_reason"


# --- replan events, keys, documentation -------------------------------------------------


def test_replan_event_types(rw: psycopg.Connection) -> None:
    plan_id = _plan(rw, _region(rw))
    sql = (
        "INSERT INTO replan_events (plan_id, event_type, payload, triggered_at)"
        " VALUES (%s, %s, '{}', '2026-09-23 13:20')"
    )
    for event_type in (
        "new_urgent_ticket",
        "new_ticket",
        "ticket_cancelled",
        "engineer_unavailable",
    ):
        rw.execute(sql, (plan_id, event_type))

    error = _violation(rw, sql, (plan_id, "reorder"))

    assert error.diag.constraint_name == "ck_replan_events__event_type"


@pytest.mark.parametrize(
    "sql",
    [
        (
            f"INSERT INTO engineers (engineer_set_id, name, start_geom, shift_start, shift_end,"
            f" vehicle_type, skills) VALUES (999999, 'x', {POINT}, '09:00', '18:00', 'car',"
            f" ARRAY['local_work'])"
        ),
        (
            "INSERT INTO plans (region_id, engineer_set_id, plan_date, algorithm, status,"
            " parent_plan_id, created_at) VALUES ((SELECT min(id) FROM regions),"
            " (SELECT id FROM engineer_sets LIMIT 1), '2026-09-23', 'or_tools', 'done',"
            " 999999, '2026-09-22 20:00')"
        ),
        (
            "INSERT INTO assignments (plan_id, ticket_id, unassigned_reason, explanation)"
            " VALUES ((SELECT min(id) FROM plans), 999999, 'no_skill', 'x')"
        ),
    ],
    ids=["engineer_engineer_set", "plan_parent", "assignment_ticket"],
)
def test_foreign_keys_enforced(rw: psycopg.Connection, sql: str) -> None:
    _plan(rw, _region(rw))
    assert isinstance(_violation(rw, sql), errors.ForeignKeyViolation)


def test_every_foreign_key_is_indexed(migrated_db: Database) -> None:
    with migrated_db.connect() as conn:
        unindexed = conn.execute(
            """
            SELECT c.conrelid::regclass::text, a.attname
            FROM pg_constraint c
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
            WHERE c.contype = 'f'
              AND NOT EXISTS (
                  SELECT 1 FROM pg_index i
                  WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1]
              )
            """
        ).fetchall()
    assert unindexed == []


def test_every_table_and_column_is_commented(migrated_db: Database) -> None:
    with migrated_db.connect() as conn:
        tables = conn.execute(
            "SELECT relname FROM pg_class WHERE relname = ANY(%s)"
            " AND obj_description(oid, 'pg_class') IS NULL",
            (TABLES,),
        ).fetchall()
        columns = conn.execute(
            "SELECT c.relname, a.attname FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid"
            " WHERE c.relname = ANY(%s) AND a.attnum > 0 AND NOT a.attisdropped"
            " AND a.attname <> 'id' AND col_description(c.oid, a.attnum) IS NULL",
            (TABLES,),
        ).fetchall()
    assert tables == []
    assert columns == []
