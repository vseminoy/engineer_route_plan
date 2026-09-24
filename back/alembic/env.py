"""Applies migrations as the schema owner, logging in the application's format.

The address comes from `MIGRATION_DATABASE_URL` in the process environment;
`alembic.ini` holds none.
"""

from alembic import context
from sqlalchemy import create_engine, pool

from src.config import MigrationSettings
from src.logging import configure_logging, get_logger

settings = MigrationSettings()
configure_logging(settings)
log = get_logger("alembic.env")


def _sqlalchemy_url(url: str) -> str:
    """Names the driver in a libpq-style URL (`postgresql://...`): without it
    SQLAlchemy picks psycopg2, which is not installed."""
    scheme, _, rest = url.partition("://")
    if scheme in ("postgresql", "postgres"):
        return f"postgresql+psycopg://{rest}"
    return url


def run_migrations_online() -> None:
    # `hide_parameters`: a failed statement's parameters (role passwords among them)
    # stay out of the exception text that `migration_failed` logs.
    engine = create_engine(
        _sqlalchemy_url(settings.migration_database_url),
        poolclass=pool.NullPool,
        hide_parameters=True,
    )
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=None)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


def run_migrations() -> None:
    if context.is_offline_mode():
        # A revision passes role passwords as bind parameters; rendered as SQL text
        # they would end up in the generated script.
        raise RuntimeError(
            "offline mode is not supported: migrations run against a live database"
        )
    run_migrations_online()


try:
    run_migrations()
except Exception:
    log.exception("migration_failed")
    # From the command line, exit without the interpreter's plain-text traceback so
    # every line of the container log stays one JSON record; the stack is already in
    # the record above. Programmatic callers (`alembic.command`) get the exception.
    # Source: https://alembic.sqlalchemy.org/en/latest/api/config.html (Config.cmd_opts)
    if context.config.cmd_opts is not None:
        raise SystemExit(1) from None
    raise
