"""plans failed reason timeout shutdown

Revision ID: 46c1bba9efff
Revises: 1b0ce84eb128
Create Date: 2026-09-29 09:19:26.456111

The solver watchdog and the startup sweep of stuck `running` plans
(`plan_builder.PlanBuilder._solve`, `plan_builder.sweep_running_plans`) close a plan with
`failed_reason='timeout'` or `'shutdown'`, but `ck_plans__failed_reason` from
`c124884e0c63` never allowed either value: both writes fail with a `CheckViolation`,
silently swallowed by the caller, which leaves the plan stuck in `running` forever —
exactly the outcome the watchdog and the sweep exist to prevent. Widens the constraint to
the actual set of reasons the code writes.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '46c1bba9efff'
down_revision: str | Sequence[str] | None = '1b0ce84eb128'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE plans DROP CONSTRAINT ck_plans__failed_reason")
    op.execute(
        "ALTER TABLE plans ADD CONSTRAINT ck_plans__failed_reason "
        "CHECK (failed_reason IN ('osrm_unavailable', 'db_unavailable', 'build_error', "
        "'timeout', 'shutdown'))"
    )
    op.execute(
        "COMMENT ON COLUMN plans.failed_reason IS "
        "'Причина отказа; заполнено только при status = failed. timeout — солвер или его "
        "воркер не уложились в бюджет и вотчдог его прибил; shutdown — план остался "
        "running при остановке сервера и закрыт стартовой чисткой'"
    )


def downgrade() -> None:
    op.execute(
        "COMMENT ON COLUMN plans.failed_reason IS "
        "'Причина отказа; заполнено только при status = failed'"
    )
    op.execute("ALTER TABLE plans DROP CONSTRAINT ck_plans__failed_reason")
    op.execute(
        "ALTER TABLE plans ADD CONSTRAINT ck_plans__failed_reason "
        "CHECK (failed_reason IN ('osrm_unavailable', 'db_unavailable', 'build_error'))"
    )
