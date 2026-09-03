# 46 — M11 Owner Learning Note

## 1. Concept implemented

M11 implements an outcome-blind multi-label semantic dataset, two representation baselines, an
offline checksum-verified Hugging Face encoder, a deterministic PyTorch linear classification
head, early stopping/checkpoints, held-out error/robustness/calibration analysis and an
incremental-value experiment against existing risk signals.

## 2. Why it is used here

Tabular features capture size, paths and graph/history facts but can miss meaning inside a patch.
A semantic encoder maps bounded path/status/diff text into a dense vector where related changes can
be closer even without exact token overlap. A small trainable head then maps that representation to
ReleaseProof categories. It is only useful if the added signal beats simpler baselines and improves
the existing system on defensible held-out evidence.

## 3. Algorithm and data assumptions

- A tokenizer converts text to integer token IDs; MiniLM applies learned attention layers and
  pooling to produce one normalized 384-value vector per change.
- A batch is a group of vectors processed together. The linear layer produces eight logits. The
  sigmoid maps each logit to a score, but each category is independent and multiple labels may be
  active.
- `BCEWithLogitsLoss` combines a numerically stable sigmoid and binary cross-entropy for every
  row/category cell. Backpropagation computes parameter gradients; AdamW updates weights and bias.
- Only training rows update parameters. Validation selects threshold/checkpoint and triggers early
  stopping. Test rows are inspected once for final evidence.
- The fixture's synthetic labels, one repository, six training rows and unsupported categories
  violate assumptions needed for product generalization and calibration. Scores are not
  probabilities.
- Freezing the encoder limits trainable capacity and reproducibility risk. It does not make a tiny
  dataset representative or remove biases inherited from pretrained data.

## 4. Key code paths

- `packages/dataset_core/semantic.py`: admitted fields, annotation validation, text derivation,
  frozen split/lineage and leakage checks.
- `adapters/semantic/huggingface.py`: checksum-verified local-only encoder/tokenizer boundary.
- `packages/ml_core/semantic.py`: baselines, PyTorch training, metrics, calibration abstention,
  artifact validation, optional inference and ensemble gate.
- `eng/provision_m11_encoder.py`: explicit exact-revision download and local manifest.
- `eng/evaluate_m11_semantic.py`: frozen artifact generation and network-free reproduction check.
- `datasets/public/m11_semantic_dataset_v1.json`, `models/public/m11_semantic_head_v1.json` and
  `artifacts/evaluation/m11_semantic_eval_v1.json`: immutable data/model/evaluation evidence.

## 5. Exact experiment/test to rerun

```text
uv sync --frozen --group dev --group ml --group semantic --group ai
uv run python -m eng.evaluate_m4_baseline --check
uv run python -m eng.evaluate_m5_classical --check
uv run python -m eng.evaluate_m11_semantic --check
uv run pytest tests/unit/test_semantic_model.py
```

Inspect `benchmark`, `training`, `held_out`, `error_analysis`, `calibration_and_confidence`,
`robustness`, `incremental_value`, `promotion` and all SHA-256 lineage fields. Do not tune after
examining the held-out result.

## 6. Likely interview question and answer

**Question:** Why use a pretrained transformer but train only a linear PyTorch head, and why was it
not promoted?

**Answer:** The pretrained encoder supplies useful semantic structure that beat a train-only TF-IDF
baseline on validation, while freezing it avoids pretending six training rows can support
fine-tuning. The head still demonstrates tensors, batches, multi-label loss, backpropagation,
checkpoints and inference. It was not promoted because the four-row, one-repository synthetic test
set cannot support calibration or statistical lift, several classes have no support, and the
semantic/XGBoost ensemble added zero F1 and average precision over XGBoost.
