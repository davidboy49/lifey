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


def CTX():
    return SimpleNamespace(user_data={})


def _query(data):
    message = SimpleNamespace(edit_text=AsyncMock())
    q = SimpleNamespace(data=data, edit_message_text=AsyncMock(), message=message)
    return q


def test_yes_is_mirrored_once_into_habits_and_flow_walks_to_the_summary(pg):
    today = quality.today().isoformat()
    steps = [("alcohol_units", "2"), ("late_caffeine", "1"), ("late_meal", "skip"), ("rpe", "6")]
    last = None
    for field, value in steps:
        last = _query(f"ci:{today}:{field}:{value}")
        asyncio.run(bot.checkin_answer(last, last.data, CTX()))
    habits = [l for l in db.get_activity_logs(today) if l["category"] == "unholy_habit"]
    assert sorted(h["tag"] for h in habits) == ["alcohol", "late_caffeine"]
    assert next(h for h in habits if h["tag"] == "alcohol")["value"] == 2.0
    row = db.get_checkin(today)
    assert row["late_meal"] is None and row["rpe"] == 6                # skipped stays unknown
    assert "Check-in saved" in last.edit_message_text.call_args.args[0]

    # answering the same question again does not log the habit twice
    again = _query(f"ci:{today}:alcohol_units:3")
    asyncio.run(bot.checkin_answer(again, again.data, CTX()))
    alcohol = [l for l in db.get_activity_logs(today) if l.get("tag") == "alcohol"]
    assert len(alcohol) == 1 and db.get_checkin(today)["alcohol_units"] == 3.0


def test_a_none_answer_logs_no_habit(pg):
    today = quality.today().isoformat()
    q = _query(f"ci:{today}:alcohol_units:0")
    asyncio.run(bot.checkin_answer(q, q.data, CTX()))
    assert [l for l in db.get_activity_logs(today) if l["category"] == "unholy_habit"] == []
    assert db.get_checkin(today)["alcohol_units"] == 0.0
    # and the next question is the caffeine one
    assert "Caffeine" in q.edit_message_text.call_args.args[0]


def test_summary_text_reads_naturally():
    text = checkin.summary({"alcohol_units": 0.0, "late_caffeine": True, "late_meal": None, "rpe": 6})
    assert "Alcohol: None" in text and "Late caffeine: Yes" in text and "Workout: Medium" in text
    assert "Late meal" not in text


# ---------- how you woke up ----------

def test_feeling_callbacks_are_validated():
    assert checkin.parse_feeling("mf:2026-10-13:4") == ("2026-10-13", 4)
    assert checkin.parse_feeling("mf:2026-10-13:6") is None
    assert checkin.parse_feeling("mf:2026-10-13:x") is None
    assert checkin.parse_feeling("ci:2026-10-13:rpe:3") is None
    row = checkin.feeling_keyboard("2026-10-13").inline_keyboard[0]
    assert [b.callback_data.rsplit(":", 1)[1] for b in row] == ["1", "2", "3", "4", "5"]


def test_rating_does_not_count_as_the_evening_check_in(pg):
    today = quality.today().isoformat()
    q = _query(f"mf:{today}:4")
    asyncio.run(bot.feeling_answer(q, q.data))
    assert db.get_checkin(today)["wake_feeling"] == 4
    assert db.get_checkin(today)["alcohol_units"] is None
    sent = SimpleNamespace(send_message=AsyncMock())
    asyncio.run(bot.habit_checkin(SimpleNamespace(bot=sent)))   # evening questions still due
    assert sent.send_message.await_count == 1
    assert "saved" in q.edit_message_text.call_args.args[0]


def test_feeling_command_sets_today_and_rejects_nonsense(pg, monkeypatch):
    monkeypatch.setattr(bot, "AUTHORIZED_CHAT_ID", "123")
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=123), message=message, callback_query=None)
    asyncio.run(bot.feeling_command(update, SimpleNamespace(args=["2"])))
    assert db.get_checkin(quality.today().isoformat())["wake_feeling"] == 2
    asyncio.run(bot.feeling_command(update, SimpleNamespace(args=["9"])))
    assert "Usage" in message.reply_text.call_args.args[0]


def test_feelings_by_day_only_include_rated_days(pg):
    db.save_checkin_answer("2026-10-10", "wake_feeling", 5)
    db.save_checkin_answer("2026-10-11", "rpe", 3)
    assert db.get_wake_feelings("2026-10-09", "2026-10-12") == {"2026-10-10": 5}


def test_more_button_takes_an_exact_typed_drink_count(pg):
    today = quality.today().isoformat()
    assert checkin.parse(f"ci:{today}:alcohol_units:more") == (today, "alcohol_units", "more")
    assert checkin.parse(f"ci:{today}:rpe:more") is None
    assert checkin.parse_count("5") == 5.0 and checkin.parse_count("4,5") == 4.5
    assert checkin.parse_count("abc") is None and checkin.parse_count("31") is None and checkin.parse_count("-1") is None

    ctx = CTX()
    q = _query(f"ci:{today}:alcohol_units:more")
    asyncio.run(bot.checkin_answer(q, q.data, ctx))
    assert ctx.user_data["checkin_typed"]["field"] == "alcohol_units"
    assert db.get_checkin(today) is None                              # nothing saved until the number arrives

    pending = ctx.user_data["checkin_typed"]
    asyncio.run(bot._finish_checkin_step(pending["message"].edit_text, pending["day"], pending["field"], 6.0))
    assert db.get_checkin(today)["alcohol_units"] == 6.0
    assert "Caffeine" in q.message.edit_text.call_args.args[0]
    alcohol = [l for l in db.get_activity_logs(today) if l.get("tag") == "alcohol"]
    assert len(alcohol) == 1 and alcohol[0]["value"] == 6.0
