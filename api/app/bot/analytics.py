#!/usr/bin/env python3
"""
Advanced Biometric Intelligence & Analytics Module
Provides:
- HRV Baseline Banding (rolling normal range +/- 0.75 SD)
- Biomarker Correlation Matrix
- Sleep Architecture Disruption Index
- Unholy Habit Impact Quantification
"""

import numpy as np
import pandas as pd
from app.bot import store as db
from app.health import quality


def calculate_hrv_baseline(df: pd.DataFrame, window: int = 28) -> pd.DataFrame:
    """
    Computes personalized HRV baseline bands:
    - baseline_mean: rolling 28-day mean of HRV
    - baseline_sd: rolling 28-day standard deviation
    - band_lower: baseline_mean - (0.75 * baseline_sd)
    - band_upper: baseline_mean + (0.75 * baseline_sd)
    - status: 'Suppressed' (below lower), 'Balanced' (within band), 'Elevated' (above upper)
    """
    if df.empty or "hrv_last_night" not in df.columns:
        return df

    df_calc = df.copy().sort_values("date")
    df_calc["hrv_numeric"] = pd.to_numeric(df_calc["hrv_last_night"], errors="coerce")

    # Previous calendar days only: today's reading cannot shift its own baseline.
    indexed = pd.Series(df_calc["hrv_numeric"].to_numpy(), index=pd.to_datetime(df_calc["date"]))
    history = indexed.rolling(f"{int(window)}D", closed="left", min_periods=7)
    df_calc["hrv_baseline_mean"] = history.mean().to_numpy()
    df_calc["hrv_baseline_sd"] = history.std().to_numpy()
    df_calc["hrv_baseline_count"] = indexed.rolling(f"{int(window)}D", closed="left").count().to_numpy()

    # Calculate baseline normal bands (+/- 0.75 SD)
    df_calc["hrv_band_lower"] = (df_calc["hrv_baseline_mean"] - 0.75 * df_calc["hrv_baseline_sd"]).round(1)
    df_calc["hrv_band_upper"] = (df_calc["hrv_baseline_mean"] + 0.75 * df_calc["hrv_baseline_sd"]).round(1)
    df_calc["hrv_severe_lower"] = (df_calc["hrv_baseline_mean"] - 1.5 * df_calc["hrv_baseline_sd"]).round(1)

    # Classify daily HRV status
    def classify_hrv(row):
        val = row["hrv_numeric"]
        lower = row["hrv_band_lower"]
        upper = row["hrv_band_upper"]
        if pd.isna(val) or pd.isna(lower):
            return "Calibrating"
        if val < row["hrv_severe_lower"]:
            return "Severe Suppression"
        if val < lower:
            return "Suppressed"
        if val > upper:
            return "Above personal band"
        return "Balanced"

    df_calc["hrv_band_status"] = df_calc.apply(classify_hrv, axis=1)
    return df_calc


def calculate_sleep_disruption_index(row: dict | pd.Series) -> dict:
    """
    Computes a Sleep Architecture Disruption Score (0 = Optimal, 100 = Severe Disruption).
    Evaluates:
    - Deep sleep ratio (optimal >= 15%)
    - REM sleep ratio (optimal >= 20%)
    - Awake interruption ratio (optimal <= 10%)
    - Overnight average stress (optimal <= 20)
    """
    duration = quality.number(row.get("sleep_duration")) or 0
    deep = quality.number(row.get("sleep_deep"))
    rem = quality.number(row.get("sleep_rem"))
    awake = quality.number(row.get("sleep_awake"))
    stress_avg = quality.number(row.get("overnight_stress_avg"))

    if duration <= 0 or any(v is None for v in (deep, rem, awake)):
        return {
            "score": None,
            "category": "No Sleep Data",
            "deep_pct": 0,
            "rem_pct": 0,
            "awake_pct": 0,
            "drivers": []
        }

    deep_pct = (deep / duration) * 100.0
    rem_pct = (rem / duration) * 100.0
    awake_pct = (awake / duration) * 100.0

    penalty = 0.0
    drivers = []

    # Deep Sleep penalty
    if deep_pct < 10.0:
        penalty += 25.0
        drivers.append("Low Deep Sleep (<10%)")
    elif deep_pct < 15.0:
        penalty += 12.0
        drivers.append("Suboptimal Deep Sleep (<15%)")

    # REM Sleep penalty
    if rem_pct < 15.0:
        penalty += 20.0
        drivers.append("Low REM Sleep (<15%)")
    elif rem_pct < 20.0:
        penalty += 10.0
        drivers.append("Suboptimal REM Sleep (<20%)")

    # Awake Time penalty
    if awake_pct > 18.0:
        penalty += 25.0
        drivers.append("Frequent Nighttime Awakenings (>18%)")
    elif awake_pct > 12.0:
        penalty += 12.0
        drivers.append("Elevated Awake Time (>12%)")

    # Overnight Stress penalty
    if stress_avg is not None and stress_avg > 35.0:
        penalty += 30.0
        drivers.append("High Overnight Sympathetic Stress (>35)")
    elif stress_avg is not None and stress_avg > 25.0:
        penalty += 15.0
        drivers.append("Moderate Overnight Stress (>25)")

    disruption_score = min(100.0, max(0.0, penalty))
    
    if disruption_score <= 15:
        category = "Restorative"
    elif disruption_score <= 35:
        category = "Mild Disruption"
    elif disruption_score <= 60:
        category = "Moderate Disruption"
    else:
        category = "High Disruption"

    return {
        "score": round(disruption_score, 1),
        "category": category,
        "deep_pct": round(deep_pct, 1),
        "rem_pct": round(rem_pct, 1),
        "awake_pct": round(awake_pct, 1),
        "drivers": drivers
    }


def calculate_correlation_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates Pearson correlation matrix across biometric metrics and habit markers.
    """
    if df.empty:
        return pd.DataFrame()

    candidate_cols = [
        "hrv_last_night",
        "sleep_score",
        "sleep_duration",
        "sleep_deep",
        "sleep_rem",
        "resting_hr",
        "bb_max",
        "bb_drained",
        "stress_avg",
        "steps",
        "alcohol_logged"
    ]

    available_cols = [c for c in candidate_cols if c in df.columns]
    df_subset = df[available_cols].copy()

    for col in available_cols:
        df_subset[col] = pd.to_numeric(df_subset[col], errors="coerce")

    # Drop columns that have all NaNs or zero variance
    valid_cols = [c for c in available_cols if df_subset[c].dropna().nunique() > 1]
    if len(valid_cols) < 2:
        return pd.DataFrame()

    # Convert sleep seconds to hours for cleaner display
    if "sleep_duration" in valid_cols:
        df_subset["sleep_duration"] = df_subset["sleep_duration"] / 3600.0
    if "sleep_deep" in valid_cols:
        df_subset["sleep_deep"] = df_subset["sleep_deep"] / 3600.0
    if "sleep_rem" in valid_cols:
        df_subset["sleep_rem"] = df_subset["sleep_rem"] / 3600.0

    friendly_names = {
        "hrv_last_night": "HRV (ms)",
        "sleep_score": "Sleep Score",
        "sleep_duration": "Sleep (hrs)",
        "sleep_deep": "Deep Sleep (hrs)",
        "sleep_rem": "REM Sleep (hrs)",
        "resting_hr": "Resting HR",
        "bb_max": "Body Battery Peak",
        "bb_drained": "Body Battery Drained",
        "stress_avg": "Avg Stress",
        "steps": "Steps",
        "alcohol_logged": "Alcohol Logged"
    }

    df_renamed = df_subset[valid_cols].rename(columns=friendly_names)
    corr = df_renamed.corr(method="pearson", min_periods=14).round(2)
    return corr


def analyze_habit_impact(df_metrics: pd.DataFrame, df_logs: pd.DataFrame | None = None) -> dict:
    """Decline causal/next-night comparison without episode-aligned exposure data."""
    return {"has_data": False, "total_days": len(df_metrics), "alcohol_days": 0,
            "clean_days": 0, "alcohol_impact": None,
            "summary": "Habit comparison is unavailable until occurrence times, sleep episodes, "
                       "and explicit no-habit check-ins can be aligned. Unlogged days are unknown."}


def detect_exact_desaturation_events(epochs_data) -> list[dict]:
    """Exploratory sampled drops; no diagnostic interpretation or exact onset claim."""
    rows = quality.measured_records(epochs_data)
    events, recent, active = [], [], []
    baseline = None
    previous = None
    for rec in rows:
        ts, value = rec["timestamp"], rec["spo2_value"]
        if previous and (ts - previous["timestamp"] > 120 or rec["epoch_type"] != previous["epoch_type"]):
            # A gap or change of recording context cannot close an observed event.
            active, recent, baseline = [], [], None
        if active:
            active.append(rec)
            if value >= baseline - 1.5:
                nadir = min(active, key=lambda r: r["spo2_value"])
                events.append({"date": rec["date"], "start_time": active[0]["time_str"],
                    "nadir_time": nadir["time_str"], "end_time": rec["time_str"],
                    "duration_seconds": int(ts - active[0]["timestamp"]),
                    "baseline_spo2": round(baseline, 1), "nadir_spo2": nadir["spo2_value"],
                    "drop_magnitude": round(baseline - nadir["spo2_value"], 1),
                    "sleep_stage": nadir.get("sleep_stage") or "Unknown",
                    "respiration_rate": nadir.get("respiration_rate"), "severity": "INFO",
                    "event_type": "OBSERVED_DROP"})
                active = []
                recent = [value]
        else:
            baseline = float(np.median(recent)) if recent else value
            if recent and (baseline - value >= 3 or value < 90):
                active = [previous, rec]
            else:
                recent = (recent + [value])[-15:]
        previous = rec
    # Unrecovered events at recording end have unknown duration; omit them.
    return events


def calculate_oxygen_desaturation_index(events, sleep_duration_seconds, *, observed_seconds=None):
    """Compatibility name: descriptive event rate only, requiring supplied coverage."""
    sleep_seconds = quality.number(sleep_duration_seconds)
    coverage = quality.number(observed_seconds)
    available = sleep_seconds is not None and sleep_seconds > 0 and coverage is not None and coverage > 0
    return {"odi_score": round(len(events) / (coverage / 3600), 1) if available else None,
            "event_count": len(events) if available else None,
            "sleep_hours": sleep_seconds / 3600 if sleep_seconds is not None else None,
            "classification": "Exploratory sampled event rate" if available else "Unavailable",
            "status_color": "#64748b",
            "description": "Events per observed hour; not a sleep-apnea index." if available
                           else "Insufficient verified observation coverage."}


def calculate_hypoxic_burden(epochs_data) -> dict:
    """Estimate time below thresholds over bounded observed intervals only."""
    records = quality.measured_records(epochs_data)
    intervals = quality.observed_intervals(records)
    seconds = sum(duration for _, duration in intervals)
    low90 = sum(duration for row, duration in intervals if row["spo2_value"] < 90)
    low85 = sum(duration for row, duration in intervals if row["spo2_value"] < 85)
    values = [row["spo2_value"] for row in records]
    return {"t90_minutes": round(low90 / 60, 2) if seconds else None,
            "t85_minutes": round(low85 / 60, 2) if seconds else None,
            "observed_seconds": seconds, "sample_count": len(records),
            "min_spo2": min(values) if values else None,
            "mean_spo2": round(float(np.mean(values)), 1) if values else None,
            "hypoxic_fraction_pct": round(low90 / seconds * 100, 1) if seconds else None}


def analyze_chrono_distribution(events: list[dict]) -> dict:
    """
    Bins exact-moment drop events into hourly buckets (00:00 to 23:00)
    to identify the Peak Vulnerability Window (e.g. 03:00 - 05:00 AM).
    """
    hourly_counts = {h: 0 for h in range(24)}
    hourly_severities = {h: {"CRITICAL": 0, "WARNING": 0, "MILD": 0} for h in range(24)}

    for ev in events:
        nadir_time = ev.get("nadir_time") or ev.get("start_time") or ""
        try:
            hour = int(nadir_time.split(":")[0])
            if 0 <= hour <= 23:
                hourly_counts[hour] += 1
                sev = ev.get("severity", "MILD")
                if sev in hourly_severities[hour]:
                    hourly_severities[hour][sev] += 1
        except Exception:
            continue

    # Find peak window (e.g. 2-hour sliding window with highest count)
    peak_count = 0
    peak_window = "None"
    for h in range(23):
        w_count = hourly_counts[h] + hourly_counts[h+1]
        if w_count > peak_count and w_count > 0:
            peak_count = w_count
            peak_window = f"{h:02d}:00 - {(h+2)%24:02d}:00"

    return {
        "hourly_counts": hourly_counts,
        "hourly_severities": hourly_severities,
        "peak_window": peak_window,
        "peak_event_count": peak_count
    }


if __name__ == "__main__":
    print("Testing Analytics Module...")
    df = db.get_df(limit=30)
    df_bands = calculate_hrv_baseline(df)
    print(f"Calculated baseline for {len(df_bands)} days.")
    if not df_bands.empty:
        latest = df_bands.iloc[-1]
        print(f"Latest HRV: {latest.get('hrv_last_night')} ms | Baseline: {latest.get('hrv_baseline_mean')} +/- {latest.get('hrv_baseline_sd')} ms")
        print(f"Bands: [{latest.get('hrv_band_lower')} - {latest.get('hrv_band_upper')}] Status: {latest.get('hrv_band_status')}")
    corr = calculate_correlation_matrix(df)
    print("Correlation matrix shape:", corr.shape)

