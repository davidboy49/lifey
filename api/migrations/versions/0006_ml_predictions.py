"""ML predictions, model registry, weekly accuracy

Revision ID: 0006
Revises: 0005

Every prediction is stored next to the value that actually happened (filled in later,
NULL until then, never 0). Baselines are first-class "models" (naive, mean7) so the
accuracy report always has something to compare a real model against.
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

SQL = """
CREATE TABLE ml.predictions (
    made_on           DATE NOT NULL,       -- the day the prediction was produced (Asia/Phnom_Penh)
    target_date       DATE NOT NULL,       -- the day the predicted value belongs to
    metric            TEXT NOT NULL,       -- features key, e.g. sleep_hours
    horizon_days      INTEGER NOT NULL,
    model_name        TEXT NOT NULL,       -- naive | mean7 | lightgbm | timesfm
    model_version     TEXT NOT NULL,       -- YYYY-MM-DD of the artifact, or v1 for baselines
    y_hat             DOUBLE PRECISION NOT NULL,
    lo                DOUBLE PRECISION,
    hi                DOUBLE PRECISION,
    naive_pred        DOUBLE PRECISION,    -- "tomorrow = today" for the same row
    mean7_pred        DOUBLE PRECISION,
    actual            DOUBLE PRECISION,
    actual_filled_at  TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (made_on, metric, horizon_days, model_name, model_version)
);
CREATE INDEX predictions_target_idx ON ml.predictions (target_date);

CREATE TABLE ml.model_registry (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_name        TEXT NOT NULL,
    model_version     TEXT NOT NULL,
    kind              TEXT NOT NULL,
    target            TEXT NOT NULL,
    horizon_days      INTEGER NOT NULL,
    path              TEXT,
    trained_through   DATE,
    cv_mae            DOUBLE PRECISION,
    last30_mae        DOUBLE PRECISION,
    naive_last30_mae  DOUBLE PRECISION,
    status            TEXT NOT NULL CHECK (status IN ('candidate','promoted','retired','rejected')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    promoted_at       TIMESTAMPTZ,
    UNIQUE (model_name, model_version)
);

CREATE TABLE ml.accuracy_weekly (
    week_start     DATE NOT NULL,
    metric         TEXT NOT NULL,
    model_name     TEXT NOT NULL,
    model_version  TEXT NOT NULL,
    n              INTEGER NOT NULL,
    mae            DOUBLE PRECISION,
    naive_mae      DOUBLE PRECISION,
    mean7_mae      DOUBLE PRECISION,
    skill          DOUBLE PRECISION,
    computed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (week_start, metric, model_name, model_version)
);
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute("DROP TABLE ml.accuracy_weekly, ml.model_registry, ml.predictions")
