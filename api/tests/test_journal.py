"""Journal layer: the bot's data shapes on Lifey's tables, and the history carry-over."""
import json
from datetime import date, datetime, timezone

import psycopg
import pytest

from app.bot import store
from app.health import journal_import as ji
from app.health import store as health_store

DAY = "2026-10-09"


def test_log_roundtrip_has_the_old_row_shape(pg):
    log_id = store.log_activity(date_str=DAY, category="master", tag="master", note="", value=1)
    row = store.get_activity_log(log_id)
    assert set(row) == {"id", "date", "timestamp", "category", "tag", "note", "value", "occurred_at"}
    assert row["date"] == DAY and row["value"] == 1.0
    assert len(row["timestamp"]) == 19          # 'YYYY-MM-DD HH:MM:SS', as the bot slices it
    assert store.get_activity_logs(limit=5)[0]["id"] == log_id
    assert store.delete_activity_log(log_id) is True
    assert store.get_activity_log(log_id) is None


def test_quit_logs_reasons_and_training_selectors(pg):
    store.log_activity(DAY, "master", "master", value=2)
    store.log_activity(DAY, "wellbeing", "mood", value=4)
    store.log_activity(DAY, "quit_reason", "reason", note="more energy")
    store.log_activity(DAY, "training", "upper_a", note="Upper A", value=1)
    store.log_activity(DAY, "unholy_habit", "alcohol", value=2)
    assert {l["tag"] for l in store.get_quit_logs()} == {"master", "mood"}
    assert [r["note"] for r in store.get_quit_reasons()] == ["more energy"]
    assert [t["tag"] for t in store.get_training_logs(days=3650)] == ["upper_a"]
    assert store.delete_training_logs(DAY) == 1
    assert store.get_training_logs(days=3650) == []


def test_get_df_keeps_column_names_and_rebuilds_provenance(pg):
    health_store.save_day(pg, DAY, {"summary": {"totalSteps": 5, "restingHeartRate": 55},
                                    "sleep_error": "down"})
    pg.commit()
    store.log_activity(DAY, "unholy_habit", "alcohol", value=1)
    df = store.get_df(30)
    row = df.iloc[-1]
    assert row["date"] == DAY and row["steps"] == 5 and row["resting_hr"] == 55
    assert row["alcohol_logged"] == 1
    raw = json.loads(row["raw_json"])
    assert raw["_sources"]["summary"]["status"] == "available"
    assert raw["_sources"]["sleep"]["status"] == "unavailable" or raw["_sources"]["sleep"]["status"] == "fetch_failed"
    assert raw["_metric_sources"]["steps"]["endpoint"] == "summary"


def test_coaching_reads_the_ported_frame(pg):
    from app.bot import coaching
    health_store.save_day(pg, DAY, {"summary": {"totalSteps": 5, "restingHeartRate": 55}})
    pg.commit()
    evidence = coaching.build_evidence(store.get_df(28))
    assert {f["metric"] for f in evidence["facts"]} >= {"resting_hr", "steps"}


def test_alert_lifecycle_and_delivery_tracking(pg):
    store.upsert_alert(DAY, "INFO", "SPO2_MIN", "low twice", {"e": 1}, "observations-v1")
    row = store.pending_alert(DAY, "SPO2_MIN", "observations-v1")
    assert row["delivered"] is False
    store.mark_alert_delivered(row["id"])
    store.upsert_alert(DAY, "INFO", "SPO2_MIN", "low twice", {"e": 1}, "observations-v1")      # same message
    assert store.pending_alert(DAY, "SPO2_MIN", "observations-v1")["delivered"] is True
    store.upsert_alert(DAY, "INFO", "SPO2_MIN", "changed message", {"e": 2}, "observations-v1")  # new message
    assert store.pending_alert(DAY, "SPO2_MIN", "observations-v1")["delivered"] is False
    assert len(store.get_recent_alerts()) == 1
    store.resolve_alert(DAY, "SPO2_MIN", "observations-v1")
    assert store.get_recent_alerts() == []


def _old_journal():
    return ji.Journal(
        activity_logs=[
            {"id": 7, "date": "2026-10-01", "timestamp": "2026-10-01 09:15:00", "category": "master",
             "tag": "master", "note": "", "value": "1", "occurred_at": None},
            {"id": 9, "date": "2026-10-02", "timestamp": "2026-10-02 21:30:00", "category": "free_note",
             "tag": "note", "note": "sore quads", "value": None, "occurred_at": "20:00"},
        ],
        body_comp=[{"date": "2026-10-01", "weight": "78.4", "body_fat": None, "waist": "84"}],
        anomaly_alerts=[{"id": 1, "date": "2026-10-01", "timestamp": "2026-10-01 10:00:00", "severity": "INFO",
                         "alert_type": "SPO2_MIN", "message": "m", "metrics_json": '{"a": 1}', "acknowledged": 0,
                         "algorithm_version": "observations-v1", "alert_state": "active", "delivered": "t"}],
        action_plans=[{"id": 3, "period_start": "2026-09-25", "period_end": "2026-10-01",
                       "generated_at": "2026-10-01 08:00:00", "model": "m", "headline": "h",
                       "plan_text": "do x", "watchlist_json": '["hrv"]', "evidence_json": None}],
        coaching_reports=[{"id": 4, "date": "2026-10-01", "generated_at": "2026-10-01 08:00:00",
                           "report_text": "recap", "evidence": '{"facts": []}', "model": "m", "validation": "ok"}],
    )


def test_history_keeps_ids_local_times_and_fields(pg):
    counts = ji.load(pg, _old_journal())
    pg.commit()
    assert counts["activity_logs"] == 2 and counts["action_plans"] == 1
    note = store.get_activity_log(9)
    assert note["timestamp"] == "2026-10-02 21:30:00" and note["occurred_at"] == "20:00"   # local time preserved
    assert store.get_latest_action_plan()["plan_text"] == "do x"
    assert store.get_latest_coaching_report()["report_text"] == "recap"
    assert store.get_recent_alerts()[0]["delivered"] is True
    assert pg.execute("SELECT weight, waist FROM journal.body_comp").fetchone() == (78.4, 84.0)


def test_new_rows_never_collide_with_carried_over_ids(pg):
    ji.load(pg, _old_journal())
    pg.commit()
    new_id = store.log_activity("2026-10-09", "master", "master", value=1)
    assert new_id > 9


def test_reload_mirrors_old_deletions_but_never_touches_lifey_rows(pg):
    ji.load(pg, _old_journal())
    pg.commit()
    mine = store.log_activity("2026-10-09", "free_note", "note", note="written in Lifey")
    journal = _old_journal()
    journal.activity_logs = [r for r in journal.activity_logs if r["id"] != 7]   # /undo in the old bot
    ji.load(pg, journal)
    pg.commit()
    assert store.get_activity_log(7) is None
    assert store.get_activity_log(9) is not None
    assert store.get_activity_log(mine)["note"] == "written in Lifey"


def test_missing_old_tables_are_tolerated(pg, database_url):
    with psycopg.connect(database_url, autocommit=True) as c:
        c.execute("DROP TABLE IF EXISTS activity_logs, body_comp, anomaly_alerts, action_plans, coaching_reports")
    with psycopg.connect(database_url) as old:
        journal = ji.read_live(old)
    assert journal.activity_logs == [] and journal.body_comp == []


def test_week_and_action_plan_are_generated_from_current_data(pg):
    from app.bot import reports
    assert reports.ensure_weekly_report() is None and reports.ensure_action_plan() is None   # nothing to say yet
    health_store.save_day(pg, "2026-10-09", {"summary": {"totalSteps": 5, "restingHeartRate": 55}})
    pg.commit()
    report = reports.ensure_weekly_report()
    assert "Recorded period" in report["report_text"] and report["date"] == "2026-10-09"
    again = reports.ensure_weekly_report()
    assert again["id"] == report["id"]                      # not regenerated while still current
    health_store.save_day(pg, "2026-10-10", {"summary": {"totalSteps": 9, "restingHeartRate": 54}})
    pg.commit()
    assert reports.ensure_weekly_report()["id"] != report["id"]   # data moved on, so the recap did
    plan = reports.ensure_action_plan()
    assert plan["period_end"] == "2026-10-10" and plan["headline"].startswith("Recorded observations")


def test_weekly_review_nudge_links_to_the_page_and_runs_on_sundays(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.bot import bot

    assert bot.WEEKLY_REVIEW_DAY == 0                       # python-telegram-bot: 0 is Sunday
    monkeypatch.setattr(bot, "AUTHORIZED_CHAT_ID", "123")
    monkeypatch.setenv("WEB_URL", "https://lifey.example/")
    send = AsyncMock()
    asyncio.run(bot.weekly_review_nudge(SimpleNamespace(bot=SimpleNamespace(send_message=send))))
    kwargs = send.call_args.kwargs
    button = kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.url == "https://lifey.example/review" and kwargs["chat_id"] == "123"

    monkeypatch.delenv("WEB_URL")
    asyncio.run(bot.weekly_review_nudge(SimpleNamespace(bot=SimpleNamespace(send_message=send))))
    assert send.call_args.kwargs["reply_markup"] is None    # no address: still tells you, without a dead link
