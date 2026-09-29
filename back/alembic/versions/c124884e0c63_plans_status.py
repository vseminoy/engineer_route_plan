"""plans status

Revision ID: c124884e0c63
Revises: cb3db41d521a
Create Date: 2026-09-27 00:00:00.000000

Plan build runs in the background after the request that queued it answers: a plan row
exists (`running`) before its routes are known, gets its assignments once the build
finishes (`done`), or stays without them if the build failed (`failed`, with
`failed_reason`). Existing rows predate this and are always fully built: they backfill
to `done`.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c124884e0c63"
down_revision: str | Sequence[str] | None = "cb3db41d521a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE plans ADD COLUMN status TEXT NOT NULL DEFAULT 'done'")
    op.execute("ALTER TABLE plans ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE plans ADD CONSTRAINT ck_plans__status "
        "CHECK (status IN ('running', 'done', 'failed'))"
    )
    op.execute("ALTER TABLE plans ADD COLUMN failed_reason TEXT")
    op.execute(
        "ALTER TABLE plans ADD CONSTRAINT ck_plans__failed_reason "
        "CHECK (failed_reason IN ('osrm_unavailable', 'db_unavailable', 'build_error'))"
    )
    op.execute(
        "ALTER TABLE plans ADD CONSTRAINT ck_plans__status_failed_reason CHECK ("
        "(status = 'failed' AND failed_reason IS NOT NULL) OR "
        "(status != 'failed' AND failed_reason IS NULL))"
    )
    op.execute(
        "COMMENT ON COLUMN plans.status IS "
        "'Состояние построения: running — фоновая задача ещё не закончилась, "
        "done — построен, failed — построение завершилось ошибкой'"
    )
    op.execute(
        "COMMENT ON COLUMN plans.failed_reason IS "
        "'Причина отказа; заполнено только при status = failed'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE plans DROP CONSTRAINT ck_plans__status_failed_reason")
    op.execute("ALTER TABLE plans DROP CONSTRAINT ck_plans__failed_reason")
    op.execute("ALTER TABLE plans DROP COLUMN failed_reason")
    op.execute("ALTER TABLE plans DROP CONSTRAINT ck_plans__status")
    op.execute("ALTER TABLE plans DROP COLUMN status")
