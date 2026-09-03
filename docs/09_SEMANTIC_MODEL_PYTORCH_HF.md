# 09 — Semantic Model with PyTorch + Hugging Face

## Purpose
Demonstrate real deep learning by classifying semantic change categories that numeric features do not capture well.

## Primary task
Bounded multi-label classification of changed code/PR context into categories such as:
- auth/security
- database/schema
- concurrency/async
- API compatibility
- dependency/configuration
- performance-sensitive
- test/docs-only
- unknown/other

## Inputs
Bounded PR title/body, file paths, normalized/truncated diff chunks, deterministic tags. Secret scanning/redaction occurs before any hosted path. Context size is explicit.

## Training
Start from a small licensed pretrained code/text transformer. Do not train a foundation model. Owner must understand tokenizer, tensors/batches, loss, optimizer, backprop, checkpointing, overfitting and inference. PEFT/LoRA is optional only after a proper baseline.

Record seeds and nondeterminism limits; validation selects checkpoints/early stopping.

## Evaluation
Micro/macro F1, per-class precision/recall/F1/support, error examples, calibration if downstream score uses it, and leakage-resistant split when feasible.

## Model card
Intended/prohibited use, base model/license, dataset/provenance, training config, metrics, failure modes, privacy, hardware/latency, artifact checksum.

## Integration
Measure incremental value over deterministic/classical model before promotion.

## Serving
Load in a worker first. Add FastAPI only if RP-1402 returns `EXTRACT_FASTAPI` under the predeclared criteria and budgets in docs/20.

## Implemented M11 experiment

M11 implements `RP-1001..RP-1006` as a framework-light, optional experiment. The separate semantic
dataset inherits M4's frozen temporal split and admits only changed-file path, status and bounded
patch text. Synthetic multi-label annotations are outcome-blind and separately licensed. Exact
lineage, counts and leakage limitations are committed with the dataset.

The selection experiment compares train-only word unigram/bigram TF-IDF logistic regression with
the exact Apache-2.0 MiniLM representation. The frozen pretrained representation wins the
validation comparison, but the encoder is not fine-tuned because only six training rows exist. A
384-by-8 PyTorch linear head uses `BCEWithLogitsLoss`, AdamW, deterministic float64 CPU tensors,
seed 1729, bounded batches, validation checkpoints and patience-based early stopping. Mixed
precision is disabled because it is not verified for this deterministic CPU profile.

The untouched four-row synthetic test result is micro-F1 0.5333333333 and macro-F1 0.35. The full
artifact also records per-class/per-repository errors, raw predictions, whitespace robustness,
uncalibrated score diagnostics and measured local batch latency. Calibration is not attempted and
probability wording is prohibited. The semantic/XGBoost ensemble adds no F1 or average-precision
value over XGBoost and fails sample/repository gates, so the semantic model remains an optional
`candidate_not_promoted`; no Django model, serving endpoint or active recommendation change is
introduced. See docs/45 and docs/46.
