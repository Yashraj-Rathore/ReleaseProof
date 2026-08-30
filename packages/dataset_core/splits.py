"""Frozen temporal split assignment and fail-closed leakage checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from packages.change_intel import FEATURE_DEFINITIONS, FEATURE_SCHEMA_VERSION, canonical_hash
from packages.dataset_core.contracts import (
    SPLIT_RULE_VERSION,
    DatasetSplit,
    LeakageReport,
    MaterializedFeatureRow,
    ProxyLabel,
    require_aware,
)

LEAKAGE_REPORT_SCHEMA_VERSION = "leakage-report-v1"
_BANNED_PREDICTOR_TOKENS = {
    "author_key",
    "incident",
    "label",
    "outcome",
    "revert",
    "rollback",
}


class LeakageError(ValueError):
    """A formal dataset boundary failed closed."""


@dataclass(frozen=True, slots=True)
class TemporalSplitPolicy:
    train_before: datetime
    validation_before: datetime
    test_before: datetime
    version: str = SPLIT_RULE_VERSION

    def __post_init__(self) -> None:
        for field, value in (
            ("train_before", self.train_before),
            ("validation_before", self.validation_before),
            ("test_before", self.test_before),
        ):
            require_aware(value, field=field)
        if not self.train_before < self.validation_before < self.test_before:
            raise ValueError("temporal split boundaries must be strictly increasing")
        if self.version != SPLIT_RULE_VERSION:
            raise ValueError("temporal split policy version is incompatible")

    def assign(self, *, prediction_time: datetime, label: ProxyLabel) -> DatasetSplit:
        require_aware(prediction_time, field="prediction_time")
        if label is ProxyLabel.UNKNOWN:
            return DatasetSplit.EXCLUDED
        if prediction_time < self.train_before:
            return DatasetSplit.TRAIN
        if prediction_time < self.validation_before:
            return DatasetSplit.VALIDATION
        if prediction_time < self.test_before:
            return DatasetSplit.TEST
        return DatasetSplit.EXCLUDED

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": "temporal",
            "test_before": self.test_before.isoformat(),
            "train_before": self.train_before.isoformat(),
            "validation_before": self.validation_before.isoformat(),
            "version": self.version,
        }


def split_assignment_hash(rows: tuple[MaterializedFeatureRow, ...]) -> str:
    return canonical_hash(
        {row.snapshot_id: row.split for row in sorted(rows, key=lambda item: item.snapshot_id)}
    )


def _cross_split_duplicates(
    rows: tuple[MaterializedFeatureRow, ...],
    *,
    attribute: str,
) -> list[str]:
    locations: dict[str, set[DatasetSplit]] = {}
    for row in rows:
        if row.split is DatasetSplit.EXCLUDED:
            continue
        value = getattr(row, attribute)
        if not isinstance(value, str):
            raise TypeError("leakage fingerprint must be text")
        locations.setdefault(value, set()).add(row.split)
    return sorted(value for value, splits in locations.items() if len(splits) > 1)


def run_leakage_checks(
    rows: tuple[MaterializedFeatureRow, ...],
    *,
    policy: TemporalSplitPolicy,
) -> LeakageReport:
    violations: list[str] = []
    expected_features = {definition.name for definition in FEATURE_DEFINITIONS}
    for row in rows:
        expected_split = policy.assign(
            prediction_time=row.prediction_time,
            label=row.label.label,
        )
        if row.split is not expected_split:
            violations.append(f"split_assignment:{row.snapshot_id}")
        if row.feature_schema_version != FEATURE_SCHEMA_VERSION:
            violations.append(f"feature_schema:{row.snapshot_id}")
        if set(row.feature_values) != expected_features:
            violations.append(f"feature_shape:{row.snapshot_id}")
        predictor_text = " ".join(
            (
                *row.feature_values.keys(),
                *row.feature_provenance.keys(),
                *row.feature_provenance.values(),
            )
        ).casefold()
        if any(token in predictor_text for token in _BANNED_PREDICTOR_TOKENS):
            violations.append(f"outcome_predictor:{row.snapshot_id}")
        if row.label.label is not ProxyLabel.UNKNOWN:
            observed_at = row.label.observed_at
            if observed_at is None or observed_at < row.prediction_time:
                violations.append(f"future_information:{row.snapshot_id}")
        elif row.split is not DatasetSplit.EXCLUDED:
            violations.append(f"unknown_not_excluded:{row.snapshot_id}")

    checks = (
        ("head_sha_cross_split", "head_sha"),
        ("diff_hash_cross_split", "diff_hash"),
        ("near_duplicate_cross_split", "near_duplicate_hash"),
        ("row_hash_cross_split", "row_hash"),
    )
    for code, attribute in checks:
        duplicates = _cross_split_duplicates(rows, attribute=attribute)
        violations.extend(f"{code}:{value}" for value in duplicates)

    passed_checks = (
        "prediction_time_only_features",
        "no_author_identity_predictor",
        "no_outcome_derived_predictor",
        "complete_observation_before_inclusion",
        "fixed_temporal_assignment",
        "no_head_sha_across_splits",
        "no_diff_hash_across_splits",
        "no_near_duplicate_across_splits",
        "exact_feature_schema",
    )
    report_payload = {
        "passed_checks": list(passed_checks) if not violations else [],
        "schema_version": LEAKAGE_REPORT_SCHEMA_VERSION,
        "violations": sorted(violations),
    }
    report = LeakageReport(
        schema_version=LEAKAGE_REPORT_SCHEMA_VERSION,
        passed_checks=passed_checks if not violations else (),
        violations=tuple(sorted(violations)),
        report_hash=canonical_hash(report_payload),
    )
    if report.violations:
        raise LeakageError("dataset leakage checks failed: " + ", ".join(report.violations))
    return report
