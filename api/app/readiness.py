"""Readiness from verified daily metrics.

Deliberately simple and explainable: each metric is compared with the
person's own trailing baseline, and the verdict says how many metrics
backed it. Missing data lowers confidence; it is never filled in.
"""
from __future__ import annotations

from statistics import fmean, pstdev

from .models import Metric, Reason, Readiness

# metric key -> (weight, higher_is_better)
WEIGHTS = {"hrv": (0.45, True), "sleep": (0.35, True), "rhr": (0.20, False)}
MIN_BASELINE_DAYS = 10


def baseline(series: list[float | None]) -> tuple[float | None, float | None, int]:
    """Mean and sd of the days before the latest one."""
    prior = [v for v in series[:-1] if v is not None]
    if len(prior) < MIN_BASELINE_DAYS:
        return None, None, len(prior)
    return fmean(prior), max(pstdev(prior), 1e-6), len(prior)


def build_metric(key, label, unit, series, provenance, higher_is_better=True) -> Metric:
    value = series[-1] if series else None
    mean, sd, _ = baseline(series)
    covered = sum(v is not None for v in series)
    delta = None
    status = "unknown"
    if value is not None and mean:
        delta = round((value - mean) / mean * 100, 1)
        z = (value - mean) / sd
        z = z if higher_is_better else -z
        status = "good" if z >= -0.5 else "watch" if z >= -1.25 else "alert"
    return Metric(
        key=key, label=label, unit=unit,
        value=None if value is None else round(value, 1),
        baseline=None if mean is None else round(mean, 1),
        baseline_sd=None if sd is None else round(sd, 1),
        delta_pct=delta, status=status,
        provenance="not_recorded" if value is None else provenance,
        coverage=f"{covered}/{len(series)}", series=series,
    )


def readiness(metrics: list[Metric]) -> tuple[Readiness, list[Reason]]:
    used, zs = [], []
    for m in metrics:
        w = WEIGHTS.get(m.key)
        if not w or m.value is None or m.baseline is None or not m.baseline_sd:
            continue
        z = (m.value - m.baseline) / m.baseline_sd
        zs.append((w[0], z if w[1] else -z))
        used.append(m)

    if len(used) < 2:
        return Readiness(
            score=None, label="Not enough data",
            summary="Fewer than two verified metrics have a personal baseline yet, so no verdict is given.",
            action="Wear the watch overnight and sync again.", confidence="low",
        ), []

    total = sum(w for w, _ in zs)
    z = sum(w * v for w, v in zs) / total
    score = max(0, min(100, round(60 + 18 * z)))
    label = "Primed" if score >= 75 else "Steady" if score >= 55 else "Ease off" if score >= 35 else "Recover"
    action = {
        "Primed": "Good day for your hardest session. Keep bedtime consistent.",
        "Steady": "Train as planned, aerobic work over intensity.",
        "Ease off": "Keep it light today: a walk or easy zone 2, and protect tonight's sleep.",
        "Recover": "Rest day. Go to bed earlier and see how tomorrow reads.",
    }[label]
    confidence = "high" if len(used) == 3 else "medium"

    reasons = []
    for m in sorted(used, key=lambda m: abs(m.delta_pct or 0), reverse=True):
        d = m.delta_pct or 0
        direction = "above" if d > 0 else "below"
        reasons.append(Reason(
            text=f"{m.label} is {abs(d):.0f}% {direction} your usual ({m.value:g} vs {m.baseline:g} {m.unit}).",
            evidence=[m.key],
        ))
    missing = [m.label for m in metrics if m.key in WEIGHTS and m not in used]
    summary = f"Based on {len(used)} of 3 verified signals against your own 4-week baseline."
    if missing:
        summary += f" {', '.join(missing)} missing, so confidence is lower."
    return Readiness(score=score, label=label, summary=summary, action=action, confidence=confidence), reasons
