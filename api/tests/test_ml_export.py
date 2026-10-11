"""Export format, metrics helpers."""
import math
from datetime import date

import numpy as np

from app.ml import evaluate, export, features


def test_export_round_trips_into_the_same_frame(pg, tmp_path, monkeypatch):
    for d, secs, hrv in (("2026-09-20", 25200, 50), ("2026-09-22", 21600, None)):  # 21st has no row
        pg.execute("INSERT INTO health.daily_metrics (date, sleep_duration, hrv_last_night) VALUES (%s,%s,%s)",
                   (d, secs, hrv))
    pg.commit()
    out = tmp_path / "d.csv"
    assert export.main([str(out)]) == 0
    frame = features.frame_from_csv(out)
    assert list(frame.index.strftime("%Y-%m-%d")) == ["2026-09-20", "2026-09-21", "2026-09-22"]
    assert frame["sleep_hours"].iloc[0] == 7.0
    assert math.isnan(frame["sleep_hours"].iloc[1]) and not frame["row_present"].iloc[1]
    assert math.isnan(frame["hrv"].iloc[2])          # NULL stays missing, not 0


def test_mae_ignores_missing_pairs_and_skill_sign():
    m, n = evaluate.mae([7, 6, np.nan, 5], [6, 6, 9, np.nan])
    assert (m, n) == (0.5, 2)
    assert evaluate.skill(0.5, 1.0) == 0.5
    assert evaluate.skill(1.5, 1.0) < 0
    assert math.isnan(evaluate.skill(1.0, 0.0))
    assert evaluate.mae([np.nan], [1.0])[1] == 0
