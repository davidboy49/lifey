"""The evening check-in: answers are saved one tap at a time, unknown stays NULL, yes mirrors into habits."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot import bot, checkin
from app.bot import store as db
from app.health import quality


def test_parse_accepts_only_known_fields_and_values():
    assert checkin.parse("ci:2026-10-12:alcohol_units:2") == ("2026-10-12", "alcohol_units", "2")
    assert checkin.parse("ci:2026-10-12:rpe:skip") == ("2026-10-12", "rpe", None)
    assert checkin.parse("ci:2026-10-12:rpe:9") is None            # not one of the offered values
    assert checkin.parse("ci:2026-10-12:password:1") is None
    assert checkin.parse("ci:short:rpe:3") is None
    assert checkin.parse("cmd:menu") is None


def test_every_button_fits_telegram_callback_limit():
    for i in range(len(checkin.STEPS)):
        for row in checkin.keyboard("2026-10-12", i).inline_keyboard:
            assert all(len(b.callback_data.encode()) <= 64 for b in row)


def test_saving_answers_keeps_unanswered_fields_null(pg):
    today = quality.today().isoformat()
    assert db.get_checkin(today) is None
    db.save_checkin_answer(today, "alcohol_units", 0)             # a recorded dry day is not unknown
    db.save_checkin_answer(today, "rpe", 6)
    row = db.get_checkin(today)
    assert row["alcohol_units"] == 0.0 and row["rpe"] == 6
    assert row["late_caffeine"] is None and row["late_meal"] is None
    db.save_checkin_answer(today, "late_caffeine", 1)
    assert db.get_checkin(today)["late_caffeine"] is True and db.get_checkin(today)["alcohol_units"] == 0.0
    with pytest.raises(ValueError):
        db.save_checkin_answer(today, "date; DROP TABLE x", 1)


def _query(data):
    message = SimpleNamespace()
    q = SimpleNamespace(data=data, edit_message_text=AsyncMock(), message=message)
    return q


def test_yes_is_mirrored_once_into_habits_and_flow_walks_to_the_summary(pg):
    today = quality.today().isoformat()
    steps = [("alcohol_units", "2"), ("late_caffeine", "1"), ("late_meal", "skip"), ("rpe", "6")]
    last = None
    for field, value in steps:
        last = _query(f"ci:{today}:{field}:{value}")
        asyncio.run(bot.checkin_answer(last, last.data))
    habits = [l for l in db.get_activity_logs(today) if l["category"] == "unholy_habit"]
    assert sorted(h["tag"] for h in habits) == ["alcohol", "late_caffeine"]
    assert next(h for h in habits if h["tag"] == "alcohol")["value"] == 2.0
    row = db.get_checkin(today)
    assert row["late_meal"] is None and row["rpe"] == 6                # skipped stays unknown
    assert "Check-in saved" in last.edit_message_text.call_args.args[0]

    # answering the same question again does not log the habit twice
    again = _query(f"ci:{today}:alcohol_units:3")
    asyncio.run(bot.checkin_answer(again, again.data))
    alcohol = [l for l in db.get_activity_logs(today) if l.get("tag") == "alcohol"]
    assert len(alcohol) == 1 and db.get_checkin(today)["alcohol_units"] == 3.0


def test_a_none_answer_logs_no_habit(pg):
    today = quality.today().isoformat()
    q = _query(f"ci:{today}:alcohol_units:0")
    asyncio.run(bot.checkin_answer(q, q.data))
    assert [l for l in db.get_activity_logs(today) if l["category"] == "unholy_habit"] == []
    assert db.get_checkin(today)["alcohol_units"] == 0.0
    # and the next question is the caffeine one
    assert "Caffeine" in q.edit_message_text.call_args.args[0]


def test_summary_text_reads_naturally():
    text = checkin.summary({"alcohol_units": 0.0, "late_caffeine": True, "late_meal": None, "rpe": 6})
    assert "Alcohol: None" in text and "Late caffeine: Yes" in text and "Workout: Medium" in text
    assert "Late meal" not in text
