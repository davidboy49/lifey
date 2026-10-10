from typing import Literal
from pydantic import BaseModel

Status = Literal["good", "watch", "alert", "unknown"]
# How a number came to exist. The UI shows this on every figure, so an
# estimate is never mistaken for a measurement and a gap is never a zero.
Provenance = Literal["measured", "estimate", "score", "not_recorded"]
Confidence = Literal["high", "medium", "low"]


class Metric(BaseModel):
    key: str
    label: str
    unit: str
    value: float | None
    baseline: float | None
    baseline_sd: float | None
    delta_pct: float | None
    status: Status
    provenance: Provenance
    coverage: str  # "26/28": days with data in the window
    series: list[float | None]


class Readiness(BaseModel):
    score: int | None
    label: str
    summary: str
    action: str
    confidence: Confidence


class Reason(BaseModel):
    text: str
    evidence: list[str]


class Today(BaseModel):
    date: str
    source: Literal["demo", "garmin"]
    synced_at: str | None
    readiness: Readiness
    metrics: list[Metric]
    reasons: list[Reason]
