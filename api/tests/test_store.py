"""Persistence behaviour against a real PostgreSQL."""
from datetime import date, timedelta

import psycopg
import pytest

from app.health import store, sync

DAY = "2026-09-21"


def one(conn, sql, *params):
    return conn.execute(sql, params).fetchone()


def test_replay_partial_failure_and_empty_correction(pg):
    store.save_day(pg, DAY, {"summary": {"totalSteps": 25}, "sleep": {"dailySleepDTO": {"sleepTimeSeconds": 25000}}})
    store.save_day(pg, DAY, {"summary": {"totalSteps": 30}, "sleep_error": "down"})
    steps, sleep, sources = one(pg, "SELECT steps, sleep_duration, metric_sources FROM health.daily_metrics WHERE date=%s", DAY)
    assert steps == 30 and sleep == 25000  # failed endpoint keeps its earlier value
    assert sources["sleep_duration"]["status"] == "fetch_failed"

    store.save_day(pg, DAY, {"sleep": {}})  # a successful empty answer is a correction
    assert one(pg, "SELECT sleep_duration FROM health.daily_metrics WHERE date=%s", DAY)[0] is None
    assert one(pg, "SELECT count(*) FROM health.spo2_samples")[0] == 0


def test_every_distinct_payload_is_archived(pg):
    store.save_day(pg, DAY, {"summary": {"totalSteps": 25}})
    store.save_day(pg, DAY, {"summary": {"totalSteps": 25}})  # identical: no duplicate
    store.save_day(pg, DAY, {"summary": {"totalSteps": 40}})  # corrected: both kept
    n = one(pg, "SELECT count(*) FROM health.source_payloads WHERE endpoint='summary'")[0]
    assert n == 2


def test_downstream_failure_rolls_back_the_whole_day(pg, monkeypatch):
    store.save_day(pg, DAY, {"summary": {"totalSteps": 25}})
    pg.commit()

    def boom(*args, **kwargs):
        raise RuntimeError("injected oxygen failure")

    monkeypatch.setattr(store, "_save_oxygen", boom)
    with pytest.raises(RuntimeError):
        store.save_day(pg, DAY, {"summary": {"totalSteps": 99}})
    pg.rollback()
    assert one(pg, "SELECT steps FROM health.daily_metrics WHERE date=%s", DAY)[0] == 25
    assert one(pg, "SELECT count(*) FROM health.source_payloads WHERE endpoint='summary'")[0] == 1


def test_genuine_samples_replay_without_duplicates(pg):
    payload = {"pulse_ox": {"spO2ContinuousValues": [
        {"epochTimestamp": 1789948770000 + i * 15000, "spO2Reading": v} for i, v in enumerate([97, 88, 97])]}}
    store.save_day(pg, DAY, payload)
    store.save_day(pg, DAY, payload)
    assert one(pg, "SELECT count(*) FROM health.spo2_samples WHERE date=%s", DAY)[0] == 3
    availability, count = one(pg, "SELECT availability, sample_count FROM health.spo2_processing WHERE date=%s", DAY)
    assert availability == "available" and count == 3


def test_summary_only_oxygen_creates_no_samples(pg):
    store.save_day(pg, DAY, {"summary": {"averageSpo2": 96, "lowestSpo2": 82}})
    assert one(pg, "SELECT count(*) FROM health.spo2_samples")[0] == 0
    assert one(pg, "SELECT availability FROM health.spo2_processing WHERE date=%s", DAY)[0] == "unavailable"
    assert one(pg, "SELECT spo2_avg, spo2_min FROM health.daily_metrics WHERE date=%s", DAY) == (96.0, 82.0)


def test_missing_activity_fields_are_null_not_zero(pg):
    store.save_day(pg, "2026-09-20", {"activities": [
        {"activityId": 1, "activityType": {"typeKey": "strength_training"}, "duration": 1800, "calories": 0}]})
    row = pg.execute("SELECT distance_meters, avg_speed, elevation_gain, calories, started_local, date "
                     "FROM health.activities").fetchone()
    assert row[0] is None and row[1] is None and row[2] is None
    assert row[3] == 0                       # Garmin's own zero is preserved
    assert row[4] is None                    # no invented midnight
    assert row[5] == date(2026, 9, 20)
    assert one(pg, "SELECT workout_type FROM health.daily_metrics WHERE date=%s", "2026-09-20")[0] == "Strength Training (30m)"


def test_sync_lock_prevents_parallel_run(pg, database_url):
    other = psycopg.connect(database_url)
    try:
        with sync.sync_job(pg):
            with pytest.raises(RuntimeError, match="already running"):
                with sync.sync_job(other):
                    pytest.fail("second worker acquired the lock")
    finally:
        other.close()


class FakeGarmin:
    """Day ending in 21 succeeds; anything else fails every endpoint."""

    def __getattr__(self, name):
        def call(*args):
            ds = args[0]
            if not ds.endswith("21"):
                raise RuntimeError("down")
            if name == "get_stats":
                return {"totalSteps": 5, "restingHeartRate": 55}
            return {}
        return call


def test_sync_reports_partial_failure_and_saves_nothing_for_an_empty_day(pg):
    result = sync.run_sync(pg, ["2026-09-21", "2026-09-22"], api=FakeGarmin(), pause=0)
    assert result["status"] == "partial"
    assert result["synced_dates"] == ["2026-09-21"] and result["failed_dates"] == ["2026-09-22"]
    assert one(pg, "SELECT count(*) FROM health.daily_metrics WHERE date=%s", "2026-09-22")[0] == 0
    status, details = one(pg, "SELECT status, details FROM health.sync_runs ORDER BY id DESC LIMIT 1")
    assert status == "partial" and details["failed_dates"] == ["2026-09-22"]


def test_cli_exit_status_is_nonzero_unless_fully_successful(pg, monkeypatch):
    monkeypatch.setattr(sync, "get_api", lambda: FakeGarmin())
    monkeypatch.setattr(sync.time, "sleep", lambda _: None)
    monkeypatch.setattr(sync, "window", lambda days: ["2026-09-21", "2026-09-22"])
    assert sync.main(["smart", "2"]) == 1


def test_migrations_leave_expected_tables(pg):
    tables = {r[0] for r in pg.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='health'").fetchall()}
    assert {"daily_metrics", "endpoint_state", "source_payloads", "spo2_samples",
            "spo2_processing", "activities", "sync_runs"} <= tables


def test_samples_outside_valid_range_are_rejected_by_the_database(pg):
    with pytest.raises(psycopg.errors.CheckViolation):
        pg.execute("INSERT INTO health.spo2_samples(date, ts, value, source) VALUES (%s, now(), 0, 'SLEEP')", (DAY,))


def test_today_endpoint_reads_real_data_and_keeps_gaps(pg):
    from fastapi.testclient import TestClient
    from app.main import app

    anchor = date(2026, 9, 21)
    for i in range(14):
        d = anchor - timedelta(days=13 - i)
        if i == 5:
            continue  # a day with no row at all
        store.save_day(pg, d.isoformat(), {
            "summary": {"totalSteps": 8000 + i * 10, "restingHeartRate": 52},
            "hrv": {"hrvSummary": {"lastNightAvg": 60 + (i % 3), "status": "BALANCED"}},
            "sleep": {"dailySleepDTO": {"sleepScores": {"overall": {"value": 75}}}},
        })
    pg.commit()
    body = TestClient(app).get("/api/today").json()
    assert body["source"] == "garmin" and body["date"] == "2026-09-21"
    hrv = next(m for m in body["metrics"] if m["key"] == "hrv")
    assert len(hrv["series"]) == 28
    assert hrv["series"][-1] == 61.0 and hrv["series"][-1 - 8] is None  # gap preserved
    assert body["readiness"]["score"] is not None
    spo2 = next(m for m in body["metrics"] if m["key"] == "spo2")
    assert spo2["value"] is None and spo2["provenance"] == "not_recorded"
