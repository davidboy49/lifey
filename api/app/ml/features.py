"""The ONE place features are defined.

Imported by the training notebooks and by the nightly job, so a feature can never
mean one thing in training and another in production (training-serving skew).

Rules baked in here:
- Dates are calendar dates in Asia/Phnom_Penh; sleep is already filed under the
  wake-up date by ingestion.
- Every calendar day in the range gets a row. A day with no sync is a row of NaN,
  never dropped and never filled.
- A baseline for day D uses only days before D (no leakage of the day itself).
- Nothing is imputed. Missing stays NaN and carries a `<metric>_missing` flag.

Add new features as small pure functions and call them from `build`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

BASELINE_WINDOW = 28      # calendar days
MIN_BASELINE_DAYS = 14    # real readings required before a baseline is trusted
FLAG_Z = 1.5
REL_SD_FLOOR = 0.02       # same idea as readiness.spread: a flat history never yields a huge z


@dataclass(frozen=True)
class Metric:
    key: str                  # name in features
    column: str               # column in health.daily_metrics
    label: str
    unit: str
    higher_is_better: bool
    scale: float = 1.0        # divide the stored value by this (seconds -> hours)


METRICS: tuple[Metric, ...] = (
    Metric("sleep_hours", "sleep_duration", "Sleep", "h", True, 3600.0),
    Metric("sleep_score", "sleep_score", "Sleep score", "/100", True),
    Metric("hrv", "hrv_last_night", "HRV", "ms", True),
    Metric("resting_hr", "resting_hr", "Resting HR", "bpm", False),
    Metric("bb_max", "bb_max", "Body Battery high", "/100", True),
    Metric("stress_avg", "stress_avg", "Stress", "/100", False),
)
BY_KEY = {m.key: m for m in METRICS}


def load_daily(conn, start: date, end: date) -> pd.DataFrame:
    """Raw daily metrics over [start, end] on a complete calendar index."""
    columns = ", ".join(f"{m.column} AS {m.key}" for m in METRICS)
    rows = conn.execute(
        f"SELECT date, {columns} FROM health.daily_metrics WHERE date BETWEEN %s AND %s ORDER BY date",
        (start, end)).fetchall()
    frame = pd.DataFrame(rows, columns=["date", *[m.key for m in METRICS]])
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("date")
    index = pd.date_range(start, end, freq="D", name="date")
    present = frame.index
    frame = frame.reindex(index)
    frame["row_present"] = frame.index.isin(present)
    for m in METRICS:
        frame[m.key] = pd.to_numeric(frame[m.key], errors="coerce").astype(float) / m.scale
    return frame


def baseline_features(frame: pd.DataFrame, metric: Metric) -> pd.DataFrame:
    """value, trailing baseline (excluding the day), spread, z, and missing flag."""
    value = frame[metric.key]
    prior = value.shift(1).rolling(BASELINE_WINDOW, min_periods=MIN_BASELINE_DAYS)
    mean, sd = prior.mean(), prior.std(ddof=0)
    n = value.shift(1).rolling(BASELINE_WINDOW, min_periods=1).count()
    spread = pd.concat([sd.fillna(0.0), mean.abs() * REL_SD_FLOOR], axis=1).max(axis=1).clip(lower=1e-6)
    z = (value - mean) / spread
    return pd.DataFrame({
        metric.key: value,
        f"{metric.key}_missing": value.isna(),
        f"{metric.key}_baseline": mean,
        f"{metric.key}_sd": spread.where(mean.notna()),
        f"{metric.key}_baseline_n": n.fillna(0).astype(int),
        f"{metric.key}_z": z,
    }, index=frame.index)


def build(frame: pd.DataFrame) -> pd.DataFrame:
    """Feature matrix, one row per calendar day. Pure: no I/O."""
    parts = [frame[["row_present"]]] + [baseline_features(frame, m) for m in METRICS]
    out = pd.concat(parts, axis=1)
    out["n_metrics_present"] = sum((~out[f"{m.key}_missing"]).astype(int) for m in METRICS)
    return out


def feature_frame(conn, end: date, days: int = 60) -> pd.DataFrame:
    """Load enough history for baselines, then build. `days` is the span returned."""
    start = end - timedelta(days=days - 1 + BASELINE_WINDOW)
    return build(load_daily(conn, start, end)).iloc[BASELINE_WINDOW:]
