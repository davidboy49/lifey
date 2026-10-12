# Lifey ML workspace

You write the ML here. The plumbing (data, shared features, metrics, nightly job) is provided.

## Setup

```bash
cd api
python -m venv .venv                      # already exists on this machine
.venv/Scripts/python -m pip install -e ".[ml]"
.venv/Scripts/python -m jupyterlab ../ml/notebooks
```

The `ml` extra is for your laptop only. It is never installed in the production image.

## Data

`ml/data/daily_metrics.csv` is already exported (git-ignored: it is your health data).
To refresh it, either:

```bash
# A) no tunnel: run the same SQL on the VPS (exact SQL is features.EXPORT_SQL)
ssh -i ~/.ssh/lifey_deploy_ed25519 root@167.233.30.225 \
  "docker exec lifey-db-1 psql -U lifey -d lifey -c \"\\copy ($(python -c 'from app.ml.features import EXPORT_SQL;print(EXPORT_SQL)')) to stdout csv header\"" > ml/data/daily_metrics.csv

# B) tunnel + module (needs DATABASE_URL pointing at localhost:5439)
ssh -N -L 5439:127.0.0.1:5439 -i ~/.ssh/lifey_deploy_ed25519 root@167.233.30.225
python -m app.ml.export ml/data/daily_metrics.csv
```

Run (A) from `api/` so the import resolves. One row per calendar day; days with no row are NaN, never 0.

## Notebooks, in order

| # | Notebook | You will learn |
|---|---|---|
| 00 | `00_explore` | autocorrelation, missingness, outliers vs artifacts |
| 01 | `01_baselines` | target alignment, leakage, walk-forward scoring, skill |
| 02 | `02_lightgbm_shap` | boosting on tiny data, time-series CV, SHAP |
| 03 | `03_timesfm` | zero-shot foundation models, quantile bands, calibration |

Every notebook starts with the same provided setup cell. Everything else is a TODO for you.
Keep outputs out of git: the repo is public and outputs contain your numbers
(`pip install nbstripout && nbstripout --install` in the repo).

## Rules that keep training and production identical

1. **Features live only in `api/app/ml/features.py`.** Do not compute features inside a notebook for a model you
   plan to ship. The nightly job imports that same file.
2. **Nothing is filled silently.** If a model needs gaps filled, write a named function and flag the filled days.
3. **Evaluate walk-forward**, never with random splits.
4. **Same metrics everywhere:** `app.ml.evaluate.mae` (skips missing pairs, reports how many it used) and
   `app.ml.evaluate.skill` (`1 - MAE_model / MAE_naive`).

## Leakage checklist (read before you trust a score)

- Row `t` may use only data known by the end of day `t`. The target is day `t+1` or later.
- `sleep_score`, `bb_max` and Garmin readiness are *derived* from sleep and HRV. Same-night derived scores must
  not predict the metric they were derived from.
- Baselines and rolling windows must exclude the day being predicted (`features.py` already does).
- Partial nights (`incomplete` column, sleep < 3 h or Body Battery high < 10) are not valid readings: baselines and
  `features.clean(frame, key)` skip them. Decide deliberately whether your own features should too.
- No scaling, selection or tuning on the validation fold.
- If a shuffled-target run still scores well, something leaks.

## Model artifact contract (what the nightly job will load)

File: `ml/models/<target>_h<horizon>_<YYYY-MM-DD>.joblib`, e.g. `sleep_hours_h1_2026-10-25.joblib`.
Keep the last 3. Content is a `dict`:

| key | meaning |
|---|---|
| `model` | fitted estimator with `.predict(X)` (or `None` for `naive`/`mean7`) |
| `kind` | `"naive" \| "mean7" \| "lightgbm" \| "timesfm"` |
| `feature_names` | ordered list of columns taken from `features.build(...)` |
| `target` | `"sleep_hours"` (or `"hrv"`, `"resting_hr"`) |
| `horizon` | days ahead, `1` |
| `trained_through` | last date used for fitting |
| `cv_mae`, `last30_mae`, `naive_last30_mae` | numbers from your evaluation |
| `features_version` | string you bump when `features.py` changes meaning |

Promotion rule (Phase 3b, built by the assistant): a new artifact replaces the incumbent only if its
`last30_mae` is lower on the last 30 scored days.

## What the nightly job will do with your winner

Compute `features.build` for the latest date, take `feature_names`, call `model.predict`, and write one row per
prediction to `ml.predictions` (made_on, target_date, y_hat, naive_pred, mean7_pred). Actuals are filled in
after the fact and a weekly report scores model vs naive. You do not write any of that.

## Glossary

- **MAE**: mean absolute error, in the unit of the target (hours).
- **Skill**: improvement over the naive baseline; positive is good.
- **Leakage**: information from the future (or the target) sneaking into features.
- **Walk-forward**: train on the past, predict the next step, move forward, repeat.
- **Zero-shot**: use a pretrained model without any training on your data.
- **SHAP**: per-prediction feature contributions.
