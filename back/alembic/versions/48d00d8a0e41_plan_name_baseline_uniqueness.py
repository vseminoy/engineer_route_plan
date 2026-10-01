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

Rows from before this constraint existed can already violate it (several active
baseline_fcfs plans built for the same combination over time); the index cannot be
created until those are resolved, so the losers of each group — every plan but the
most recently created one — and anything replanned from them are deleted first, the
same way `DELETE /plan/{id}` deletes a plan's tree.
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
    losers = (
        "losers AS ("
        "    SELECT id FROM ("
        "        SELECT id, row_number() OVER ("
        "            PARTITION BY engineer_set_id, plan_date ORDER BY id DESC"
        "        ) AS rn"
        "        FROM plans"
        "        WHERE algorithm = 'baseline_fcfs' AND status IN ('running', 'done')"
        "    ) ranked WHERE rn > 1"
        "), "
        "tree AS ("
        "    SELECT id FROM losers"
        "    UNION ALL"
        "    SELECT p.id FROM plans p JOIN tree t ON p.parent_plan_id = t.id"
        ")"
    )
    op.execute(
        f"WITH RECURSIVE {losers} "
        "DELETE FROM replan_events "
        "WHERE plan_id IN (SELECT id FROM tree) OR result_plan_id IN (SELECT id FROM tree)"
    )
    op.execute(
        f"WITH RECURSIVE {losers} "
        "DELETE FROM assignments WHERE plan_id IN (SELECT id FROM tree)"
    )
    op.execute(f"WITH RECURSIVE {losers} DELETE FROM plans WHERE id IN (SELECT id FROM tree)")
    op.execute(
        "CREATE UNIQUE INDEX ux_plans__active_baseline_per_set_date ON plans "
        "(engineer_set_id, plan_date) "
        "WHERE algorithm = 'baseline_fcfs' AND status IN ('running', 'done')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ux_plans__active_baseline_per_set_date")
    op.execute("ALTER TABLE plans DROP COLUMN name")
