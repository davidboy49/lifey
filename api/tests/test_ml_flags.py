"""Baselines, flags, crash nights and the templated briefing, on a real PostgreSQL."""
from datetime import date, timedelta

import pytest

from app.ml import briefing, features, flags

END = date(2026, 9, 30)


def put(conn, day, *, sleep_h=None, score=None, hrv=None, rhr=None, bb=None, stress=None):
    conn.execute(
        """INSERT INTO health.daily_metrics (date, sleep_duration, sleep_score, hrv_last_night,
                                              resting_hr, bb_max, stress_avg)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (day, None if sleep_h is None else round(sleep_h * 3600), score, hrv, rhr, bb, stress))


def seed(conn, days=40, *, skip=(), last=None):
    """`days` of mildly varying history ending the day before END; `last` overrides END itself."""
    for i in range(days):
        day = END - timedelta(days=days - i)
        if day in skip:
            continue
        wobble = (i % 2) * 0.4
        put(conn, day, sleep_h=7.0 + wobble, score=75 + (i % 2) * 4, hrv=50 + (i % 2) * 4,
            rhr=55 + (i % 2), bb=80 + (i % 2) * 2, stress=30 + (i % 2) * 2)
    if last is not None:
        put(conn, END, **last)
    conn.commit()


def frame(conn):
    return features.feature_frame(conn, END, days=7)


def test_every_calendar_day_gets_a_row_and_gaps_stay_missing(pg):
    gap = END - timedelta(days=3)
    seed(pg, skip={gap}, last=dict(sleep_h=7.2, score=77, hrv=52, rhr=55, bb=81, stress=31))
    f = frame(pg)
    assert len(f) == 7 and f.index[-1].date() == END
    row = f.loc[gap.isoformat()]
    assert not row["row_present"] and row["hrv_missing"] and row["sleep_hours"] != row["sleep_hours"]  # NaN


def test_sleep_is_converted_to_hours_and_baseline_excludes_the_day(pg):
    seed(pg, last=dict(sleep_h=4.0, score=40, hrv=30, rhr=60, bb=50, stress=60))
    row = frame(pg).loc[END.isoformat()]
    assert row["sleep_hours"] == pytest.approx(4.0)
    assert 6.9 < row["sleep_hours_baseline"] < 7.5   # unaffected by the 4 h night itself
    assert row["sleep_hours_z"] < -1.5


def test_short_history_is_flagged_not_guessed(pg):
    seed(pg, days=10, last=dict(sleep_h=4.0, score=40, hrv=30, rhr=60, bb=50, stress=60))
    out, crash = flags.compute_day(frame(pg), END)
    assert {f["flag"] for f in out} == {"insufficient_baseline"}
    assert crash["crash"] is False


def test_crash_night_when_hrv_and_sleep_fall(pg):
    seed(pg, last=dict(sleep_h=4.5, score=50, hrv=30, rhr=60, bb=40, stress=50))
    out, crash = flags.compute_day(frame(pg), END)
    assert crash["crash"] and set(crash["reasons"]) >= {"hrv", "sleep_hours"}
    assert {f["metric"]: f["flag"] for f in out}["hrv"] == "low"


def test_one_signal_alone_is_not_a_crash(pg):
    # HRV far down but sleep normal: flagged low, not a crash night.
    seed(pg, last=dict(sleep_h=7.2, score=77, hrv=30, rhr=55, bb=81, stress=31))
    out, crash = flags.compute_day(frame(pg), END)
    assert {f["metric"]: f["flag"] for f in out}["hrv"] == "low" and crash["crash"] is False
    pg.execute("DELETE FROM health.daily_metrics WHERE date=%s", (END,))
    # Sleep far down but HRV normal: also not a crash night.
    put(pg, END, sleep_h=4.0, score=40, hrv=52, rhr=55, bb=81, stress=31)
    pg.commit()
    assert flags.compute_day(frame(pg), END)[1]["crash"] is False


def test_normal_night_is_not_a_crash(pg):
    seed(pg, last=dict(sleep_h=7.2, score=77, hrv=52, rhr=55, bb=81, stress=31))
    _, crash = flags.compute_day(frame(pg), END)
    assert crash == {"date": END, "crash": False, "reasons": []}


def test_refresh_is_idempotent_and_persists(pg):
    seed(pg, last=dict(sleep_h=4.5, score=50, hrv=30, rhr=60, bb=40, stress=50))
    flags.refresh(pg, end=END, days=7)
    flags.refresh(pg, end=END, days=7)
    n = pg.execute("SELECT count(*) FROM ml.daily_flags").fetchone()[0]
    assert n == 7 * len(features.METRICS)
    assert pg.execute("SELECT crash FROM ml.crash_nights WHERE date=%s", (END,)).fetchone()[0] is True
    assert pg.execute("SELECT count(*) FROM ml.daily_flags WHERE value = 0").fetchone()[0] == 0


def _check_shape(text):
    lines = text.splitlines()
    assert len(lines) <= 4
    assert sum(l.startswith("Action:") for l in lines) == 1 and lines[-1].startswith("Action:")
    assert "!" not in text and text.isascii()


def test_briefing_normal_day(pg):
    seed(pg, last=dict(sleep_h=7.2, score=77, hrv=52, rhr=55, bb=81, stress=31))
    text = briefing.build(pg, END)
    _check_shape(text)
    assert "normal range" in text and "usual" in text


def test_briefing_crash_day_names_a_number(pg):
    seed(pg, last=dict(sleep_h=4.5, score=50, hrv=30, rhr=60, bb=40, stress=50))
    text = briefing.build(pg, END)
    _check_shape(text)
    assert "Crash night" in text and "h tonight" in text


def test_briefing_says_so_when_there_is_no_data(pg):
    seed(pg)   # nothing recorded for END
    text = briefing.build(pg, END)
    _check_shape(text)
    assert "No sleep" in text and "sync" in text


def test_send_refuses_without_token(monkeypatch):
    monkeypatch.delenv("AGENT_BOT_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        briefing.send("x")
