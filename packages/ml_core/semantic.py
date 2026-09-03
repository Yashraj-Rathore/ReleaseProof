"""Deterministic PyTorch semantic-head experiment over frozen HF embeddings."""

from __future__ import annotations

import copy
import math
import platform
import re
from dataclasses import dataclass
from importlib.metadata import version
from typing import cast

import numpy as np
import torch
from numpy.typing import NDArray
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from torch import nn

from packages.change_intel import canonical_hash
from packages.dataset_core import DatasetSplit, SemanticDataset, SemanticDatasetRow
from packages.retrieval_core import EMBEDDING_ARTIFACT

SEMANTIC_EMBEDDING_SCHEMA_VERSION = "semantic-frozen-embeddings-v1"
SEMANTIC_EXPERIMENT_VERSION = "semantic-risk-experiment-v1"
SEMANTIC_HEAD_ARTIFACT_VERSION = "semantic-minilm-linear-head-v1"
SEMANTIC_HEAD_SCHEMA_VERSION = "semantic-head-artifact-v1"
SEMANTIC_EVALUATION_VERSION = "semantic-evaluation-v1"
SEMANTIC_THRESHOLD_POLICY_VERSION = "semantic-threshold-v1"
SEMANTIC_ENSEMBLE_EXPERIMENT_VERSION = "semantic-risk-ensemble-v1"
SEMANTIC_MODEL_CARD_VERSION = "semantic-model-card-v1"
SEMANTIC_RUNTIME = {
    "python": "3.13.15",
    "sentence-transformers": "6.0.0",
    "torch": "2.13.0",
    "transformers": "5.15.1",
}
RANDOM_SEED = 1729
EMBEDDING_DIMENSION = 384
MAX_TOKENS = 256
TRAINING_BATCH_SIZE = 2
MAX_EPOCHS = 200
EARLY_STOPPING_PATIENCE = 20
EARLY_STOPPING_MIN_DELTA = 1e-7
LEARNING_RATE = 0.05
WEIGHT_DECAY = 0.01
THRESHOLD_CANDIDATES = (0.3, 0.5, 0.7)
MINIMUM_PROMOTION_ROWS = 200
MINIMUM_PROMOTION_ROWS_PER_CLASS = 50
MINIMUM_PROMOTION_REPOSITORIES = 3
MINIMUM_INCREMENTAL_F1 = 0.02
MINIMUM_INCREMENTAL_PR_AUC = 0.02
NUMERIC_REPRODUCIBILITY_TOLERANCE = 1e-7

_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class SemanticModelError(ValueError):
    """A semantic dataset/model/artifact boundary is incompatible."""


@dataclass(frozen=True, slots=True)
class SemanticScore:
    artifact_version: str
    artifact_sha256: str
    dataset_manifest_sha256: str
    embedding_model_id: str
    embedding_revision: str
    categories: tuple[str, ...]
    model_scores: tuple[float, ...]
    predicted_categories: tuple[str, ...]
    threshold: float
    calibrated_probability: None
    probability_display_allowed: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "artifact_sha256": self.artifact_sha256,
            "artifact_version": self.artifact_version,
            "calibrated_probability": self.calibrated_probability,
            "categories": list(self.categories),
            "dataset_manifest_sha256": self.dataset_manifest_sha256,
            "embedding_model_id": self.embedding_model_id,
            "embedding_revision": self.embedding_revision,
            "model_scores": list(self.model_scores),
            "predicted_categories": list(self.predicted_categories),
            "probability_display_allowed": self.probability_display_allowed,
            "threshold": self.threshold,
        }


def _round(value: float) -> float:
    return round(float(value), 10)


def _number(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SemanticModelError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise SemanticModelError(f"{field} must be finite")
    return result


def _integer(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SemanticModelError(f"{field} must be an integer")
    return value


def _canonical_json_sha256(value: object) -> str:
    return canonical_hash(value)


def _runtime_versions() -> dict[str, str]:
    torch_version = version("torch").split("+")[0]
    return {
        "python": platform.python_version(),
        "sentence-transformers": version("sentence-transformers"),
        "torch": torch_version,
        "transformers": version("transformers"),
    }


def require_semantic_runtime() -> dict[str, str]:
    runtime = _runtime_versions()
    if runtime != SEMANTIC_RUNTIME:
        raise SemanticModelError(f"semantic runtime is incompatible: {runtime!r}")
    return runtime


def _eligible_rows(dataset: SemanticDataset, split: DatasetSplit) -> tuple[SemanticDatasetRow, ...]:
    return tuple(row for row in dataset.rows if row.split is split)


def _label_matrix(rows: tuple[SemanticDatasetRow, ...]) -> NDArray[np.float64]:
    return np.asarray([row.label_vector for row in rows], dtype=np.float64)


def _validate_matrix(matrix: NDArray[np.float64], *, rows: int, columns: int) -> None:
    if matrix.shape != (rows, columns) or not np.isfinite(matrix).all():
        raise SemanticModelError("semantic matrix shape or values are invalid")


def validate_frozen_embeddings(
    artifact: dict[str, object], *, dataset: SemanticDataset
) -> dict[str, dict[str, object]]:
    required = {
        "dataset_manifest_sha256",
        "encoder",
        "generation",
        "root_sha256",
        "rows",
        "schema_version",
        "synthetic",
    }
    if (
        set(artifact) != required
        or artifact.get("schema_version") != SEMANTIC_EMBEDDING_SCHEMA_VERSION
    ):
        raise SemanticModelError("frozen semantic embedding schema is invalid")
    stored_hash = artifact.get("root_sha256")
    payload = {key: value for key, value in artifact.items() if key != "root_sha256"}
    if not isinstance(stored_hash, str) or _canonical_json_sha256(payload) != stored_hash:
        raise SemanticModelError("frozen semantic embedding checksum is invalid")
    if artifact.get("dataset_manifest_sha256") != dataset.manifest_sha256:
        raise SemanticModelError("frozen embeddings do not match the semantic dataset")
    encoder = artifact.get("encoder")
    expected_encoder = {
        "adapter_version": "hf-semantic-encoder-v1",
        "dimension": EMBEDDING_DIMENSION,
        "license": EMBEDDING_ARTIFACT.license,
        "max_tokens": MAX_TOKENS,
        "model_id": EMBEDDING_ARTIFACT.model_id,
        "revision": EMBEDDING_ARTIFACT.revision,
        "safetensors_sha256": EMBEDDING_ARTIFACT.safetensors_sha256,
    }
    if encoder != expected_encoder or artifact.get("synthetic") is not True:
        raise SemanticModelError("frozen semantic encoder identity is invalid")
    raw_rows = artifact.get("rows")
    if not isinstance(raw_rows, list) or len(raw_rows) != len(dataset.rows):
        raise SemanticModelError("frozen semantic embedding rows are incomplete")
    dataset_rows = {row.snapshot_id: row for row in dataset.rows}
    parsed: dict[str, dict[str, object]] = {}
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict) or set(raw_row) != {
            "original",
            "snapshot_id",
            "whitespace_variant",
        }:
            raise SemanticModelError("frozen semantic embedding row schema is invalid")
        snapshot_id = raw_row.get("snapshot_id")
        if (
            not isinstance(snapshot_id, str)
            or snapshot_id in parsed
            or snapshot_id not in dataset_rows
        ):
            raise SemanticModelError("frozen semantic embedding snapshot identity is invalid")
        original = raw_row.get("original")
        variant = raw_row.get("whitespace_variant")
        if not isinstance(original, dict) or not isinstance(variant, dict):
            raise SemanticModelError("frozen semantic embedding payload is invalid")
        for name, item in (("original", original), ("whitespace_variant", variant)):
            required_vector_fields = {
                "text_sha256",
                "token_count",
                "truncated",
                "vector",
                "vector_sha256",
            }
            if set(item) != required_vector_fields:
                raise SemanticModelError(f"frozen {name} vector schema is invalid")
            vector = item.get("vector")
            if (
                not isinstance(vector, list)
                or len(vector) != EMBEDDING_DIMENSION
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    for value in vector
                )
            ):
                raise SemanticModelError(f"frozen {name} vector is invalid")
            vector_values = [_round(float(value)) for value in vector]
            if item.get("vector_sha256") != _canonical_json_sha256(vector_values):
                raise SemanticModelError(f"frozen {name} vector checksum is invalid")
            token_count = item.get("token_count")
            if (
                isinstance(token_count, bool)
                or not isinstance(token_count, int)
                or token_count < 1
                or item.get("truncated") is not (token_count > MAX_TOKENS)
            ):
                raise SemanticModelError(f"frozen {name} tokenization metadata is invalid")
        if original.get("text_sha256") != dataset_rows[snapshot_id].text_sha256:
            raise SemanticModelError("frozen original text does not match the dataset")
        parsed[snapshot_id] = cast(dict[str, object], raw_row)
    if set(parsed) != set(dataset_rows):
        raise SemanticModelError("frozen semantic embedding identity set is invalid")
    return parsed


def _embedding_matrix(
    rows: tuple[SemanticDatasetRow, ...],
    embeddings: dict[str, dict[str, object]],
    *,
    variant: str = "original",
) -> NDArray[np.float64]:
    result = np.asarray(
        [cast(dict[str, object], embeddings[row.snapshot_id][variant])["vector"] for row in rows],
        dtype=np.float64,
    )
    _validate_matrix(result, rows=len(rows), columns=EMBEDDING_DIMENSION)
    return result


def _confusion_metrics(
    labels: NDArray[np.float64],
    scores: NDArray[np.float64],
    threshold: float,
    categories: tuple[str, ...],
) -> dict[str, object]:
    predictions = (scores >= threshold).astype(np.int64)
    truth = labels.astype(np.int64)
    per_class: dict[str, dict[str, object]] = {}
    class_f1: list[float] = []
    class_ap: list[float] = []
    class_roc: list[float] = []
    for index, category in enumerate(categories):
        actual = truth[:, index]
        predicted = predictions[:, index]
        tp = int(np.sum((actual == 1) & (predicted == 1)))
        fp = int(np.sum((actual == 0) & (predicted == 1)))
        tn = int(np.sum((actual == 0) & (predicted == 0)))
        fn = int(np.sum((actual == 1) & (predicted == 0)))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        support = int(actual.sum())
        ap: float | None = None
        roc: float | None = None
        if 0 < support < len(actual):
            ap = float(average_precision_score(actual, scores[:, index]))
            roc = float(roc_auc_score(actual, scores[:, index]))
            class_ap.append(ap)
            class_roc.append(roc)
        class_f1.append(f1)
        per_class[category] = {
            "false_negative": fn,
            "false_positive": fp,
            "f1": _round(f1),
            "pr_auc_average_precision": _round(ap) if ap is not None else None,
            "precision": _round(precision),
            "prevalence": _round(support / len(actual)) if len(actual) else None,
            "recall": _round(recall),
            "roc_auc": _round(roc) if roc is not None else None,
            "support": support,
            "true_negative": tn,
            "true_positive": tp,
        }
    tp_micro = int(np.sum((truth == 1) & (predictions == 1)))
    fp_micro = int(np.sum((truth == 0) & (predictions == 1)))
    fn_micro = int(np.sum((truth == 1) & (predictions == 0)))
    precision_micro = tp_micro / (tp_micro + fp_micro) if tp_micro + fp_micro else 0.0
    recall_micro = tp_micro / (tp_micro + fn_micro) if tp_micro + fn_micro else 0.0
    f1_micro = (
        2 * precision_micro * recall_micro / (precision_micro + recall_micro)
        if precision_micro + recall_micro
        else 0.0
    )
    flat_truth = truth.ravel()
    flat_scores = scores.ravel()
    micro_ap = float(average_precision_score(flat_truth, flat_scores))
    micro_roc = float(roc_auc_score(flat_truth, flat_scores))
    return {
        "exact_match": _round(float(np.mean(np.all(predictions == truth, axis=1)))),
        "hamming_loss": _round(float(np.mean(predictions != truth))),
        "macro_f1": _round(float(np.mean(class_f1))),
        "macro_pr_auc_average_precision_defined_classes": (
            _round(float(np.mean(class_ap))) if class_ap else None
        ),
        "macro_roc_auc_defined_classes": _round(float(np.mean(class_roc))) if class_roc else None,
        "micro_f1": _round(f1_micro),
        "micro_pr_auc_average_precision": _round(micro_ap),
        "micro_roc_auc": _round(micro_roc),
        "per_class": per_class,
        "row_count": len(labels),
        "threshold": threshold,
    }


def _select_threshold(
    labels: NDArray[np.float64], scores: NDArray[np.float64], categories: tuple[str, ...]
) -> tuple[float, list[dict[str, object]]]:
    candidates: list[dict[str, object]] = []
    for threshold in THRESHOLD_CANDIDATES:
        metrics = _confusion_metrics(labels, scores, threshold, categories)
        candidates.append(
            {
                "macro_f1": metrics["macro_f1"],
                "micro_f1": metrics["micro_f1"],
                "threshold": threshold,
            }
        )
    selected = max(
        candidates,
        key=lambda item: (
            _number(item["macro_f1"], field="macro_f1"),
            _number(item["micro_f1"], field="micro_f1"),
            _number(item["threshold"], field="threshold"),
        ),
    )
    return _number(selected["threshold"], field="selected threshold"), candidates


def _binary_logistic_scores(
    train_x: NDArray[np.float64],
    train_y: NDArray[np.float64],
    evaluation_x: NDArray[np.float64],
) -> NDArray[np.float64]:
    columns: list[NDArray[np.float64]] = []
    for index in range(train_y.shape[1]):
        target = train_y[:, index].astype(np.int64)
        unique = np.unique(target)
        if len(unique) == 1:
            columns.append(np.full(len(evaluation_x), float(unique[0]), dtype=np.float64))
            continue
        model = LogisticRegression(
            C=1.0,
            max_iter=1_000,
            random_state=RANDOM_SEED,
            solver="liblinear",
        )
        model.fit(train_x, target)
        columns.append(cast(NDArray[np.float64], model.predict_proba(evaluation_x)[:, 1]))
    return np.column_stack(columns)


def benchmark_representations(
    dataset: SemanticDataset, embedding_artifact: dict[str, object]
) -> dict[str, object]:
    embeddings = validate_frozen_embeddings(embedding_artifact, dataset=dataset)
    train = _eligible_rows(dataset, DatasetSplit.TRAIN)
    validation = _eligible_rows(dataset, DatasetSplit.VALIDATION)
    train_y = _label_matrix(train)
    validation_y = _label_matrix(validation)

    vectorizer = TfidfVectorizer(
        lowercase=True,
        max_features=256,
        ngram_range=(1, 2),
        token_pattern=r"(?u)\b[\w./+-]+\b",  # noqa: S106 - sklearn token regex
    )
    train_tfidf = cast(
        NDArray[np.float64], vectorizer.fit_transform([row.text for row in train]).toarray()
    )
    validation_tfidf = cast(
        NDArray[np.float64], vectorizer.transform([row.text for row in validation]).toarray()
    )
    tfidf_scores = _binary_logistic_scores(train_tfidf, train_y, validation_tfidf)
    tfidf_threshold, tfidf_candidates = _select_threshold(
        validation_y, tfidf_scores, dataset.categories
    )
    train_embedding = _embedding_matrix(train, embeddings)
    validation_embedding = _embedding_matrix(validation, embeddings)
    embedding_scores = _binary_logistic_scores(train_embedding, train_y, validation_embedding)
    embedding_threshold, embedding_candidates = _select_threshold(
        validation_y, embedding_scores, dataset.categories
    )
    tfidf_metrics = _confusion_metrics(
        validation_y, tfidf_scores, tfidf_threshold, dataset.categories
    )
    embedding_metrics = _confusion_metrics(
        validation_y, embedding_scores, embedding_threshold, dataset.categories
    )
    pretrained_selected = _number(
        embedding_metrics["macro_f1"], field="embedding macro_f1"
    ) >= _number(tfidf_metrics["macro_f1"], field="tfidf macro_f1")
    return {
        "decision": {
            "encoder_fine_tuning": False,
            "pretrained_representation_selected_for_head": pretrained_selected,
            "reason": (
                "Use the frozen pretrained representation for a bounded PyTorch head; do not "
                "fine-tune the encoder on six training rows."
                if pretrained_selected
                else "The pretrained representation did not match the simpler validation baseline; "
                "retain the PyTorch head only as pipeline evidence and do not select it."
            ),
        },
        "pretrained_minilm_logistic": {
            "representation": "frozen normalized 384-dimensional MiniLM embedding",
            "threshold_candidates": embedding_candidates,
            "validation_metrics": embedding_metrics,
        },
        "tfidf_logistic": {
            "representation": "train-only word unigram/bigram TF-IDF capped at 256 features",
            "threshold_candidates": tfidf_candidates,
            "validation_metrics": tfidf_metrics,
            "vocabulary_size": len(vectorizer.vocabulary_),
        },
    }


class _SemanticLinearHead(nn.Module):
    def __init__(self, output_dimension: int) -> None:
        super().__init__()
        self.linear = nn.Linear(EMBEDDING_DIMENSION, output_dimension, dtype=torch.float64)
        nn.init.zeros_(self.linear.weight)
        nn.init.zeros_(self.linear.bias)

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        return cast(torch.Tensor, self.linear(values))


def _state_payload(model: _SemanticLinearHead) -> dict[str, object]:
    return {
        "bias": [_round(value) for value in model.linear.bias.detach().cpu().tolist()],
        "weight": [
            [_round(value) for value in row] for row in model.linear.weight.detach().cpu().tolist()
        ],
    }


def _scores(model: _SemanticLinearHead, matrix: NDArray[np.float64]) -> NDArray[np.float64]:
    with torch.no_grad():
        logits = model(torch.from_numpy(matrix).to(dtype=torch.float64))
        return cast(NDArray[np.float64], torch.sigmoid(logits).cpu().numpy())


def _train_head(
    train_x: NDArray[np.float64],
    train_y: NDArray[np.float64],
    validation_x: NDArray[np.float64],
    validation_y: NDArray[np.float64],
) -> tuple[_SemanticLinearHead, dict[str, object]]:
    torch.manual_seed(RANDOM_SEED)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    model = _SemanticLinearHead(train_y.shape[1])
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)
    positives = train_y.sum(axis=0)
    negatives = len(train_y) - positives
    pos_weight = np.where(positives > 0, negatives / np.maximum(positives, 1), 1.0)
    loss_function = nn.BCEWithLogitsLoss(
        pos_weight=torch.from_numpy(pos_weight).to(dtype=torch.float64)
    )
    train_tensor = torch.from_numpy(train_x).to(dtype=torch.float64)
    train_labels = torch.from_numpy(train_y).to(dtype=torch.float64)
    validation_tensor = torch.from_numpy(validation_x).to(dtype=torch.float64)
    validation_labels = torch.from_numpy(validation_y).to(dtype=torch.float64)

    best_loss = math.inf
    best_state: dict[str, torch.Tensor] | None = None
    best_epoch = 0
    without_improvement = 0
    checkpoints: list[dict[str, object]] = []
    history: list[dict[str, object]] = []
    for epoch in range(1, MAX_EPOCHS + 1):
        model.train()
        batch_losses: list[float] = []
        for start in range(0, len(train_tensor), TRAINING_BATCH_SIZE):
            optimizer.zero_grad(set_to_none=True)
            logits = model(train_tensor[start : start + TRAINING_BATCH_SIZE])
            loss = loss_function(logits, train_labels[start : start + TRAINING_BATCH_SIZE])
            loss.backward()
            optimizer.step()
            batch_losses.append(float(loss.detach().cpu()))
        model.eval()
        with torch.no_grad():
            validation_loss = float(
                loss_function(model(validation_tensor), validation_labels).detach().cpu()
            )
        history.append(
            {
                "epoch": epoch,
                "training_loss": _round(float(np.mean(batch_losses))),
                "validation_loss": _round(validation_loss),
            }
        )
        if validation_loss < best_loss - EARLY_STOPPING_MIN_DELTA:
            best_loss = validation_loss
            best_epoch = epoch
            without_improvement = 0
            best_state = {
                name: value.detach().clone() for name, value in model.state_dict().items()
            }
            checkpoints.append(
                {
                    "epoch": epoch,
                    "state_sha256": _canonical_json_sha256(_state_payload(model)),
                    "validation_loss": _round(validation_loss),
                }
            )
        else:
            without_improvement += 1
            if without_improvement >= EARLY_STOPPING_PATIENCE:
                break
    if best_state is None:
        raise SemanticModelError("semantic training did not produce a checkpoint")
    model.load_state_dict(best_state)
    model.eval()
    return model, {
        "best_epoch": best_epoch,
        "best_validation_loss": _round(best_loss),
        "checkpoint_count": len(checkpoints),
        "checkpoints": checkpoints,
        "early_stopped": len(history) < MAX_EPOCHS,
        "epochs_completed": len(history),
        "history": history,
    }


def _raw_predictions(
    rows: tuple[SemanticDatasetRow, ...],
    scores: NDArray[np.float64],
    threshold: float,
    categories: tuple[str, ...],
) -> list[dict[str, object]]:
    predictions: list[dict[str, object]] = []
    for row, row_scores in zip(rows, scores, strict=True):
        predicted = tuple(
            category
            for category, score in zip(categories, row_scores, strict=True)
            if score >= threshold
        )
        predictions.append(
            {
                "actual_categories": list(row.categories),
                "false_negative_categories": sorted(set(row.categories) - set(predicted)),
                "false_positive_categories": sorted(set(predicted) - set(row.categories)),
                "model_scores": {
                    category: _round(float(score))
                    for category, score in zip(categories, row_scores, strict=True)
                },
                "predicted_categories": list(predicted),
                "repository_numeric_id": row.repository_numeric_id,
                "snapshot_id": row.snapshot_id,
            }
        )
    return predictions


def _per_repository(
    rows: tuple[SemanticDatasetRow, ...],
    scores: NDArray[np.float64],
    threshold: float,
    categories: tuple[str, ...],
) -> dict[str, object]:
    repositories: dict[str, object] = {}
    for repository_id in sorted({row.repository_numeric_id for row in rows}):
        indexes = [
            index for index, row in enumerate(rows) if row.repository_numeric_id == repository_id
        ]
        labels = _label_matrix(tuple(rows[index] for index in indexes))
        repository_scores = scores[indexes]
        metrics = _confusion_metrics(labels, repository_scores, threshold, categories)
        raw = _raw_predictions(
            tuple(rows[index] for index in indexes), repository_scores, threshold, categories
        )
        repositories[str(repository_id)] = {
            "error_snapshot_ids": [
                item["snapshot_id"]
                for item in raw
                if item["false_negative_categories"] or item["false_positive_categories"]
            ],
            "metrics": metrics,
            "row_count": len(indexes),
        }
    return repositories


def _confidence_and_calibration(
    labels: NDArray[np.float64], scores: NDArray[np.float64], threshold: float
) -> dict[str, object]:
    flattened = scores.ravel()
    distances = np.abs(flattened - threshold)
    return {
        "calibration": {
            "calibrated_probability": None,
            "minimum_rows": MINIMUM_PROMOTION_ROWS,
            "probability_display_allowed": False,
            "raw_score_brier_diagnostic": _round(float(np.mean((scores - labels) ** 2))),
            "reason": "The held-out synthetic sample is below the frozen calibration minimum.",
            "status": "not_attempted_insufficient_sample",
        },
        "confidence_score_diagnostics": {
            "maximum_score": _round(float(np.max(flattened))),
            "mean_distance_from_selected_threshold": _round(float(np.mean(distances))),
            "mean_score": _round(float(np.mean(flattened))),
            "minimum_score": _round(float(np.min(flattened))),
            "wording": "uncalibrated model scores; not probabilities or certainty",
        },
    }


def _binary_risk_metrics(
    labels: NDArray[np.int64], scores: NDArray[np.float64]
) -> dict[str, object]:
    predictions = scores >= 0.5
    tp = int(np.sum((labels == 1) & predictions))
    fp = int(np.sum((labels == 0) & predictions))
    tn = int(np.sum((labels == 0) & ~predictions))
    fn = int(np.sum((labels == 1) & ~predictions))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "false_negative": fn,
        "false_positive": fp,
        "f1": _round(f1),
        "pr_auc_average_precision": _round(float(average_precision_score(labels, scores))),
        "precision": _round(precision),
        "prevalence": _round(float(np.mean(labels))),
        "recall": _round(recall),
        "roc_auc": _round(float(roc_auc_score(labels, scores))),
        "row_count": len(labels),
        "threshold": 0.5,
        "true_negative": tn,
        "true_positive": tp,
    }


def _incremental_value(
    *,
    test_rows: tuple[SemanticDatasetRow, ...],
    semantic_scores: NDArray[np.float64],
    threshold: float,
    categories: tuple[str, ...],
    risk_comparison: dict[str, object],
) -> dict[str, object]:
    raw_rows = risk_comparison.get("rows")
    if not isinstance(raw_rows, list) or len(raw_rows) != len(test_rows):
        raise SemanticModelError("risk comparison rows do not match the held-out semantic rows")
    by_id = {
        str(item["snapshot_id"]): item
        for item in raw_rows
        if isinstance(item, dict) and isinstance(item.get("snapshot_id"), str)
    }
    if set(by_id) != {row.snapshot_id for row in test_rows}:
        raise SemanticModelError("risk comparison snapshot identities are invalid")
    risky_categories = {
        "api_compatibility",
        "auth_security",
        "concurrency_async",
        "database_schema",
        "dependency_configuration",
        "performance_sensitive",
    }
    risky_indexes = [
        index for index, category in enumerate(categories) if category in risky_categories
    ]
    attention_scores = np.max(semantic_scores[:, risky_indexes], axis=1)
    labels = np.asarray(
        [
            int(cast(dict[str, object], by_id[row.snapshot_id])["proxy_positive"] is True)
            for row in test_rows
        ],
        dtype=np.int64,
    )
    heuristic_scores = np.asarray(
        [
            _number(
                cast(dict[str, object], by_id[row.snapshot_id])["heuristic_score"],
                field="heuristic_score",
            )
            for row in test_rows
        ],
        dtype=np.float64,
    )
    xgboost_scores = np.asarray(
        [
            _number(
                cast(dict[str, object], by_id[row.snapshot_id])["xgboost_score"],
                field="xgboost_score",
            )
            for row in test_rows
        ],
        dtype=np.float64,
    )
    # A fixed validation-declared OR-style candidate: semantic attention may raise, never lower,
    # the frozen XGBoost signal. It is evaluated once and is not tuned on held-out rows.
    ensemble_scores = np.maximum(xgboost_scores, attention_scores)
    heuristic = _binary_risk_metrics(labels, heuristic_scores)
    boosted = _binary_risk_metrics(labels, xgboost_scores)
    ensemble = _binary_risk_metrics(labels, ensemble_scores)
    f1_delta = _number(ensemble["f1"], field="ensemble f1") - max(
        _number(heuristic["f1"], field="heuristic f1"),
        _number(boosted["f1"], field="xgboost f1"),
    )
    pr_delta = _number(ensemble["pr_auc_average_precision"], field="ensemble PR-AUC") - max(
        _number(heuristic["pr_auc_average_precision"], field="heuristic PR-AUC"),
        _number(boosted["pr_auc_average_precision"], field="xgboost PR-AUC"),
    )
    positive_count = int(labels.sum())
    negative_count = len(labels) - positive_count
    repositories = len({row.repository_numeric_id for row in test_rows})
    gate_checks = {
        "f1_gain_at_least_0_02": f1_delta >= MINIMUM_INCREMENTAL_F1,
        "held_out_rows_at_least_200": len(labels) >= MINIMUM_PROMOTION_ROWS,
        "pr_auc_gain_at_least_0_02": pr_delta >= MINIMUM_INCREMENTAL_PR_AUC,
        "recall_not_reduced": _number(ensemble["recall"], field="ensemble recall")
        >= max(
            _number(heuristic["recall"], field="heuristic recall"),
            _number(boosted["recall"], field="xgboost recall"),
        ),
        "repositories_at_least_3": repositories >= MINIMUM_PROMOTION_REPOSITORIES,
        "rows_per_class_at_least_50": min(positive_count, negative_count)
        >= MINIMUM_PROMOTION_ROWS_PER_CLASS,
    }
    return {
        "active_recommendation_changed": False,
        "candidate_configuration": {
            "combination": "max(frozen_xgboost_score, semantic_risky_category_max_score)",
            "risk_categories": sorted(risky_categories),
            "semantic_category_threshold": threshold,
            "version": SEMANTIC_ENSEMBLE_EXPERIMENT_VERSION,
        },
        "decision": "keep_semantic_optional_not_integrated",
        "gate_checks": gate_checks,
        "metrics": {
            "deterministic_heuristic": heuristic,
            "semantic_xgboost_candidate": ensemble,
            "xgboost_candidate": boosted,
        },
        "observed_deltas": {
            "f1_vs_best_existing": _round(f1_delta),
            "pr_auc_vs_best_existing": _round(pr_delta),
        },
        "reason": (
            "The synthetic four-row, one-repository holdout fails mandatory sample, repository, "
            "calibration, and defensible incremental-value gates."
        ),
        "source_artifacts": risk_comparison.get("source_artifacts"),
    }


def train_semantic_experiment(
    dataset: SemanticDataset,
    embedding_artifact: dict[str, object],
    *,
    training_code_commit: str,
    risk_comparison: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    if _SHA_PATTERN.fullmatch(training_code_commit) is None:
        raise SemanticModelError("semantic training code commit must be a 40-character SHA")
    runtime = require_semantic_runtime()
    embeddings = validate_frozen_embeddings(embedding_artifact, dataset=dataset)
    benchmark = benchmark_representations(dataset, embedding_artifact)
    train = _eligible_rows(dataset, DatasetSplit.TRAIN)
    validation = _eligible_rows(dataset, DatasetSplit.VALIDATION)
    test = _eligible_rows(dataset, DatasetSplit.TEST)
    if not train or not validation or not test:
        raise SemanticModelError("semantic experiment requires frozen train/validation/test rows")
    train_x = _embedding_matrix(train, embeddings)
    validation_x = _embedding_matrix(validation, embeddings)
    test_x = _embedding_matrix(test, embeddings)
    train_y = _label_matrix(train)
    validation_y = _label_matrix(validation)
    test_y = _label_matrix(test)
    model, training = _train_head(train_x, train_y, validation_x, validation_y)
    validation_scores = _scores(model, validation_x)
    threshold, threshold_evidence = _select_threshold(
        validation_y, validation_scores, dataset.categories
    )
    test_scores = _scores(model, test_x)
    state = _state_payload(model)
    state_sha256 = _canonical_json_sha256(state)
    model_payload: dict[str, object] = {
        "artifact_version": SEMANTIC_HEAD_ARTIFACT_VERSION,
        "categories": list(dataset.categories),
        "dataset": {
            "dataset_version": dataset.dataset_version,
            "manifest_sha256": dataset.manifest_sha256,
            "source_manifest_sha256": dataset.source_manifest_sha256,
            "source_split_sha256": dataset.source_split_sha256,
            "synthetic": True,
        },
        "embedding_artifact_sha256": embedding_artifact["root_sha256"],
        "encoder": embedding_artifact["encoder"],
        "experiment_version": SEMANTIC_EXPERIMENT_VERSION,
        "lifecycle": "candidate_not_promoted",
        "model_card_version": SEMANTIC_MODEL_CARD_VERSION,
        "probability_display_allowed": False,
        "runtime_compatibility": runtime,
        "schema_version": SEMANTIC_HEAD_SCHEMA_VERSION,
        "state": state,
        "state_sha256": state_sha256,
        "threshold": threshold,
        "threshold_policy_version": SEMANTIC_THRESHOLD_POLICY_VERSION,
        "training": {
            **training,
            "config": {
                "batch_size": TRAINING_BATCH_SIZE,
                "cpu_only": True,
                "deterministic_algorithms": True,
                "early_stopping_min_delta": EARLY_STOPPING_MIN_DELTA,
                "early_stopping_patience": EARLY_STOPPING_PATIENCE,
                "loss": "BCEWithLogitsLoss",
                "max_epochs": MAX_EPOCHS,
                "mixed_precision": False,
                "mixed_precision_reason": "not verified for the CPU-only deterministic profile",
                "optimizer": "AdamW",
                "random_seed": RANDOM_SEED,
                "trainable_parameters": EMBEDDING_DIMENSION * len(dataset.categories)
                + len(dataset.categories),
                "weight_decay": WEIGHT_DECAY,
                "learning_rate": LEARNING_RATE,
            },
        },
        "training_code_commit": training_code_commit,
        "validation_selection": {
            "metrics": _confusion_metrics(
                validation_y, validation_scores, threshold, dataset.categories
            ),
            "threshold_candidates": threshold_evidence,
            "test_data_used_for_selection": False,
        },
    }
    model_artifact = {**model_payload, "artifact_sha256": _canonical_json_sha256(model_payload)}
    validate_semantic_model_artifact(model_artifact)

    whitespace_test_x = _embedding_matrix(test, embeddings, variant="whitespace_variant")
    whitespace_scores = _scores(model, whitespace_test_x)
    original_prediction = test_scores >= threshold
    variant_prediction = whitespace_scores >= threshold
    raw_predictions = _raw_predictions(test, test_scores, threshold, dataset.categories)
    token_counts = [
        _integer(
            cast(dict[str, object], embeddings[row.snapshot_id]["original"])["token_count"],
            field="token_count",
        )
        for row in dataset.rows
    ]
    stable_evaluation: dict[str, object] = {
        "benchmark": benchmark,
        "calibration_and_confidence": _confidence_and_calibration(test_y, test_scores, threshold),
        "dataset": dataset.as_dict()["manifest"],
        "embedding_artifact_sha256": embedding_artifact["root_sha256"],
        "error_analysis": {
            "failures": [
                item
                for item in raw_predictions
                if item["false_negative_categories"] or item["false_positive_categories"]
            ],
            "per_repository": _per_repository(test, test_scores, threshold, dataset.categories),
            "unseen_training_categories": [
                category
                for index, category in enumerate(dataset.categories)
                if int(train_y[:, index].sum()) == 0
            ],
        },
        "evaluation_version": SEMANTIC_EVALUATION_VERSION,
        "held_out": {
            "metrics": _confusion_metrics(test_y, test_scores, threshold, dataset.categories),
            "raw_predictions": raw_predictions,
            "test_rows_used_once_after_selection": True,
        },
        "incremental_value": _incremental_value(
            test_rows=test,
            semantic_scores=test_scores,
            threshold=threshold,
            categories=dataset.categories,
            risk_comparison=risk_comparison,
        ),
        "limitations": [
            "The dataset is explicitly synthetic and contains only 14 included rows.",
            "One repository cannot measure repository-holdout generalization.",
            "Several semantic categories have no training or held-out support.",
            "Proxy outcomes used only by the separate ensemble evaluation are not incidents.",
            "The frozen encoder was not fine-tuned; only a small linear head was trained.",
            "Model scores are uncalibrated and must not be presented as probabilities.",
            "No customer code, public repository, GPU, hosted provider, or model service was used.",
        ],
        "model_artifact_sha256": model_artifact["artifact_sha256"],
        "model_card_version": SEMANTIC_MODEL_CARD_VERSION,
        "promotion": {
            "active_model_changed": False,
            "decision": "candidate_not_promoted",
            "human_approval_required": True,
            "rollback": "deterministic-heuristic-v1",
        },
        "robustness": {
            "perturbation": (
                "collapse whitespace while retaining the same bounded path/status/patch tokens"
            ),
            "prediction_cell_agreement": _round(
                float(np.mean(original_prediction == variant_prediction))
            ),
            "row_exact_prediction_agreement": _round(
                float(np.mean(np.all(original_prediction == variant_prediction, axis=1)))
            ),
            "variant_metrics": _confusion_metrics(
                test_y, whitespace_scores, threshold, dataset.categories
            ),
        },
        "runtime_compatibility": runtime,
        "schema_version": SEMANTIC_EVALUATION_VERSION,
        "synthetic": True,
        "tokenization": {
            "max_observed_tokens": max(token_counts),
            "max_tokens": MAX_TOKENS,
            "mean_observed_tokens": _round(float(np.mean(token_counts))),
            "rows_truncated": sum(count > MAX_TOKENS for count in token_counts),
            "tokenizer_source": "exact local encoder revision",
        },
        "training_code_commit": training_code_commit,
    }
    evaluation = {
        **stable_evaluation,
        "root_sha256": _canonical_json_sha256(stable_evaluation),
    }
    return model_artifact, evaluation


def validate_semantic_model_artifact(artifact: dict[str, object]) -> None:
    required = {
        "artifact_sha256",
        "artifact_version",
        "categories",
        "dataset",
        "embedding_artifact_sha256",
        "encoder",
        "experiment_version",
        "lifecycle",
        "model_card_version",
        "probability_display_allowed",
        "runtime_compatibility",
        "schema_version",
        "state",
        "state_sha256",
        "threshold",
        "threshold_policy_version",
        "training",
        "training_code_commit",
        "validation_selection",
    }
    if set(artifact) != required:
        raise SemanticModelError("semantic model artifact top-level schema is invalid")
    payload = {key: value for key, value in artifact.items() if key != "artifact_sha256"}
    if artifact.get("artifact_sha256") != _canonical_json_sha256(payload):
        raise SemanticModelError("semantic model artifact checksum is invalid")
    if (
        artifact.get("schema_version") != SEMANTIC_HEAD_SCHEMA_VERSION
        or artifact.get("artifact_version") != SEMANTIC_HEAD_ARTIFACT_VERSION
        or artifact.get("lifecycle") != "candidate_not_promoted"
        or artifact.get("probability_display_allowed") is not False
        or artifact.get("runtime_compatibility") != SEMANTIC_RUNTIME
    ):
        raise SemanticModelError("semantic model artifact identity or lifecycle is invalid")
    categories = artifact.get("categories")
    state = artifact.get("state")
    if not isinstance(categories, list) or not categories or not isinstance(state, dict):
        raise SemanticModelError("semantic model categories or state are invalid")
    weight = state.get("weight")
    bias = state.get("bias")
    if (
        not isinstance(weight, list)
        or len(weight) != len(categories)
        or any(not isinstance(row, list) or len(row) != EMBEDDING_DIMENSION for row in weight)
        or not isinstance(bias, list)
        or len(bias) != len(categories)
    ):
        raise SemanticModelError("semantic model state shape is invalid")
    numeric_values = [value for row in weight for value in cast(list[object], row)] + bias
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in numeric_values
    ):
        raise SemanticModelError("semantic model state contains invalid values")
    if artifact.get("state_sha256") != _canonical_json_sha256(state):
        raise SemanticModelError("semantic model state checksum is invalid")
    threshold = artifact.get("threshold")
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or threshold not in THRESHOLD_CANDIDATES
    ):
        raise SemanticModelError("semantic model threshold is invalid")
    encoder = artifact.get("encoder")
    if not isinstance(encoder, dict) or encoder.get("revision") != EMBEDDING_ARTIFACT.revision:
        raise SemanticModelError("semantic model encoder lineage is invalid")
    training_commit = artifact.get("training_code_commit")
    if not isinstance(training_commit, str) or _SHA_PATTERN.fullmatch(training_commit) is None:
        raise SemanticModelError("semantic model training commit is invalid")


def score_semantic_embedding(
    artifact: dict[str, object], *, embedding: tuple[float, ...]
) -> SemanticScore:
    """Run optional candidate inference without changing the active recommendation."""
    validate_semantic_model_artifact(artifact)
    if len(embedding) != EMBEDDING_DIMENSION or any(
        not math.isfinite(value) for value in embedding
    ):
        raise SemanticModelError("semantic inference embedding is invalid")
    state = cast(dict[str, object], artifact["state"])
    weight = np.asarray(state["weight"], dtype=np.float64)
    bias = np.asarray(state["bias"], dtype=np.float64)
    logits = weight @ np.asarray(embedding, dtype=np.float64) + bias
    scores = 1.0 / (1.0 + np.exp(-logits))
    categories = tuple(cast(list[str], artifact["categories"]))
    threshold = _number(artifact["threshold"], field="threshold")
    predicted = tuple(
        category for category, score in zip(categories, scores, strict=True) if score >= threshold
    )
    dataset = cast(dict[str, object], artifact["dataset"])
    encoder = cast(dict[str, object], artifact["encoder"])
    return SemanticScore(
        artifact_version=SEMANTIC_HEAD_ARTIFACT_VERSION,
        artifact_sha256=str(artifact["artifact_sha256"]),
        dataset_manifest_sha256=str(dataset["manifest_sha256"]),
        embedding_model_id=str(encoder["model_id"]),
        embedding_revision=str(encoder["revision"]),
        categories=categories,
        model_scores=tuple(_round(float(score)) for score in scores),
        predicted_categories=predicted,
        threshold=threshold,
        calibrated_probability=None,
        probability_display_allowed=False,
    )


def comparison_payload(value: dict[str, object]) -> dict[str, object]:
    """Remove checksum fields for tolerant same-config reproducibility comparison."""
    result = copy.deepcopy(value)
    for key in list(result):
        if key.endswith("sha256"):
            result.pop(key)
    return result
