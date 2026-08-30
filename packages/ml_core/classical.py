"""Governed classical-model training, evaluation, artifacts, and inference."""

from __future__ import annotations

import base64
import hashlib
import math
import platform
import re
from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import version
from typing import cast

import numpy as np
import pandas as pd
import xgboost as xgb
from numpy.typing import NDArray
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from xgboost import XGBClassifier

from packages.change_intel import FEATURE_SCHEMA_VERSION, canonical_hash
from packages.change_intel.contracts import FeatureScalar
from packages.change_intel.features import FEATURE_DEFINITIONS
from packages.dataset_core import DatasetBuild, DatasetSplit, MaterializedFeatureRow, ProxyLabel
from packages.ml_core.baseline import (
    BASELINE_ARTIFACT_VERSION,
    THRESHOLD_POLICY_VERSION,
    baseline_artifact_hash,
    evaluate_baseline,
)

CLASSICAL_ARTIFACT_SCHEMA_VERSION = "classical-risk-artifact-v1"
CLASSICAL_EXPERIMENT_VERSION = "classical-risk-experiment-v1"
PREPROCESSOR_VERSION = "classical-preprocessor-v1"
LOGISTIC_ARTIFACT_VERSION = "logistic-risk-v1"
XGBOOST_ARTIFACT_VERSION = "xgboost-risk-v1"
CLASSICAL_THRESHOLD_POLICY_VERSION = "classical-threshold-v1"
MODEL_CARD_VERSION = "classical-model-card-v1"
RANDOM_SEED = 1729
MODEL_SCORE_THRESHOLDS = (0.3, 0.5, 0.7)
MINIMUM_VALIDATION_RECALL = 0.75
FALSE_NEGATIVE_COST = 5
FALSE_POSITIVE_COST = 2
CALIBRATION_MINIMUM_ROWS = 200
CALIBRATION_MINIMUM_PER_CLASS = 50
CALIBRATION_BIN_COUNT = 10
CALIBRATION_MINIMUM_BIN_ROWS = 20
CALIBRATION_MAX_ECE = 0.05
CALIBRATION_MAX_BIN_GAP = 0.10
CALIBRATION_MINIMUM_BRIER_IMPROVEMENT = 0.01
NUMERIC_REPRODUCIBILITY_TOLERANCE = 1e-8

_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_EXPECTED_RUNTIME = {
    "numpy": "2.5.2",
    "pandas": "3.0.5",
    "python": "3.13.15",
    "scikit-learn": "1.9.0",
    "xgboost": "3.4.1",
}


class ModelKind(StrEnum):
    LOGISTIC = "logistic_regression"
    XGBOOST = "xgboost"


class ModelCompatibilityError(ValueError):
    """The feature or model artifact cannot be used safely for inference."""


@dataclass(frozen=True, slots=True)
class AssociationContribution:
    feature: str
    value: float
    contribution: float
    explanation: str

    def as_dict(self) -> dict[str, object]:
        return {
            "contribution": self.contribution,
            "explanation": self.explanation,
            "feature": self.feature,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class LearnedScore:
    model_artifact_version: str
    model_artifact_hash: str
    feature_schema_version: str
    model_score: int | None
    calibrated_probability: None
    band: str
    proxy_prediction: bool | None
    probability_display_allowed: bool
    contributions: tuple[AssociationContribution, ...]
    missing_required: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "band": self.band,
            "calibrated_probability": self.calibrated_probability,
            "contributions": [item.as_dict() for item in self.contributions],
            "feature_schema_version": self.feature_schema_version,
            "missing_required": list(self.missing_required),
            "model_artifact_hash": self.model_artifact_hash,
            "model_artifact_version": self.model_artifact_version,
            "model_score": self.model_score,
            "probability_display_allowed": self.probability_display_allowed,
            "proxy_prediction": self.proxy_prediction,
        }


def _round(value: float) -> float:
    return round(float(value), 10)


def _required_number(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelCompatibilityError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ModelCompatibilityError(f"{field} must be finite")
    return result


def _eligible(dataset: DatasetBuild, split: DatasetSplit) -> tuple[MaterializedFeatureRow, ...]:
    return tuple(
        row
        for row in dataset.rows
        if row.split is split and row.label.label in {ProxyLabel.POSITIVE, ProxyLabel.NEGATIVE}
    )


def _labels(rows: tuple[MaterializedFeatureRow, ...]) -> NDArray[np.int64]:
    return np.asarray(
        [1 if row.label.label is ProxyLabel.POSITIVE else 0 for row in rows],
        dtype=np.int64,
    )


def _feature_number(value: FeatureScalar, *, feature: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelCompatibilityError(f"feature {feature} must be numeric or null")
    result = float(value)
    if not math.isfinite(result):
        raise ModelCompatibilityError(f"feature {feature} must be finite")
    return result


def fit_preprocessor(rows: tuple[MaterializedFeatureRow, ...]) -> dict[str, object]:
    """Fit explicit train-only imputation/scaling and missingness indicators."""
    if not rows:
        raise ValueError("preprocessing requires non-empty training rows")
    input_names = [definition.name for definition in FEATURE_DEFINITIONS]
    nullable_names = [definition.name for definition in FEATURE_DEFINITIONS if definition.nullable]
    for row in rows:
        if row.feature_schema_version != FEATURE_SCHEMA_VERSION:
            raise ModelCompatibilityError("training row feature schema is incompatible")
        if set(row.feature_values) != set(input_names):
            raise ModelCompatibilityError("training row does not match the exact feature schema")
    frame = pd.DataFrame(
        [
            {name: _feature_number(row.feature_values[name], feature=name) for name in input_names}
            for row in rows
        ],
        columns=input_names,
        dtype="float64",
    )
    imputation: dict[str, dict[str, object]] = {}
    filled = frame.copy()
    for definition in FEATURE_DEFINITIONS:
        series = frame[definition.name]
        if not definition.nullable and series.isna().any():
            raise ModelCompatibilityError(f"required feature {definition.name} is missing")
        if definition.nullable:
            observed = series.dropna()
            if observed.empty:
                fill = 0.0
                strategy = "zero_no_training_observation"
            else:
                fill = float(observed.median())
                strategy = "training_median"
            fill = _round(fill)
            imputation[definition.name] = {
                "fill_value": fill,
                "observed_training_rows": int(observed.size),
                "strategy": strategy,
            }
            filled[definition.name] = series.fillna(fill)
    for name in nullable_names:
        filled[f"missing__{name}"] = frame[name].isna().astype("float64")
    output_names = input_names + [f"missing__{name}" for name in nullable_names]
    means: dict[str, float] = {}
    scales: dict[str, float] = {}
    for name in output_names:
        mean = _round(float(filled[name].mean()))
        scale = _round(float(filled[name].std(ddof=0)))
        if scale == 0.0:
            scale = 1.0
        means[name] = mean
        scales[name] = scale
    payload: dict[str, object] = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "imputation": imputation,
        "input_feature_names": input_names,
        "missing_indicator_features": nullable_names,
        "output_feature_names": output_names,
        "scaling": {"mean": means, "scale": scales, "strategy": "training_zscore"},
        "training_row_count": len(rows),
        "version": PREPROCESSOR_VERSION,
    }
    return {**payload, "preprocessor_hash": canonical_hash(payload)}


def _string_list(value: object, *, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ModelCompatibilityError(f"{field} must be a string list")
    return cast(list[str], value)


def _number_mapping(value: object, *, field: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ModelCompatibilityError(f"{field} must be an object")
    result: dict[str, float] = {}
    for key, item in value.items():
        if not isinstance(key, str) or isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ModelCompatibilityError(f"{field} must contain numeric values")
        result[key] = float(item)
    return result


def transform_features(
    values: dict[str, FeatureScalar],
    preprocessor: dict[str, object],
) -> tuple[NDArray[np.float64] | None, tuple[str, ...], dict[str, float]]:
    """Apply the frozen train-time transform or return explicit required missingness."""
    if preprocessor.get("version") != PREPROCESSOR_VERSION:
        raise ModelCompatibilityError("preprocessor version is incompatible")
    if preprocessor.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
        raise ModelCompatibilityError("preprocessor feature schema is incompatible")
    input_names = _string_list(preprocessor.get("input_feature_names"), field="input names")
    output_names = _string_list(preprocessor.get("output_feature_names"), field="output names")
    nullable_names = set(
        _string_list(preprocessor.get("missing_indicator_features"), field="missing indicators")
    )
    if set(values) != set(input_names):
        raise ModelCompatibilityError("inference payload does not match the exact feature schema")
    imputation = preprocessor.get("imputation")
    scaling = preprocessor.get("scaling")
    if not isinstance(imputation, dict) or not isinstance(scaling, dict):
        raise ModelCompatibilityError("preprocessor metadata is invalid")
    means = _number_mapping(scaling.get("mean"), field="scaling mean")
    scales = _number_mapping(scaling.get("scale"), field="scaling scale")
    raw: dict[str, float] = {}
    missing_required: list[str] = []
    for name in input_names:
        value = _feature_number(values[name], feature=name)
        if value is None:
            if name not in nullable_names:
                missing_required.append(name)
                continue
            rule = imputation.get(name)
            if not isinstance(rule, dict):
                raise ModelCompatibilityError(f"imputation rule for {name} is invalid")
            fill = rule.get("fill_value")
            if isinstance(fill, bool) or not isinstance(fill, (int, float)):
                raise ModelCompatibilityError(f"imputation fill for {name} is invalid")
            raw[name] = float(fill)
        else:
            raw[name] = value
        if name in nullable_names:
            raw[f"missing__{name}"] = 1.0 if value is None else 0.0
    if missing_required:
        return None, tuple(sorted(missing_required)), raw
    if (
        set(output_names) != set(raw)
        or set(means) != set(output_names)
        or set(scales) != set(output_names)
    ):
        raise ModelCompatibilityError("preprocessor output metadata is inconsistent")
    transformed = []
    for name in output_names:
        if scales[name] <= 0.0:
            raise ModelCompatibilityError(f"preprocessor scale for {name} is invalid")
        transformed.append((raw[name] - means[name]) / scales[name])
    return np.asarray([transformed], dtype=np.float64), (), raw


def transform_rows(
    rows: tuple[MaterializedFeatureRow, ...], preprocessor: dict[str, object]
) -> NDArray[np.float64]:
    matrices: list[NDArray[np.float64]] = []
    for row in rows:
        matrix, missing, _raw = transform_features(row.feature_values, preprocessor)
        if matrix is None or missing:
            raise ModelCompatibilityError("evaluation row is missing a required feature")
        matrices.append(matrix)
    return np.concatenate(matrices, axis=0)


def _confusion(
    labels: NDArray[np.int64], scores: NDArray[np.float64], threshold: float
) -> dict[str, object]:
    predicted = scores >= threshold
    actual = labels == 1
    true_positive = int(np.sum(predicted & actual))
    false_positive = int(np.sum(predicted & ~actual))
    true_negative = int(np.sum(~predicted & ~actual))
    false_negative = int(np.sum(~predicted & actual))
    precision = (
        true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "false_negative": false_negative,
        "false_positive": false_positive,
        "f1": _round(f1),
        "negative_count": int(np.sum(~actual)),
        "positive_count": int(np.sum(actual)),
        "precision": _round(precision),
        "prevalence": _round(float(np.mean(actual))),
        "recall": _round(recall),
        "row_count": int(labels.size),
        "threshold": threshold,
        "true_negative": true_negative,
        "true_positive": true_positive,
    }


def _ranking(labels: NDArray[np.int64], scores: NDArray[np.float64]) -> dict[str, float | None]:
    if len(np.unique(labels)) != 2:
        return {"pr_auc_average_precision": None, "roc_auc": None}
    return {
        "pr_auc_average_precision": _round(average_precision_score(labels, scores)),
        "roc_auc": _round(roc_auc_score(labels, scores)),
    }


def _metrics(
    labels: NDArray[np.int64], scores: NDArray[np.float64], threshold: float
) -> dict[str, object]:
    return {**_confusion(labels, scores, threshold), **_ranking(labels, scores)}


def _select_threshold(labels: NDArray[np.int64], scores: NDArray[np.float64]) -> dict[str, object]:
    table = [_confusion(labels, scores, threshold) for threshold in MODEL_SCORE_THRESHOLDS]
    eligible = [
        row for row in table if float(cast(float, row["recall"])) >= MINIMUM_VALIDATION_RECALL
    ]
    candidates = eligible or table

    def key(row: dict[str, object]) -> tuple[float, float, float, float]:
        cost = FALSE_NEGATIVE_COST * int(
            cast(int, row["false_negative"])
        ) + FALSE_POSITIVE_COST * int(cast(int, row["false_positive"]))
        return (
            -float(cost),
            float(cast(float, row["f1"])),
            float(cast(float, row["precision"])),
            float(cast(float, row["threshold"])),
        )

    selected = max(candidates, key=key)
    return {
        "recall_floor_met": bool(eligible),
        "selected_threshold": selected["threshold"],
        "selection_rule": "validation_only_min_cost_then_f1_precision_higher_threshold",
        "threshold_table": table,
    }


def _candidate_key(candidate: dict[str, object]) -> tuple[float, float, float, str]:
    metrics = cast(dict[str, object], candidate["validation_metrics"])
    selection = cast(dict[str, object], candidate["threshold_selection"])
    cost = FALSE_NEGATIVE_COST * int(
        cast(int, metrics["false_negative"])
    ) + FALSE_POSITIVE_COST * int(cast(int, metrics["false_positive"]))
    return (
        -float(cost),
        float(cast(float, metrics["f1"])),
        float(cast(float, metrics["pr_auc_average_precision"] or 0.0)),
        canonical_hash(
            {"config": candidate["config"], "threshold": selection["selected_threshold"]}
        ),
    )


def _calibration_declaration(train_labels: NDArray[np.int64]) -> dict[str, object]:
    prevalence = float(np.mean(train_labels))
    return {
        "acceptance_tolerances": {
            "maximum_ece": CALIBRATION_MAX_ECE,
            "maximum_reliability_bin_gap": CALIBRATION_MAX_BIN_GAP,
            "minimum_brier_improvement_over_baseline": CALIBRATION_MINIMUM_BRIER_IMPROVEMENT,
        },
        "brier_baseline": {
            "constant_score": _round(prevalence),
            "strategy": "training_split_proxy_prevalence_constant",
        },
        "candidates": ["sigmoid_platt", "isotonic"],
        "minimum_sample": {
            "negative_rows": CALIBRATION_MINIMUM_PER_CLASS,
            "positive_rows": CALIBRATION_MINIMUM_PER_CLASS,
            "total_rows": CALIBRATION_MINIMUM_ROWS,
        },
        "reliability": {
            "bin_count": CALIBRATION_BIN_COUNT,
            "ece_weighting": "observed_bin_fraction",
            "minimum_rows_per_bin": CALIBRATION_MINIMUM_BIN_ROWS,
            "strategy": "equal_width_frozen_0_to_1",
        },
    }


def _calibration_result(
    declaration: dict[str, object],
    validation_labels: NDArray[np.int64],
    test_labels: NDArray[np.int64],
    test_scores: NDArray[np.float64],
) -> dict[str, object]:
    positives = int(np.sum(validation_labels == 1))
    negatives = int(np.sum(validation_labels == 0))
    enough = (
        validation_labels.size >= CALIBRATION_MINIMUM_ROWS
        and positives >= CALIBRATION_MINIMUM_PER_CLASS
        and negatives >= CALIBRATION_MINIMUM_PER_CLASS
    )
    baseline = cast(dict[str, object], declaration["brier_baseline"])
    baseline_score = float(cast(float, baseline["constant_score"]))
    return {
        "calibrated_probability": None,
        "probability_display_allowed": False,
        "status": "not_attempted_insufficient_validation_sample"
        if not enough
        else "not_implemented",
        "test_diagnostics": {
            "constant_baseline_brier": _round(float(np.mean((baseline_score - test_labels) ** 2))),
            "ece": None,
            "maximum_reliability_bin_gap": None,
            "model_score_brier_not_a_calibration_claim": _round(
                float(np.mean((test_scores - test_labels) ** 2))
            ),
            "test_rows": int(test_labels.size),
        },
        "validation_sample": {
            "negative_rows": negatives,
            "positive_rows": positives,
            "total_rows": int(validation_labels.size),
        },
    }


def _runtime_versions() -> dict[str, str]:
    installed = {
        "numpy": version("numpy"),
        "pandas": version("pandas"),
        "python": platform.python_version(),
        "scikit-learn": version("scikit-learn"),
        "xgboost": version("xgboost-cpu"),
    }
    if installed != _EXPECTED_RUNTIME:
        raise RuntimeError(f"M5 training runtime does not match its exact pins: {installed}")
    return installed


def _train_logistic(
    train_x: NDArray[np.float64],
    train_y: NDArray[np.int64],
    validation_x: NDArray[np.float64],
    validation_y: NDArray[np.int64],
) -> tuple[LogisticRegression, list[dict[str, object]], dict[str, object]]:
    fitted: list[tuple[LogisticRegression, dict[str, object]]] = []
    for c_value in (0.1, 1.0, 10.0):
        for class_weight in (None, "balanced"):
            config = {
                "C": c_value,
                "class_weight": class_weight,
                "max_iter": 1000,
                "random_state": RANDOM_SEED,
                "solver": "liblinear",
            }
            model = LogisticRegression(**config)
            model.fit(train_x, train_y)
            scores = cast(NDArray[np.float64], model.predict_proba(validation_x)[:, 1])
            selection = _select_threshold(validation_y, scores)
            threshold = float(cast(float, selection["selected_threshold"]))
            candidate = {
                "config": config,
                "threshold_selection": selection,
                "validation_metrics": _metrics(validation_y, scores, threshold),
            }
            fitted.append((model, candidate))
    selected_model, selected = max(fitted, key=lambda item: _candidate_key(item[1]))
    table = [item[1] for item in fitted]
    return selected_model, table, selected


def _train_xgboost(
    train_x: NDArray[np.float64],
    train_y: NDArray[np.int64],
    validation_x: NDArray[np.float64],
    validation_y: NDArray[np.int64],
) -> tuple[XGBClassifier, list[dict[str, object]], dict[str, object]]:
    fitted: list[tuple[XGBClassifier, dict[str, object]]] = []
    for max_depth, n_estimators in ((1, 8), (1, 16), (2, 8), (2, 16)):
        config: dict[str, object] = {
            "colsample_bytree": 1.0,
            "eval_metric": "logloss",
            "learning_rate": 0.1,
            "max_depth": max_depth,
            "min_child_weight": 0.0,
            "n_estimators": n_estimators,
            "n_jobs": 1,
            "objective": "binary:logistic",
            "random_state": RANDOM_SEED,
            "reg_lambda": 1.0,
            "subsample": 1.0,
            "tree_method": "hist",
        }
        model = XGBClassifier(**config)
        model.fit(train_x, train_y, verbose=False)
        scores = cast(NDArray[np.float64], model.predict_proba(validation_x)[:, 1])
        selection = _select_threshold(validation_y, scores)
        threshold = float(cast(float, selection["selected_threshold"]))
        candidate: dict[str, object] = {
            "config": config,
            "threshold_selection": selection,
            "validation_metrics": _metrics(validation_y, scores, threshold),
        }
        fitted.append((model, candidate))
    selected_model, selected = max(fitted, key=lambda item: _candidate_key(item[1]))
    table = [item[1] for item in fitted]
    return selected_model, table, selected


def _raw_predictions(
    rows: tuple[MaterializedFeatureRow, ...], scores: NDArray[np.float64], threshold: float
) -> list[dict[str, object]]:
    return [
        {
            "actual_proxy_label": row.label.label,
            "model_score": _round(float(score)),
            "predicted_proxy_positive": bool(score >= threshold),
            "snapshot_id": row.snapshot_id,
            "split": row.split,
        }
        for row, score in zip(rows, scores, strict=True)
    ]


def _model_payload_hash(payload: dict[str, object]) -> str:
    return canonical_hash(payload)


def train_classical_models(
    dataset: DatasetBuild,
    *,
    training_code_commit: str,
) -> dict[str, object]:
    """Train candidates and inspect the held-out test only after declarations are frozen."""
    if _SHA_PATTERN.fullmatch(training_code_commit) is None:
        raise ValueError("training_code_commit must be an exact lowercase commit SHA")
    runtime = _runtime_versions()
    train_rows = _eligible(dataset, DatasetSplit.TRAIN)
    validation_rows = _eligible(dataset, DatasetSplit.VALIDATION)
    test_rows = _eligible(dataset, DatasetSplit.TEST)
    if not train_rows or not validation_rows or not test_rows:
        raise ValueError("classical evaluation requires non-empty train/validation/test splits")
    if dataset.manifest.leakage_report.violations:
        raise ValueError("classical training refuses a dataset with leakage violations")

    preprocessor = fit_preprocessor(train_rows)
    train_x = transform_rows(train_rows, preprocessor)
    validation_x = transform_rows(validation_rows, preprocessor)
    test_x = transform_rows(test_rows, preprocessor)
    train_y = _labels(train_rows)
    validation_y = _labels(validation_rows)
    test_y = _labels(test_rows)

    experiment_declaration = {
        "calibration": _calibration_declaration(train_y),
        "cost_assumptions": {
            "false_negative_cost_units": FALSE_NEGATIVE_COST,
            "false_positive_cost_units": FALSE_POSITIVE_COST,
            "minimum_validation_recall": MINIMUM_VALIDATION_RECALL,
        },
        "final_test_rule": "inspect_once_after_model_calibration_and_threshold_rules_are_frozen",
        "target": "documented proxy_positive within the admitted 30-day observation window",
        "target_population": "releaseproof-m4-synthetic-v1 fixture changes only",
        "threshold_candidates": list(MODEL_SCORE_THRESHOLDS),
        "version": CLASSICAL_EXPERIMENT_VERSION,
    }

    logistic, logistic_tuning, logistic_selected = _train_logistic(
        train_x, train_y, validation_x, validation_y
    )
    boosted, boosted_tuning, boosted_selected = _train_xgboost(
        train_x, train_y, validation_x, validation_y
    )

    # Final-test inspection begins here. Nothing below participates in tuning.
    calibration_declaration = cast(dict[str, object], experiment_declaration["calibration"])
    logistic_scores = cast(NDArray[np.float64], logistic.predict_proba(test_x)[:, 1])
    boosted_scores = cast(NDArray[np.float64], boosted.predict_proba(test_x)[:, 1])
    logistic_threshold = _required_number(
        cast(dict[str, object], logistic_selected["threshold_selection"])["selected_threshold"],
        field="logistic selected threshold",
    )
    boosted_threshold = _required_number(
        cast(dict[str, object], boosted_selected["threshold_selection"])["selected_threshold"],
        field="XGBoost selected threshold",
    )
    output_names = _string_list(preprocessor["output_feature_names"], field="output names")

    logistic_payload: dict[str, object] = {
        "artifact_version": LOGISTIC_ARTIFACT_VERSION,
        "coefficients": [_round(item) for item in logistic.coef_[0]],
        "intercept": _round(logistic.intercept_[0]),
        "ordered_feature_names": output_names,
        "preprocessor_hash": preprocessor["preprocessor_hash"],
        "selected_config": logistic_selected["config"],
        "selected_threshold": logistic_threshold,
        "threshold_policy_version": CLASSICAL_THRESHOLD_POLICY_VERSION,
    }
    logistic_artifact = {
        **logistic_payload,
        "algorithm": "scikit_learn_logistic_regression",
        "artifact_hash": _model_payload_hash(logistic_payload),
        "calibration": _calibration_result(
            calibration_declaration, validation_y, test_y, logistic_scores
        ),
        "coefficient_interpretation": (
            "standardized-feature associations; sign is direction, not causation"
        ),
        "lifecycle": "candidate_not_promoted",
        "raw_test_predictions": _raw_predictions(test_rows, logistic_scores, logistic_threshold),
        "test_metrics": _metrics(test_y, logistic_scores, logistic_threshold),
        "tuning": logistic_tuning,
    }

    booster = boosted.get_booster()
    raw_booster = bytes(booster.save_raw(raw_format="json"))
    importance = booster.get_score(importance_type="gain")
    boosted_payload: dict[str, object] = {
        "artifact_version": XGBOOST_ARTIFACT_VERSION,
        "booster_json_base64": base64.b64encode(raw_booster).decode("ascii"),
        "booster_json_sha256": hashlib.sha256(raw_booster).hexdigest(),
        "ordered_feature_names": output_names,
        "preprocessor_hash": preprocessor["preprocessor_hash"],
        "selected_config": boosted_selected["config"],
        "selected_threshold": boosted_threshold,
        "threshold_policy_version": CLASSICAL_THRESHOLD_POLICY_VERSION,
    }
    boosted_artifact = {
        **boosted_payload,
        "algorithm": "xgboost_binary_logistic_cpu_hist",
        "artifact_hash": _model_payload_hash(boosted_payload),
        "calibration": _calibration_result(
            calibration_declaration, validation_y, test_y, boosted_scores
        ),
        "feature_importance_gain": {
            output_names[int(name[1:])]: _round(value)
            for name, value in sorted(importance.items())
            if name.startswith("f")
            and name[1:].isdigit()
            and int(name[1:]) < len(output_names)
            and isinstance(value, float)
        },
        "importance_interpretation": "split-gain associations; not causation",
        "lifecycle": "candidate_not_promoted",
        "raw_test_predictions": _raw_predictions(test_rows, boosted_scores, boosted_threshold),
        "test_metrics": _metrics(test_y, boosted_scores, boosted_threshold),
        "tuning": boosted_tuning,
    }
    heuristic = evaluate_baseline(dataset)
    payload: dict[str, object] = {
        "active_selection": {
            "active_artifact_hash": baseline_artifact_hash(),
            "active_artifact_version": BASELINE_ARTIFACT_VERSION,
            "candidate_artifacts": [
                logistic_artifact["artifact_hash"],
                boosted_artifact["artifact_hash"],
            ],
            "decision": "keep_deterministic_heuristic",
            "human_approval_required_for_change": True,
            "probability_display_allowed": False,
            "reasons": [
                "dataset is explicitly synthetic",
                "one repository does not provide repository-holdout evidence",
                "four validation and four test rows are below the frozen calibration minimum",
                "learned-model product value is not yet validated",
            ],
            "rollback": {
                "artifact_hash": baseline_artifact_hash(),
                "artifact_version": BASELINE_ARTIFACT_VERSION,
                "threshold_policy_version": THRESHOLD_POLICY_VERSION,
            },
        },
        "artifact_schema_version": CLASSICAL_ARTIFACT_SCHEMA_VERSION,
        "baseline_comparison": {
            "artifact_hash": heuristic["baseline_artifact_hash"],
            "artifact_version": heuristic["baseline_artifact_version"],
            "test_metrics": cast(dict[str, object], heuristic["metrics"])["test"],
        },
        "dataset": {
            "dataset_version": dataset.manifest.dataset_version,
            "feature_schema_version": dataset.manifest.feature_schema_version,
            "leakage_report_hash": dataset.manifest.leakage_report.report_hash,
            "manifest_hash": dataset.manifest.manifest_hash,
            "split_hash": dataset.manifest.split_hash,
            "synthetic": dataset.manifest.synthetic,
        },
        "experiment_declaration": experiment_declaration,
        "limitations": [
            "All measurements are on deliberately synthetic fixture rows and validate "
            "implementation only.",
            "Proxy labels are not incidents and do not prove change causality.",
            "The four-row held-out test makes every metric unstable.",
            "No repository holdout, customer outcome, production calibration, or product lift "
            "is measured.",
            "Candidate scores are not calibrated probabilities and are not the active product "
            "model.",
        ],
        "model_card_version": MODEL_CARD_VERSION,
        "models": {
            LOGISTIC_ARTIFACT_VERSION: logistic_artifact,
            XGBOOST_ARTIFACT_VERSION: boosted_artifact,
        },
        "preprocessing": preprocessor,
        "reproducibility": {
            "deterministic_controls": {
                "cpu_only": True,
                "random_seed": RANDOM_SEED,
                "xgboost_n_jobs": 1,
            },
            "expected_numeric_absolute_tolerance": NUMERIC_REPRODUCIBILITY_TOLERANCE,
            "known_variance": "native-library/CPU differences may vary final floating point digits",
            "recorded_environment": {
                "machine": platform.machine() or "unknown",
                "operating_system": platform.system(),
                "python_implementation": platform.python_implementation(),
            },
        },
        "runtime_compatibility": runtime,
        "training_code_commit": training_code_commit,
    }
    return {**payload, "artifact_hash": canonical_hash(payload)}


def validate_classical_artifact(artifact: dict[str, object]) -> None:
    if artifact.get("artifact_schema_version") != CLASSICAL_ARTIFACT_SCHEMA_VERSION:
        raise ModelCompatibilityError("classical artifact schema is incompatible")
    stored_hash = artifact.get("artifact_hash")
    if not isinstance(stored_hash, str):
        raise ModelCompatibilityError("classical artifact hash is missing")
    payload = {key: value for key, value in artifact.items() if key != "artifact_hash"}
    if canonical_hash(payload) != stored_hash:
        raise ModelCompatibilityError("classical artifact checksum is invalid")
    training_commit = artifact.get("training_code_commit")
    if not isinstance(training_commit, str) or _SHA_PATTERN.fullmatch(training_commit) is None:
        raise ModelCompatibilityError("classical artifact training commit is invalid")
    if artifact.get("runtime_compatibility") != _EXPECTED_RUNTIME:
        raise ModelCompatibilityError("classical artifact runtime compatibility is invalid")
    dataset = artifact.get("dataset")
    preprocessing = artifact.get("preprocessing")
    models = artifact.get("models")
    if (
        not isinstance(dataset, dict)
        or dataset.get("feature_schema_version") != FEATURE_SCHEMA_VERSION
    ):
        raise ModelCompatibilityError("classical artifact feature schema is incompatible")
    if not isinstance(preprocessing, dict) or not isinstance(models, dict):
        raise ModelCompatibilityError("classical artifact model metadata is invalid")
    preprocessor_payload = {
        key: value for key, value in preprocessing.items() if key != "preprocessor_hash"
    }
    if canonical_hash(preprocessor_payload) != preprocessing.get("preprocessor_hash"):
        raise ModelCompatibilityError("classical preprocessor checksum is invalid")
    model_payload_fields = {
        LOGISTIC_ARTIFACT_VERSION: (
            "artifact_version",
            "coefficients",
            "intercept",
            "ordered_feature_names",
            "preprocessor_hash",
            "selected_config",
            "selected_threshold",
            "threshold_policy_version",
        ),
        XGBOOST_ARTIFACT_VERSION: (
            "artifact_version",
            "booster_json_base64",
            "booster_json_sha256",
            "ordered_feature_names",
            "preprocessor_hash",
            "selected_config",
            "selected_threshold",
            "threshold_policy_version",
        ),
    }
    for model_version in (LOGISTIC_ARTIFACT_VERSION, XGBOOST_ARTIFACT_VERSION):
        model = models.get(model_version)
        if not isinstance(model, dict) or not isinstance(model.get("artifact_hash"), str):
            raise ModelCompatibilityError(f"{model_version} metadata is invalid")
        if model.get("preprocessor_hash") != preprocessing.get("preprocessor_hash"):
            raise ModelCompatibilityError(f"{model_version} preprocessor binding is invalid")
        model_payload = {field: model.get(field) for field in model_payload_fields[model_version]}
        if canonical_hash(model_payload) != model.get("artifact_hash"):
            raise ModelCompatibilityError(f"{model_version} checksum is invalid")
        calibration = model.get("calibration")
        if (
            not isinstance(calibration, dict)
            or calibration.get("probability_display_allowed") is not False
            or calibration.get("calibrated_probability") is not None
        ):
            raise ModelCompatibilityError(f"{model_version} calibration gate is invalid")
    boosted = cast(dict[str, object], models[XGBOOST_ARTIFACT_VERSION])
    encoded = boosted.get("booster_json_base64")
    if not isinstance(encoded, str):
        raise ModelCompatibilityError("XGBoost serialized model is invalid")
    try:
        raw_booster = base64.b64decode(encoded, validate=True)
    except ValueError as error:
        raise ModelCompatibilityError("XGBoost serialized model is invalid") from error
    if hashlib.sha256(raw_booster).hexdigest() != boosted.get("booster_json_sha256"):
        raise ModelCompatibilityError("XGBoost serialized model checksum is invalid")
    selection = artifact.get("active_selection")
    if (
        not isinstance(selection, dict)
        or selection.get("active_artifact_version") != BASELINE_ARTIFACT_VERSION
        or selection.get("active_artifact_hash") != baseline_artifact_hash()
        or selection.get("probability_display_allowed") is not False
    ):
        raise ModelCompatibilityError("classical active-model selection is invalid")


def _score_band(score: float, threshold: float) -> str:
    if score >= threshold:
        return "high"
    if score >= threshold / 2:
        return "medium"
    return "low"


def score_classical_candidate(
    artifact: dict[str, object],
    *,
    model_artifact_version: str,
    feature_schema_version: str,
    values: dict[str, FeatureScalar],
) -> LearnedScore:
    """Run checksum-verified candidate inference without probability wording."""
    validate_classical_artifact(artifact)
    if feature_schema_version != FEATURE_SCHEMA_VERSION:
        raise ModelCompatibilityError("inference feature schema is incompatible")
    preprocessing = cast(dict[str, object], artifact["preprocessing"])
    models = cast(dict[str, object], artifact["models"])
    model = models.get(model_artifact_version)
    if not isinstance(model, dict):
        raise ModelCompatibilityError("requested model artifact is unavailable")
    artifact_hash = model.get("artifact_hash")
    if not isinstance(artifact_hash, str):
        raise ModelCompatibilityError("requested model artifact hash is invalid")
    matrix, missing, _raw = transform_features(values, preprocessing)
    if matrix is None:
        return LearnedScore(
            model_artifact_version=model_artifact_version,
            model_artifact_hash=artifact_hash,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            model_score=None,
            calibrated_probability=None,
            band="unknown",
            proxy_prediction=None,
            probability_display_allowed=False,
            contributions=(),
            missing_required=missing,
        )
    threshold = model.get("selected_threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise ModelCompatibilityError("model threshold is invalid")
    threshold_float = float(threshold)
    output_names = _string_list(preprocessing["output_feature_names"], field="output names")
    if model_artifact_version == LOGISTIC_ARTIFACT_VERSION:
        coefficients_value = model.get("coefficients")
        intercept = model.get("intercept")
        if (
            not isinstance(coefficients_value, list)
            or len(coefficients_value) != len(output_names)
            or isinstance(intercept, bool)
            or not isinstance(intercept, (int, float))
        ):
            raise ModelCompatibilityError("logistic parameters are invalid")
        coefficients = np.asarray(coefficients_value, dtype=np.float64)
        margin = float(matrix[0] @ coefficients + float(intercept))
        score = 1.0 / (1.0 + math.exp(-margin))
        contribution_values = matrix[0] * coefficients
    elif model_artifact_version == XGBOOST_ARTIFACT_VERSION:
        encoded = model.get("booster_json_base64")
        if not isinstance(encoded, str):
            raise ModelCompatibilityError("XGBoost model payload is invalid")
        try:
            raw_model = base64.b64decode(encoded, validate=True)
        except ValueError as error:
            raise ModelCompatibilityError("XGBoost model payload is not valid base64") from error
        booster = xgb.Booster()
        booster.load_model(bytearray(raw_model))
        matrix_data = xgb.DMatrix(matrix)
        score = float(booster.predict(matrix_data)[0])
        contribution_values = cast(
            NDArray[np.float64], booster.predict(matrix_data, pred_contribs=True)[0][:-1]
        )
    else:
        raise ModelCompatibilityError("requested model artifact version is incompatible")
    ranked = sorted(
        zip(output_names, matrix[0], contribution_values, strict=True),
        key=lambda item: (-abs(float(item[2])), item[0]),
    )[:8]
    contributions = tuple(
        AssociationContribution(
            feature=name,
            value=_round(float(value)),
            contribution=_round(float(contribution)),
            explanation="Model association for the standardized feature; not a causal claim.",
        )
        for name, value, contribution in ranked
    )
    return LearnedScore(
        model_artifact_version=model_artifact_version,
        model_artifact_hash=artifact_hash,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        model_score=round(max(0.0, min(1.0, score)) * 100),
        calibrated_probability=None,
        band=_score_band(score, threshold_float),
        proxy_prediction=score >= threshold_float,
        probability_display_allowed=False,
        contributions=contributions,
        missing_required=(),
    )


def current_model_summary(artifact: dict[str, object]) -> dict[str, object]:
    """Return a bounded public summary; never expose serialized model bytes."""
    validate_classical_artifact(artifact)
    selection = cast(dict[str, object], artifact["active_selection"])
    dataset = cast(dict[str, object], artifact["dataset"])
    models = cast(dict[str, object], artifact["models"])
    candidates: list[dict[str, object]] = []
    for model_version in (LOGISTIC_ARTIFACT_VERSION, XGBOOST_ARTIFACT_VERSION):
        model = cast(dict[str, object], models[model_version])
        candidates.append(
            {
                "algorithm": model["algorithm"],
                "artifact_hash": model["artifact_hash"],
                "artifact_version": model_version,
                "calibration_status": cast(dict[str, object], model["calibration"])["status"],
                "lifecycle": model["lifecycle"],
                "probability_display_allowed": False,
                "test_metrics": model["test_metrics"],
            }
        )
    return {
        "active": {
            "artifact_hash": selection["active_artifact_hash"],
            "artifact_version": selection["active_artifact_version"],
            "decision": selection["decision"],
            "probability_display_allowed": False,
            "reasons": selection["reasons"],
        },
        "candidates": candidates,
        "dataset": dataset,
        "evaluation_artifact_hash": artifact["artifact_hash"],
        "limitations": artifact["limitations"],
        "model_card_version": artifact["model_card_version"],
    }
