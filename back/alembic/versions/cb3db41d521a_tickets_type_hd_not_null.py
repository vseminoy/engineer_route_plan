"""tickets type_hd not null

Revision ID: cb3db41d521a
Revises: 5d23f2956ce7
Create Date: 2026-09-25 09:57:33.889173

Every ticket has a type HD: it decides the ticket's skill, priority and time on site, and
the loader rejects a row without it. The column holds no NULL, so the constraint applies
to existing rows as they are, and the running application writes the column already.
A NULL left by a write outside the application fails the upgrade instead of being filled
with an invented type.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cb3db41d521a"
down_revision: str | Sequence[str] | None = "5d23f2956ce7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE tickets ALTER COLUMN type_hd SET NOT NULL")
    op.execute(
        "COMMENT ON COLUMN tickets.type_hd IS 'Тип заявки HD из входного файла как есть; "
        "обязателен: по нему определяются навык, приоритет и время работы на объекте'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tickets ALTER COLUMN type_hd DROP NOT NULL")
    op.execute(
        "COMMENT ON COLUMN tickets.type_hd IS 'Тип заявки HD из входного файла как есть; "
        "NULL — поле пусто'"
    )
