"""Statistical flags and the crash-night rule (Phase 2: no ML).

    python -m app.ml.flags [--days 7]

A flag says only that a reading is far from the person's own recent baseline.
It never says why and never diagnoses.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date

import pandas as pd
from psycopg.types.json import Jsonb

from .. import db
from ..health import quality
from . import features
from .features import FLAG_Z, METRICS, MIN_BASELINE_DAYS

VERSION = "z28-v2"
# Crash night = HRV is HRV_CRASH_Z below its own baseline AND sleep corroborates (either
# sleep metric SLEEP_CORROBORATE_Z below its baseline). Tuned on 92 trusted days of real
# history: the looser "any one metric" rule fired on ~22% of nights (~6.5/month), this one
# on ~11% (~3.3/month) and every hit has both signals.
HRV_CRASH_Z = 1.5
SLEEP_CORROBORATE_Z = 1.0
SLEEP_METRICS = ("sleep_score", "sleep_hours")


def _num(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) or pd.isna(x) else float(x)


def classify(value, z, baseline_n) -> str:
    if value is None:
        return "no_data"
    if baseline_n < MIN_BASELINE_DAYS or z is None:
        return "insufficient_baseline"
    return "low" if z <= -FLAG_Z else "high" if z >= FLAG_Z else "normal"


def compute_day(frame: pd.DataFrame, day: date) -> tuple[list[dict], dict]:
    """Flag rows for every metric plus the crash-night verdict for one date."""
    row = frame.loc[pd.Timestamp(day)]
    flags = []
    for m in METRICS:
        value, z, n = _num(row[m.key]), _num(row[f"{m.key}_z"]), int(row[f"{m.key}_baseline_n"])
        flags.append({
            "date": day, "metric": m.key, "flag": classify(value, z, n), "baseline_days": n,
            "value": value, "z": z,
            "baseline": _num(row[f"{m.key}_baseline"]), "sd": _num(row[f"{m.key}_sd"]),
        })
    z = {f["metric"]: f["z"] for f in flags if f["flag"] != "insufficient_baseline"}
    hrv_low = z.get("hrv") is not None and z["hrv"] <= -HRV_CRASH_Z
    sleep_low = [k for k in SLEEP_METRICS if z.get(k) is not None and z[k] <= -SLEEP_CORROBORATE_Z]
    reasons = ["hrv", *sleep_low] if hrv_low and sleep_low else []
    return flags, {"date": day, "crash": bool(reasons), "reasons": reasons}


def save(conn, flags: list[dict], crash: dict) -> None:
    for f in flags:
        conn.execute(
            """INSERT INTO ml.daily_flags (date, metric, value, baseline, sd, z, flag, baseline_days, algorithm_version)
               VALUES (%(date)s,%(metric)s,%(value)s,%(baseline)s,%(sd)s,%(z)s,%(flag)s,%(baseline_days)s,%(v)s)
               ON CONFLICT (date, metric, algorithm_version) DO UPDATE SET
                 value=excluded.value, baseline=excluded.baseline, sd=excluded.sd, z=excluded.z,
                 flag=excluded.flag, baseline_days=excluded.baseline_days, computed_at=NOW()""",
            {**f, "v": VERSION})
    conn.execute(
        """INSERT INTO ml.crash_nights (date, crash, reasons, algorithm_version) VALUES (%s,%s,%s,%s)
           ON CONFLICT (date, algorithm_version) DO UPDATE SET
             crash=excluded.crash, reasons=excluded.reasons, computed_at=NOW()""",
        (crash["date"], crash["crash"], Jsonb(crash["reasons"]), VERSION))


def refresh(conn, end: date | None = None, days: int = 7) -> list[tuple[list[dict], dict]]:
    """Recompute flags for the last `days` dates and persist them. Idempotent."""
    end = end or quality.today()
    frame = features.feature_frame(conn, end, days=days)
    results = []
    for ts in frame.index:
        flags, crash = compute_day(frame, ts.date())
        save(conn, flags, crash)
        results.append((flags, crash))
    conn.commit()
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args(argv)
    with db.connect() as conn:
        results = refresh(conn, days=args.days)
    print(json.dumps([{"date": c["date"].isoformat(), "crash": c["crash"], "reasons": c["reasons"]}
                      for _, c in results], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
