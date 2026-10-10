"""Money module: bank statement import.

The importer is the existing external script that feeds Sure. Lifey runs it
as an adapter so this module can later be replaced by a native importer
without touching callers. Off unless ENABLE_BANK_IMPORT=1.
"""
from __future__ import annotations

import json
import os
import subprocess

PYTHON = os.environ.get("SURE_IMPORT_PYTHON", "/opt/sure_import/venv/bin/python")
SCRIPT = os.environ.get("SURE_IMPORT_SCRIPT", "/opt/sure_import/bank_statement_import.py")
TIMEOUT_S = 180


def enabled() -> bool:
    return os.environ.get("ENABLE_BANK_IMPORT") == "1"


def run_statement_import(path: str) -> dict:
    """Always returns a summary dict; failures carry an "error" key."""
    for label, target in (("Python", PYTHON), ("script", SCRIPT)):
        if not os.access(target, os.R_OK):
            return {"error": f"Importer {label} not found or not readable: {target}"}
    try:
        proc = subprocess.run([PYTHON, SCRIPT, path], capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"error": "Importer took longer than 3 minutes and was stopped."}
    except OSError as e:
        return {"error": f"Could not start the importer: {e}"}
    lines = proc.stdout.strip().splitlines()
    try:
        summary = json.loads(lines[-1])
    except (IndexError, ValueError):
        detail = (proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}")[-300:]
        return {"error": detail}
    return summary if isinstance(summary, dict) else {"error": f"Unexpected importer output: {lines[-1][:200]}"}
