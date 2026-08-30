# 33 — M5 Owner Learning Note

## 1. Concept implemented

M5 implements a leakage-controlled tabular ML experiment: train-only preprocessing, logistic
regression, an XGBoost candidate, validation-only hyperparameter/threshold selection, one final
held-out evaluation, calibration abstention, immutable model lineage and checksum-verified
inference.

## 2. Why it is used here

The heuristic is transparent but cannot learn weights or interactions from data. Logistic
regression is the interpretable learned baseline: each standardized coefficient has a direction
and magnitude. XGBoost tests whether nonlinear feature interactions add value. ReleaseProof keeps
the simpler heuristic active unless learned evidence adds defensible held-out value.

## 3. Algorithm and data assumptions

- Rows are independent enough after temporal/repository/duplicate leakage controls; the one-repo
  fixture cannot validate the repository-independence assumption.
- Proxy labels approximate follow-up risk but are not incidents or causal truth.
- Logistic regression models a linear log-odds relationship after scaling; regularization controls
  coefficient magnitude.
- XGBoost builds sequential shallow trees to correct prior residual errors and can model nonlinear
  interactions, but tiny data makes it easy to overfit.
- Class prevalence, feature missingness and observation windows in deployment must resemble the
  evaluated target population before metrics or calibration transfer.
- An uncalibrated sigmoid/tree score is useful for ranking or bands but is not automatically a
  probability.

## 4. Key code paths

- `packages/ml_core/classical.py`: preprocessor, tuning, frozen evaluation, artifact validation and
  candidate inference.
- `eng/evaluate_m5_classical.py`: rebuild and exact/tolerance reproducibility gate.
- `models/public/m5_classical_ml_v1.json`: immutable raw experiment/model artifact.
- `apps/web/risk/artifacts.py`: bounded checksum-validated loading with deterministic fallback.
- `apps/web/risk/api.py` and `views.py`: tenant-scoped model/risk evidence presentation.

## 5. Exact experiment/test to rerun

```text
uv run python -m eng.evaluate_m4_baseline --check
uv run python -m eng.evaluate_m5_classical --check
uv run pytest tests/unit/test_classical_ml.py tests/web/test_risk_evidence.py
```

Inspect `test_metrics`, `raw_test_predictions`, `calibration`, `tuning`, `active_selection` and all
hash bindings in the JSON artifact. Do not tune after examining held-out results.

## 6. Likely interview question and answer

**Question:** Why did you not promote XGBoost—or call its output a probability?

**Answer:** XGBoost did not add defensible held-out value over the heuristic on the frozen synthetic
fixture, and four validation/test rows cannot support the predeclared calibration gate. I therefore
kept it as a checksum-versioned candidate, exposed only a model score/band, retained explicit
UNKNOWN behavior and left the transparent deterministic heuristic active. Promotion needs larger,
provenance-controlled, repository-aware real proxy data and successful held-out calibration.
