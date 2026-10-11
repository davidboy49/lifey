"""Sleep debt, regularity, outcomes and the suggestions built on them."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import sleep_report as sr
from app.auth import service
from app.bot import store
from app.health import quality
from app.health import store as health_store
from app.main import app

ORIGIN = {"Origin": "http://localhost:3000"}
T = 7.0


def night(i, hours, bed_min=None, wake_min=None, weekday=None, **extra):
    d = date(2026, 9, 1) + timedelta(days=i)
    return {"date": d.isoformat(), "weekday": d.weekday() if weekday is None else weekday, "hours": hours,
            "score": None, "hrv": None, "resting_hr": None, "steps": None, "stress": None, "bed": None, "wake": None,
            "bed_min": bed_min, "wake_min": wake_min, "awake_min": None, "garmin_need_next_h": None,
            "garmin_need_base_h": None, "garmin_need_feedback": None, **extra}


def test_missing_nights_are_unknown_not_zero_and_short_recordings_are_excluded():
    nights = [night(0, 6.0), night(1, None), night(2, 1.5), night(3, 7.5)]
    d = sr.debt(nights, target=T, window=4)
    assert d["hours"] == 1.0                      # only the 6.0 h night is short; None and 1.5 h do not count
    assert (d["nights_counted"], d["nights_missing"], d["nights_excluded"]) == (2, 1, 1)


def test_a_long_night_does_not_cancel_an_earlier_shortfall():
    d = sr.debt([night(0, 5.0), night(1, 9.0)], target=T, window=2)
    assert d["hours"] == 2.0 and d["nights_short"] == 1


def test_target_progress_reports_the_gap_and_the_trend_honestly():
    nights = [night(i, 6.0) for i in range(14)] + [night(14 + i, 6.6) for i in range(14)]
    p = sr.target_progress(nights, target=T)
    assert p["mean_h"] == 6.3 and p["gap_h"] == 0.7 and p["met"] is False
    assert p["earlier_mean_h"] == 6.0 and p["recent_mean_h"] == 6.6


def test_bedtimes_either_side_of_midnight_are_close_together():
    # 23:30 is 330 min after 18:00, 00:30 is 390: an hour apart, not 23 hours
    nights = [night(i, 7.0, bed_min=330 if i % 2 else 390, wake_min=420) for i in range(10)]
    r = sr.regularity(nights)
    assert r["enough"] and r["bed_sd_min"] == 30 and r["wake_sd_min"] == 0 and r["irregular"] is False
    assert r["usual_wake"] == "07:00"


def test_irregular_timing_is_flagged_and_too_few_nights_say_so():
    wobbly = [night(i, 7.0, bed_min=300 + (i % 2) * 180, wake_min=400 + (i % 2) * 180) for i in range(10)]
    assert sr.regularity(wobbly)["irregular"] is True
    assert sr.regularity(wobbly[:4]) == {"nights": 4, "enough": False}


def test_weekend_split_needs_enough_of_both():
    nights = [night(i, 6.0 if i % 7 < 5 else 8.5, weekday=i % 7) for i in range(28)]
    w = sr.weekend_split(nights)
    assert w["enough"] and w["difference_h"] == 2.5
    assert sr.weekend_split(nights[:8])["enough"] is False


def test_outcomes_compare_only_with_enough_nights_in_each_group():
    nights = [night(i, 6.0 if i < 10 else 7.5, hrv=40.0 if i < 10 else 55.0) for i in range(20)]
    rows = {r["label"]: r for r in sr.outcomes(nights, {}, set(), target=T)["rows"]}
    hrv = rows["HRV that night"]
    assert hrv["below"] == 40.0 and hrv["above"] == 55.0 and hrv["enough"] is True
    assert rows["Mood that day (1 to 5)"]["enough"] is False and rows["Mood that day (1 to 5)"]["below"] is None


def test_suggestions_are_tied_to_numbers_and_to_evidence():
    nights = [night(i, 6.0, bed_min=300, wake_min=420) for i in range(28)]
    progress, debt = sr.target_progress(nights, T), sr.debt(nights, T)
    reg = sr.regularity(nights)
    tips = {t["id"]: t for t in sr.suggestions(progress, debt, reg, {"enough": False}, None, [])}
    assert "close_gap" in tips and "60 minutes" in tips["close_gap"]["title"] or "minutes" in tips["close_gap"]["title"]
    assert "asleep by roughly" in tips["close_gap"]["detail"]
    assert tips["debt"]["evidence"] == ["vandongen2003", "depner2019"]
    assert all(e in sr.EVIDENCE for t in tips.values() for e in t["evidence"])


def test_nothing_to_suggest_when_the_target_is_met_and_timing_is_steady():
    nights = [night(i, 7.6, bed_min=300, wake_min=420) for i in range(28)]
    tips = sr.suggestions(sr.target_progress(nights, T), sr.debt(nights, T), sr.regularity(nights),
                          {"enough": False}, None, [])
    assert tips == []


def test_every_study_states_how_far_it_can_be_trusted():
    for key, ev in sr.EVIDENCE.items():
        assert ev["caveat"] and ev["confidence"] in {"strong", "moderate", "weak"} and ev["url"].startswith("https://"), key


# ---------- API ----------

@pytest.fixture
def client(pg, monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "0")
    monkeypatch.setenv("APP_ORIGINS", "http://localhost:3000")
    service.create_user(pg, "david", "correct horse battery")
    c = TestClient(app, headers=ORIGIN)
    assert c.post("/api/auth/login", json={"username": "david", "password": "correct horse battery"}).status_code == 200
    return c


def test_endpoint_reads_real_rows_and_keeps_gaps(client, pg):
    today = quality.today()
    for i in range(1, 21):
        if i == 5:
            continue                                # a night with no record at all
        d = today - timedelta(days=i)
        hours = 1.5 if i == 3 else 6.0              # one partly recorded night
        bed = f"{d - timedelta(days=1):%Y-%m-%d}T23:30:00"
        wake = f"{d:%Y-%m-%d}T06:30:00"
        ms = lambda s: int(__import__("datetime").datetime.fromisoformat(s).replace(
            tzinfo=__import__("datetime").timezone.utc).timestamp() * 1000)
        health_store.save_day(pg, d.isoformat(), {"sleep": {"dailySleepDTO": {
            "sleepTimeSeconds": int(hours * 3600), "sleepScores": {"overall": {"value": 70}},
            "sleepStartTimestampLocal": ms(bed), "sleepEndTimestampLocal": ms(wake),
            "nextSleepNeed": {"actual": 540, "baseline": 480, "feedback": "HIGHLY_INCREASED"}}}})
    pg.commit()
    body = client.get("/api/sleep").json()
    kinds = {n["date"]: n["kind"] for n in body["nights"]}
    assert kinds[(today - timedelta(days=5)).isoformat()] == "missing"
    assert kinds[(today - timedelta(days=3)).isoformat()] == "incomplete"
    assert body["debt"]["nights_excluded"] >= 1 and body["debt"]["nights_missing"] >= 1
    assert body["progress"]["mean_h"] == 6.0 and body["progress"]["gap_h"] == pytest.approx(body["target_h"] - 6.0)
    assert body["regularity"]["usual_wake"] == "06:30" and body["regularity"]["usual_bed"] == "23:30"
    assert body["garmin_need"]["hours"] == 9.0
    ids = {t["id"] for t in body["suggestions"]}
    assert {"close_gap", "garmin_need"} <= ids
    assert set(body["evidence_used"]) <= set(body["evidence"])


def test_endpoint_needs_a_session():
    assert TestClient(app).get("/api/sleep").status_code in (401, 503)
