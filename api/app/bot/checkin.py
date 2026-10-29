"""The evening check-in: four quick questions, one tap each.

Unanswered is stored as NULL (unknown), never as "no". Each answer is saved the
moment it is tapped, so stopping half way keeps what was answered. A "yes" is
also written to the journal as a habit entry (unless one already exists for
the day) so the Habits page and weekly review see it.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# field, question, options [(label, value)], journal habit tag (or None)
STEPS = [
    ("alcohol_units", "🍺 Any alcohol today?", [("None", 0), ("1 drink", 1), ("2", 2), ("3", 3)], "alcohol"),
    ("late_caffeine", "☕ Caffeine after 2pm?", [("No", 0), ("Yes", 1)], "late_caffeine"),
    ("late_meal", "🍽 A big meal within 3 hours of bed?", [("No", 0), ("Yes", 1)], "late_meal"),
    ("rpe", "💪 How hard was today's workout?", [("No workout", 0), ("Easy", 3), ("Medium", 6), ("Hard", 8)], None),
]
FIELDS = [s[0] for s in STEPS]
TYPED_FIELDS = {"alcohol_units"}   # offer "More…": the user types the exact number
TYPE_IN = "more"
MAX_DRINKS = 30                    # matches the CHECK constraint on journal.checkins.alcohol_units
_LABELS = {field: {value: label for label, value in options} for field, _, options, _ in STEPS}


def step_index(field: str) -> int | None:
    return FIELDS.index(field) if field in FIELDS else None


def keyboard(day: str, index: int) -> InlineKeyboardMarkup:
    field, _, options, _ = STEPS[index]
    row = [InlineKeyboardButton(label, callback_data=f"ci:{day}:{field}:{value}") for label, value in options]
    skip = InlineKeyboardButton("Skip", callback_data=f"ci:{day}:{field}:skip")
    if field in TYPED_FIELDS:
        row.append(InlineKeyboardButton("More…", callback_data=f"ci:{day}:{field}:{TYPE_IN}"))
    return InlineKeyboardMarkup([row, [skip]])


def parse_count(text: str) -> float | None:
    """A typed drink count, e.g. "5" or "4.5"; None if it is not a number in the allowed range."""
    try:
        value = float(text.strip().replace(",", "."))
    except ValueError:
        return None
    return value if 0 <= value <= MAX_DRINKS else None


def question(day: str, index: int) -> tuple[str, InlineKeyboardMarkup]:
    text = f"🌙 <b>Evening check-in</b> · {index + 1}/{len(STEPS)}\n\n{STEPS[index][1]}"
    return text, keyboard(day, index)


def parse(data: str) -> tuple[str, str, str | None] | None:
    """`ci:<date>:<field>:<value|skip>` -> (date, field, value or None for skip), or None if malformed."""
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "ci" or parts[2] not in FIELDS:
        return None
    day, field, raw = parts[1], parts[2], parts[3]
    if len(day) != 10:
        return None
    if raw == "skip":
        return day, field, None
    if raw == TYPE_IN and field in TYPED_FIELDS:
        return day, field, raw
    allowed = {str(v) for _, v in next(o for f, _, o, _ in STEPS if f == field)}
    return (day, field, raw) if raw in allowed else None


def habit_tag(field: str) -> str | None:
    return next((tag for f, _, _, tag in STEPS if f == field), None)


def summary(row: dict | None) -> str:
    if not row:
        return "Nothing recorded."
    lines = []
    for field, _, _, _ in STEPS:
        value = row.get(field)
        if value is None:
            continue
        key = int(value) if isinstance(value, (int, float)) and float(value).is_integer() else value
        if isinstance(value, bool):
            key = int(value)
        label = _LABELS[field].get(key, f"{value:g}" if isinstance(value, (int, float)) else str(value))
        name = {"alcohol_units": "Alcohol", "late_caffeine": "Late caffeine", "late_meal": "Late meal",
                "rpe": "Workout"}[field]
        lines.append(f"• {name}: {label}")
    return "\n".join(lines) or "Nothing recorded."


# ---- how you felt on waking: one tap, asked before the day's numbers are in ----

FEELINGS = [(1, "😫", "Awful"), (2, "😕", "Rough"), (3, "😐", "Okay"), (4, "🙂", "Good"), (5, "😄", "Great")]
FEELING_NAMES = {n: f"{icon} {name}" for n, icon, name in FEELINGS}
FEELING_TEXT = "☀️ <b>How did you wake up?</b>\n\nTap before you look at your watch."


def feeling_keyboard(day: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"{icon} {n}", callback_data=f"mf:{day}:{n}")
                                  for n, icon, _ in FEELINGS]])


def parse_feeling(data: str) -> tuple[str, int] | None:
    """`mf:<date>:<1-5>` -> (date, rating), or None if malformed."""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "mf" or len(parts[1]) != 10 or parts[2] not in {"1", "2", "3", "4", "5"}:
        return None
    return parts[1], int(parts[2])
