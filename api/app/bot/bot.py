import os
import sys
import json
import logging
import html
import subprocess
from pathlib import Path
from datetime import datetime, date, timedelta, time as dtime
from telegram import (
    Update,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
# httpx logs full Telegram Bot API URLs, which include the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)

import asyncio

from app import attachments, backup_status, money, reminders
from app.bot import analytics, anomaly as anomaly_detector, checkin, coaching, quit_tracker, reports, training_plan
from app.bot import store as db
from app.health import quality

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")  # NEVER hardcode a fallback here — this file is in a PUBLIC repo
AUTHORIZED_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def is_authorized(chat_id: int) -> bool:
    if not AUTHORIZED_CHAT_ID:
        return False
    return str(chat_id) == str(AUTHORIZED_CHAT_ID)

async def check_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id:
        return False
    if not AUTHORIZED_CHAT_ID:
        if update.message:
            await update.message.reply_text(
                f"⚠️ Bot is unconfigured.\n"
                f"To authorize this chat, please add this line to your `.env` file:\n"
                f"`TELEGRAM_CHAT_ID={chat_id}`\n"
                f"Then restart the bot."
            )
        return False
    if not is_authorized(chat_id):
        if update.message:
            await update.message.reply_text("❌ Access Denied: Unauthorized User.")
        elif update.callback_query:
            await update.callback_query.answer("❌ Access Denied", show_alert=True)
        return False
    return True

def reply_target(update: Update):
    """The message to reply to: the command itself, or the message holding the tapped button."""
    return update.message or update.callback_query.message

# ---------- BUTTON MENUS ----------

# Persistent keyboard under the text box. Tapping a key sends its label as text,
# which text_message_handler routes to the matching command instead of a note.
KEYBOARD_BUTTONS = {
    "🧘 Urge": "urge",
    "🔥 Streak": "streak",
    "💥 Master": "master",
    "✍️ Log": "log",
    "📋 Notes": "notes",
    "🙂 Mood": "mood",
    "💪 Gym": "gym",
    "📊 Health": "health",
    "🔄 Sync": "sync",
    "🏠 Menu": "menu",
}

def get_reply_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["🧘 Urge", "🔥 Streak", "💥 Master"],
            ["✍️ Log", "📋 Notes", "🙂 Mood"],
            ["💪 Gym", "📊 Health", "🔄 Sync", "🏠 Menu"],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Type a note, or tap a button",
    )

def get_home_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🧘 Urge Resisted", callback_data="cmd:urge"),
            InlineKeyboardButton("🔥 Streak & My Data", callback_data="cmd:streak"),
        ],
        [
            InlineKeyboardButton("✍️ Log Habit / Note", callback_data="cmd:log"),
            InlineKeyboardButton("📋 Recent Notes", callback_data="cmd:notes"),
        ],
        [
            InlineKeyboardButton("💥 Master (slip)", callback_data="cmd:master"),
            InlineKeyboardButton("🙂 Mood & Energy", callback_data="cmd:mood"),
        ],
        [
            InlineKeyboardButton("💭 My Reasons (Why)", callback_data="cmd:why"),
            InlineKeyboardButton("🗑 Fix a Mistake", callback_data="cmd:undo"),
        ],
        [
            InlineKeyboardButton("🔄 Sync Garmin", callback_data="cmd:sync"),
            InlineKeyboardButton("📊 Health", callback_data="cmd:health"),
        ],
        [
            InlineKeyboardButton("❓ Status", callback_data="cmd:status"),
            InlineKeyboardButton("📋 Action Plan", callback_data="cmd:actionplan"),
        ],
        [
            InlineKeyboardButton("🧠 Insights", callback_data="cmd:insights"),
            InlineKeyboardButton("🫁 SpO2", callback_data="cmd:spo2"),
        ],
        [
            InlineKeyboardButton("🚨 Alerts", callback_data="cmd:alerts"),
            InlineKeyboardButton("💪 Gym", callback_data="cmd:gym"),
        ],
        [
            InlineKeyboardButton("📈 Recovery", callback_data="cmd:recover"),
            InlineKeyboardButton("📝 Weekly Recap", callback_data="cmd:week"),
        ],
        [
            InlineKeyboardButton("📦 Export CSV", callback_data="cmd:export"),
        ],
    ])

HOME_TEXT = "🏠 <b>Hermes Health Coach</b>\n\nTap a button below, or type any message to log it as a free note."

# ---------- COMMAND HANDLERS ----------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    welcome_text = (
        "🏋️ **Welcome to Hermes Health Coach Bot!**\n\n"
        "Use the buttons below the text box, or /menu for every feature.\n\n"
        "Here are the available commands:\n"
        "🏠 /menu - Tap-to-use menu of every feature\n"
        "🔥 /streak - Master-free streak & your own before/after data\n"
        "🧘 /urge - Log an urge you resisted\n"
        "🙂 /mood - Rate today's mood & energy\n"
        "💭 /why - Your reasons for quitting, shown when an urge hits\n"
        "🗑 /undo - Fix a mislog: delete a recent entry\n"
        "🔄 /sync - Smart sync Garmin data (e.g. `/sync` or `/sync 7`)\n"
        "✍️ /log - Interactive daily activity & unholy habit logger\n"
        "💥 /master - Pause & think, then log a slip if it happened (`/master 2` logs directly)\n"
        "📊 /health - Today's health metrics snapshot\n"
        "🧠 /insights - Biometric intelligence & HRV baseline bands\n"
        "🫁 /spo2 - Nocturnal SpO2 & desaturation drops analysis\n"
        "🚨 /alerts - Check active health anomaly warnings\n"
        "📋 /notes - View your recent logged habits & notes\n"
        "💪 /gym - Today's workout, adjusted to your readiness, sleep & HRV\n"
        "📈 /recover - Recorded recovery observations\n"
        "📝 /week - Latest AI coaching weekly summary\n"
        "📋 /actionplan - Latest forward-looking action plan & watch-list\n"
        "☀️ /feeling - Rate how you woke up, 1 to 5 (`/feeling 4`)\n"
        "📦 /export - Daily metrics, journal & habits as CSV (`/export 30` or `/export all`)\n"
        "❓ /status - Quick biometric readiness update\n\n"
        "💡 *Tip: You can also send me any plain text message to log a quick Free Note!*"
    )
    authorized = False
    if not AUTHORIZED_CHAT_ID:
        welcome_text += (
            f"\n⚠️ **Action Required**:\n"
            f"To authorize this bot, add `TELEGRAM_CHAT_ID={chat_id}` to your `.env` file."
        )
    elif not is_authorized(chat_id):
        welcome_text += "\n❌ You are not authorized to use this bot."
    else:
        welcome_text += "\n✅ You are authorized!"
        authorized = True

    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_reply_keyboard() if authorized else None,
    )
    if authorized:
        await update.message.reply_text(HOME_TEXT, reply_markup=get_home_keyboard(), parse_mode="HTML")

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    await reply_target(update).reply_text(HOME_TEXT, reply_markup=get_home_keyboard(), parse_mode="HTML")

async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    frame = await asyncio.to_thread(db.get_df, 28)
    text = coaching.render(coaching.build_evidence(frame))
    for offset in range(0, len(text), 3900):
        await reply_target(update).reply_text(text[offset:offset+3900])


def gym_state():
    """Today's plan and the week projection from logged sessions, Garmin activities and today's metrics."""
    today = quality.today()
    activities = db.get_activities_df(days=60)
    trained = training_plan.trained_sessions(
        db.get_training_logs(60),
        [] if activities is None or activities.empty else activities.to_dict("records"),
    )
    frame = db.get_df(1)
    row = None if frame is None or frame.empty else frame.iloc[-1].to_dict()
    plan = training_plan.plan_today(trained, today, row)
    return today, plan, training_plan.plan_week(trained, today, plan)


def gym_keyboard(plan):
    buttons = [InlineKeyboardButton("📅 This week", callback_data="gym:week")]
    # A session done on a rest/recovery day still happened, so it can be logged,
    # but the button doesn't read as an instruction to train.
    rows = [buttons]
    if plan["action"] == "train":
        rows.insert(0, [InlineKeyboardButton("✅ Done — log session", callback_data="gym:done")])
    elif plan["action"] in ("rest", "recover"):
        rows.insert(0, [InlineKeyboardButton("🏋️ Trained anyway — log it", callback_data="gym:done")])
    # Logged the wrong one, or did a different session than planned.
    buttons.insert(0, InlineKeyboardButton("🔄 Did a different session", callback_data="gym:pick"))
    return InlineKeyboardMarkup(rows)


def session_picker():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(x["name"], callback_data=f"gym:did:{x['key']}")] for x in training_plan.SESSIONS]
    )


def undo_keyboard(log_id: int, *extra_rows):
    return InlineKeyboardMarkup([*extra_rows, [InlineKeyboardButton("↩️ Undo — logged by mistake", callback_data=f"del:{log_id}")]])


def describe_log(entry: dict) -> str:
    """Short label for an entry, e.g. '💥 Master (1) · 09-25 23:05'."""
    category, tag, note = entry.get("category"), str(entry.get("tag", "")), str(entry.get("note") or "")
    if category == "training":
        what = tag.replace("_", " ").title()
    elif category in ("free_note", "quit_reason") and note:
        what = note if len(note) <= 24 else note[:23] + "…"
    else:
        what = tag.replace("_", " ").title()
        if isinstance(entry.get("value"), (int, float)):
            what += f" ({entry['value']:g})"
    stamp = str(entry.get("timestamp") or entry.get("date"))[5:16]
    return f"{log_icon(entry)} {what} · {stamp}"


async def undo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists the latest entries with a delete button each, to fix mislogs."""
    if not await check_auth(update, context):
        return
    logs = await asyncio.to_thread(db.get_activity_logs, None, 8)
    if not logs:
        await reply_target(update).reply_text("Nothing logged yet.")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🗑 {describe_log(l)}", callback_data=f"del:{l['id']}")] for l in logs
    ])
    await reply_target(update).reply_text(
        "🗑 <b>Fix a mistake</b>\nTap an entry to delete it. Newest first:",
        reply_markup=keyboard, parse_mode="HTML")


async def gym_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    today, plan, _ = await asyncio.to_thread(gym_state)
    await reply_target(update).reply_text(
        training_plan.render_today(plan, today), reply_markup=gym_keyboard(plan), parse_mode="HTML")


async def week_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    report = await asyncio.to_thread(reports.ensure_weekly_report)
    text = report["report_text"] if report else "No verified source data yet, so there is nothing to recap. Tap 🔄 Sync first."
    for offset in range(0, len(text), 3900):
        await reply_target(update).reply_text(text[offset:offset+3900])


async def actionplan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return

    plan = await asyncio.to_thread(reports.ensure_action_plan)
    if not plan:
        await reply_target(update).reply_text(
            "📋 No action plan yet: there is no verified source data to base one on. Tap 🔄 Sync first."
        )
        return

    header = f"📋 **Action Plan** ({plan.get('period_start', '')} to {plan.get('period_end', '')})\n"
    if plan.get("headline"):
        header += f"_{plan['headline']}_\n"
    body = f"{header}\n{plan['plan_text']}"

    # Split message if it exceeds Telegram's 4096 char limit
    if len(body) > 4000:
        for chunk in [body[i:i+4000] for i in range(0, len(body), 4000)]:
            await reply_target(update).reply_text(chunk, parse_mode="Markdown")
    else:
        await reply_target(update).reply_text(body, parse_mode="Markdown")

async def recover_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    frame = await asyncio.to_thread(db.get_df, 28)
    text = coaching.render(coaching.build_evidence(frame))
    for offset in range(0, len(text), 3900):
        await reply_target(update).reply_text(text[offset:offset+3900])


async def spo2_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    frame = await asyncio.to_thread(db.get_df, 1)
    if frame.empty:
        await reply_target(update).reply_text("No recorded data is available.")
        return
    row = frame.iloc[-1]
    epochs = await asyncio.to_thread(db.get_spo2_epochs_df, row["date"])
    state = await asyncio.to_thread(db.get_spo2_quality, row["date"])
    burden = analytics.calculate_hypoxic_burden(epochs)
    text = (f"Garmin oxygen observations: {row['date']}\n"
            f"Daily average: {quality.number(row.get('spo2_avg')) if quality.number(row.get('spo2_avg')) is not None else 'unavailable'}%\n"
            f"Daily minimum: {quality.number(row.get('spo2_min')) if quality.number(row.get('spo2_min')) is not None else 'unavailable'}%\n"
            f"Verified timestamped samples: {len(epochs)}\n"
            f"Detail: {state['availability']}. {state['reason']}\n")
    if burden["observed_seconds"]:
        text += (f"Accepted intervals: {burden['observed_seconds']/60:.1f} minutes; "
                 f"estimated time below 90%: {burden['t90_minutes']:.2f} minutes.\n"
                 "Intervals hold a sample until the next, at most 120 seconds. Gaps are excluded.\n")
    text += "These samples do not establish whole-night coverage or a diagnosis. Summary values cannot locate exact drop times."
    await reply_target(update).reply_text(text)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    frame = await asyncio.to_thread(db.get_df, 28)
    text = coaching.render(coaching.build_evidence(frame))
    for offset in range(0, len(text), 3900):
        await reply_target(update).reply_text(text[offset:offset+3900])


async def sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return

    from app.bot import syncer as sync

    # Parse optional days argument (e.g. /sync 7)
    days = 3
    if context.args and len(context.args) > 0 and context.args[0].isdigit():
        days = min(60, max(1, int(context.args[0])))

    status_msg = await reply_target(update).reply_text(
        f"🔄 **Syncing Garmin Health data...**\n"
        f"Fetching rolling {days}-day window (Sleep, HRV, SpO2, Body Battery)...",
        parse_mode="Markdown"
    )

    try:
        # Run sync in thread pool to prevent blocking the async Telegram event loop
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, sync.smart_sync, days)

        synced = res.get("synced_dates", [])
        failed = res.get("failed_dates", [])

        # Fetch latest updated record
        df = db.get_df(limit=1)
        latest_text = ""
        if not df.empty:
            row = df.iloc[-1]
            latest_text = (
                f"\n\n📊 **Latest Record ({row['date']}):**\n"
                f"• **Readiness:** {row.get('training_readiness') or '—'}/100\n"
                f"• **HRV:** {row.get('hrv_last_night') or '—'} ms (Avg: {row.get('hrv_weekly_avg') or '—'})\n"
                f"• **Sleep Score:** {row.get('sleep_score') or '—'}/100\n"
                f"• **SpO2 Avg/Min:** {row.get('spo2_avg') or '—'}% / {row.get('spo2_min') or '—'}%"
            )

        resp_text = (
            f"Garmin sync result: {res.get('status', 'unknown')}\n"
            f"• **Days Synced:** {len(synced)}/{days} ({', '.join(synced[:5])}{'...' if len(synced)>5 else ''})"
            f"{latest_text}"
        )
        if failed or res.get("warnings"):
            resp_text += f"\n⚠️ *Note: {len(failed)} dates failed; {len(res.get('warnings', {}))} dates have source warnings.*"

        await status_msg.edit_text(resp_text, parse_mode="Markdown")
    except Exception as e:
        await status_msg.edit_text(f"❌ **Sync Failed:** {str(e)}", parse_mode="Markdown")

# ---------- ACTIVITY & HABIT LOGGING HANDLERS ----------

LOG_ICONS = {"master": "💥", "urge_resisted": "🧘", "clean_day": "✅", "mood": "🙂", "energy": "⚡", "reason": "💭"}

def log_icon(entry: dict) -> str:
    if entry.get("category") == "training":
        return "🏋️"
    return LOG_ICONS.get(entry.get("tag")) or ("😈" if entry.get("category") == "unholy_habit" else "📝")

def get_main_log_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("😈 Log Unholy Habit", callback_data="menu_unholy"),
            InlineKeyboardButton("📝 Write Free Note", callback_data="menu_note")
        ],
        [
            InlineKeyboardButton("📋 View Today's Logs", callback_data="menu_view_today")
        ],
        [
            InlineKeyboardButton("🏠 All Features", callback_data="cmd:menu")
        ]
    ])

def get_unholy_habits_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🍷 Alcohol", callback_data="unholy_alcohol_menu"),
            InlineKeyboardButton("🍕 Late Meal", callback_data="log_habit:late_meal:1:Late Heavy Meal")
        ],
        [
            InlineKeyboardButton("☕ Late Caffeine (>2PM)", callback_data="log_habit:late_caffeine:1:Late Caffeine"),
            InlineKeyboardButton("📱 Late Screen Time", callback_data="log_habit:late_screen:1:Late Screen Time")
        ],
        [
            InlineKeyboardButton("🚬 Nicotine / Vape", callback_data="log_habit:nicotine:1:Nicotine"),
            InlineKeyboardButton("⚡ High Mental Stress", callback_data="log_habit:mental_stress:1:High Mental Stress")
        ],
        [
            InlineKeyboardButton("💥 Master", callback_data="cmd:master")
        ],
        [
            InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_main")
        ]
    ])

def get_alcohol_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🍺 1 Drink", callback_data="log_habit:alcohol:1:1 standard drink"),
            InlineKeyboardButton("🍷 2 Drinks", callback_data="log_habit:alcohol:2:2 standard drinks"),
            InlineKeyboardButton("🍾 3+ Drinks", callback_data="log_habit:alcohol:3:3+ drinks")
        ],
        [
            InlineKeyboardButton("🔙 Back to Habits", callback_data="menu_unholy")
        ]
    ])

async def master_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """💥 /master [qty] — log Master as its own category. No judgment, data only."""
    if not await check_auth(update, context):
        return
    if not context.args:
        # A bare tap or /master stops to think first; logging is one more tap.
        await reply_target(update).reply_text(
            await asyncio.to_thread(pause_text), reply_markup=pause_keyboard(), parse_mode="HTML")
        return
    # An unreadable count is rejected, never silently recorded as 1.
    qty = quality.number(context.args[0].replace(",", "."))
    if qty is None or qty <= 0:
        await reply_target(update).reply_text("Count must be a positive number, e.g. /master 2. Nothing was logged.")
        return
    today_str = quality.today().isoformat()
    log_id = db.log_activity(
        date_str=today_str,
        category="master",
        tag="master",
        note="",
        value=qty
    )
    await reply_target(update).reply_text(master_logged_text(qty, today_str),
                                          reply_markup=undo_keyboard(log_id), parse_mode="HTML")


def reasons_block() -> str:
    reasons = db.get_quit_reasons()
    if not reasons:
        return "💭 <i>No reasons saved yet. Add yours: /why I want more energy for my family</i>"
    return "💭 <b>Your reasons:</b>\n" + "\n".join(f"• {html.escape(r['note'])}" for r in reasons)


def pause_text() -> str:
    today = quality.today()
    logs = db.get_quit_logs()
    s = quit_tracker.summarize(logs, today)
    frame = db.get_df(120)
    rows = [] if frame is None or frame.empty else frame.to_dict("records")
    lines = ["⏸️ <b>Pause. Think twice.</b>\n"]
    streak = f"🔥 You're {days(s['current_streak'])} clean"
    if s["best_streak"] > s["current_streak"]:
        streak += f" — {days(s['best_streak'] - s['current_streak'])} away from your best ({days(s['best_streak'])})"
    lines.append(streak + ".")
    if s["urges_this_streak"]:
        lines.append(f"🧘 You've already beaten {s['urges_this_streak']} urge(s) this streak.")
    costs = quit_tracker.worse_after(quit_tracker.compare_next_day(logs, rows))
    if costs:
        lines.append("📊 <b>Your own data, the day after:</b>\n" + "\n".join(f"• {html.escape(c)}" for c in costs))
    lines.append("\n" + reasons_block())
    lines.append("\nIs this an urge right now, or did it already happen?")
    return "\n".join(lines)


def pause_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧘 It's an urge — help me through it", callback_data="cmd:urge")],
        [InlineKeyboardButton("📝 It already happened — log it", callback_data="quit:slip")],
    ])


URGE_FOLLOWUP_MINUTES = 15


def urge_followup_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ It passed", callback_data="urge:passed"),
        InlineKeyboardButton("😣 Still strong", callback_data="urge:strong"),
    ], [
        InlineKeyboardButton("❌ I gave in", callback_data="quit:slip"),
    ]])


async def urge_followup(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text=f"⏱️ <b>{URGE_FOLLOWUP_MINUTES} minutes later.</b> How's the urge now?",
        reply_markup=urge_followup_keyboard(), parse_mode="HTML",
    )


def schedule_urge_followup(context: ContextTypes.DEFAULT_TYPE, chat_id: int, minutes: int = URGE_FOLLOWUP_MINUTES):
    if context.job_queue is not None:
        context.job_queue.run_once(urge_followup, minutes * 60, chat_id=chat_id, name=f"urge_followup_{chat_id}")


STILL_STRONG_TIPS = (
    "Change your state right now — the urge feeds on staying put:\n"
    "• Stand up and go somewhere with other people, or outside\n"
    "• Cold shower, or splash cold water on your face\n"
    "• Push-ups until your arms burn\n"
    "• Phone in another room, screen off\n"
    "• Message a friend about anything at all"
)


async def why_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/why <reason> saves a reason; /why lists them; /why remove N deletes one."""
    if not await check_auth(update, context):
        return
    args = context.args or []
    if len(args) == 2 and args[0].lower() == "remove" and args[1].isdigit():
        reasons = db.get_quit_reasons()
        n = int(args[1])
        if 1 <= n <= len(reasons):
            db.delete_activity_log(reasons[n - 1]["id"])
            await reply_target(update).reply_text(f"Removed reason {n}.")
        else:
            await reply_target(update).reply_text(f"No reason number {n}. Send /why to see the list.")
        return
    text = " ".join(args).strip()
    if text:
        db.log_activity(date_str=quality.today().isoformat(), category=quit_tracker.REASON_CATEGORY,
                        tag="reason", note=text)
        await reply_target(update).reply_text(
            f"💭 Saved. You'll see this every time you tap 💥 Master or 🧘 Urge.\n\n{reasons_block()}",
            parse_mode="HTML")
        return
    reasons = db.get_quit_reasons()
    listing = "\n".join(f"{i}. {html.escape(r['note'])}" for i, r in enumerate(reasons, 1))
    await reply_target(update).reply_text(
        "💭 <b>Why you're quitting</b>\n\n"
        + (listing or "Nothing saved yet.")
        + "\n\nAdd one: <code>/why I want to feel proud of myself</code>\n"
          "Remove one: <code>/why remove 2</code>\n\n"
          "Write them in your own words. They're shown to you at the moment an urge hits.",
        parse_mode="HTML")


def days(n: int) -> str:
    return f"{n} day{'' if n == 1 else 's'}"


def master_logged_text(qty: float, today_str: str) -> str:
    text = f"💥 <b>Master logged</b> ({qty:g}) for <code>{today_str}</code>.\n"
    try:
        s = quit_tracker.summarize(db.get_quit_logs(), quality.today())
        text += "\nStreak restarts today."
        if s["best_streak"] > 0:
            text += f" Your best is <b>{days(s['best_streak'])}</b> — you can beat it."
        text += "\nNext time an urge hits, tap 🧘 Urge instead. It usually passes in 15–20 minutes."
    except Exception as e:
        logger.warning(f"Could not compute streak: {e}")
    return text


async def streak_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    logs = await asyncio.to_thread(db.get_quit_logs)
    frame = await asyncio.to_thread(db.get_df, 120)
    rows = [] if frame is None or frame.empty else frame.to_dict("records")
    text = (quit_tracker.render_streak(quit_tracker.summarize(logs, quality.today()))
            + "\n\n" + quit_tracker.render_comparison(quit_tracker.compare_next_day(logs, rows)))
    await reply_target(update).reply_text(text, parse_mode="HTML")


URGE_TIPS = (
    "Ride it out — urges peak and fade within 15–20 minutes:\n"
    "• Get up and leave the room you're in\n"
    "• Cold water on your face, or a cold shower\n"
    "• 20 push-ups or a 10-minute walk\n"
    "• Put the phone in another room\n"
    "• Type what triggered it (bored, stressed, tired, alone?) — it's saved as a note"
)


async def urge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    today = quality.today()
    log_id = db.log_activity(date_str=today.isoformat(), category=quit_tracker.CATEGORY,
                             tag=quit_tracker.URGE_TAG, note="", value=1)
    s = quit_tracker.summarize(db.get_quit_logs(), today)
    await reply_target(update).reply_text(
        f"🧘 <b>Urge resisted — that's a win.</b>\n"
        f"Streak: {days(s['current_streak'])} · {s['urges_this_streak']} urge(s) beaten this streak.\n\n"
        f"{URGE_TIPS}\n\n{reasons_block()}\n\n"
        f"<i>I'll check on you in {URGE_FOLLOWUP_MINUTES} minutes.</i>",
        reply_markup=undo_keyboard(log_id), parse_mode="HTML",
    )
    schedule_urge_followup(context, update.effective_chat.id)


def mood_keyboard(kind: str):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(label, callback_data=f"{kind}:{n}")
        for n, label in enumerate(["1 😞", "2 🙁", "3 😐", "4 🙂", "5 😄"], start=1)
    ]])


async def mood_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    await reply_target(update).reply_text(
        "🙂 <b>How is your mood today?</b> (1 = very low, 5 = great)",
        reply_markup=mood_keyboard("mood"), parse_mode="HTML",
    )


def checkin_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Clean today", callback_data="quit:clean"),
        InlineKeyboardButton("❌ I slipped", callback_data="quit:slip"),
    ]])


MORNING_SYNC_TIMEOUT = 180


async def morning_sync() -> str:
    """Syncs today from Garmin; returns a note for the message if data is still missing."""
    from app.bot import syncer as sync
    try:
        await asyncio.wait_for(asyncio.to_thread(sync.smart_sync, 1), MORNING_SYNC_TIMEOUT)
    except Exception as e:
        logger.warning(f"Morning pre-broadcast sync failed: {e}")
        return ("\n\n<i>I tried a fresh Garmin sync just now, but it didn't finish. "
                "Tap 🔄 Sync later for today's numbers.</i>")
    return ("\n\n<i>I synced Garmin just now and last night's data isn't there yet — "
            "your watch may not have synced to your phone. Open Garmin Connect, then tap 🔄 Sync.</i>")


async def morning_broadcast(context: ContextTypes.DEFAULT_TYPE):
    """Morning message: quit streak and today's workout, with the gym buttons."""
    today, plan, _ = await asyncio.to_thread(gym_state)
    sync_note = ""
    if plan["readiness"]["level"] == "unknown":
        # Last night's sleep/HRV/readiness isn't in yet: one on-demand sync of today only.
        sync_note = await morning_sync()
        today, plan, _ = await asyncio.to_thread(gym_state)
        if plan["readiness"]["level"] != "unknown":
            sync_note = ""
    try:
        s = quit_tracker.summarize(await asyncio.to_thread(db.get_quit_logs), today)
        streak = f"🔥 Master-free: <b>{days(s['current_streak'])}</b>"
        if s["best_streak"] > s["current_streak"]:
            streak += f" · best {days(s['best_streak'])}"
        streak += "\n\n"
    except Exception as e:
        logger.warning(f"Morning streak unavailable: {e}")
        streak = ""
    await context.bot.send_message(
        chat_id=AUTHORIZED_CHAT_ID,
        text="☀️ <b>Good morning</b>\n" + streak + training_plan.render_today(plan, today) + sync_note,
        reply_markup=gym_keyboard(plan), parse_mode="HTML",
    )


async def nightly_checkin(context: ContextTypes.DEFAULT_TYPE):
    """Evening check-in; skipped when today is already answered."""
    today = quality.today()
    s = quit_tracker.summarize(await asyncio.to_thread(db.get_quit_logs), today)
    if s["relapsed_today"] or s["clean_checked_today"]:
        return
    await context.bot.send_message(
        chat_id=AUTHORIZED_CHAT_ID,
        text=f"🌙 <b>Nightly check-in</b>\nStreak: {days(s['current_streak'])}. Were you Master-free today?",
        reply_markup=checkin_keyboard(), parse_mode="HTML",
    )


async def habit_checkin(context: ContextTypes.DEFAULT_TYPE):
    """Evening questions about the day; skipped when today already has answers."""
    today = quality.today().isoformat()
    row = await asyncio.to_thread(db.get_checkin, today)
    if row and any(row.get(f) is not None for f in checkin.FIELDS):   # the morning rating alone doesn't count
        return
    text, markup = checkin.question(today, 0)
    await context.bot.send_message(chat_id=AUTHORIZED_CHAT_ID, text=text, reply_markup=markup, parse_mode="HTML")


REMINDER_JOBS = {}   # filled below, once both coroutines exist


async def reminder_tick(context: ContextTypes.DEFAULT_TYPE):
    """Once a minute: send whichever web-configured reminders have come due."""
    now = datetime.now(quality.user_timezone())
    try:
        names = await asyncio.to_thread(reminders.due, now)
    except Exception as e:
        logger.warning(f"Reminder check failed: {e}")
        return
    if now.hour >= 9 and now.minute == 0:      # hourly, from 9am: one alert a day at most
        try:
            await backup_watch(context)
        except Exception as e:
            logger.warning(f"Backup check failed: {e}")
    for name in names:
        await asyncio.to_thread(reminders.mark_sent, name, now.date().isoformat())   # first, so it never repeats
        try:
            await REMINDER_JOBS[name](context)
        except Exception as e:
            logger.warning(f"Reminder {name} failed: {e}")


async def backup_watch(context: ContextTypes.DEFAULT_TYPE):
    """Tell the owner once a day when the off-box backup needs attention."""
    state = await asyncio.to_thread(backup_status.status)
    if not state["needs_attention"] or state["state"] == "never":
        return
    if not await asyncio.to_thread(reminders.claim_daily, "backup_alert", quality.today().isoformat()):
        return
    text = f"⚠️ <b>Backup needs attention</b>\n{html.escape(state['headline'])}"
    if state.get("hint"):
        text += f"\n{html.escape(state['hint'])}"
    await context.bot.send_message(chat_id=AUTHORIZED_CHAT_ID, text=text, parse_mode="HTML")


async def morning_feeling(context: ContextTypes.DEFAULT_TYPE):
    """Ask how you woke up; skipped when today is already rated. One message, no reminder."""
    today = quality.today().isoformat()
    row = await asyncio.to_thread(db.get_checkin, today)
    if row and row.get("wake_feeling") is not None:
        return
    await context.bot.send_message(chat_id=AUTHORIZED_CHAT_ID, text=checkin.FEELING_TEXT,
                                   reply_markup=checkin.feeling_keyboard(today), parse_mode="HTML")


REMINDER_JOBS.update({"morning_feeling": morning_feeling})


async def feeling_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    target = reply_target(update)
    today = quality.today().isoformat()
    if context.args:
        if context.args[0] not in {"1", "2", "3", "4", "5"}:
            await target.reply_text("Usage: /feeling [1-5]   (1 awful, 5 great)")
            return
        await asyncio.to_thread(db.save_checkin_answer, today, "wake_feeling", int(context.args[0]))
        await target.reply_text(f"☀️ Waking feeling saved: {checkin.FEELING_NAMES[int(context.args[0])]}")
        return
    await target.reply_text(checkin.FEELING_TEXT, reply_markup=checkin.feeling_keyboard(today), parse_mode="HTML")


async def feeling_answer(query, data: str) -> None:
    parsed = checkin.parse_feeling(data)
    if not parsed:
        return
    day, rating = parsed
    await asyncio.to_thread(db.save_checkin_answer, day, "wake_feeling", rating)
    await query.edit_message_text(f"☀️ Waking feeling saved: <b>{checkin.FEELING_NAMES[rating]}</b> · {day}",
                                  parse_mode="HTML")


REMINDER_JOBS.update({"evening_checkin": habit_checkin})


async def checkin_answer(query, data: str) -> None:
    """Save the tapped answer, mirror a "yes" into the journal, and show the next question or the summary."""
    parsed = checkin.parse(data)
    if not parsed:
        return
    day, field, raw = parsed
    if raw is not None:
        await asyncio.to_thread(db.save_checkin_answer, day, field, float(raw))
        tag = checkin.habit_tag(field)
        if tag and float(raw) > 0:
            existing = await asyncio.to_thread(db.get_activity_logs, day)
            if not any(l.get("category") == "unholy_habit" and l.get("tag") == tag for l in existing):
                await asyncio.to_thread(db.log_activity, date_str=day, category="unholy_habit", tag=tag,
                                        note="from evening check-in", value=float(raw))
    nxt = checkin.step_index(field) + 1
    if nxt < len(checkin.STEPS):
        text, markup = checkin.question(day, nxt)
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        return
    row = await asyncio.to_thread(db.get_checkin, day)
    await query.edit_message_text(f"✅ <b>Check-in saved</b> · {day}\n\n{checkin.summary(row)}", parse_mode="HTML")


def bank_import_enabled() -> bool:
    return money.enabled()


def run_statement_import(path: str) -> dict:
    return money.run_statement_import(path)


WEEKLY_REVIEW_DAY = 0  # python-telegram-bot numbers days 0-6 as Sunday-Saturday


async def weekly_review_nudge(context: ContextTypes.DEFAULT_TYPE):
    """Sunday evening: point to the weekly review page. Sends nothing without a configured address."""
    base = os.environ.get("WEB_URL", "").strip().rstrip("/")
    markup = None
    if base:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("Open the review", url=f"{base}/review")]])
    await context.bot.send_message(
        chat_id=AUTHORIZED_CHAT_ID,
        text=("📝 <b>Your weekly review is ready.</b>\n"
              "It takes about five minutes: the week in numbers, your own notes, and one change for next week."
              + ("" if base else "\n\n<i>Set WEB_URL to get a link here.</i>")),
        reply_markup=markup, parse_mode="HTML",
    )


ATTACH_DAYS = (("Yesterday", 1), ("2 days ago", 2), ("3 days ago", 3))


async def attachment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A photo or file sent to the bot becomes a journal entry; the caption is the note."""
    if not await check_auth(update, context):
        return
    message = update.message
    if not message:
        return
    if message.photo:
        item, name = message.photo[-1], None          # the largest size Telegram made
    elif message.document:
        item, name = message.document, message.document.file_name
    else:
        return
    if item.file_size and item.file_size > attachments.MAX_BYTES:
        await message.reply_text("That file is larger than 10 MB, so it wasn't saved.")
        return
    try:
        tg_file = await item.get_file()
        data = bytes(await tg_file.download_as_bytearray())
        prepared = await asyncio.to_thread(attachments.prepare, data, name)
    except attachments.Rejected as exc:
        await message.reply_text(f"Not saved: {exc}")
        return
    except Exception as exc:
        logger.warning(f"Attachment download failed: {exc}")
        await message.reply_text("Couldn't fetch that file from Telegram. Try sending it again.")
        return

    today = quality.today().isoformat()
    log_id = await asyncio.to_thread(db.log_activity, date_str=today, category="free_note", tag="note",
                                     note=(message.caption or "").strip()[:2000])
    try:
        saved = await asyncio.to_thread(attachments.save, log_id, prepared)
    except attachments.Rejected as exc:
        await asyncio.to_thread(db.delete_activity_log, log_id)
        await message.reply_text(f"Not saved: {exc}")
        return
    size = f"{saved['bytes'] / 1024 / 1024:.1f} MB" if saved["bytes"] >= 1024 * 1024 else f"{saved['bytes'] // 1024} KB"
    extra = "" if prepared["mime"] == attachments.PDF_MIME else ", location data removed"
    day_row = [InlineKeyboardButton(label, callback_data=f"attday:{log_id}:{n}") for label, n in ATTACH_DAYS]
    await message.reply_text(
        f"📎 <b>Saved to your journal</b>\n{html.escape(saved['filename'])} · {size}{extra}\n"
        f"<code>{today}</code>" + (f"\n<i>{html.escape(message.caption.strip()[:200])}</i>" if message.caption else ""),
        reply_markup=undo_keyboard(log_id, day_row), parse_mode="HTML")


async def attachment_day(query, data: str) -> None:
    """`attday:<log_id>:<days_ago>`: move a just-saved attachment entry to an earlier day."""
    try:
        _, log_id, days_ago = data.split(":")
        log_id, days_ago = int(log_id), int(days_ago)
    except ValueError:
        return
    if not 1 <= days_ago <= 7:
        return
    day = (quality.today() - timedelta(days=days_ago)).isoformat()
    if await asyncio.to_thread(db.set_log_date, log_id, day):
        await query.edit_message_reply_markup(reply_markup=undo_keyboard(log_id))
        await query.message.reply_text(f"📅 Moved to {day}.")
    else:
        await query.message.reply_text("That entry is gone.")


async def xlsx_statement_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Import an ABA .xlsx bank statement into Sure (auto bank-statement import)."""
    if not await check_auth(update, context):
        return
    doc = update.message.document
    fname = (doc.file_name or "").lower()
    if not fname.endswith(".xlsx"):
        await update.message.reply_text("Send an ABA bank statement (.xlsx) to import into Sure.")
        return
    if not bank_import_enabled():
        await update.message.reply_text(
            "🏦 Bank statement import is turned off on this server.\n"
            "To turn it on, set ENABLE_BANK_IMPORT=1 in the bot's environment file and restart the bot.")
        return
    path = f"/tmp/statement_{doc.file_id[:10]}.xlsx"
    try:
        f = await context.bot.get_file(doc.file_id)
        await f.download_to_drive(path)
    except Exception as e:
        await update.message.reply_text(f"❌ Could not download file: {e}")
        return
    await update.message.reply_text("📥 Importing statement into Sure…")
    try:
        summary = await asyncio.to_thread(run_statement_import, path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if "error" in summary:
        await update.message.reply_text(f"❌ Import failed: {summary['error']}")
    else:
        await update.message.reply_text(
            f"✅ <b>Sure import done</b>\n"
            f"• Imported: <b>{summary.get('rows_imported', 0)}</b>\n"
            f"• Already existed (skipped): {summary.get('rows_skipped_dupe', 0)}\n"
            f"• Failed: {summary.get('rows_failed', 0)}",
            parse_mode="HTML",
        )


async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    today_str = quality.today().isoformat()
    text = (
        f"✍️ <b>Daily Activity & Habit Logger</b>\n"
        f"📅 Date: <code>{today_str}</code>\n\n"
        "Choose an action below to log unholy habits, sleep disruptors, or custom free notes:"
    )
    await reply_target(update).reply_text(text, reply_markup=get_main_log_keyboard(), parse_mode="HTML")

async def notes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    logs = db.get_activity_logs(limit=15)
    if not logs:
        await reply_target(update).reply_text("📋 No activity logs or habits recorded yet. Use /log to add one!", parse_mode="HTML")
        return
    
    msg_lines = ["📋 <b>Recent Activity & Habit Logs</b>\n"]
    for l in logs:
        icon = log_icon(l)
        tag_title = l.get("tag", "").replace("_", " ").title()
        val = f" ({l['value']})" if l.get("value") is not None else ""
        note = f"\n   <i>{html.escape(str(l['note']))}</i>" if l.get("note") else ""
        msg_lines.append(f"• <code>{l['date']}</code> {icon} <b>{tag_title}</b>{val}{note}")
    
    await reply_target(update).reply_text("\n".join(msg_lines), parse_mode="HTML")

async def insights_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    frame = await asyncio.to_thread(db.get_df, 28)
    text = coaching.render(coaching.build_evidence(frame))
    for offset in range(0, len(text), 3900):
        await reply_target(update).reply_text(text[offset:offset+3900])


async def alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    
    anomalies = anomaly_detector.scan_daily_anomalies()
    recent_db_alerts = db.get_recent_alerts(limit=5)
    
    if not anomalies and not recent_db_alerts:
        await reply_target(update).reply_text("No active observation flags in the available recent data. Missing or unsynced measurements cannot be assessed.")
        return
    
    msg_lines = ["🚨 <b>Health Anomaly & Safety Monitor</b>\n"]
    if anomalies:
        msg_lines.append("<b>Current Active Flags:</b>")
        for a in anomalies:
            icon = "🛑" if a["severity"] == "CRITICAL" else "⚠️"
            msg_lines.append(f"{icon} <b>{html.escape(a['title'])}</b>\n{html.escape(a['message'])}\n")
            
    if recent_db_alerts:
        msg_lines.append("\n<b>Recent Historical Alerts:</b>")
        for alert in recent_db_alerts[:3]:
            msg_lines.append(f"• <code>{alert['timestamp']}</code> [{alert['severity']}] {html.escape(alert['alert_type'])}")
            
    await reply_target(update).reply_text("\n".join(msg_lines), parse_mode="HTML")

# ---------- DIRECT NOTE & HABIT COMMANDS ----------

async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    note_text = " ".join(context.args).strip() if context.args else ""
    if not note_text:
        await update.message.reply_text("✍️ Please provide note content. Example:\n<code>/note Sore quads from heavy squats</code>", parse_mode="HTML")
        return
    today_str = quality.today().isoformat()
    log_id = db.log_activity(date_str=today_str, category="free_note", tag="note", note=note_text)
    await update.message.reply_text(
        f"📝 <b>Free Note Logged!</b>\n"
        f"📅 Date: <code>{today_str}</code>\n"
        f"✍️ Note: <i>{html.escape(note_text)}</i>",
        reply_markup=undo_keyboard(log_id), parse_mode="HTML"
    )

async def habit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    if not context.args:
        await update.message.reply_text(
            "😈 <b>Log an Unholy Habit via Command:</b>\n\n"
            "Usage: <code>/habit &lt;name&gt; [units] [details]</code>\n\n"
            "Examples:\n"
            "• <code>/habit alcohol 2 two pints IPA</code>\n"
            "• <code>/habit late_meal 1 pizza at 11pm</code>\n"
            "• <code>/habit late_caffeine 1 espresso at 4pm</code>\n"
            "• <code>/habit stress 1 high mental fatigue</code>",
            parse_mode="HTML"
        )
        return
    tag = context.args[0].lower().replace(" ", "_")
    val = 1.0
    note_start = 1
    if len(context.args) > 1:
        try:
            val = float(context.args[1])
            note_start = 2
        except ValueError:
            val = 1.0
            note_start = 1
    note_text = " ".join(context.args[note_start:]).strip()
    today_str = quality.today().isoformat()
    log_id = db.log_activity(date_str=today_str, category="unholy_habit", tag=tag, note=note_text, value=val)
    tag_title = tag.replace("_", " ").title()
    await update.message.reply_text(
        f"✅ <b>Unholy Habit Logged!</b>\n\n"
        f"😈 <b>Habit:</b> {tag_title} ({val})\n"
        f"📅 <b>Date:</b> <code>{today_str}</code>\n"
        f"📝 <b>Details:</b> {html.escape(note_text) if note_text else 'Logged'}",
        reply_markup=undo_keyboard(log_id), parse_mode="HTML"
    )

# Handle text messages (free note logger)
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    
    if not update.message or not update.message.text:
        return
        
    text = update.message.text.strip()
    if text.startswith("/"):
        return

    # A tap on the persistent keyboard is a command, not a note.
    if text in KEYBOARD_BUTTONS:
        await COMMANDS[KEYBOARD_BUTTONS[text]](update, context)
        return

    today_str = quality.today().isoformat()
    log_id = db.log_activity(
        date_str=today_str,
        category="free_note",
        tag="note",
        note=text
    )
    
    await update.message.reply_text(
        f"📝 <b>Free Note Logged!</b>\n"
        f"📅 Date: <code>{today_str}</code>\n"
        f"✍️ Note: <i>{html.escape(text)}</i>\n\n"
        f"Available in your activity notes. Coaching does not infer a recovery score from notes.",
        reply_markup=undo_keyboard(log_id), parse_mode="HTML"
    )

# Callback Query Handler for inline buttons
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"Callback answer warning: {e}")
        
    if not await check_auth(update, context):
        return
        
    data = query.data
    today_str = quality.today().isoformat()
    
    try:
        if data.startswith("cmd:"):
            handler = COMMANDS.get(data[len("cmd:"):])
            if handler:
                await handler(update, context)
            return

        if data.startswith("attday:"):
            await attachment_day(query, data)
            return

        if data.startswith("mf:"):
            await feeling_answer(query, data)
            return

        if data.startswith("ci:"):
            await checkin_answer(query, data)
            return

        if data.startswith("export:"):
            window = _export_window(data[len("export:"):])
            if window is not False:
                await send_export(query.message, window)
            return

        if data == "quit:clean":
            s = quit_tracker.summarize(db.get_quit_logs(), quality.today())
            if s["relapsed_today"]:
                text = ("Today already has a Master log, so it can't be marked clean. "
                        "If that entry was a mistake, remove it with /undo.")
                markup = None
            else:
                markup = None
                if not s["clean_checked_today"]:
                    markup = undo_keyboard(db.log_activity(date_str=today_str, category=quit_tracker.CATEGORY,
                                                           tag=quit_tracker.CLEAN_TAG, note="", value=0))
                text = f"✅ <b>Clean day logged.</b> Streak: {days(s['current_streak'])}. Keep going."
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
            await query.message.reply_text("🙂 <b>How was your mood today?</b> (1 = very low, 5 = great)",
                                           reply_markup=mood_keyboard("mood"), parse_mode="HTML")
            return

        if data == "quit:slip":
            log_id = db.log_activity(date_str=today_str, category="master", tag="master", note="", value=1.0)
            await query.edit_message_text(master_logged_text(1.0, today_str),
                                          reply_markup=undo_keyboard(log_id), parse_mode="HTML")
            await query.message.reply_text("🙂 <b>How was your mood today?</b> (1 = very low, 5 = great)",
                                           reply_markup=mood_keyboard("mood"), parse_mode="HTML")
            return

        if data == "gym:done" or data.startswith("gym:did:"):
            today, plan, _ = await asyncio.to_thread(gym_state)
            session = plan["session"]
            if data.startswith("gym:did:"):
                session = training_plan.SESSION_BY_KEY.get(data[len("gym:did:"):], session)
            if plan["action"] == "done" and data == "gym:done":
                await query.message.reply_text(
                    f"Already logged today: <b>{html.escape(session['name'])}</b>. "
                    "Wrong one? Tap 🔄 Did a different session.", parse_mode="HTML")
                return
            # One session per day: a correction replaces what was logged earlier today.
            replaced = db.delete_training_logs(today_str)
            log_id = db.log_activity(date_str=today_str, category=training_plan.TRAINING_CATEGORY,
                                     tag=session["key"], note=session["name"], value=1)
            await query.message.reply_text(
                f"✅ <b>{html.escape(session['name'])}</b> logged for <code>{today_str}</code>"
                f"{' (replaced the earlier entry)' if replaced else ''}. "
                f"Eat protein and sleep well tonight. 💪",
                reply_markup=undo_keyboard(log_id), parse_mode="HTML")
            return

        if data == "gym:pick":
            await query.message.reply_text("🔄 <b>Which session did you do today?</b>",
                                           reply_markup=session_picker(), parse_mode="HTML")
            return

        if data.startswith("del:"):
            entry = db.get_activity_log(int(data[len("del:"):]))
            if not entry:
                await query.edit_message_text("Already removed.")
                return
            db.delete_activity_log(entry["id"])
            await query.edit_message_text(f"↩️ Removed: {html.escape(describe_log(entry))}", parse_mode="HTML")
            return

        if data == "gym:week":
            _, _, week = await asyncio.to_thread(gym_state)
            await query.message.reply_text(training_plan.render_week(week), parse_mode="HTML")
            return

        if data == "urge:passed":
            s = quit_tracker.summarize(db.get_quit_logs(), quality.today())
            await query.edit_message_text(
                f"💪 <b>You rode it out.</b> Streak intact: {days(s['current_streak'])}. "
                "Every urge you beat makes the next one weaker.", parse_mode="HTML")
            return

        if data == "urge:strong":
            await query.edit_message_text(
                f"😣 <b>Hang on — it will pass.</b>\n\n{STILL_STRONG_TIPS}\n\n{reasons_block()}\n\n"
                f"<i>I'll check again in 10 minutes.</i>", parse_mode="HTML")
            schedule_urge_followup(context, query.message.chat.id, 10)
            return

        if data.startswith(("mood:", "energy:")):
            kind, score = data.split(":")
            db.log_activity(date_str=today_str, category=quit_tracker.WELLBEING_CATEGORY,
                            tag=kind, note="", value=float(score))
            if kind == "mood":
                await query.edit_message_text(
                    f"Mood {score}/5 saved.\n⚡ <b>And your energy?</b> (1 = drained, 5 = full)",
                    reply_markup=mood_keyboard("energy"), parse_mode="HTML")
            else:
                await query.edit_message_text(f"Energy {score}/5 saved. 👍 See trends with /streak.")
            return

        if data == "menu_main":
            text = (
                f"✍️ <b>Daily Activity & Habit Logger</b>\n"
                f"📅 Date: <code>{today_str}</code>\n\n"
                "Choose an action below to log unholy habits, sleep disruptors, or custom free notes:"
            )
            await query.edit_message_text(text, reply_markup=get_main_log_keyboard(), parse_mode="HTML")
            
        elif data == "menu_unholy":
            text = (
                f"😈 <b>Log an Unholy Habit / Disruptor</b>\n"
                f"📅 Date: <code>{today_str}</code>\n\n"
                "Select what you indulged in or experienced today:"
            )
            await query.edit_message_text(text, reply_markup=get_unholy_habits_keyboard(), parse_mode="HTML")
            
        elif data == "unholy_alcohol_menu":
            text = (
                f"🍷 <b>Alcohol Intake</b>\n"
                f"📅 Date: <code>{today_str}</code>\n\n"
                "How many standard drinks did you have?"
            )
            await query.edit_message_text(text, reply_markup=get_alcohol_keyboard(), parse_mode="HTML")
            
        elif data == "menu_note":
            text = (
                f"📝 <b>Write a Free Note</b>\n"
                f"📅 Date: <code>{today_str}</code>\n\n"
                "👇 <b>Type your note directly in the message box below and send it!</b>\n\n"
                "Examples:\n"
                "• <i>Sore quads from heavy squats</i>\n"
                "• <i>Red eye flight, feeling exhausted</i>\n"
                "• <i>Drank 3L water today, energetic</i>\n\n"
                "💡 <i>Or use <code>/note &lt;text&gt;</code> anytime.</i>"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_main")]
            ])
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
            
        elif data == "menu_view_today":
            logs = db.get_activity_logs(date_str=today_str, limit=20)
            if not logs:
                text = f"📋 <b>Today's Logs ({today_str}):</b>\n\nNo habits or notes logged for today yet."
            else:
                text = f"📋 <b>Today's Logs ({today_str}):</b>\n\n"
                for l in logs:
                    icon = log_icon(l)
                    tag_title = l.get("tag", "").replace("_", " ").title()
                    val = f" ({l['value']})" if l.get("value") is not None else ""
                    note = f"\n   <i>{html.escape(str(l['note']))}</i>" if l.get("note") else ""
                    text += f"• {icon} <b>{tag_title}</b>{val}{note}\n"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_main")]
            ])
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
            
        elif data.startswith("log_habit:"):
            parts = data.split(":")
            tag = parts[1]
            val = float(parts[2]) if len(parts) > 2 and parts[2] else 1.0
            note = parts[3] if len(parts) > 3 else ""
            
            log_id = db.log_activity(
                date_str=today_str,
                category="unholy_habit",
                tag=tag,
                note=note,
                value=val
            )
            
            tag_title = tag.replace("_", " ").title()
            text = (
                f"✅ <b>Unholy Habit Logged!</b>\n\n"
                f"😈 <b>Habit:</b> {tag_title} ({val})\n"
                f"📅 <b>Date:</b> <code>{today_str}</code>\n"
                f"📝 <b>Details:</b> {html.escape(note) if note else 'Logged'}\n\n"
                f"Saved as a journal entry. Timing must be verified before any recovery comparison."
            )
            keyboard = undo_keyboard(log_id, [
                InlineKeyboardButton("➕ Log Another Habit", callback_data="menu_unholy"),
                InlineKeyboardButton("📋 View Today's Logs", callback_data="menu_view_today")
            ])
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error handling callback query '{data}': {e}", exc_info=True)
        if data.startswith("cmd:"):
            # Keep the menu intact; report the failure as its own message.
            try:
                await query.message.reply_text(f"❌ Could not run {data[len('cmd:'):]}: {e}")
            except Exception:
                pass
            return
        try:
            # Fallback plain text edit if anything failed
            await query.edit_message_text(f"Action processed: {data}")
        except Exception:
            pass

# Commands reachable from buttons, keyed by their /command name.
EXPORT_DATASETS = ("daily_metrics", "journal", "habits")
EXPORT_WINDOWS = (("7 days", "7"), ("30 days", "30"), ("90 days", "90"), ("Everything", "all"))


def _export_window(arg: str) -> int | None | bool:
    """days (int), None for everything, or False when the argument is not a window."""
    arg = arg.strip().lower()
    if arg in ("all", "everything"):
        return None
    if arg.isdigit() and 1 <= int(arg) <= 3650:
        return int(arg)
    return False


async def send_export(message, window: int | None):
    """Send the three datasets as CSV files, ready to hand to an AI assistant."""
    from app import data_routes
    stamp = quality.today().isoformat()
    label = "all history" if window is None else f"last {window} days"
    await message.reply_text(f"📦 Preparing your export ({label})…")
    for name in EXPORT_DATASETS:
        text, count = await asyncio.to_thread(data_routes.csv_text, name, window)
        suffix = "all" if window is None else f"{window}d"
        await message.reply_document(
            document=text.encode("utf-8-sig"),
            filename=f"lifey-{name}-{suffix}-{stamp}.csv",
            caption=f"{data_routes.DATASETS[name]['label']}: {count} rows ({label})",
        )


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context):
        return
    target = reply_target(update)
    if context.args:
        window = _export_window(context.args[0])
        if window is False:
            await target.reply_text("Usage: /export [days|all], for example /export 30")
            return
        await send_export(target, window)
        return
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"export:{value}")
                                      for label, value in EXPORT_WINDOWS]])
    await target.reply_text(
        "📦 <b>Export</b>\n\nDaily metrics, journal and habits as CSV files. How far back?",
        reply_markup=keyboard, parse_mode="HTML")


COMMANDS = {
    "menu": menu_command,
    "streak": streak_command,
    "urge": urge_command,
    "mood": mood_command,
    "why": why_command,
    "undo": undo_command,
    "log": log_command,
    "notes": notes_command,
    "master": master_command,
    "sync": sync_command,
    "health": health_command,
    "status": status_command,
    "insights": insights_command,
    "spo2": spo2_command,
    "alerts": alerts_command,
    "gym": gym_command,
    "recover": recover_command,
    "week": week_command,
    "actionplan": actionplan_command,
    "export": export_command,
    "feeling": feeling_command,
}

# Shown in Telegram's "Menu" button next to the text box.
BOT_COMMANDS = [
    BotCommand("menu", "Tap-to-use menu of every feature"),
    BotCommand("streak", "Master-free streak & your data"),
    BotCommand("urge", "Log an urge you resisted"),
    BotCommand("mood", "Rate mood & energy"),
    BotCommand("why", "Your reasons for quitting: /why <reason>"),
    BotCommand("undo", "Fix a mistake: delete a recent entry"),
    BotCommand("log", "Log a habit or note"),
    BotCommand("notes", "Recent habits & notes"),
    BotCommand("master", "Log a Master slip (optional qty)"),
    BotCommand("note", "Log a free note: /note <text>"),
    BotCommand("habit", "Log a habit: /habit <name> [units] [details]"),
    BotCommand("sync", "Sync Garmin data (optional days)"),
    BotCommand("health", "Today's health snapshot"),
    BotCommand("status", "Quick readiness update"),
    BotCommand("insights", "Biometric insights"),
    BotCommand("spo2", "Nocturnal SpO2 observations"),
    BotCommand("alerts", "Active anomaly warnings"),
    BotCommand("gym", "Today's workout (4-day upper/lower)"),
    BotCommand("recover", "Recovery observations"),
    BotCommand("week", "Latest weekly recap"),
    BotCommand("actionplan", "Latest action plan"),
    BotCommand("export", "Export metrics, journal & habits as CSV"),
    BotCommand("feeling", "Rate how you woke up: /feeling 1-5"),
    BotCommand("start", "Welcome & keyboard"),
]

async def post_init(app: Application):
    try:
        await app.bot.set_my_commands(BOT_COMMANDS)
    except Exception as e:
        logger.warning(f"Could not register bot command menu: {e}")

    # Automatic broadcasts, local time. Set a variable to "off" to disable it.
    #   MORNING_TIME (default 07:00, after the 06:05 Garmin sync): today's workout + streak
    #   CHECKIN_TIME (default 21:30): nightly quit-tracker check-in
    if app.job_queue is None:
        logger.warning("Scheduled broadcasts disabled: install python-telegram-bot[job-queue].")
        return
    if not AUTHORIZED_CHAT_ID:
        return
    for job, env, default in ((morning_broadcast, "MORNING_TIME", "07:00"),
                              (nightly_checkin, "CHECKIN_TIME", "21:30")):
        value = os.environ.get(env, default).strip()
        if value.lower() == "off":
            continue
        try:
            hour, minute = (int(x) for x in value.split(":"))
            at = dtime(hour, minute, tzinfo=quality.user_timezone())
        except ValueError:
            logger.warning(f"{env}={value!r} is not HH:MM; that broadcast is disabled.")
            continue
        app.job_queue.run_daily(job, at, name=job.__name__)

    # The morning feeling and the evening check-in follow the settings on the web (Settings page).
    app.job_queue.run_repeating(reminder_tick, interval=60, first=15, name="reminder_tick")

    review_time = os.environ.get("WEEKLY_REVIEW_TIME", "19:00").strip()
    if review_time.lower() != "off":
        try:
            hour, minute = (int(x) for x in review_time.split(":"))
            app.job_queue.run_daily(weekly_review_nudge, dtime(hour, minute, tzinfo=quality.user_timezone()),
                                    days=(WEEKLY_REVIEW_DAY,), name="weekly_review_nudge")
        except ValueError:
            logger.warning(f"WEEKLY_REVIEW_TIME={review_time!r} is not HH:MM; the weekly nudge is disabled.")

# ---------- MAIN RUNNING LOOP ----------

def main():
    if not BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN environment variable not set in .env")
        sys.exit(1)
        
    print("Starting Lifey bot...")
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("streak", streak_command))
    app.add_handler(CommandHandler("urge", urge_command))
    app.add_handler(CommandHandler("mood", mood_command))
    app.add_handler(CommandHandler("why", why_command))
    app.add_handler(CommandHandler("undo", undo_command))
    app.add_handler(CommandHandler("log", log_command))
    app.add_handler(CommandHandler("master", master_command))
    # Bank statement import (Sure) is unrelated to health data and needs its own
    # importer install; it is off unless ENABLE_BANK_IMPORT=1. The handler is always
    # registered so a statement sent while it's off gets a reply instead of silence.
    app.add_handler(MessageHandler(filters.Document.FileExtension("xlsx"), xlsx_statement_handler))
    app.add_handler(CommandHandler("note", note_command))
    app.add_handler(CommandHandler("habit", habit_command))
    app.add_handler(CommandHandler("notes", notes_command))
    app.add_handler(CommandHandler("insights", insights_command))
    app.add_handler(CommandHandler("alerts", alerts_command))
    app.add_handler(CommandHandler("health", health_command))
    app.add_handler(CommandHandler("gym", gym_command))
    app.add_handler(CommandHandler("week", week_command))
    app.add_handler(CommandHandler("actionplan", actionplan_command))
    app.add_handler(CommandHandler("recover", recover_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("spo2", spo2_command))
    app.add_handler(CommandHandler("sync", sync_command))
    app.add_handler(CommandHandler("export", export_command))
    app.add_handler(CommandHandler("feeling", feeling_command))
    
    # Inline buttons callback handler
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(MessageHandler(filters.PHOTO | (filters.Document.ALL & ~filters.Document.FileExtension("xlsx")),
                                   attachment_handler))

    async def on_error(update, context):
        # Telegram's side hiccups (Bad Gateway, timeouts) are retried by polling; just note them.
        logger.warning(f"Bot error: {type(context.error).__name__}: {context.error}")
    app.add_error_handler(on_error)
    
    # Free text message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    
    # Start polling
    app.run_polling()

if __name__ == "__main__":
    main()

