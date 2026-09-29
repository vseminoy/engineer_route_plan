"""engineer sets

Revision ID: 1b0ce84eb128
Revises: c124884e0c63
Create Date: 2026-09-28 11:36:39.525722

A region can hold several sets of brigades: the `default` set (kind `demo`), which the
region's first data load creates and keeps updating, and any number of `generated` sets a
user creates with their own generator parameters. `engineers.engineer_set_id` and
`plans.engineer_set_id` move brigades and plans from being scoped by region alone to being
scoped by one set of the region. `engineers.region_id` is dropped: a brigade's region is
its set's region (`engineer_sets.region_id`), and nothing reads a brigade by region_id
directly any more. `plans.region_id` stays — a plan's tickets are still looked up by
region, independently of which set built the plan.

Existing regions have no `engineer_sets` row yet, so this migration backfills one `default`
set per region from `data/regions.toml` (the same file the generator itself reads), by
region code — the parameters the region's brigades were actually generated with, since that
file has not changed since. A region no longer in that file falls back to its current
brigade count and a seed of its own code, with both shift shares 0 — display-only values
for a region that cannot be regenerated with them again anyway.
"""

import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1b0ce84eb128"
down_revision: str | Sequence[str] | None = "c124884e0c63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = """
CREATE TABLE engineer_sets (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    region_id      BIGINT NOT NULL REFERENCES regions (id),
    name           TEXT NOT NULL,
    kind           TEXT NOT NULL,
    engineers      INTEGER NOT NULL,
    morning_share  DOUBLE PRECISION NOT NULL,
    evening_share  DOUBLE PRECISION NOT NULL,
    seed           TEXT NOT NULL,
    CONSTRAINT ux_engineer_sets__region_id_name UNIQUE (region_id, name),
    CONSTRAINT ck_engineer_sets__kind CHECK (kind IN ('demo', 'generated')),
    CONSTRAINT ck_engineer_sets__engineers CHECK (engineers BETWEEN 1 AND 30),
    CONSTRAINT ck_engineer_sets__morning_share
        CHECK (morning_share >= 0 AND morning_share <= 1),
    CONSTRAINT ck_engineer_sets__evening_share
        CHECK (evening_share >= 0 AND evening_share <= 1),
    CONSTRAINT ck_engineer_sets__seed CHECK (char_length(seed) BETWEEN 1 AND 50)
);

CREATE INDEX ix_engineer_sets__region_id ON engineer_sets (region_id);

COMMENT ON TABLE engineer_sets IS
    'Набор бригад региона: одна запись — один набор, демо (default) или дополнительный';
COMMENT ON COLUMN engineer_sets.region_id IS
    'Регион набора; у региона один демо-набор и любое число дополнительных';
COMMENT ON COLUMN engineer_sets.name IS
    'Название набора, уникальное в регионе; у демо-набора всегда default';
COMMENT ON COLUMN engineer_sets.kind IS
    'demo — набор default, ведётся загрузкой данных региона и не удаляется; generated — создан пользователем';
COMMENT ON COLUMN engineer_sets.engineers IS 'Число бригад набора — параметр генератора';
COMMENT ON COLUMN engineer_sets.morning_share IS
    'Доля бригад набора на утренней смене (округляется вниз при генерации)';
COMMENT ON COLUMN engineer_sets.evening_share IS
    'Доля бригад набора на вечерней смене (округляется вниз при генерации)';
COMMENT ON COLUMN engineer_sets.seed IS
    'Зерно генератора набора; те же seed и остальные параметры всегда дают тот же состав бригад';

GRANT SELECT, INSERT, UPDATE, DELETE ON engineer_sets TO app_rw;
GRANT SELECT ON engineer_sets TO app_ro;
"""


def _default_set_params(conn: Any) -> list[dict[str, Any]]:
    """One row per existing region: its `default` set's generator parameters, from
    `data/regions.toml` by region code where the region is still there, otherwise from
    its currently stored brigades (see the module docstring)."""
    config_path = Path(__file__).resolve().parents[2] / "data" / "regions.toml"
    with config_path.open("rb") as f:
        config = tomllib.load(f)
    regions_cfg = config.get("regions", {})
    shifts_cfg = config.get("shifts", {})
    morning_share = shifts_cfg.get("morning", {}).get("share")
    evening_share = shifts_cfg.get("evening", {}).get("share")

    rows = []
    for region_id, code in conn.execute(sa.text("SELECT id, code FROM regions")).fetchall():
        region_cfg = regions_cfg.get(code)
        if region_cfg is not None and morning_share is not None and evening_share is not None:
            rows.append(
                {
                    "region_id": region_id,
                    "engineers": region_cfg["engineers"],
                    "morning_share": morning_share,
                    "evening_share": evening_share,
                    "seed": code,
                }
            )
        else:
            count = conn.execute(
                sa.text("SELECT count(*) FROM engineers WHERE region_id = :region_id"),
                {"region_id": region_id},
            ).scalar_one()
            rows.append(
                {
                    "region_id": region_id,
                    "engineers": max(count, 1),
                    "morning_share": 0.0,
                    "evening_share": 0.0,
                    "seed": code,
                }
            )
    return rows


def upgrade() -> None:
    op.execute(SCHEMA)

    conn = op.get_bind()
    for row in _default_set_params(conn):
        conn.execute(
            sa.text(
                "INSERT INTO engineer_sets"
                " (region_id, name, kind, engineers, morning_share, evening_share, seed)"
                " VALUES"
                " (:region_id, 'default', 'demo', :engineers, :morning_share, :evening_share, :seed)"
            ),
            row,
        )

    op.execute(
        "ALTER TABLE engineers ADD COLUMN engineer_set_id BIGINT REFERENCES engineer_sets (id)"
    )
    op.execute(
        "UPDATE engineers SET engineer_set_id = engineer_sets.id"
        " FROM engineer_sets"
        " WHERE engineer_sets.region_id = engineers.region_id AND engineer_sets.kind = 'demo'"
    )
    op.execute("ALTER TABLE engineers ALTER COLUMN engineer_set_id SET NOT NULL")
    op.execute("DROP INDEX ix_engineers__region_id")
    op.execute("ALTER TABLE engineers DROP COLUMN region_id")
    op.execute("CREATE INDEX ix_engineers__engineer_set_id ON engineers (engineer_set_id)")
    op.execute(
        "COMMENT ON COLUMN engineers.engineer_set_id IS"
        " 'Набор бригад, к которому относится бригада; заявки берёт региона этого набора'"
    )

    op.execute("ALTER TABLE plans ADD COLUMN engineer_set_id BIGINT REFERENCES engineer_sets (id)")
    op.execute(
        "UPDATE plans SET engineer_set_id = engineer_sets.id"
        " FROM engineer_sets"
        " WHERE engineer_sets.region_id = plans.region_id AND engineer_sets.kind = 'demo'"
    )
    op.execute("ALTER TABLE plans ALTER COLUMN engineer_set_id SET NOT NULL")
    op.execute("CREATE INDEX ix_plans__engineer_set_id ON plans (engineer_set_id)")
    op.execute(
        "COMMENT ON COLUMN plans.engineer_set_id IS"
        " 'Набор бригад, для которого построен план; не меняется, в т.ч. при перепланировании'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE plans DROP COLUMN engineer_set_id")

    op.execute("ALTER TABLE engineers ADD COLUMN region_id BIGINT REFERENCES regions (id)")
    op.execute(
        "UPDATE engineers SET region_id = engineer_sets.region_id"
        " FROM engineer_sets"
        " WHERE engineer_sets.id = engineers.engineer_set_id"
    )
    op.execute("ALTER TABLE engineers ALTER COLUMN region_id SET NOT NULL")
    op.execute("CREATE INDEX ix_engineers__region_id ON engineers (region_id)")
    op.execute("ALTER TABLE engineers DROP COLUMN engineer_set_id")

    op.execute("DROP TABLE engineer_sets")
