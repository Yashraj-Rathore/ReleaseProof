"""Transparent deterministic risk baseline and frozen evaluation harness."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from packages.change_intel import FEATURE_SCHEMA_VERSION, canonical_hash
from packages.change_intel.contracts import FeatureScalar
from packages.dataset_core import DatasetBuild, DatasetSplit, MaterializedFeatureRow, ProxyLabel

BASELINE_SCHEMA_VERSION = "deterministic-risk-score-v1"
BASELINE_ARTIFACT_VERSION = "deterministic-heuristic-v1"
THRESHOLD_POLICY_VERSION = "deterministic-threshold-v1"
EVALUATION_SCHEMA_VERSION = "heuristic-evaluation-v1"
CANDIDATE_THRESHOLDS = (20, 30, 40, 50)
SELECTED_THRESHOLD = 30
MINIMUM_VALIDATION_RECALL = 0.75


class RiskBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RuleContribution:
    rule_id: str
    points: int
    reason: str
    source_features: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "points": self.points,
            "reason": self.reason,
            "rule_id": self.rule_id,
            "source_features": list(self.source_features),
        }


@dataclass(frozen=True, slots=True)
class HeuristicScore:
    schema_version: str
    artifact_version: str
    artifact_hash: str
    feature_schema_version: str
    threshold_policy_version: str
    threshold: int
    score: int | None
    calibrated_probability: None
    band: RiskBand
    proxy_prediction: bool | None
    contributions: tuple[RuleContribution, ...]
    missing_required: tuple[str, ...]
    result_hash: str

    def as_dict(self) -> dict[str, object]:
        return {
            "artifact_hash": self.artifact_hash,
            "artifact_version": self.artifact_version,
            "band": self.band,
            "calibrated_probability": self.calibrated_probability,
            "contributions": [item.as_dict() for item in self.contributions],
            "feature_schema_version": self.feature_schema_version,
            "missing_required": list(self.missing_required),
            "proxy_prediction": self.proxy_prediction,
            "result_hash": self.result_hash,
            "schema_version": self.schema_version,
            "score": self.score,
            "threshold": self.threshold,
            "threshold_policy_version": self.threshold_policy_version,
        }


_RULE_DECLARATIONS: tuple[dict[str, object], ...] = (
    {"rule_id": "large_change", "points": 20, "condition": "lines_added + lines_deleted >= 100"},
    {"rule_id": "many_files", "points": 15, "condition": "files_changed >= 4"},
    {"rule_id": "migration", "points": 25, "condition": "migration_files_changed >= 1"},
    {"rule_id": "dependency", "points": 15, "condition": "dependency_files_changed >= 1"},
    {"rule_id": "sensitive", "points": 25, "condition": "sensitive_files_changed >= 1"},
    {"rule_id": "no_tests", "points": 10, "condition": "test_files_changed == 0"},
    {"rule_id": "large_deletion", "points": 10, "condition": "lines_deleted >= 50"},
    {"rule_id": "wide_blast", "points": 15, "condition": "blast_transitive_modules >= 5"},
    {
        "rule_id": "prior_failure_proxies",
        "points": 15,
        "condition": "prior_failure_proxy_count_90d >= 2",
    },
)
_REQUIRED_FEATURES = (
    "dependency_files_changed",
    "files_changed",
    "lines_added",
    "lines_deleted",
    "migration_files_changed",
    "sensitive_files_changed",
    "test_files_changed",
)


def baseline_artifact_hash() -> str:
    return canonical_hash(
        {
            "artifact_version": BASELINE_ARTIFACT_VERSION,
            "bands": {"high_min": 40, "low_max": 19, "medium_max": 39},
            "candidate_thresholds": list(CANDIDATE_THRESHOLDS),
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "rules": list(_RULE_DECLARATIONS),
            "schema_version": BASELINE_SCHEMA_VERSION,
            "selected_threshold": SELECTED_THRESHOLD,
            "threshold_policy_version": THRESHOLD_POLICY_VERSION,
        }
    )


def _integer(values: dict[str, FeatureScalar], name: str) -> int | None:
    value = values.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"baseline feature {name} must be an integer")
    return value


def _score_payload(
    *,
    score: int | None,
    band: RiskBand,
    prediction: bool | None,
    contributions: tuple[RuleContribution, ...],
    missing_required: tuple[str, ...],
) -> dict[str, object]:
    return {
        "artifact_hash": baseline_artifact_hash(),
        "artifact_version": BASELINE_ARTIFACT_VERSION,
        "band": band,
        "calibrated_probability": None,
        "contributions": [item.as_dict() for item in contributions],
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "missing_required": list(missing_required),
        "proxy_prediction": prediction,
        "schema_version": BASELINE_SCHEMA_VERSION,
        "score": score,
        "threshold": SELECTED_THRESHOLD,
        "threshold_policy_version": THRESHOLD_POLICY_VERSION,
    }


def score_features(
    *,
    feature_schema_version: str,
    values: dict[str, FeatureScalar],
) -> HeuristicScore:
    if feature_schema_version != FEATURE_SCHEMA_VERSION:
        raise ValueError("baseline feature schema is incompatible")
    parsed = {name: _integer(values, name) for name in _REQUIRED_FEATURES}
    missing_required = tuple(sorted(name for name, value in parsed.items() if value is None))
    artifact_hash = baseline_artifact_hash()
    if missing_required:
        payload = _score_payload(
            score=None,
            band=RiskBand.UNKNOWN,
            prediction=None,
            contributions=(),
            missing_required=missing_required,
        )
        return HeuristicScore(
            schema_version=BASELINE_SCHEMA_VERSION,
            artifact_version=BASELINE_ARTIFACT_VERSION,
            artifact_hash=artifact_hash,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            threshold_policy_version=THRESHOLD_POLICY_VERSION,
            threshold=SELECTED_THRESHOLD,
            score=None,
            calibrated_probability=None,
            band=RiskBand.UNKNOWN,
            proxy_prediction=None,
            contributions=(),
            missing_required=missing_required,
            result_hash=canonical_hash(payload),
        )

    lines_added = parsed["lines_added"] or 0
    lines_deleted = parsed["lines_deleted"] or 0
    tests_changed = parsed["test_files_changed"] or 0
    contributions: list[RuleContribution] = []

    def add(rule_id: str, points: int, reason: str, *features: str) -> None:
        contributions.append(
            RuleContribution(
                rule_id=f"{BASELINE_ARTIFACT_VERSION}.{rule_id}",
                points=points,
                reason=reason,
                source_features=features,
            )
        )

    if lines_added + lines_deleted >= 100:
        add("large_change", 20, "At least 100 changed lines.", "lines_added", "lines_deleted")
    if (parsed["files_changed"] or 0) >= 4:
        add("many_files", 15, "At least four files changed.", "files_changed")
    if (parsed["migration_files_changed"] or 0) >= 1:
        add("migration", 25, "A migration/schema file changed.", "migration_files_changed")
    if (parsed["dependency_files_changed"] or 0) >= 1:
        add(
            "dependency",
            15,
            "A dependency manifest or lockfile changed.",
            "dependency_files_changed",
        )
    if (parsed["sensitive_files_changed"] or 0) >= 1:
        add(
            "sensitive",
            25,
            "A deterministic sensitive-area path changed.",
            "sensitive_files_changed",
        )
    if tests_changed == 0:
        add("no_tests", 10, "No test file changed in this snapshot.", "test_files_changed")
    if lines_deleted >= 50:
        add("large_deletion", 10, "At least 50 lines were deleted.", "lines_deleted")
    blast = _integer(values, "blast_transitive_modules")
    if blast is not None and blast >= 5:
        add(
            "wide_blast",
            15,
            "Static blast radius reached at least five modules.",
            "blast_transitive_modules",
        )
    prior_failures = _integer(values, "prior_failure_proxy_count_90d")
    if prior_failures is not None and prior_failures >= 2:
        add(
            "prior_failure_proxies",
            15,
            "At least two pre-change check-failure proxies touched this area.",
            "prior_failure_proxy_count_90d",
        )
    score = min(100, sum(item.points for item in contributions))
    band = RiskBand.LOW if score < 20 else RiskBand.MEDIUM if score < 40 else RiskBand.HIGH
    prediction = score >= SELECTED_THRESHOLD
    frozen_contributions = tuple(contributions)
    payload = _score_payload(
        score=score,
        band=band,
        prediction=prediction,
        contributions=frozen_contributions,
        missing_required=(),
    )
    return HeuristicScore(
        schema_version=BASELINE_SCHEMA_VERSION,
        artifact_version=BASELINE_ARTIFACT_VERSION,
        artifact_hash=artifact_hash,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        threshold_policy_version=THRESHOLD_POLICY_VERSION,
        threshold=SELECTED_THRESHOLD,
        score=score,
        calibrated_probability=None,
        band=band,
        proxy_prediction=prediction,
        contributions=frozen_contributions,
        missing_required=(),
        result_hash=canonical_hash(payload),
    )


def _eligible(
    rows: tuple[MaterializedFeatureRow, ...], split: DatasetSplit
) -> list[MaterializedFeatureRow]:
    return [
        row
        for row in rows
        if row.split is split and row.label.label in {ProxyLabel.POSITIVE, ProxyLabel.NEGATIVE}
    ]


def _confusion(rows: list[MaterializedFeatureRow], *, threshold: int) -> dict[str, object]:
    true_positive = false_positive = true_negative = false_negative = 0
    predictions: list[tuple[int, bool]] = []
    for row in rows:
        scored = score_features(
            feature_schema_version=row.feature_schema_version,
            values=row.feature_values,
        )
        if scored.score is None:
            raise ValueError("evaluation row produced UNKNOWN from required deterministic features")
        predicted = scored.score >= threshold
        actual = row.label.label is ProxyLabel.POSITIVE
        predictions.append((scored.score, actual))
        if predicted and actual:
            true_positive += 1
        elif predicted:
            false_positive += 1
        elif actual:
            false_negative += 1
        else:
            true_negative += 1
    positives = true_positive + false_negative
    negatives = true_negative + false_positive
    precision = (
        true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    )
    recall = true_positive / positives if positives else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "false_negative": false_negative,
        "false_positive": false_positive,
        "f1": round(f1, 8),
        "negative_count": negatives,
        "positive_count": positives,
        "precision": round(precision, 8),
        "prevalence": round(positives / len(rows), 8) if rows else None,
        "recall": round(recall, 8),
        "row_count": len(rows),
        "threshold": threshold,
        "true_negative": true_negative,
        "true_positive": true_positive,
    }


def _ranking_metrics(rows: list[MaterializedFeatureRow]) -> dict[str, float | None]:
    scored_rows: list[tuple[int, bool, str]] = []
    for row in rows:
        score = score_features(
            feature_schema_version=row.feature_schema_version,
            values=row.feature_values,
        ).score
        if score is None:
            raise ValueError("ranking evaluation cannot include UNKNOWN scores")
        scored_rows.append((score, row.label.label is ProxyLabel.POSITIVE, row.snapshot_id))
    positives = [item for item in scored_rows if item[1]]
    negatives = [item for item in scored_rows if not item[1]]
    if not positives or not negatives:
        return {"pr_auc_average_precision": None, "roc_auc": None}
    score_groups: dict[int, list[bool]] = {}
    for score, actual, _snapshot_id in scored_rows:
        score_groups.setdefault(score, []).append(actual)
    true_positive = false_positive = 0
    average_precision = 0.0
    previous_recall = 0.0
    for score in sorted(score_groups, reverse=True):
        group = score_groups[score]
        true_positive += sum(group)
        false_positive += len(group) - sum(group)
        recall = true_positive / len(positives)
        precision = true_positive / (true_positive + false_positive)
        average_precision += (recall - previous_recall) * precision
        previous_recall = recall
    pairwise = 0.0
    for positive_score, _actual, _snapshot_id in positives:
        for negative_score, _negative_actual, _negative_snapshot_id in negatives:
            if positive_score > negative_score:
                pairwise += 1.0
            elif positive_score == negative_score:
                pairwise += 0.5
    return {
        "pr_auc_average_precision": round(average_precision, 8),
        "roc_auc": round(pairwise / (len(positives) * len(negatives)), 8),
    }


def _threshold_table(rows: list[MaterializedFeatureRow]) -> list[dict[str, object]]:
    return [_confusion(rows, threshold=threshold) for threshold in CANDIDATE_THRESHOLDS]


def _selected_from_validation(table: list[dict[str, object]]) -> int:
    def numeric(row: dict[str, object], field: str) -> float:
        value = row[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"threshold metric {field} must be numeric")
        return float(value)

    eligible = [row for row in table if numeric(row, "recall") >= MINIMUM_VALIDATION_RECALL]
    if not eligible:
        raise ValueError("no candidate threshold meets the frozen validation recall floor")
    selected = max(
        eligible,
        key=lambda row: (
            numeric(row, "precision"),
            numeric(row, "f1"),
            numeric(row, "threshold"),
        ),
    )
    return int(numeric(selected, "threshold"))


def evaluate_baseline(dataset: DatasetBuild) -> dict[str, object]:
    validation_rows = _eligible(dataset.rows, DatasetSplit.VALIDATION)
    test_rows = _eligible(dataset.rows, DatasetSplit.TEST)
    train_rows = _eligible(dataset.rows, DatasetSplit.TRAIN)
    if not validation_rows or not test_rows:
        raise ValueError("baseline evaluation requires non-empty validation and test splits")
    validation_thresholds = _threshold_table(validation_rows)
    selected = _selected_from_validation(validation_thresholds)
    if selected != SELECTED_THRESHOLD:
        raise ValueError("frozen threshold policy does not match validation-only selection")
    raw_predictions: list[dict[str, object]] = []
    for row in sorted(dataset.rows, key=lambda item: item.snapshot_id):
        if row.split is DatasetSplit.EXCLUDED:
            continue
        score = score_features(
            feature_schema_version=row.feature_schema_version,
            values=row.feature_values,
        )
        raw_predictions.append(
            {
                "actual_proxy_label": row.label.label,
                "band": score.band,
                "predicted_proxy_positive": score.proxy_prediction,
                "score": score.score,
                "snapshot_id": row.snapshot_id,
                "split": row.split,
            }
        )
    metrics: dict[str, object] = {}
    for split, rows in (
        (DatasetSplit.TRAIN, train_rows),
        (DatasetSplit.VALIDATION, validation_rows),
        (DatasetSplit.TEST, test_rows),
    ):
        metrics[split.value] = {
            **_confusion(rows, threshold=SELECTED_THRESHOLD),
            **_ranking_metrics(rows),
        }
    payload: dict[str, object] = {
        "baseline_artifact_hash": baseline_artifact_hash(),
        "baseline_artifact_version": BASELINE_ARTIFACT_VERSION,
        "calibration": "not_applicable_score_not_probability",
        "candidate_thresholds": list(CANDIDATE_THRESHOLDS),
        "dataset_manifest_hash": dataset.manifest.manifest_hash,
        "dataset_version": dataset.manifest.dataset_version,
        "evaluation_schema_version": EVALUATION_SCHEMA_VERSION,
        "feature_schema_version": dataset.manifest.feature_schema_version,
        "limitations": [
            "All rows are synthetic and measure implementation behavior only.",
            "Proxy labels are not production incidents or proof of change causality.",
            "One admitted fixture repository permits temporal but not repository-holdout "
            "evaluation.",
            "Small split counts make every metric unstable and unsuitable for product claims.",
        ],
        "metrics": metrics,
        "minimum_validation_recall": MINIMUM_VALIDATION_RECALL,
        "raw_predictions": raw_predictions,
        "selected_threshold": SELECTED_THRESHOLD,
        "selection_rule": "validation_only_max_precision_then_f1_then_threshold_with_recall_floor",
        "split_hash": dataset.manifest.split_hash,
        "synthetic": True,
        "test_thresholds": _threshold_table(test_rows),
        "threshold_policy_version": THRESHOLD_POLICY_VERSION,
        "validation_thresholds": validation_thresholds,
    }
    return {**payload, "evaluation_hash": canonical_hash(payload)}
