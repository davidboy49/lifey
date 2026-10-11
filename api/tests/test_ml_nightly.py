"""Nightly predictions, actuals, accuracy report and the promotion gate, on real PostgreSQL."""
from datetime import date, timedelta

import pytest

from app.ml import nightly, registry, report

D = date(2026, 9, 30)


class Plus1:                       # stand-in for a fitted estimator (module level so it can be pickled)
    def predict(self, x):
        return [float(x["sleep_hours"].iloc[0]) + 1.0]


def put(conn, day, sleep_h):
    conn.execute("INSERT INTO health.daily_metrics (date, sleep_duration, hrv_last_night) VALUES (%s,%s,%s)",
                 (day, None if sleep_h is None else round(sleep_h * 3600), 50))


def seed(conn, through=D, days=20, value=lambda i: 7.0 + (i % 3) * 0.5):
    for i in range(days):
        put(conn, through - timedelta(days=days - 1 - i), value(i))
    conn.commit()


def preds(conn):
    return conn.execute(
        "SELECT model_name, y_hat, naive_pred, mean7_pred, actual, target_date FROM ml.predictions "
        "ORDER BY made_on, model_name").fetchall()


def test_baselines_are_logged_for_tomorrow(pg):
    seed(pg)
    out = nightly.run(pg, D)
    assert out["target_date"] == "2026-10-01"
    rows = {r[0]: r for r in preds(pg)}
    assert set(rows) == {"naive", "mean7"}
    last = 7.0 + ((20 - 1) % 3) * 0.5
    assert rows["naive"][1] == pytest.approx(last)
    assert rows["naive"][4] is None                       # actual not known yet, and not 0


def test_no_reading_means_no_prediction(pg):
    seed(pg, through=D - timedelta(days=1))               # nothing recorded for D itself
    nightly.run(pg, D)
    assert preds(pg) == []


def test_actuals_are_filled_when_they_arrive_and_never_as_zero(pg):
    seed(pg)
    nightly.run(pg, D)                                    # predicts 10-01
    assert nightly.fill_actuals(pg, D + timedelta(days=1)) == 0     # no 10-01 row yet
    put(pg, D + timedelta(days=1), None)                  # row exists, sleep not recorded
    pg.commit()
    assert nightly.fill_actuals(pg, D + timedelta(days=1)) == 0
    pg.execute("UPDATE health.daily_metrics SET sleep_duration = %s WHERE date = %s",
               (6 * 3600, D + timedelta(days=1)))
    pg.commit()
    assert nightly.fill_actuals(pg, D + timedelta(days=1)) == 2     # naive + mean7
    assert {r[4] for r in preds(pg)} == {6.0}


def test_rerun_is_idempotent_and_does_not_rewrite_scored_rows(pg):
    seed(pg)
    nightly.run(pg, D)
    pg.execute("UPDATE ml.predictions SET actual = 6.0")
    pg.commit()
    before = preds(pg)
    nightly.run(pg, D)
    assert preds(pg) == before and len(before) == 2


def test_weekly_report_scores_models_against_naive(pg):
    seed(pg, days=40, value=lambda i: 7.0 + (i % 2))      # alternating 7 / 8: naive is always 1 h off
    for k in range(12):
        nightly.run(pg, D - timedelta(days=11 - k))
    nightly.fill_actuals(pg, D)
    text = report.build(pg, D)
    assert "Forecast accuracy" in text and "naive" in text and "mean7" in text and "!" not in text
    scores = {s["model_name"]: s for s in report.window_scores(pg, D, 30)}
    assert scores["naive"]["n"] > 0 and scores["naive"]["mae"] == pytest.approx(1.0)
    assert scores["mean7"]["mae"] < scores["naive"]["mae"]
    assert scores["mean7"]["skill"] > 0 and scores["naive"]["skill"] == pytest.approx(0.0)
    assert pg.execute("SELECT count(*) FROM ml.accuracy_weekly").fetchone()[0] == 2


def test_report_with_no_scored_rows_says_so(pg):
    assert "no scored predictions yet" in report.build(pg, D)


def test_promotion_gate():
    ok = {"mae": 0.6, "n": 25, "naive_mae": 0.9}
    assert report.should_promote(ok, None)                                      # beats naive, enough days
    assert not report.should_promote({**ok, "n": 10}, None)                    # too few scored days
    assert not report.should_promote({**ok, "mae": 1.0}, None)                 # worse than naive
    assert report.should_promote(ok, {"mae": 0.7, "n": 25})
    assert not report.should_promote(ok, {"mae": 0.6, "n": 25})                # a tie is not a win
    assert not report.should_promote(None, None)


def test_registry_promote_retires_the_previous_and_prunes_files(pg, tmp_path):
    for v in ("2026-09-01", "2026-10-01"):
        registry.register(pg, model_name="lightgbm", model_version=v, kind="lightgbm",
                          target="sleep_hours", horizon_days=1, path=f"/x/{v}.joblib")
    registry.promote(pg, "lightgbm", "2026-09-01")
    registry.promote(pg, "lightgbm", "2026-10-01")
    status = dict(pg.execute("SELECT model_version, status FROM ml.model_registry").fetchall())
    assert status == {"2026-09-01": "retired", "2026-10-01": "promoted"}

    for d in ("2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01"):
        (tmp_path / f"sleep_hours_h1_{d}.joblib").write_text("x")
    (tmp_path / "other_h1_2026-01-01.joblib").write_text("x")
    removed = registry.prune_files(tmp_path, "sleep_hours_h1", keep=3)
    assert [p.name for p in removed] == ["sleep_hours_h1_2026-07-01.joblib"]
    assert (tmp_path / "other_h1_2026-01-01.joblib").exists()


def test_promoted_artifact_is_used(pg, tmp_path):
    joblib = pytest.importorskip("joblib")

    path = tmp_path / "sleep_hours_h1_2026-09-29.joblib"
    joblib.dump({"model": Plus1(), "feature_names": ["sleep_hours"]}, path)
    seed(pg)
    registry.register(pg, model_name="stub", model_version="2026-09-29", kind="lightgbm",
                      target="sleep_hours", horizon_days=1, path=str(path))
    registry.promote(pg, "stub", "2026-09-29")
    pg.commit()
    nightly.run(pg, D)
    got = {r[0]: r[1] for r in preds(pg)}
    assert got["stub"] == pytest.approx(got["naive"] + 1.0)
