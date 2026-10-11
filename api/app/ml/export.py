"""Export daily features to a CSV for notebooks (read-only).

    python -m app.ml.export ml/data/daily_metrics.csv

Needs DATABASE_URL. Postgres is not public, so open an SSH tunnel first (see ml/README.md).
The CSV holds health data: it lives in ml/data/, which is git-ignored.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from .. import db
from .features import EXPORT_SQL, METRICS


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(argv[0])
    out.parent.mkdir(parents=True, exist_ok=True)
    with db.connect() as conn:
        rows = conn.execute(EXPORT_SQL).fetchall()
    with out.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["date", *[m.key for m in METRICS]])
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
