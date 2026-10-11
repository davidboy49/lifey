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


# ---------- Walker's tips and the doctor panel ----------

from app import sleep_advice as adv


def _reg(irregular=False):
    return {"enough": True, "nights": 12, "wake_sd_min": 90 if irregular else 15, "bed_sd_min": 80 if irregular else 20,
            "usual_wake": "06:30", "usual_bed": "23:30", "irregular": irregular}


def _tips(habit_days=None, entry_days=12, reg=None, awake=None, training=2):
    return {t["id"]: t for t in adv.walker_tips(habit_days or {}, entry_days, reg or _reg(), awake, training)}


def test_all_twelve_tips_are_present_and_each_says_what_lifey_can_see():
    tips = adv.walker_tips({}, 12, _reg(), 38.0, 2)
    assert len(tips) == 12 and len({t["id"] for t in tips}) == 12
    assert {t["state"] for t in tips} <= {"look", "fine", "unknown", "not_measured", "info"}
    unseen = [t for t in tips if t["state"] == "not_measured"]
    assert {t["id"] for t in unseen} >= {"medicines", "wind_down", "bath", "light"}   # no data, and it says so


def test_a_habit_is_called_out_only_with_enough_days_logged():
    assert _tips({"late_caffeine": 4})["stimulants"]["state"] == "look"
    assert _tips({})["stimulants"]["state"] == "fine"
    assert _tips({"late_caffeine": 4}, entry_days=3)["stimulants"]["state"] == "unknown"    # silence is not "none"
    assert _tips({"alcohol": 1})["alcohol"]["state"] == "fine"


def test_irregular_timing_is_called_out_and_steady_timing_is_not():
    assert _tips(reg=_reg(True))["schedule"]["state"] == "look"
    assert _tips(reg=_reg(False))["schedule"]["state"] == "fine"
    assert _tips(reg={"enough": False, "nights": 3})["schedule"]["state"] == "unknown"


def test_nothing_in_the_advice_or_doctor_panel_claims_a_diagnosis():
    tips = adv.walker_tips({"late_caffeine": 5, "alcohol": 4}, 14, _reg(True), 70.0, 0)
    flags = adv.doctor_flags({"nights_counted": 12, "nights_under_6": 6, "window": 14}, _reg(True), 70.0)
    text = " ".join(f"{t['topic']} {t['advice']} {t['data'] or ''}" for t in tips) + " ".join(flags) + " ".join(adv.doctor_topics())
    for word in ("diagnos", "you have insomnia", "you have sleep apnea", "disorder"):
        assert word not in text.lower(), word


def test_the_doctor_summary_states_its_source_and_its_blind_spots():
    nights = [night(i, 6.0 if i % 3 else 7.5, bed_min=330, wake_min=420, awake_min=40.0) for i in range(28)]
    summary = adv.doctor_summary(nights, sr.regularity(nights), adv.awake_average(nights), "2026-10-11")
    assert "not a sleep study" in summary and "Nights recorded: 28 of 28" in summary
    assert "Not measured by Lifey: snoring" in summary and "Average sleep:" in summary


def test_extra_studies_state_their_limits():
    for key, ev in adv.EXTRA_EVIDENCE.items():
        assert ev["caveat"] and ev["confidence"] in {"strong", "moderate", "weak"} and ev["url"].startswith("https://"), key
    assert "disputed" in adv.EXTRA_EVIDENCE["walker2017"]["caveat"]


def test_endpoint_includes_walker_tips_and_the_doctor_panel(client, pg):
    body = client.get("/api/sleep").json()
    assert len(body["walker"]["tips"]) == 12 and body["walker"]["source"] in body["evidence"]
    assert body["walker"]["critique"] in body["evidence"]
    assert body["doctor"]["source"] in body["evidence"] and len(body["doctor"]["topics"]) == 5
    assert "Not measured by Lifey" in body["doctor"]["summary"]
