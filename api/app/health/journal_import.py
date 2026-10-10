"""Carry vidhealth's journal tables into Lifey's `journal` schema.

Idempotent and safe to repeat until the cutover:
- activity_logs are reloaded by `origin='vidhealth'`, so something deleted with
  /undo in the old bot disappears here too, and rows Lifey itself wrote
  (origin='lifey') are never touched. Original ids are kept so inline buttons
  and references stay valid.
- body_comp upserts by date; alerts upsert by (date, type, version);
  action plans and coaching reports keep their ids and are never overwritten.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from psycopg import Connection
from psycopg.types.json import Jsonb

from . import quality


@dataclass
class Journal:
    activity_logs: list[dict] = field(default_factory=list)
    body_comp: list[dict] = field(default_factory=list)
    anomaly_alerts: list[dict] = field(default_factory=list)
    action_plans: list[dict] = field(default_factory=list)
    coaching_reports: list[dict] = field(default_factory=list)


TABLES = {
    "activity_logs": ["id", "date", "timestamp", "category", "tag", "note", "value", "occurred_at"],
    "body_comp": ["date", "weight", "body_fat", "waist"],
    "anomaly_alerts": ["id", "date", "timestamp", "severity", "alert_type", "message", "metrics_json",
                       "acknowledged", "algorithm_version", "alert_state", "delivered"],
    "action_plans": ["id", "period_start", "period_end", "generated_at", "model", "headline", "plan_text",
                     "watchlist_json", "evidence_json"],
    "coaching_reports": ["id", "date", "generated_at", "report_text", "evidence", "model", "validation"],
}


def _float(v):
    return None if v in (None, "") else float(v)


def _bool(v) -> bool:
    return str(v).strip().lower() in {"t", "true", "1", "yes"}


def _json(v):
    if v in (None, ""):
        return None
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return None


def _when(v):
    """Old timestamps are naive local strings or ISO with an offset."""
    if not v:
        return None
    try:
        parsed = datetime.fromisoformat(str(v).replace(" ", "T", 1))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=quality.user_timezone())


def read_live(old: Connection) -> Journal:
    """Read every journal table from a running vidhealth database."""
    journal = Journal()
    for table, columns in TABLES.items():
        have = {r[0] for r in old.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
            (table,))}
        picked = [c for c in columns if c in have]
        if not picked:
            continue  # the old database predates this table
        cur = old.execute(f"SELECT {', '.join(picked)} FROM {table}")
        setattr(journal, table, [dict(zip(picked, r)) for r in cur.fetchall()])
    return journal


def read_dump(dump) -> Journal:
    """Read the same tables from a pgdumplib archive (rows arrive as strings)."""
    from .import_vidhealth import _columns

    journal = Journal()
    entries = {e.tag: e for e in dump.entries if e.desc == "TABLE" and e.namespace == "public"}
    for table in TABLES:
        if table not in entries:
            continue
        names = _columns(entries[table])
        setattr(journal, table, [dict(zip(names, r)) for r in dump.table_data("public", table)])
    return journal


def load(conn: Connection, journal: Journal) -> dict:
    counts = {}
    with conn.transaction():
        conn.execute("DELETE FROM journal.activity_logs WHERE origin='vidhealth'")
        kept = 0
        for r in journal.activity_logs:
            if not r.get("date") or not r.get("category") or not r.get("tag"):
                continue
            conn.execute(
                """INSERT INTO journal.activity_logs (id, date, ts, category, tag, note, value, occurred_at, origin)
                   VALUES (%s,%s,COALESCE(%s, NOW()),%s,%s,%s,%s,%s,'vidhealth')
                   ON CONFLICT (id) DO NOTHING""",
                (int(r["id"]), r["date"], _when(r.get("timestamp")), r["category"], r["tag"],
                 r.get("note"), _float(r.get("value")), r.get("occurred_at")))
            kept += 1
        counts["activity_logs"] = kept

        for r in journal.body_comp:
            conn.execute(
                """INSERT INTO journal.body_comp (date, weight, body_fat, waist) VALUES (%s,%s,%s,%s)
                   ON CONFLICT (date) DO UPDATE SET weight=excluded.weight, body_fat=excluded.body_fat,
                   waist=excluded.waist""",
                (r["date"], _float(r.get("weight")), _float(r.get("body_fat")), _float(r.get("waist"))))
        counts["body_comp"] = len(journal.body_comp)

        for r in journal.anomaly_alerts:
            if not r.get("date"):
                continue
            conn.execute(
                """INSERT INTO journal.anomaly_alerts (date, ts, severity, alert_type, message, metrics,
                          acknowledged, algorithm_version, alert_state, delivered)
                   VALUES (%s,COALESCE(%s, NOW()),%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (date, alert_type, algorithm_version) DO NOTHING""",
                (r["date"], _when(r.get("timestamp")), r.get("severity") or "INFO", r.get("alert_type") or "UNKNOWN",
                 r.get("message") or "", Jsonb(_json(r.get("metrics_json"))), _bool(r.get("acknowledged")),
                 r.get("algorithm_version") or "legacy", r.get("alert_state") or "active", _bool(r.get("delivered"))))
        counts["anomaly_alerts"] = len(journal.anomaly_alerts)

        for r in journal.action_plans:
            conn.execute(
                """INSERT INTO journal.action_plans
                     (id, period_start, period_end, generated_at, model, headline, plan_text, watchlist, evidence)
                   VALUES (%s,%s,%s,COALESCE(%s, NOW()),%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                (int(r["id"]), r["period_start"], r["period_end"], _when(r.get("generated_at")), r.get("model"),
                 r.get("headline"), r.get("plan_text") or "", Jsonb(_json(r.get("watchlist_json"))),
                 Jsonb(_json(r.get("evidence_json")))))
        counts["action_plans"] = len(journal.action_plans)

        for r in journal.coaching_reports:
            conn.execute(
                """INSERT INTO journal.coaching_reports
                     (id, date, generated_at, report_text, evidence, model, validation)
                   VALUES (%s,%s,COALESCE(%s, NOW()),%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                (int(r["id"]), r["date"], _when(r.get("generated_at")), r.get("report_text") or "",
                 Jsonb(_json(r.get("evidence")) or {}), r.get("model"), r.get("validation")))
        counts["coaching_reports"] = len(journal.coaching_reports)

        for table in ("activity_logs", "anomaly_alerts", "action_plans", "coaching_reports"):
            conn.execute(
                f"""SELECT setval(pg_get_serial_sequence('journal.{table}', 'id'),
                           GREATEST((SELECT COALESCE(MAX(id), 1) FROM journal.{table}), 1))""")
    return counts
