"""plan name and baseline uniqueness

Revision ID: 48d00d8a0e41
Revises: 46c1bba9efff
Create Date: 2026-10-01 06:26:45.896006

Adds `plans.name`, backfilled from the plan's own id ("План №{id}") and, for
`baseline_fcfs` plans, the name of their engineer set ("План №{id} · {имя набора}").
From this revision on, application code always sets it in the same statement as the
insert (`insert_running_plan`, `insert_replanned_plan`) — never left to a default.

Adds a partial unique index enforcing at most one active (`running` or `done`)
`baseline_fcfs` plan per `(engineer_set_id, plan_date)`: `POST /plan/build` relies on
it (`ON CONFLICT ... DO NOTHING`) so that two concurrent requests for the same
combination cannot both queue a build.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "48d00d8a0e41"
down_revision: str | Sequence[str] | None = "46c1bba9efff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE plans ADD COLUMN name TEXT")
    op.execute(
        "UPDATE plans SET name = 'План №' || plans.id"
        " || CASE WHEN plans.algorithm = 'baseline_fcfs'"
        " THEN ' · ' || engineer_sets.name ELSE '' END"
        " FROM engineer_sets WHERE engineer_sets.id = plans.engineer_set_id"
    )
    op.execute("ALTER TABLE plans ALTER COLUMN name SET NOT NULL")
    op.execute(
        "COMMENT ON COLUMN plans.name IS "
        "'Название плана; выставляется автоматически при построении (План №{id}, "
        "у baseline_fcfs — с именем набора бригад) и может быть изменено "
        "PATCH /plan/{plan_id}'"
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_plans__active_baseline_per_set_date ON plans "
        "(engineer_set_id, plan_date) "
        "WHERE algorithm = 'baseline_fcfs' AND status IN ('running', 'done')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ux_plans__active_baseline_per_set_date")
    op.execute("ALTER TABLE plans DROP COLUMN name")
