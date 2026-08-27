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
