"""Pure provenance and parsing rules, ported from vidhealth's integrity tests."""
import pytest

from app.health import quality as q


@pytest.mark.parametrize("payload", [{}, {"summary": {"averageSpo2": 96, "lowestSpo2": 82}}])
def test_missing_epochs_never_generate_measurements(payload):
    rows, status = q.parse_oxygen("2026-09-21", payload)
    assert rows == []
    assert status["availability"] == "unavailable"


def test_seconds_and_milliseconds_parse_identically_without_inferred_stages():
    def payload(scale):
        return {"pulse_ox": {"spO2ContinuousValues": [{"epochTimestamp": 1789948770 * scale, "spO2Reading": 95.5}]}}
    first, _ = q.parse_oxygen("2026-09-21", payload(1))
    second, _ = q.parse_oxygen("2026-09-21", payload(1000))
    assert first == second
    assert first[0]["respiration_rate"] is None
    assert first[0]["sleep_stage"] == "Unknown"
    assert first[0]["spo2_value"] == 95.5


def test_archived_garmin_iso_sleep_epochs_are_measured_utc_samples():
    raw = {"sleep": {"wellnessEpochSPO2DataDTOList": [
        {"epochTimestamp": "2026-09-21T23:59:00.0", "epochDuration": 60, "spo2Reading": 96},
        {"epochTimestamp": "2026-09-22T00:00:00.0", "epochDuration": 60, "spo2Reading": 94}],
        "wellnessEpochRespirationDataDTOList": [{"startTimeGMT": 1790035140000, "respirationValue": 15.5}]}}
    rows, state = q.parse_oxygen("2026-09-22", raw)
    assert state["availability"] == "available"
    assert len(rows) == 2
    assert rows[1]["timestamp"] - rows[0]["timestamp"] == 60
    assert rows[0]["epoch_type"] == "SLEEP"


def test_unknown_epoch_schema_is_parse_failure():
    rows, status = q.parse_oxygen("2026-09-21", {"pulse_ox": {"spO2ContinuousValues": [[1789948770, 96]]}})
    assert not rows and status["availability"] == "parse_failed"


def test_partial_sync_retains_sources_and_marks_them_stale():
    old = q.merge_sources({}, {"sleep": {"dailySleepDTO": {"sleepTimeSeconds": 25000}}, "summary": {"totalSteps": 7}}, "old-time")
    merged = q.merge_sources(old, {"sleep_error": "unavailable", "summary": {"totalSteps": 0}}, "new-time")
    assert merged["sleep"] == old["sleep"]
    assert merged["_sources"]["sleep"]["fetched_at"] == "old-time"
    assert merged["_sources"]["sleep"]["status"] == "fetch_failed"
    assert merged["summary"]["totalSteps"] == 0


def test_successful_empty_source_can_correct_old_data():
    old = q.merge_sources({}, {"sleep": {"dailySleepDTO": {"sleepTimeSeconds": 25000}}})
    merged = q.merge_sources(old, {"sleep": {}})
    assert merged["sleep"] == {}
    assert q.parse_daily(merged)[0]["sleep_duration"] is None


def test_malformed_source_does_not_replace_previous():
    old = {"summary": {"totalSteps": 10}}
    merged = q.merge_sources(old, {"summary": []})
    assert merged["summary"] == old["summary"]
    assert merged["_sources"]["summary"]["status"] == "parse_failed"


def test_missing_steps_are_not_zero_and_explicit_zero_is_preserved():
    assert q.parse_daily({})[0]["steps"] is None
    assert q.parse_daily({"steps": []})[0]["steps"] is None
    assert q.parse_daily({"summary": {"totalSteps": 0}})[0]["steps"] == 0
    assert q.parse_daily({"steps": [{"steps": 0}]})[0]["steps"] == 0
    assert q.parse_daily({"steps": [{"steps": 2}, {}]})[0]["steps"] is None


def test_readiness_and_independent_hr_fallbacks():
    metrics, sources, _ = q.parse_daily({"summary": {"restingHeartRate": 60}, "heart_rate": {"minHeartRate": 48},
                                         "training_readiness": {"score": 0}})
    assert metrics["training_readiness"] == 0
    assert metrics["resting_hr"] == 60 and metrics["min_hr"] == 48
    assert sources["min_hr"]["endpoint"] == "heart_rate"


def test_out_of_range_vendor_sentinels_are_unavailable():
    values, _, issues = q.parse_daily({"summary": {"averageStressLevel": -1, "averageSpo2": 101}})
    assert values["stress_avg"] is None and values["spo2_avg"] is None
    assert set(issues) == {"stress_avg", "spo2_avg"}
