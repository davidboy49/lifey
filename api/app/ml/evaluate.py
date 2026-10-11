"""The metrics the nightly job and the promotion gate use. Notebooks import these too,
so "better" means the same thing everywhere.

Deliberately small: the modelling and the walk-forward loop are yours to write.
"""
from __future__ import annotations

import numpy as np


def mae(y_true, y_pred) -> tuple[float, int]:
    """Mean absolute error over pairs where both values exist, and how many pairs that was.

    Rows with a missing actual or a missing prediction are skipped, never counted as 0.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    ok = ~(np.isnan(y_true) | np.isnan(y_pred))
    if not ok.any():
        return float("nan"), 0
    return float(np.abs(y_true[ok] - y_pred[ok]).mean()), int(ok.sum())


def skill(model_mae: float, naive_mae: float) -> float:
    """1 - model/naive. Positive means better than "tomorrow = today"; 0 is a tie; negative is worse."""
    if not naive_mae or np.isnan(naive_mae) or np.isnan(model_mae):
        return float("nan")
    return 1.0 - model_mae / naive_mae
