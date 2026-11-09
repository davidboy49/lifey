"""Event reviews: looking back on one event or day.

The event name and date are the owner's own words, never picked from data. The day's Garmin numbers are
shown next to a review but never stored in it, so a later resync corrects them. Photos reuse the journal
attachment pipeline (sniffed by their bytes, re-encoded so GPS and device metadata are dropped) and live in
the same ATTACHMENTS_DIR, so the nightly backup already covers them.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import date

from .. import attachments
from .. import db as database
from ..health import quality

LOOP_TAGS = ["loneliness", "urge", "drinking", "stress", "pois", "poor_sleep"]
LOOP_LABELS = {"loneliness": "Loneliness", "urge": "Urge", "drinking": "Drinking", "stress": "Stress",
               "pois": "POIS", "poor_sleep": "Poor sleep"}
EVENT_MAX = 120
TEXT_MAX = 2000
LESSON_MAX = 200
MAX_BACK_DAYS = 400
MAX_PHOTOS = 6
LIST_MAX = 500

FIELDS = ("date", "event", "mood", "energy", "notes", "went_well", "would_change", "loop_tags", "lesson")
COLUMNS = "id, date, event, mood, energy, notes, went_well, would_change, loop_tags, lesson, created_at, updated_at"


class Invalid(ValueError):
    """The review can't be saved as given; the message is safe to show."""


def _text(value, name: str, limit: int) -> str:
    text = (value or "").strip() if isinstance(value, str) or value is None else None
    if text is None:
        raise Invalid(f"{name} must be text.")
    if len(text) > limit:   # reject loudly: a silent cut would lose the owner's words
        raise Invalid(f"{name} can be up to {limit} characters; yours is {len(text)}. Nothing was saved.")
    return text


def _scale(value, name: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise Invalid(f"{name} must be 1 to 5.")
    if isinstance(value, float) and not value.is_integer():
        raise Invalid(f"{name} must be 1 to 5.")
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise Invalid(f"{name} must be 1 to 5.") from None
    if not 1 <= n <= 5:
        raise Invalid(f"{name} must be 1 to 5.")
    return n


def parse_day(value) -> date:
    try:
        day = value if isinstance(value, date) else date.fromisoformat(str(value))
    except ValueError:
        raise Invalid("Use a date like 2026-11-09.") from None
    today = quality.today()
    if day > today:
        raise Invalid("That day has not happened yet.")
    if (today - day).days > MAX_BACK_DAYS:
        raise Invalid(f"Reviews can go back at most {MAX_BACK_DAYS} days.")
    return day


def parse_tags(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    out: list[str] = []
    for raw in value:
        tag = str(raw).strip().lower().replace(" ", "_")
        if tag not in LOOP_TAGS:
            raise Invalid(f"Unknown loop tag '{raw}'. Use: {', '.join(LOOP_TAGS)}.")
        if tag not in out:
            out.append(tag)
    return [t for t in LOOP_TAGS if t in out]   # stable order


def validate(data: dict) -> dict:
    """Clean a full review. Raises Invalid with a readable reason."""
    if data.get("date") in (None, ""):
        raise Invalid("Set the date of the event.")
    event = _text(data.get("event"), "Event", EVENT_MAX)
    if not event:
        raise Invalid("Name the event.")
    return {
        "date": parse_day(data["date"]),
        "event": event,
        "mood": _scale(data.get("mood"), "Mood"),
        "energy": _scale(data.get("energy"), "Energy"),
        "notes": _text(data.get("notes"), "Notes", TEXT_MAX),
        "went_well": _text(data.get("went_well"), "What went well", TEXT_MAX),
        "would_change": _text(data.get("would_change"), "What you'd change", TEXT_MAX),
        "loop_tags": parse_tags(data.get("loop_tags")),
        "lesson": " ".join(_text(data.get("lesson"), "Lesson", LESSON_MAX).split()),   # one line
    }


def _public(row: dict) -> dict:
    out = dict(row)
    out["date"] = row["date"].isoformat()
    out["created_at"] = row["created_at"].isoformat()
    out["updated_at"] = row["updated_at"].isoformat()
    out["loop_tags"] = list(row["loop_tags"] or [])
    return out


def _rows(conn, sql: str, params=()) -> list[dict]:
    cur = conn.execute(sql, params)
    names = [c.name for c in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def create(clean: dict) -> dict:
    with database.connect() as conn:
        [row] = _rows(conn, f"""INSERT INTO journal.event_reviews ({', '.join(FIELDS)})
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING {COLUMNS}""",
                      [clean[f] for f in FIELDS])
        conn.commit()
    return {**_public(row), "photos": []}


def update(review_id: int, clean: dict) -> dict | None:
    with database.connect() as conn:
        rows = _rows(conn, f"""UPDATE journal.event_reviews SET {', '.join(f'{f}=%s' for f in FIELDS)},
                                      updated_at=NOW() WHERE id=%s RETURNING {COLUMNS}""",
                     [*(clean[f] for f in FIELDS), review_id])
        conn.commit()
    if not rows:
        return None
    return {**_public(rows[0]), "photos": photos_for([review_id]).get(review_id, [])}


def get(review_id: int) -> dict | None:
    with database.connect() as conn:
        rows = _rows(conn, f"SELECT {COLUMNS} FROM journal.event_reviews WHERE id=%s", (review_id,))
    if not rows:
        return None
    return {**_public(rows[0]), "photos": photos_for([review_id]).get(review_id, [])}


def list_reviews(start: date | None = None, end: date | None = None, tag: str | None = None,
                 limit: int = LIST_MAX) -> list[dict]:
    """Newest first. `tag` is one loop tag; only reviews that ticked it are returned."""
    where, params = [], []
    if start:
        where.append("date >= %s")
        params.append(start)
    if end:
        where.append("date <= %s")
        params.append(end)
    if tag:
        where.append("loop_tags @> ARRAY[%s]::TEXT[]")
        params.append(parse_tags([tag])[0])
    sql = f"SELECT {COLUMNS} FROM journal.event_reviews"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY date DESC, id DESC LIMIT %s"
    params.append(max(1, min(int(limit), LIST_MAX)))
    with database.connect() as conn:
        rows = [_public(r) for r in _rows(conn, sql, params)]
    photos = photos_for([r["id"] for r in rows])
    for r in rows:
        r["photos"] = photos.get(r["id"], [])
    return rows


def tag_counts(rows: list[dict]) -> dict[str, int]:
    return {t: sum(1 for r in rows if t in r["loop_tags"]) for t in LOOP_TAGS}


def lessons() -> list[dict]:
    with database.connect() as conn:
        return [{"id": r["id"], "date": r["date"].isoformat(), "event": r["event"], "lesson": r["lesson"]}
                for r in _rows(conn, "SELECT id, date, event, lesson FROM journal.event_reviews "
                                     "WHERE lesson <> '' ORDER BY date DESC, id DESC")]


def delete(review_id: int) -> bool:
    """Delete the review, its photo rows (cascade) and then the files."""
    with database.connect() as conn:
        names = [n for r in conn.execute("SELECT stored_name, thumb_name FROM journal.event_review_photos "
                                         "WHERE review_id=%s", (review_id,)).fetchall() for n in r if n]
        n = conn.execute("DELETE FROM journal.event_reviews WHERE id=%s", (review_id,)).rowcount
        conn.commit()
    if n:
        attachments.remove_files(names)
    return n > 0


# ---------- the day's data (read only, never stored on the review) ----------

def day_data(day: date) -> dict:
    """That day's Garmin numbers and activities. Missing values are None; `has_data` is False on a blank day."""
    with database.connect() as conn:
        metrics = _rows(conn, """SELECT sleep_score, sleep_duration, hrv_last_night, hrv_status, resting_hr,
                                        training_readiness, bb_max, bb_min
                                 FROM health.daily_metrics WHERE date=%s""", (day,))
        acts = _rows(conn, """SELECT activity_id, name, type, started_local, duration_seconds, distance_meters, avg_hr
                              FROM health.activities WHERE date=%s
                              ORDER BY started_local NULLS LAST, activity_id""", (day,))
    m = metrics[0] if metrics else {}
    out_metrics = {
        "sleep_score": m.get("sleep_score"),
        "sleep_seconds": m.get("sleep_duration"),
        "hrv_ms": m.get("hrv_last_night"),
        "hrv_status": m.get("hrv_status"),
        "resting_hr": m.get("resting_hr"),
        "training_readiness": m.get("training_readiness"),
        "body_battery_high": m.get("bb_max"),
        "body_battery_low": m.get("bb_min"),
    }
    activities = [{
        "id": a["activity_id"], "name": a["name"], "type": a["type"],
        "start": a["started_local"].strftime("%H:%M") if a["started_local"] else None,
        "duration_seconds": a["duration_seconds"], "distance_meters": a["distance_meters"], "avg_hr": a["avg_hr"],
    } for a in acts]
    has = any(v is not None for k, v in out_metrics.items() if k != "hrv_status") or bool(activities)
    return {"date": day.isoformat(), "has_data": has, "metrics": out_metrics, "activities": activities}


# ---------- photos ----------

def _photo(row) -> dict:
    return {"id": row[0], "review_id": row[1], "filename": row[2], "mime": row[3], "bytes": row[4],
            "width": row[5], "height": row[6], "has_thumb": bool(row[7])}


def photos_for(review_ids: list[int]) -> dict[int, list[dict]]:
    if not review_ids:
        return {}
    with database.connect() as conn:
        rows = conn.execute("SELECT id, review_id, filename, mime, bytes, width, height, thumb_name "
                            "FROM journal.event_review_photos WHERE review_id = ANY(%s) ORDER BY id",
                            (review_ids,)).fetchall()
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r[1], []).append(_photo(r))
    return out


def prepare_photo(data: bytes, filename: str | None) -> dict:
    prepared = attachments.prepare(data, filename)
    if prepared["mime"] == attachments.PDF_MIME:
        raise attachments.Rejected("Only photos (JPEG, PNG, WebP) can be added to a review.")
    return prepared


def save_photo(review_id: int, prepared: dict) -> dict:
    with database.connect() as conn:
        if not conn.execute("SELECT 1 FROM journal.event_reviews WHERE id=%s", (review_id,)).fetchone():
            raise attachments.Rejected("That review no longer exists.")
        count = conn.execute("SELECT count(*) FROM journal.event_review_photos WHERE review_id=%s",
                             (review_id,)).fetchone()[0]
        if count >= MAX_PHOTOS:
            raise attachments.Rejected(f"A review can hold up to {MAX_PHOTOS} photos.")
        if attachments.used(conn) + len(prepared["data"]) > attachments.total_cap():
            raise attachments.Rejected("The attachment storage is full.")
        token = uuid.uuid4().hex
        stored = f"{token}.{attachments.EXT[prepared['mime']]}"
        thumb = f"{token}.thumb.jpg" if prepared["thumb"] else None
        base = attachments.root()
        attachments.write_file(base, stored, prepared["data"])
        if thumb:
            attachments.write_file(base, thumb, prepared["thumb"])
        row = conn.execute(
            "INSERT INTO journal.event_review_photos (review_id, filename, mime, bytes, width, height, sha256, "
            "stored_name, thumb_name) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "RETURNING id, review_id, filename, mime, bytes, width, height, thumb_name",
            (review_id, prepared["filename"], prepared["mime"], len(prepared["data"]), prepared["width"],
             prepared["height"], hashlib.sha256(prepared["data"]).hexdigest(), stored, thumb)).fetchone()
        conn.commit()
    return _photo(row)


def get_photo(photo_id: int, thumb: bool = False):
    """(path, mime, download name) or None."""
    with database.connect() as conn:
        row = conn.execute("SELECT stored_name, thumb_name, mime, filename FROM journal.event_review_photos "
                           "WHERE id=%s", (photo_id,)).fetchone()
    if not row:
        return None
    if thumb:
        if not row[1]:
            return None
        path, mime = attachments.file_path(row[1]), "image/jpeg"
    else:
        path, mime = attachments.file_path(row[0]), row[2]
    return (path, mime, row[3]) if path.is_file() else None


def delete_photo(photo_id: int) -> bool:
    with database.connect() as conn:
        row = conn.execute("DELETE FROM journal.event_review_photos WHERE id=%s RETURNING stored_name, thumb_name",
                           (photo_id,)).fetchone()
        conn.commit()
    if not row:
        return False
    attachments.remove_files([n for n in row if n])
    return True
