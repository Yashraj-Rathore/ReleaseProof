# 45 — M11 Semantic Model Card

## Artifact identity

- Card version: `semantic-model-card-v1`
- Dataset: `datasets/public/m11_semantic_dataset_v1.json`, file SHA-256
  `c56e3ee5b97fdcec858cbe13103af8032736f58a3d83915f0b8f098d61621782`
- Frozen embeddings: `artifacts/evaluation/m11_minilm_embeddings_v1.json`, file SHA-256
  `ed149aa1b34c0be265d2fce90e21712ec1b20ab7bd791a4423a231bfe4ef92f7`
- PyTorch head: `models/public/m11_semantic_head_v1.json`, file SHA-256
  `8be3cfb757454a072a6827323f342bc43be672c3f95781e0e72049a8568a7d0c`
- Evaluation: `artifacts/evaluation/m11_semantic_eval_v1.json`, file SHA-256
  `fca8f5426a2c50bc6624482b71f3c331158fd6fa4f7468d2840adb3a4f019693`
- Dataset manifest SHA-256:
  `eddf5fc7000fc3c459094b48a1b01acd0c10ab9bc0db3fc01616f2df50bf4645`
- Model artifact SHA-256:
  `217ae49a7c42046db89428564b17730b730d6a694a4778f6d0d3a8755fac89cd`
- Model-state SHA-256:
  `6e0c7a7a944c401e6d8bc63c805c3d3f10961e51e563430308cc76b58eea33fd`
- Training code commit: `c05854dd3d26ee2e2aa2ad2fce336263fc2c742c`

The committed artifacts are small synthetic evidence. The pretrained weights are not committed;
they must be provisioned explicitly by exact revision and checksum into the ignored private model
directory. Load and inference are local-files-only with remote code disabled.

## Intended and prohibited use

The experiment classifies bounded change text into eight multi-label semantic categories. It
validates a provenance-controlled semantic dataset, tokenization/representation comparison,
deterministic PyTorch training, held-out evaluation, robustness checks and artifact lineage.

It must not be used or described as a production risk probability, incident predictor, merge or
deployment authority, customer-quality measurement, general code-understanding benchmark or
representative latency result. It is not wired into active risk scoring or recommendation fusion.

## Data, labels and privacy

The separate dataset derives from the admitted MIT-licensed M4 fictional fixture and inherits the
unchanged M4 temporal split and checksums: 6 train, 4 validation, 4 held-out test and 2 excluded
rows. There is only one repository. Category annotations are explicitly synthetic, outcome-blind,
CC0-1.0 metadata and cover all 16 source rows.

Only normalized changed-file path, status and patch are admitted to semantic text. Outcome,
proxy-label, observation-window result and deployment fields are blinded. Text is UTF-8 bounded to
4,096 bytes, exact text cannot cross split boundaries, and tokenizer input is capped at 256 tokens.
The fixture has no customer/private code and cannot establish annotation quality, repository
generalization or real prevalence. `api_compatibility`, `concurrency_async` and `unknown_other`
have no positive training examples; several test classes have no positive support.

## Encoder and selection

The encoder is Apache-2.0
`sentence-transformers/all-MiniLM-L6-v2@1110a243fdf4706b3f48f1d95db1a4f5529b4d41`,
384 dimensions. Its `model.safetensors` SHA-256 is
`53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db`.
The runtime is CPython 3.13.15, CPU PyTorch 2.13.0, Transformers 5.15.1 and
sentence-transformers 6.0.0.

A train-only word unigram/bigram TF-IDF logistic baseline and a frozen MiniLM-embedding logistic
baseline were compared on validation only. At the selected 0.3 threshold, TF-IDF produced micro-F1
0.4705882353 and macro-F1 0.2666666667; frozen MiniLM produced micro-F1 0.5333333333 and macro-F1
0.35. The pretrained representation was therefore selected, but the encoder was not fine-tuned:
six training rows cannot support that complexity.

## PyTorch training

The multi-label head is one 384-by-8 linear layer with 3,080 trainable parameters. It uses
`BCEWithLogitsLoss`, AdamW, seed 1729, float64 CPU tensors, batch size 2, learning rate 0.05,
weight decay 0.01, deterministic algorithms, a 200-epoch ceiling and patience-20 early stopping.
Mixed precision is disabled because it was not verified for this deterministic CPU profile.
Checkpoints retain safe JSON tensor state rather than pickle; validation selected epoch 6 and
threshold 0.3, and training stopped early.

## Held-out synthetic measurements

The untouched four-row test split produced exact-match 0.0, hamming loss 0.21875, micro-F1
0.5333333333, macro-F1 0.35, micro average precision 0.767816092 and micro ROC-AUC 0.8185185185.
These ranking figures are unstable at four rows and undefined classes are excluded only from their
named macro summaries.

| Category | Support | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| API compatibility | 1 | 0.0 | 0.0 | 0.0 |
| Auth/security | 2 | 0.6666666667 | 1.0 | 0.8 |
| Concurrency/async | 0 | 0.0 | 0.0 | 0.0 |
| Database/schema | 0 | 0.0 | 0.0 | 0.0 |
| Dependency/configuration | 1 | 1.0 | 1.0 | 1.0 |
| Performance-sensitive | 1 | 1.0 | 1.0 | 1.0 |
| Test/docs-only | 0 | 0.0 | 0.0 | 0.0 |
| Unknown/other | 0 | 0.0 | 0.0 | 0.0 |

All four held-out rows have at least one classification error. The model misses the only API
compatibility label and over-predicts test/docs-only on every test row. Per-repository reporting is
present, but it is the same four-row result because the dataset contains one repository. Collapsing
whitespace preserved 100% prediction-cell and exact-row prediction agreement.

## Calibration, incremental value and promotion

The frozen calibration gate requires at least 200 held-out rows. Calibration is therefore not
attempted, calibrated probability is null, and all outputs are explicitly uncalibrated model
scores. A diagnostic Brier value is not promoted as calibration evidence.

The predeclared ensemble takes the maximum of the frozen XGBoost score and the maximum score among
six risk-related semantic categories. On the same four test rows it adds 0.00 F1 and 0.00 average
precision over the best existing candidate. It also fails the minimum 200 rows, 50 rows per class
and three repositories gates. The semantic model remains `candidate_not_promoted`, active
recommendations remain unchanged, and `deterministic-heuristic-v1` remains the rollback/active
artifact. Promotion requires a new immutable, licensed, multi-repository dataset and human review.

## Environment, latency and failure behavior

The recorded Windows x86-64 CPU run encoded a 16-row batch ten times after model load: median
48.50185 ms, minimum 46.8459 ms and observed p95 52.3711 ms. This excludes cold load, database,
queue and application overhead and is not a service SLO.

Missing/incomplete/tampered model caches, embeddings, model state or lineage fail closed. The
normal validator rebuilds from committed embeddings without a network or model download. No hosted
or paid provider was called, and the model cannot merge, deploy, execute code or widen a sandbox.

GitHub Actions run `33767255599` passed exact commit
`05652062d7fba69eb48427357173d05d366b83ab` on 2026-09-03, including the canonical Linux
rebuild/tests, authoritative PostgreSQL contracts, Compose, the pinned fixture runner and live
sandbox/SeaweedFS checks. Those non-M11 infrastructure checks guard existing boundaries; they do
not turn this synthetic model result into a production-quality or arbitrary-code safety claim.

## Reproduction

```text
uv sync --frozen --group dev --group ml --group semantic --group ai
uv run python -m eng.evaluate_m11_semantic --check
uv run pytest tests/unit/test_semantic_model.py
```

To reproduce the original real-encoder artifact intentionally, first run
`uv run python -m eng.provision_m11_encoder`, review the verified local manifest, then run the
evaluator with `--write`, the explicit ignored model directory and an exact training-code commit.
That provisioning step downloads the named public weights; it is never part of tests or implicit
runtime behavior.
