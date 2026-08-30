# 32 — M5 Classical Risk Model Card

## Artifact identity

- Card version: `classical-model-card-v1`
- Experiment artifact: `models/public/m5_classical_ml_v1.json`
- Canonical root payload SHA-256 contract:
  `cb552fd83b257d67248d804c931cf604942d76bac245069b64f58048bfa9a8d6`
- Committed file SHA-256:
  `e0c58feb3f824a8d7fa7786d1ba19da8de5c0ee45b00f0401265ab9294aaa044`
- Training code commit: `e63fcff3b2afd18775cd3a1cb01bb4688db316a3`
- Dataset manifest: `releaseproof-m4-synthetic-v1`, hash
  `eab561cbce6cc9986e5b8d9a248b268e3709407dff7f23b111c36c932dd86456`
- Frozen split hash: `81d51ed7011c86744f2cf4bff15cb98bb1aa440b1c81ece921ed9b4a21f0c11b`
- Feature schema: `change-features-v1`
- Preprocessor hash: `41f9072f1e5d34aa1e934788fe1026b096222482534acca308ce7dc6b7ddcd33`

The JSON artifact is small, synthetic, source-controlled evidence. The XGBoost native JSON bytes
have their own checksum inside the artifact. The root, preprocessing and model checksums are
validated before candidate inference. Large or private future artifacts belong in content-addressed
object storage rather than Git.

## Intended and prohibited use

The experiment predicts the documented `proxy_positive` label within the admitted 30-day fixture
observation window. It validates preprocessing, training, comparison, artifact loading and
evaluation behavior. It must not be described as incident prediction, customer performance,
production calibration, release safety, or measured business value. Neither learned candidate is
approved for active product scoring.

ReleaseProof keeps `deterministic-heuristic-v1` active. Learned outputs are advisory candidates and
cannot merge, deploy, change the recommendation policy, or authorize code execution.

## Data and preprocessing

The unchanged M4 fixture has 16 explicitly synthetic rows: 6 train, 4 validation, 4 held-out test
and 2 excluded unknown labels. Seven included rows are proxy-positive and seven are proxy-negative.
The one-repository dataset has a temporal split but no repository holdout.

The shared preprocessor fits on the six training rows only. It validates the exact 25-feature input
schema, uses recorded training medians for nullable features (or a recorded zero when training has
no observation), adds nullable-feature missingness indicators and applies frozen training z-score
parameters. Required missing input produces UNKNOWN; incompatible schemas or invalid checksums are
rejected.

## Training and selection

All candidates use seed 1729. Logistic regression compares `C` 0.1/1/10 and optional balanced class
weights with the liblinear solver. XGBoost compares depths 1/2 and 8/16 estimators using CPU `hist`,
one thread, learning rate 0.1 and otherwise frozen parameters. Only train/validation data select
hyperparameters and one of model-score thresholds 0.3/0.5/0.7. The cost rule assigns five units to
a false negative, two to a false positive and first requires validation recall of at least 0.75.

Selected artifacts:

| Candidate | Selected configuration | Threshold | Artifact hash |
|---|---|---:|---|
| Logistic | `C=10`, no class weighting, liblinear | 0.7 | `67ab25274ea4fc70e7154f521060b98abe0c8d3ccccb4250fe1348ba8603c947` |
| XGBoost | depth 2, 16 estimators, CPU hist, one thread | 0.7 | `1eb6f54d30d97baee0b8d57cd2f7b9b4b690ffce34d01db8169e20181cec2f78` |

Logistic coefficients are stored in exact ordered standardized-feature order. XGBoost gain
importance is stored where a split used a feature. These are associations, not causal explanations.

## Held-out synthetic measurements

The final four test rows were inspected after the experiment, calibration and threshold rules were
declared. These tiny fictional-fixture results are raw harness evidence only.

| Artifact | TP | FP | TN | FN | Precision | Recall | F1 | PR-AUC/AP | ROC-AUC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Deterministic heuristic | 2 | 2 | 0 | 0 | 0.50 | 1.00 | 0.66666667 | 0.41666667 | 0.125 |
| Logistic candidate | 1 | 1 | 1 | 1 | 0.50 | 0.50 | 0.50 | 0.50 | 0.25 |
| XGBoost candidate | 1 | 2 | 0 | 1 | 0.33333333 | 0.50 | 0.40 | 0.41666667 | 0.25 |

Logistic has higher ranking metrics than the heuristic on these four rows but lower recall/F1 at the
validation-selected threshold. XGBoost does not add defensible value. No statistical or product
conclusion is possible at this sample size.

## Calibration and uncertainty

Before final-test inspection, the experiment froze sigmoid/Platt and isotonic candidates, a
training-prevalence constant Brier baseline, 10 equal-width reliability bins, 20 rows per bin,
minimum 200 validation rows and 50 rows per class, maximum ECE 0.05, maximum bin gap 0.10 and
minimum Brier improvement 0.01. The four validation rows fail the minimum-sample gate, so
calibration is not attempted. Candidate numbers remain model scores/bands; calibrated probability
is null and probability wording is prohibited.

## Promotion, rollback and privacy

Both learned models remain `candidate_not_promoted`. The deterministic heuristic is the active and
rollback artifact because the evidence is synthetic, lacks a repository holdout, fails calibration
sample requirements and does not establish product value. Any later promotion requires a new
immutable dataset/artifact, leakage review, held-out comparison and human approval.

No public repository was mined, no customer/private code was used, no model was downloaded and no
hosted or paid provider was called. The fixture remains MIT-licensed under its recorded source
admission.

## Reproduction

Run:

```text
uv sync --frozen --group dev --group ml
uv run python -m eng.evaluate_m5_classical --check
uv run pytest tests/unit/test_classical_ml.py tests/web/test_risk_evidence.py
```

The committed run was byte-repeatable on its recorded Windows x86-64 CPU environment. The check
allows at most `1e-8` absolute numeric variation after excluding native XGBoost bytes and recorded
platform identity; model/runtime checksums remain exact for the committed artifact. GPU training is
not used.
