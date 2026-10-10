from fastapi.testclient import TestClient

from app.main import app
from app.readiness import build_metric, readiness

client = TestClient(app)


def test_today_is_labelled_demo_and_keeps_gaps():
    body = client.get("/api/today").json()
    assert body["source"] == "demo"
    hrv = next(m for m in body["metrics"] if m["key"] == "hrv")
    assert None in hrv["series"]  # gaps stay gaps, never zeros
    assert 0 not in hrv["series"]


def test_missing_metric_is_not_recorded_not_zero():
    spo2 = next(m for m in client.get("/api/today").json()["metrics"] if m["key"] == "spo2")
    assert spo2["value"] is None and spo2["provenance"] == "not_recorded"


def test_no_verdict_without_enough_baseline():
    m = [build_metric("hrv", "HRV", "ms", [None] * 27 + [50.0], "estimate")]
    verdict, reasons = readiness(m)
    assert verdict.score is None and reasons == []


def test_import_refused_when_disabled(monkeypatch):
    monkeypatch.delenv("ENABLE_BANK_IMPORT", raising=False)
    r = client.post("/api/money/import", files={"file": ("a.xlsx", b"x")})
    assert r.status_code == 409
