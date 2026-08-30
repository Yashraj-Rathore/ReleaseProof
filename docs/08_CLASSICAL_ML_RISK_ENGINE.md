# 08 — Classical ML Risk Engine

## Progression
1. **Heuristic baseline:** transparent rule score; never call it probability.
2. **Logistic regression:** simple learnable baseline.
3. **XGBoost candidate:** only promoted when comparison justifies it.

## Target
Predict a documented proxy outcome for a configured observation window—not “an incident” unless ground truth truly is an incident label.

## Metrics
Always report class prevalence. Use precision/recall/F1 and PR-AUC as primary imbalance-aware evidence, ROC-AUC as context, confusion matrix, threshold table, and Brier/reliability if probability is displayed.

## Calibration
If UI says “78%,” calibration must be measured and tied to exact artifact. Otherwise show risk score/band.

Before inspecting the final test set, the experiment declaration names the target population, calibration method candidates, Brier baseline, reliability/ECE calculation and bin/minimum-sample rules, plus numeric acceptance tolerances selected from the validation set and operational cost assumptions. The untouched test set evaluates that frozen rule. Failure of any declared tolerance disables probability wording for that artifact; there is no universal post-hoc threshold chosen after seeing test results.

## Thresholds
Select on validation data according to explicit operational tradeoff (e.g. high positive recall without excessive HOLD/REVIEW). Never tune on final test.

## Explanations
Model-native importance may be shown carefully. SHAP is optional only if value/latency/dependency cost is justified. Explanations are association, not causation.

## Inference
Exact feature-schema compatibility. Missing/incompatible required input => explicit fallback/UNKNOWN, never arbitrary silent fill.

## Promotion gate
Dataset manifest valid; leakage checks pass; metrics artifact exists; baseline comparison documented; reproducibility rerun works; security/privacy acceptable; exact checksum/version registered.

## Implemented M4 heuristic baseline

`deterministic-heuristic-v1` is a transparent additive 0-100 score over exact
`change-features-v1` inputs. Source-controlled rules cover change size/file count, migrations,
dependencies, deterministic sensitive paths, missing test changes, large deletion, available
static blast radius and available prior check-failure proxies. Every contribution names points,
reason and source features; incompatible schema is rejected and missing required core values yield
UNKNOWN.

Candidate thresholds 20/30/40/50 and a 0.75 validation recall floor are frozen. Threshold 30 was
selected from the synthetic validation split by maximum precision, then F1, then the higher
threshold; the held-out synthetic test set was evaluated afterward without retuning. On only four
test rows the raw confusion is TP=2, FP=2, TN=0, FN=0 (precision 0.50, recall 1.00, F1 0.66666667,
average precision 0.41666667 and ROC-AUC 0.125). These unstable fictional-fixture measurements
validate the harness and expose false positives; they do not establish model/customer performance.
Calibration is explicitly not applicable because the output is not a probability.

## Implemented M5 classical candidates

`classical-preprocessor-v1` validates exact `change-features-v1` input, fits only on training rows,
records nullable-feature median/zero imputation, adds missingness indicators and freezes z-score
parameters. Required missing input returns UNKNOWN; schema or artifact incompatibility is rejected.

`logistic-risk-v1` and `xgboost-risk-v1` use the immutable M4 temporal split. Candidate
hyperparameters and model-score thresholds 0.3/0.5/0.7 use train/validation only under a frozen
five-unit false-negative/two-unit false-positive cost rule and 0.75 recall floor. The final four
test rows are evaluated once after selection/calibration rules are declared. Exact raw results,
parameters, coefficients/gain associations, native XGBoost JSON, runtime versions, checksums and
rollback metadata are in `models/public/m5_classical_ml_v1.json`.

The calibration declaration freezes sigmoid/Platt and isotonic candidates, a training-prevalence
Brier baseline, 10 equal-width bins with 20 rows per bin, minimum 200 validation rows/50 per class,
ECE at most 0.05, bin gap at most 0.10 and Brier improvement at least 0.01. Four validation rows fail
the sample gate, so calibration is not attempted and probability wording is prohibited.

On the four synthetic held-out rows, logistic records TP=1, FP=1, TN=1, FN=1, F1=0.50,
AP=0.50 and ROC-AUC=0.25. XGBoost records TP=1, FP=2, TN=0, FN=1, F1=0.40,
AP=0.41666667 and ROC-AUC=0.25. These unstable fixture figures do not establish product value.
Neither model defensibly improves the heuristic, so both remain candidates and
`deterministic-heuristic-v1` remains active. The full model card is docs/32.
