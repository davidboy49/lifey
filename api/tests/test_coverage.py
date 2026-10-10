"""Coverage report: gaps are listed, never filled."""
from datetime import date

from app.health import store
from app.ml import coverage


def test_report_lists_gaps_and_metric_completeness(pg):
    for d, steps in (("2026-09-20", 100), ("2026-09-22", 300)):  # 21st has no row at all
        store.save_day(pg, d, {"summary": {"totalSteps": steps}})
    pg.commit()
    report = coverage.build_report(pg, days=7, today=date(2026, 9, 23))
    assert report["rows"] == 2
    assert report["first_date"] == "2026-09-20" and report["last_date"] == "2026-09-22"
    assert report["missing_dates"] == ["2026-09-21"]
    assert report["metrics"]["steps"]["non_null"] == 2
    assert report["metrics"]["hrv_last_night"]["non_null"] == 0
    assert report["days_since_last_row"] == 1


def test_empty_database(pg):
    report = coverage.build_report(pg, today=date(2026, 9, 23))
    assert report["rows"] == 0 and report["missing_dates"] == []
