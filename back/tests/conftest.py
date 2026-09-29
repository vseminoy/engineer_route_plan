from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from testcontainers.community.postgres import PostgresContainer

import src.app as app_module

BACK_DIR = Path(__file__).resolve().parents[1]
IMAGE = "postgis/postgis:16-3.4"
RW_PASSWORD = "rw-test"
RO_PASSWORD = "ro-test"


@pytest.fixture(autouse=True)
def _no_startup_sweep_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """`app.py`'s `lifespan` calls `sweep_running_plans` against the real `db_pool`
    before serving, but most tests build `create_app()` against an unreachable fake
    `database_url` and never intended to touch the database at startup at all —
    `db_pool.open(wait=False)` itself already performs no I/O. Stubbed out here so
    every such test keeps behaving as it did before this call existed; tests/test_app.py
    overrides this stub with its own fake to check the wiring, and the sweep's own
    behaviour is covered directly in tests/service/test_plan_builder.py and
    tests/repository/test_plans.py, with no real app involved."""

    async def _noop(*_args: Any, **_kwargs: Any) -> list[int]:
        return []

    monkeypatch.setattr(app_module, "sweep_running_plans", _noop)


@dataclass(frozen=True)
class Database:
    host: str
    port: int
    dbname: str
    owner: str
    owner_password: str

    @property
    def url(self) -> str:
        """libpq-style URL, the form the stand passes in MIGRATION_DATABASE_URL."""
        return (
            f"postgresql://{self.owner}:{self.owner_password}@{self.host}:{self.port}/{self.dbname}"
        )

    def connect(self, user: str | None = None, password: str | None = None) -> psycopg.Connection:
        return psycopg.connect(
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            user=user or self.owner,
            password=password or self.owner_password,
        )


@pytest.fixture(scope="session")
def database() -> Iterator[Database]:
    with PostgresContainer(
        IMAGE, username="owner", password="owner-test", dbname="plan", driver=None
    ) as container:
        yield Database(
            host=container.get_container_host_ip(),
            port=int(container.get_exposed_port(5432)),
            dbname="plan",
            owner="owner",
            owner_password="owner-test",
        )


@pytest.fixture
def migration_env(database: Database, monkeypatch: pytest.MonkeyPatch) -> Database:
    """The environment `alembic/env.py` and the revision read, set for this process."""
    monkeypatch.setenv("MIGRATION_DATABASE_URL", database.url)
    monkeypatch.setenv("APP_RW_PASSWORD", RW_PASSWORD)
    monkeypatch.setenv("APP_RO_PASSWORD", RO_PASSWORD)
    monkeypatch.setenv("LOG_FORMAT", "json")
    return database


def applied_revisions(db: Database) -> list[tuple[str]]:
    """Applied revisions; empty after `downgrade base`, which keeps the table itself."""
    with db.connect() as conn:
        exists = conn.execute("SELECT to_regclass('alembic_version')").fetchone()
        if not exists or exists[0] is None:
            return []
        return conn.execute("SELECT version_num FROM alembic_version").fetchall()


def alembic_config() -> Config:
    return Config(str(BACK_DIR / "alembic.ini"))


@pytest.fixture
def empty_db(migration_env: Database) -> Database:
    """The database with every revision rolled back."""
    command.downgrade(alembic_config(), "base")
    return migration_env


@pytest.fixture
def migrated_db(migration_env: Database) -> Database:
    """The database at the latest revision; a no-op when it already is."""
    command.upgrade(alembic_config(), "head")
    return migration_env
