"""Parity suite: vidhealth's bot, quit-tracker and gym-plan tests, run against the port.

These were written against vidhealth's `bot`, `db`, `quit_tracker` and
`training_plan` modules; the names below point at their Lifey equivalents so
the original assertions are unchanged."""
import asyncio
import json
from contextlib import contextmanager
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from app import money
from app.bot import bot, quit_tracker, training_plan
from app.bot import store as db
from app.health import quality as q



def test_master_tap_pauses_before_logging(monkeypatch):
    monkeypatch.setattr(bot, "AUTHORIZED_CHAT_ID", "123")
    monkeypatch.setattr(db, "log_activity", lambda **kw: pytest.fail("a tap must not log straight away"))
    monkeypatch.setattr(db, "get_quit_logs", lambda: [_log("2026-09-01", "master")])
    monkeypatch.setattr(db, "get_quit_reasons", lambda: [{"id": 1, "note": "Energy for <my> family"}])
    monkeypatch.setattr(db, "get_df", lambda *a: pd.DataFrame())
    message = SimpleNamespace(text="💥 Master", reply_text=AsyncMock())
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=123), message=message)
    asyncio.run(bot.text_message_handler(update, SimpleNamespace(args=None)))
    text = message.reply_text.call_args.args[0]
    assert "Think twice" in text and "Energy for &lt;my&gt; family" in text
    buttons = [b.callback_data for row in message.reply_text.call_args.kwargs["reply_markup"].inline_keyboard for b in row]
    assert buttons == ["cmd:urge", "quit:slip"]


def test_master_with_explicit_count_logs_directly(monkeypatch):
    monkeypatch.setattr(bot, "AUTHORIZED_CHAT_ID", "123")
    logged = []
    monkeypatch.setattr(db, "log_activity", lambda **kw: logged.append(kw))
    monkeypatch.setattr(db, "get_quit_logs", lambda: [])
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=123), message=message)
    asyncio.run(bot.master_command(update, SimpleNamespace(args=["2"])))
    assert [(e["category"], e["value"]) for e in logged] == [("master", 2.0)]


def test_urge_schedules_a_follow_up(monkeypatch):
    monkeypatch.setattr(bot, "AUTHORIZED_CHAT_ID", "123")
    monkeypatch.setattr(db, "log_activity", lambda **kw: None)
    monkeypatch.setattr(db, "get_quit_logs", lambda: [])
    monkeypatch.setattr(db, "get_quit_reasons", lambda: [])
    jobs = SimpleNamespace(run_once=lambda *a, **kw: scheduled.append((a[1], kw["chat_id"])))
    scheduled = []
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=123), message=message)
    asyncio.run(bot.urge_command(update, SimpleNamespace(args=None, job_queue=jobs)))
    assert scheduled == [(15 * 60, 123)]


def test_menu_button_runs_command_in_the_buttons_chat(monkeypatch):
    monkeypatch.setattr(bot, "AUTHORIZED_CHAT_ID", "123")
    monkeypatch.setattr(db, "get_activity_logs", lambda **kw: [])
    message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(data="cmd:notes", answer=AsyncMock(), message=message)
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=123), message=None, callback_query=query)
    asyncio.run(bot.callback_query_handler(update, SimpleNamespace(args=None)))
    assert "No activity logs" in message.reply_text.call_args.args[0]


def test_every_menu_button_maps_to_a_command():
    buttons = [b for row in bot.get_home_keyboard().inline_keyboard for b in row]
    assert all(b.callback_data[len("cmd:"):] in bot.COMMANDS for b in buttons)
    assert set(bot.KEYBOARD_BUTTONS.values()) <= set(bot.COMMANDS)


def _log(day, tag, category="master", value=1, ts="12:00:00"):
    return {"date": day, "timestamp": f"{day} {ts}", "category": category, "tag": tag, "value": value}


def test_quit_streak_counts_days_since_last_slip_and_best_run():
    logs = [_log("2026-09-01", "urge_resisted"), _log("2026-09-05", "master"),
            _log("2026-09-06", "urge_resisted"), _log("2026-09-10", "master", category="unholy_habit"),
            _log("2026-09-12", "urge_resisted")]
    s = quit_tracker.summarize(logs, date(2026, 9, 13))
    assert s["current_streak"] == 3 and s["best_streak"] == 5
    assert s["urges_total"] == 3 and s["urges_this_streak"] == 1
    assert s["relapses_7d"] == 1 and s["relapses_30d"] == 2


def test_quit_comparison_uses_next_day_and_only_tracked_days():
    logs = [_log("2026-09-10", "clean_day", value=0)]
    logs += [_log(f"2026-09-{d:02d}", "master") for d in (10, 12, 14, 16, 18)]
    # Before tracking started: must not count as a clean day.
    rows = [{"date": "2026-09-05", "sleep_score": 10}]
    rows += [{"date": f"2026-09-{d:02d}", "sleep_score": 60 if d % 2 else 80} for d in range(11, 21)]
    c = quit_tracker.compare_next_day(logs, rows)
    sleep = next(m for m in c["metrics"] if m["label"] == "Sleep score")
    assert (sleep["after_n"], sleep["after_avg"]) == (5, 60)
    assert (sleep["other_n"], sleep["other_avg"]) == (5, 80)
    assert sleep["enough"] and "worse" in quit_tracker.render_comparison(c)


def test_quit_comparison_refuses_to_judge_small_samples():
    logs = [_log("2026-09-10", "master")]
    rows = [{"date": "2026-09-11", "sleep_score": 50}, {"date": "2026-09-12", "sleep_score": 90}]
    text = quit_tracker.render_comparison(quit_tracker.compare_next_day(logs, rows))
    assert "need ≥5 days" in text and "worse" not in text and "better" not in text


def _trained(*days):
    return {date(2026, 9, d) for d in days}


def test_gym_rotates_sessions_and_rests_after_two_days_in_a_row():
    # Mon 21 and Tue 22 trained -> Wed 23 rest; Thu 24 next session in rotation.
    trained = _trained(21, 22)
    assert training_plan.plan_day(trained, date(2026, 9, 23))["action"] == "rest"
    thu = training_plan.plan_day(trained, date(2026, 9, 24))
    assert thu["action"] == "train" and thu["session"]["key"] == "upper_b"


def test_gym_forces_sessions_late_in_week_and_stops_at_four():
    assert training_plan.plan_day(_trained(21), date(2026, 9, 25))["action"] == "train"  # Fri: 3 left, 3 days
    assert training_plan.plan_day(_trained(21, 22, 24, 25), date(2026, 9, 26))["action"] == "rest"


def test_gym_readiness_adjusts_only_from_todays_measurements():
    today = date(2026, 9, 24)
    low = {"date": "2026-09-24", "training_readiness": 22, "sleep_duration": 8 * 3600}
    assert training_plan.plan_today(set(), today, low)["action"] == "recover"
    short_sleep = {"date": "2026-09-24", "training_readiness": 70, "sleep_duration": 5 * 3600}
    plan = training_plan.plan_today(set(), today, short_sleep)
    assert plan["action"] == "train" and plan["readiness"]["level"] == "lighter"
    assert "Lighter today" in training_plan.render_today(plan, today)
    stale = {"date": "2026-09-20", "training_readiness": 10}
    assert training_plan.plan_today(set(), today, stale)["readiness"]["level"] == "unknown"


def test_gym_counts_garmin_strength_activities():
    days = training_plan.trained_sessions([], [{"date": "2026-09-21", "activity_type": "strength_training"},
                                               {"date": "2026-09-22", "activity_type": "running"}])
    assert days == {date(2026, 9, 21): None}


def test_gym_rotation_follows_the_session_actually_logged():
    # Planned Upper A on Monday but did Lower B: next is Upper A again, not Lower A.
    trained = training_plan.trained_sessions([{"date": "2026-09-21", "tag": "lower_b"}], [])
    assert training_plan.plan_day(trained, date(2026, 9, 22))["session"]["key"] == "upper_a"
    # A later correction on the same day wins.
    trained = training_plan.trained_sessions([{"date": "2026-09-21", "tag": "lower_b"},
                                              {"date": "2026-09-21", "tag": "upper_a"}], [])
    assert training_plan.plan_day(trained, date(2026, 9, 22))["session"]["key"] == "lower_a"


def test_gym_week_lists_the_exercises_for_each_training_day():
    today = date(2026, 9, 24)
    plan = training_plan.plan_today({}, today, None)
    text = training_plan.render_week(training_plan.plan_week({}, today, plan))
    assert "Barbell bench press" in text and "Back squat" in text and "chest, back, shoulders" in text


def test_morning_broadcast_sends_streak_and_todays_workout(monkeypatch):
    monkeypatch.setattr(bot, "AUTHORIZED_CHAT_ID", "123")
    monkeypatch.setattr(bot.quality, "today", lambda: date(2026, 9, 24))
    monkeypatch.setattr(db, "get_activities_df", lambda days: pd.DataFrame())
    monkeypatch.setattr(db, "get_training_logs", lambda days: [])
    monkeypatch.setattr(db, "get_df", lambda n: pd.DataFrame())
    monkeypatch.setattr(db, "get_quit_logs", lambda: [_log("2026-09-20", "master")])
    from app.bot import syncer as sync
    monkeypatch.setattr(sync, "smart_sync", lambda days: {"status": "success"})
    send = AsyncMock()
    asyncio.run(bot.morning_broadcast(SimpleNamespace(bot=SimpleNamespace(send_message=send))))
    kw = send.call_args.kwargs
    assert kw["chat_id"] == "123" and "4 days" in kw["text"] and "Upper A" in kw["text"]
    assert "No Garmin data for today" in kw["text"]


def test_gym_button_on_rest_days_logs_without_prompting_training():
    labels = lambda action: [b.text for row in bot.gym_keyboard({"action": action}).inline_keyboard for b in row]
    assert labels("train")[0].startswith("✅ Done")
    assert labels("rest")[0].startswith("🏋️ Trained anyway") and labels("recover")[0].startswith("🏋️ Trained anyway")
    assert labels("done") == ["🔄 Did a different session", "📅 This week"]


def _callback(data, monkeypatch):
    message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(data=data, answer=AsyncMock(), message=message, edit_message_text=AsyncMock())
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=123), message=None, callback_query=query)
    asyncio.run(bot.callback_query_handler(update, SimpleNamespace(args=None, job_queue=None)))
    return message, query


def test_undo_button_deletes_the_mislogged_entry(monkeypatch):
    monkeypatch.setattr(bot, "AUTHORIZED_CHAT_ID", "123")
    deleted = []
    entry = {"id": 7, "category": "master", "tag": "master", "value": 1.0, "timestamp": "2026-09-26 22:10:00"}
    monkeypatch.setattr(db, "get_activity_log", lambda i: entry if i == 7 else None)
    monkeypatch.setattr(db, "delete_activity_log", lambda i: deleted.append(i))
    _, query = _callback("del:7", monkeypatch)
    assert deleted == [7] and "Removed" in query.edit_message_text.call_args.args[0]
    _, query = _callback("del:8", monkeypatch)
    assert deleted == [7] and "Already removed" in query.edit_message_text.call_args.args[0]


def test_logging_a_different_session_replaces_todays_entry(monkeypatch):
    monkeypatch.setattr(bot, "AUTHORIZED_CHAT_ID", "123")
    monkeypatch.setattr(bot.quality, "today", lambda: date(2026, 9, 24))
    logs = [{"date": "2026-09-24", "tag": "upper_a"}]
    monkeypatch.setattr(db, "get_training_logs", lambda days: list(logs))
    monkeypatch.setattr(db, "get_activities_df", lambda days: pd.DataFrame())
    monkeypatch.setattr(db, "get_df", lambda n: pd.DataFrame())
    monkeypatch.setattr(db, "delete_training_logs", lambda d: (len(logs), logs.clear())[0])
    monkeypatch.setattr(db, "log_activity", lambda **kw: logs.append({"date": kw["date_str"], "tag": kw["tag"]}) or 9)
    message, _ = _callback("gym:did:lower_b", monkeypatch)
    assert logs == [{"date": "2026-09-24", "tag": "lower_b"}]
    assert "replaced the earlier entry" in message.reply_text.call_args.args[0]
    assert message.reply_text.call_args.kwargs["reply_markup"].inline_keyboard[-1][0].callback_data == "del:9"


def _morning(monkeypatch, rows_before, rows_after, sync_fn):
    from app.bot import syncer as sync
    monkeypatch.setattr(bot, "AUTHORIZED_CHAT_ID", "123")
    monkeypatch.setattr(bot.quality, "today", lambda: date(2026, 9, 27))
    monkeypatch.setattr(db, "get_activities_df", lambda days: pd.DataFrame())
    monkeypatch.setattr(db, "get_training_logs", lambda days: [])
    monkeypatch.setattr(db, "get_quit_logs", lambda: [])
    state = {"rows": rows_before}
    monkeypatch.setattr(db, "get_df", lambda n: pd.DataFrame(state["rows"]))
    calls = []
    def fake_sync(days):
        calls.append(days)
        state["rows"] = rows_after
        return sync_fn()
    monkeypatch.setattr(sync, "smart_sync", fake_sync)
    send = AsyncMock()
    asyncio.run(bot.morning_broadcast(SimpleNamespace(bot=SimpleNamespace(send_message=send))))
    return calls, send.call_args.kwargs["text"]


def test_morning_broadcast_syncs_first_when_todays_data_is_missing(monkeypatch):
    fresh = [{"date": "2026-09-27", "training_readiness": 70, "sleep_duration": 8 * 3600}]
    calls, text = _morning(monkeypatch, [], fresh, lambda: {"status": "success"})
    assert calls == [1] and "readiness 70/100" in text and "synced Garmin just now" not in text


def test_morning_broadcast_skips_sync_when_data_is_already_in(monkeypatch):
    fresh = [{"date": "2026-09-27", "training_readiness": 70}]
    calls, _ = _morning(monkeypatch, fresh, fresh, lambda: pytest.fail("synced needlessly"))
    assert calls == []


def test_morning_broadcast_still_sends_when_sync_fails(monkeypatch):
    def boom():
        raise RuntimeError("Another Garmin sync is already running.")
    calls, text = _morning(monkeypatch, [], [], boom)
    assert calls == [1] and "didn't finish" in text and "Upper A" in text


def _statement_update():
    doc = SimpleNamespace(file_name="ABA_statement.xlsx", file_id="abcdefghijkl")
    return SimpleNamespace(effective_chat=SimpleNamespace(id=123),
                           message=SimpleNamespace(document=doc, reply_text=AsyncMock()))


def test_statement_sent_while_import_is_off_gets_a_reply(monkeypatch):
    monkeypatch.setattr(bot, "AUTHORIZED_CHAT_ID", "123")
    monkeypatch.delenv("ENABLE_BANK_IMPORT", raising=False)
    update = _statement_update()
    asyncio.run(bot.xlsx_statement_handler(update, SimpleNamespace(bot=None)))
    assert "turned off" in update.message.reply_text.call_args.args[0]


def test_statement_import_reports_a_missing_importer(monkeypatch, tmp_path):
    monkeypatch.setattr(money, "PYTHON", str(tmp_path / "missing-python"))
    assert "not found or not readable" in bot.run_statement_import("x.xlsx")["error"]


def test_statement_import_parses_summary_and_reports_crashes(monkeypatch, tmp_path):
    import sys
    script = tmp_path / "importer.py"
    monkeypatch.setattr(money, "PYTHON", sys.executable)
    monkeypatch.setattr(money, "SCRIPT", str(script))
    script.write_text('print("reading"); print(\'{"rows_imported": 3, "rows_skipped_dupe": 1}\')')
    assert bot.run_statement_import("x.xlsx") == {"rows_imported": 3, "rows_skipped_dupe": 1}
    script.write_text('import sys; sys.exit("Sure API key rejected")')
    assert "Sure API key rejected" in bot.run_statement_import("x.xlsx")["error"]


def test_export_sends_three_csv_files(monkeypatch):
    from app import data_routes
    monkeypatch.setattr(bot, "AUTHORIZED_CHAT_ID", "123")
    monkeypatch.setattr(data_routes, "csv_text", lambda name, days=None: ("a,b" + chr(10) + name, 1))
    message = SimpleNamespace(reply_text=AsyncMock(), reply_document=AsyncMock())
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=123), message=message, callback_query=None)
    asyncio.run(bot.export_command(update, SimpleNamespace(args=["30"])))
    sent = [c.kwargs["filename"] for c in message.reply_document.call_args_list]
    assert len(sent) == 3
    assert any("daily_metrics" in f for f in sent) and any("journal" in f for f in sent) and any("habits" in f for f in sent)
    assert all(f.endswith(".csv") for f in sent)


def test_export_without_a_window_offers_buttons_and_rejects_nonsense(monkeypatch):
    monkeypatch.setattr(bot, "AUTHORIZED_CHAT_ID", "123")
    message = SimpleNamespace(reply_text=AsyncMock(), reply_document=AsyncMock())
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=123), message=message, callback_query=None)
    asyncio.run(bot.export_command(update, SimpleNamespace(args=[])))
    markup = message.reply_text.call_args.kwargs["reply_markup"]
    assert [b.callback_data for b in markup.inline_keyboard[0]] == ["export:7", "export:30", "export:90", "export:all"]
    message.reply_text.reset_mock()
    asyncio.run(bot.export_command(update, SimpleNamespace(args=["banana"])))
    assert "Usage" in message.reply_text.call_args.args[0]
    message.reply_document.assert_not_called()
