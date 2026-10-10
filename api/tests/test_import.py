"""History import: replay semantics, using in-memory history (no dump file needed)."""
from datetime import datetime, timezone

from app.health import import_vidhealth as imp

DAY = "2026-09-21"


def history(*replays, legacy=()):
    h = imp.History()
    for day, received, payload in replays:
        h.replays[day].append((received, payload))
        h.from_payloads.add(day)
    for day, received, payload in legacy:
        h.replays[day].append((received, payload))
        h.from_legacy.add(day)
    return h


def one(conn, sql, *params):
    return conn.execute(sql, params).fetchone()


def test_payloads_replay_in_order_and_keep_their_original_receipt_time(pg):
    h = history(
        (DAY, "2026-09-21T08:00:00+00:00", {"summary": {"totalSteps": 25}, "sleep": {"dailySleepDTO": {"sleepTimeSeconds": 25000}}}),
        (DAY, "2026-09-21T20:00:00+00:00", {"summary": {"totalSteps": 30}, "sleep_error": "down"}),
    )
    result = imp.import_history(pg, h)
    assert result["days_imported"] == 1 and result["days_failed"] == 0
    steps, sleep, synced = one(pg, "SELECT steps, sleep_duration, synced_at FROM health.daily_metrics WHERE date=%s", DAY)
    assert steps == 30 and sleep == 25000
    assert synced == datetime(2026, 9, 21, 20, 0, tzinfo=timezone.utc)  # not the import time
    status, fetched = one(pg, "SELECT status, fetched_at FROM health.endpoint_state WHERE date=%s AND endpoint='sleep'", DAY)
    assert status == "fetch_failed" and fetched == datetime(2026, 9, 21, 8, 0, tzinfo=timezone.utc)


def test_legacy_stored_payload_is_stamped_with_its_own_sync_time_never_now(pg):
    h = history(legacy=[("2026-07-01", "2026-07-01T09:30:00+00:00", {"summary": {"totalSteps": 7}})])
    imp.import_history(pg, h)
    fetched, synced = one(pg, """SELECT e.fetched_at, d.synced_at FROM health.endpoint_state e
                                 JOIN health.daily_metrics d USING (date) WHERE date=%s AND endpoint='summary'""", "2026-07-01")
    assert fetched == synced == datetime(2026, 7, 1, 9, 30, tzinfo=timezone.utc)


def test_legacy_synthetic_oxygen_is_never_imported(pg):
    legacy = {"summary": {"averageSpo2": 96, "lowestSpo2": 88},
              "pulse_ox": {"spO2ContinuousValues": [[1789948770, 96]]}}  # unknown shape
    imp.import_history(pg, history(legacy=[(DAY, None, legacy)]))
    assert one(pg, "SELECT count(*) FROM health.spo2_samples")[0] == 0
    assert one(pg, "SELECT availability FROM health.spo2_processing WHERE date=%s", DAY)[0] == "parse_failed"


def test_import_is_repeatable(pg):
    h = history((DAY, "2026-09-21T08:00:00+00:00", {"summary": {"totalSteps": 25},
        "pulse_ox": {"spO2ContinuousValues": [{"epochTimestamp": 1789948770000, "spO2Reading": 95}]}}))
    imp.import_history(pg, h)
    before = (one(pg, "SELECT count(*) FROM health.source_payloads")[0],
              one(pg, "SELECT count(*) FROM health.spo2_samples")[0])
    imp.import_history(pg, h)
    after = (one(pg, "SELECT count(*) FROM health.source_payloads")[0],
             one(pg, "SELECT count(*) FROM health.spo2_samples")[0])
    assert before == after == (2, 1)


def test_dry_run_writes_nothing(pg):
    h = history((DAY, None, {"summary": {"totalSteps": 25}}))
    result = imp.import_history(pg, h, dry_run=True)
    assert result["days_to_import"] == 1
    assert one(pg, "SELECT count(*) FROM health.daily_metrics")[0] == 0


def test_a_bad_day_is_reported_and_does_not_stop_the_rest(pg):
    h = history((DAY, None, {"summary": {"totalSteps": 25}}), ("not-a-date", None, {"summary": {"totalSteps": 1}}))
    result = imp.import_history(pg, h)
    assert result["days_imported"] == 1 and result["days_failed"] == 1
    assert "not-a-date" in result["errors"]
