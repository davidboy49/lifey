"""Nightly job: log predictions, then fill in the actuals that have arrived.

    python -m app.ml.nightly [--date YYYY-MM-DD]

Runs after the morning Garmin sync. Always writes the two baselines (naive, mean7)
so accuracy history accumulates from day one, and also the promoted model when the
registry has one. A day with no reading produces no prediction, never a guess.

Definition of `mean7` here (production comparison only; your notebook may choose differently):
mean of the last 7 calendar days, needing at least 4 real readings.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, timedelta

import pandas as pd

from .. import db
from ..health import quality
from . import features
from .features import BY_KEY

TARGET = "sleep_hours"
HORIZON = 1
MEAN7_WINDOW, MEAN7_MIN = 7, 4


def _num(x):
    return None if x is None or pd.isna(x) else float(x)


def baseline_predictions(frame: pd.DataFrame, made_on: date, metric: str = TARGET) -> list[dict]:
    """naive and mean7 for `made_on` + horizon. Pure."""
    ts = pd.Timestamp(made_on)
    if ts not in frame.index:
        return []
    series = features.clean(frame, metric)   # partial recordings are not readings
    naive = _num(series.loc[ts])
    if naive is None:
        return []   # no (usable) reading today: no predictions, so every model is scored on the same rows
    mean7 = _num(series.rolling(MEAN7_WINDOW, min_periods=MEAN7_MIN).mean().loc[ts])
    rows = []
    for name, value in (("naive", naive), ("mean7", mean7)):
        if value is None:
            continue
        rows.append({"model_name": name, "model_version": "v1", "y_hat": value, "lo": None, "hi": None})
    for r in rows:
        r.update(naive_pred=naive, mean7_pred=mean7)
    return rows


def model_predictions(conn, frame: pd.DataFrame, made_on: date) -> list[dict]:
    """Predictions from the promoted registry artifact, if any. Imports joblib lazily."""
    row = conn.execute(
        """SELECT model_name, model_version, path FROM ml.model_registry
           WHERE status='promoted' AND target=%s AND horizon_days=%s ORDER BY promoted_at DESC LIMIT 1""",
        (TARGET, HORIZON)).fetchone()
    if row is None or not row[2]:
        return []
    import joblib  # noqa: PLC0415 - only needed once a model exists

    name, version, path = row
    artifact = joblib.load(path)
    if artifact.get("model") is None:
        return []
    built = features.build(frame)
    ts = pd.Timestamp(made_on)
    x = built.loc[[ts], artifact["feature_names"]]
    y_hat = float(artifact["model"].predict(x)[0])
    if math.isnan(y_hat):
        return []
    return [{"model_name": name, "model_version": version, "y_hat": y_hat, "lo": None, "hi": None}]


def save_predictions(conn, made_on: date, rows: list[dict], naive, mean7) -> None:
    for r in rows:
        conn.execute(
            """INSERT INTO ml.predictions (made_on, target_date, metric, horizon_days, model_name,
                   model_version, y_hat, lo, hi, naive_pred, mean7_pred)
               VALUES (%(made_on)s,%(target)s,%(metric)s,%(h)s,%(model_name)s,%(model_version)s,
                       %(y_hat)s,%(lo)s,%(hi)s,%(naive)s,%(mean7)s)
               ON CONFLICT (made_on, metric, horizon_days, model_name, model_version) DO UPDATE SET
                   y_hat=excluded.y_hat, lo=excluded.lo, hi=excluded.hi,
                   naive_pred=excluded.naive_pred, mean7_pred=excluded.mean7_pred
                   WHERE ml.predictions.actual IS NULL""",
            {**r, "made_on": made_on, "target": made_on + timedelta(days=HORIZON), "metric": TARGET,
             "h": HORIZON, "naive": naive, "mean7": mean7})


def fill_actuals(conn, today: date) -> int:
    """Copy realised values into ml.predictions. A missing reading stays NULL."""
    filled = 0
    metrics = [r[0] for r in conn.execute(
        "SELECT DISTINCT metric FROM ml.predictions WHERE actual IS NULL AND target_date <= %s", (today,))]
    for key in metrics:
        m = BY_KEY.get(key)
        if m is None:
            continue
        # A partial recording is not an outcome to score against: leave the actual NULL.
        # COALESCE: a NULL Body Battery or duration must read as "not partial", never as NULL.
        partial = (f" AND NOT (COALESCE(d.sleep_duration < {features.INCOMPLETE_SLEEP_H * 3600}, false) "
                   f"OR COALESCE(d.bb_max < {features.INCOMPLETE_BB_MAX}, false))"
                   ) if key in features.NIGHT_METRICS else ""
        cur = conn.execute(
            f"""UPDATE ml.predictions p SET actual = d.{m.column}::float / %s, actual_filled_at = NOW()
                FROM health.daily_metrics d
                WHERE p.metric = %s AND p.actual IS NULL AND d.date = p.target_date
                  AND d.{m.column} IS NOT NULL{partial}""", (m.scale, key))
        filled += cur.rowcount
    return filled


def run(conn, made_on: date | None = None) -> dict:
    made_on = made_on or quality.today()
    frame = features.feature_frame(conn, made_on, days=14)
    rows = baseline_predictions(frame, made_on)
    naive = next((r["y_hat"] for r in rows if r["model_name"] == "naive"), None)
    mean7 = next((r["y_hat"] for r in rows if r["model_name"] == "mean7"), None)
    rows += model_predictions(conn, frame, made_on) if rows else []
    save_predictions(conn, made_on, rows, naive, mean7)
    filled = fill_actuals(conn, made_on)
    conn.commit()
    return {"made_on": made_on.isoformat(), "target_date": (made_on + timedelta(days=HORIZON)).isoformat(),
            "predictions": [{k: r[k] for k in ("model_name", "model_version", "y_hat")} for r in rows],
            "actuals_filled": filled}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat)
    args = parser.parse_args(argv)
    with db.connect() as conn:
        print(json.dumps(run(conn, args.date), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
