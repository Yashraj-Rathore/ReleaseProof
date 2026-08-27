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
