"""Import vidhealth history from a `pg_dump -Fc` file.

    python -m app.health.import_vidhealth path/to/vidhealth.dump [--dry-run]

Nothing is copied row-for-row. Raw source payloads are replayed in their
original order through the same merge and parse rules as a live sync, so the
result is exactly what Lifey would have stored had it been receiving the data:

- Days with archived payloads (`source_payloads`) replay each payload with its
  original receipt time, which reproduces stale/failed-fetch states.
- Older days only have the stored merged payload (`daily_metrics.raw_json`).
  That is replayed once, stamped with the row's own `synced_at`, never "now".
- Legacy oxygen detail tables are ignored: only genuine timestamped samples
  inside the raw payloads are ever stored.
- Journal, training and body-composition logs are not imported (no Lifey
  module for them yet). ENT and quit tracking are intentionally dropped.

Safe to re-run: payloads are de-duplicated by hash and days are re-merged.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field

from psycopg import Connection

from .. import db
from . import store


@dataclass
class History:
    # date -> [(received_at_iso, payload)] in replay order
    replays: dict[str, list[tuple[str | None, dict]]] = field(default_factory=lambda: defaultdict(list))
    from_payloads: set[str] = field(default_factory=set)
    from_legacy: set[str] = field(default_factory=set)
    skipped: dict[str, str] = field(default_factory=dict)


def _columns(entry) -> list[str]:
    names = []
    for line in entry.defn.splitlines():
        m = re.match(r"\s+(\"?[\w-]+\"?)\s+\S+", line)
        if m and not line.strip().upper().startswith(("CREATE", "CONSTRAINT", "PRIMARY", "UNIQUE")):
            names.append(m.group(1).strip('"'))
    return names


def _iso(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace(" ", "T", 1) if " " in value and "T" not in value else value


def _json(value) -> dict | None:
    if not value:
        return None
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def read_dump(path: str) -> History:
    import pgdumplib  # optional dependency, only needed for imports

    dump = pgdumplib.load(path)
    entry = {e.tag: e for e in dump.entries if e.desc == "TABLE" and e.namespace == "public"}
    for needed in ("daily_metrics", "source_payloads"):
        if needed not in entry:
            raise SystemExit(f"{needed} table not found: is this a vidhealth dump?")

    history = History()

    sp_cols = _columns(entry["source_payloads"])
    payload_rows = []
    for row in dump.table_data("public", "source_payloads"):
        rec = dict(zip(sp_cols, row))
        body = _json(rec.get("payload"))
        if body is None or not rec.get("date"):
            continue
        payload_rows.append((rec["date"], _iso(rec.get("received_at")), int(rec.get("id") or 0), body))
    # received_at ties inside one transaction; the identity id preserves insertion order.
    for day, received, _, body in sorted(payload_rows, key=lambda r: (r[0], r[1] or "", r[2])):
        history.replays[day].append((received, body))
        history.from_payloads.add(day)

    dm_cols = _columns(entry["daily_metrics"])
    for row in dump.table_data("public", "daily_metrics"):
        rec = dict(zip(dm_cols, row))
        day = rec.get("date")
        if not day or day in history.from_payloads:
            continue
        body = _json(rec.get("raw_json"))
        if not body:
            history.skipped[day] = "no stored payload"
            continue
        history.replays[day].append((_iso(rec.get("synced_at")), body))
        history.from_legacy.add(day)
    return history


def import_history(conn: Connection, history: History, *, dry_run: bool = False) -> dict:
    imported = failed = 0
    errors: dict[str, str] = {}
    if dry_run:
        return {"dry_run": True, "days_to_import": len(history.replays),
                "from_payload_archive": len(history.from_payloads),
                "from_stored_json": len(history.from_legacy),
                "skipped_no_payload": history.skipped}
    for day in sorted(history.replays):
        try:
            for received, payload in history.replays[day]:
                store.save_day(conn, day, payload, fetched_at=received)
            conn.commit()
            imported += 1
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            failed += 1
            errors[day] = type(exc).__name__
    return {"dry_run": False, "days_imported": imported, "days_failed": failed,
            "from_payload_archive": len(history.from_payloads),
            "from_stored_json": len(history.from_legacy),
            "skipped_no_payload": history.skipped, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dump")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    history = read_dump(args.dump)
    if args.dry_run:
        print(json.dumps(import_history(None, history, dry_run=True), indent=2))  # type: ignore[arg-type]
        return 0
    with db.connect() as conn:
        result = import_history(conn, history)
    print(json.dumps(result, indent=2))
    return 0 if not result["days_failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
