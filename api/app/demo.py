"""Deterministic sample data so the UI works before a Garmin account is linked.
Always labelled source="demo" in the API response."""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from .models import Today
from .readiness import build_metric, readiness

DAYS = 28


def _series(seed, base, amp, noise, today, gaps=(), digits=0):
    rng = random.Random(seed)
    out = []
    for i in range(DAYS):
        v = base + amp * math.sin(i / 4.3) + rng.gauss(0, noise)
        out.append(None if i in gaps else round(v, digits))
    out[-1] = today
    return out


def today_payload() -> Today:
    metrics = [
        build_metric("hrv", "HRV, overnight", "ms", _series(1, 62, 4, 3.2, 58, gaps=(6, 19)), "estimate"),
        build_metric("sleep", "Sleep score", "pts", _series(2, 76, 5, 4, 72, gaps=(11,)), "score"),
        build_metric("rhr", "Resting heart rate", "bpm", _series(3, 52, 1.5, 1.1, 53, gaps=(3, 4)), "measured", higher_is_better=False),
        build_metric("steps", "Steps", "", _series(4, 9200, 1800, 1500, 7430), "measured"),
        build_metric("spo2", "Blood oxygen, daily average", "%", [None] * DAYS, "measured"),
    ]
    verdict, reasons = readiness(metrics)
    return Today(
        date=datetime.now(timezone.utc).date().isoformat(),
        source="demo",
        synced_at=(datetime.now(timezone.utc) - timedelta(minutes=38)).isoformat(timespec="minutes"),
        readiness=verdict, metrics=metrics, reasons=reasons,
    )
