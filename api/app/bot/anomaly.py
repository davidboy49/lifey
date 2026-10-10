"""Descriptive source-backed observations; no diagnoses or inferred exact timings."""
import asyncio
import json
import os
import pandas as pd
from app.bot import store as db
from app.bot import coaching
from app.health import quality

VERSION = "observations-v1"


def scan_daily_anomalies(target_date=None):
    frame = db.get_df(limit=35)
    if frame.empty:
        return []
    target_date = target_date or str(frame.iloc[-1]["date"])
    frame = frame[frame["date"] <= target_date]
    if frame.empty or str(frame.iloc[-1]["date"]) != target_date:
        return []
    evidence = coaching.build_evidence(frame, 28)
    facts = evidence["facts"]
    results = []
    for metric, threshold, direction, label in [
        ("spo2_min", 90, "below", "Garmin low oxygen estimates repeated"),
        ("training_readiness", 50, "below", "Garmin readiness below 50 on repeated days")]:
        recent = [f for f in facts if f["metric"] == metric
                  and pd.Timestamp(f["date"]) >= pd.Timestamp(target_date) - pd.Timedelta(days=2)]
        flagged = [f for f in recent if f["value"] < threshold]
        if len(flagged) >= 2 and any(f["date"] == target_date for f in flagged):
            message = "; ".join(f["text"] for f in flagged)
            if metric == "spo2_min":
                message += " Wrist estimates may include sensor artifacts; this is not an apnea diagnosis or an exact event timeline."
            results.append({"date": target_date, "severity": "INFO", "alert_type": metric.upper(),
                "title": label, "message": message, "metrics": {"evidence": flagged}})
    return results


async def _send_telegram_alert(anomaly):
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    from telegram import Bot
    async with Bot(token=token) as bot:
        await bot.send_message(chat_id=chat, text=f"Recorded observation: {anomaly['date']}\n{anomaly['title']}\n{anomaly['message']}")
    return True


def dispatch_alerts_if_needed(target_date=None, notify_telegram=True):
    frame = db.get_df(limit=1 if target_date is None else 35)
    if frame.empty:
        return []
    target_date = target_date or str(frame.iloc[-1]["date"])
    anomalies = scan_daily_anomalies(target_date)
    relevant = frame[frame["date"] == target_date]
    if relevant.empty:
        return []
    evidence = coaching.build_evidence(relevant, 1)
    evaluated = {f["metric"].upper() for f in evidence["facts"]} & {"SPO2_MIN", "TRAINING_READINESS"}
    active = {a["alert_type"] for a in anomalies}
    for kind in evaluated - active:
        db.resolve_alert(target_date, kind, VERSION)
    for item in anomalies:
        db.upsert_alert(target_date, item["severity"], item["alert_type"], item["message"],
                        item["metrics"], VERSION)
    # Failed delivery leaves delivered=false, allowing the next sync to retry.
    if notify_telegram:
        for item in anomalies:
            try:
                row = db.pending_alert(target_date, item["alert_type"], VERSION)
                if row and not row["delivered"] and asyncio.run(_send_telegram_alert(item)):
                    db.mark_alert_delivered(row["id"])
            except Exception:
                pass  # Keep pending; never mark a failed send delivered.
    return anomalies
