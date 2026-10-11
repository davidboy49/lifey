"""Weekly accuracy report and the model promotion gate.

    python -m app.ml.report [--date YYYY-MM-DD] [--send]

Every model is scored on rows that have a real actual, against "tomorrow = today" and the
7-day mean on the same rows. Missing actuals are excluded and counted, never treated as 0.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from .. import db
from ..health import quality
from . import briefing
from .evaluate import skill

MIN_N_TO_PROMOTE = 20   # scored days required in the last-30 window before a model can be promoted


def window_scores(conn, end: date, days: int, metric: str = "sleep_hours") -> list[dict]:
    """Per (model_name, model_version): n, mae, and the naive / mean7 MAE on the same rows."""
    start = end - timedelta(days=days - 1)
    rows = conn.execute(
        """SELECT model_name, model_version, count(*) AS n,
                  avg(abs(actual - y_hat)) AS mae,
                  avg(abs(actual - naive_pred)) AS naive_mae,
                  avg(abs(actual - mean7_pred)) AS mean7_mae
           FROM ml.predictions
           WHERE metric = %s AND actual IS NOT NULL AND target_date BETWEEN %s AND %s
           GROUP BY model_name, model_version ORDER BY model_name, model_version""",
        (metric, start, end)).fetchall()
    out = []
    for name, version, n, mae, naive_mae, mean7_mae in rows:
        mae = None if mae is None else float(mae)
        naive_mae = None if naive_mae is None else float(naive_mae)
        out.append({"model_name": name, "model_version": version, "n": int(n), "mae": mae,
                    "naive_mae": naive_mae, "mean7_mae": None if mean7_mae is None else float(mean7_mae),
                    "skill": None if mae is None or not naive_mae else skill(mae, naive_mae)})
    return out


def save_weekly(conn, end: date, scores: list[dict], metric: str = "sleep_hours") -> None:
    week_start = end - timedelta(days=6)
    for s in scores:
        conn.execute(
            """INSERT INTO ml.accuracy_weekly (week_start, metric, model_name, model_version, n, mae,
                                               naive_mae, mean7_mae, skill)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (week_start, metric, model_name, model_version) DO UPDATE SET
                 n=excluded.n, mae=excluded.mae, naive_mae=excluded.naive_mae,
                 mean7_mae=excluded.mean7_mae, skill=excluded.skill, computed_at=NOW()""",
            (week_start, metric, s["model_name"], s["model_version"], s["n"], s["mae"],
             s["naive_mae"], s["mean7_mae"], s["skill"]))


def render(week: list[dict], month: list[dict], end: date) -> str:
    def fmt(scores):
        if not scores:
            return "no scored predictions yet"
        parts = []
        for s in scores:
            mae = "n/a" if s["mae"] is None else f"{s['mae']:.2f} h"
            sk = "" if s["skill"] is None or s["model_name"] == "naive" else f", skill {s['skill']:+.0%}"
            parts.append(f"{s['model_name']} {mae} (n={s['n']}{sk})")
        return "; ".join(parts)

    return "\n".join([
        f"Forecast accuracy, next-night sleep, to {end.isoformat()}.",
        "Last 7 days: " + fmt(week) + ".",
        "Last 30 days: " + fmt(month) + ".",
    ])


def should_promote(candidate: dict | None, incumbent: dict | None) -> bool:
    """Gate: enough scored days, and a lower MAE than the incumbent (or than naive if there is none)."""
    if candidate is None or candidate.get("mae") is None or candidate["n"] < MIN_N_TO_PROMOTE:
        return False
    if incumbent is not None and incumbent.get("mae") is not None:
        return candidate["mae"] < incumbent["mae"]
    naive = candidate.get("naive_mae")
    return naive is not None and candidate["mae"] < naive


def build(conn, end: date | None = None) -> str:
    end = end or quality.today()
    week, month = window_scores(conn, end, 7), window_scores(conn, end, 30)
    save_weekly(conn, end, week)
    conn.commit()
    return render(week, month, end)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args(argv)
    with db.connect() as conn:
        text = build(conn, args.date)
    print(text)
    if args.send:
        try:
            briefing.send(text)
        except Exception as exc:  # noqa: BLE001 - never echo the token
            print(f"Not sent: {type(exc).__name__}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
