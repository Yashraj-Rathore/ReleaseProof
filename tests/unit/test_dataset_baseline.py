from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from eng.evaluate_m4_baseline import (
    ADMISSION_PATH,
    DEFAULT_OUTPUT,
    SNAPSHOTS_PATH,
    build_artifact,
    build_fixture_dataset,
)
from eng.validate import COMMANDS
from packages.dataset_core import (
    AcquisitionMethod,
    DatasetSplit,
    LeakageError,
    ProxyLabel,
    SourceAdmission,
    SourceKind,
    TemporalSplitPolicy,
    extract_approved_source,
    parse_source_admission,
    run_leakage_checks,
)
from packages.ml_core import (
    BASELINE_ARTIFACT_VERSION,
    SELECTED_THRESHOLD,
    RiskBand,
    evaluate_baseline,
    score_features,
)

FIXTURE_CODE_COMMIT = "f" * 40


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _policy() -> TemporalSplitPolicy:
    return TemporalSplitPolicy(
        train_before=datetime(2024, 7, 1, tzinfo=UTC),
        validation_before=datetime(2024, 11, 1, tzinfo=UTC),
        test_before=datetime(2025, 4, 1, tzinfo=UTC),
    )


def test_fixture_dataset_manifest_materialization_and_splits_are_reproducible() -> None:
    first = build_fixture_dataset(extraction_code_commit=FIXTURE_CODE_COMMIT)
    second = build_fixture_dataset(extraction_code_commit=FIXTURE_CODE_COMMIT)

    assert first.as_dict() == second.as_dict()
    assert first.manifest.synthetic is True
    assert first.manifest.extraction_code_commit == FIXTURE_CODE_COMMIT
    assert first.manifest.counts == {
        "class_balance": {"proxy_negative": 7, "proxy_positive": 7, "unknown": 2},
        "included_rows": 14,
        "positive_prevalence": 0.5,
        "split_counts": {"excluded": 2, "test": 4, "train": 6, "validation": 4},
        "total_rows": 16,
        "unknown_rows": 2,
    }
    assert first.manifest.leakage_report.violations == ()
    assert len(first.manifest.leakage_report.passed_checks) == 9
    assert len(first.manifest.manifest_hash) == 64
    assert len(first.manifest.split_hash) == 64
    assert all(len(row.row_hash) == 64 for row in first.rows)
    assert all("outcome" not in row.feature_values for row in first.rows)
    assert {row.snapshot_id for row in first.rows if row.label.label is ProxyLabel.UNKNOWN} == {
        "m4-015",
        "m4-016",
    }
    assert all(
        row.split is DatasetSplit.EXCLUDED
        for row in first.rows
        if row.label.label is ProxyLabel.UNKNOWN
    )


def test_unapproved_source_and_public_source_without_complete_controls_fail_closed() -> None:
    admission = parse_source_admission(_json_object(ADMISSION_PATH))
    payload = _json_object(SNAPSHOTS_PATH)
    with pytest.raises(PermissionError, match="not approved"):
        extract_approved_source(admission=replace(admission, approved=False), payload=payload)

    public = SourceAdmission(
        source_id="public-example",
        source_kind=SourceKind.PUBLIC_REPOSITORY,
        repository_numeric_id=123,
        canonical_url="https://github.com/example/repository",
        license_spdx="MIT",
        license_evidence_sha256="a" * 64,
        license_version="commit-a",
        terms_url="https://docs.github.com/site-policy/github-terms/github-terms-of-service",
        terms_reviewed_at=datetime(2025, 6, 1, tzinfo=UTC),
        acquisition_method=AcquisitionMethod.GITHUB_API,
        allowed_fields=admission.allowed_fields,
        allowed_artifacts=("feature_rows",),
        redistribution_allowed=False,
        redistribution_notes="Aggregate features only; no raw redistribution.",
        retention_days=None,
        attribution="Example repository maintainers.",
        as_of=datetime(2025, 6, 1, tzinfo=UTC),
        observation_window_days=30,
        reviewer="fixture-reviewer",
        approved=True,
        synthetic=False,
        max_records=100,
        rate_limit_per_hour=50,
    )
    with pytest.raises(PermissionError, match="retention limit"):
        extract_approved_source(admission=public, payload=payload)


def test_duplicate_and_future_information_leakage_checks_fail_closed() -> None:
    dataset = build_fixture_dataset(extraction_code_commit=FIXTURE_CODE_COMMIT)
    train = next(row for row in dataset.rows if row.split is DatasetSplit.TRAIN)
    test = next(row for row in dataset.rows if row.split is DatasetSplit.TEST)
    duplicate_rows = tuple(
        replace(row, near_duplicate_hash=train.near_duplicate_hash) if row is test else row
        for row in dataset.rows
    )
    with pytest.raises(LeakageError, match="near_duplicate_cross_split"):
        run_leakage_checks(duplicate_rows, policy=_policy())

    contaminated_rows = tuple(
        replace(row, feature_provenance={**row.feature_provenance, "leaked": "outcome.label"})
        if row is train
        else row
        for row in dataset.rows
    )
    with pytest.raises(LeakageError, match="outcome_predictor"):
        run_leakage_checks(contaminated_rows, policy=_policy())


def test_heuristic_evaluation_freezes_validation_threshold_before_synthetic_test() -> None:
    dataset = build_fixture_dataset(extraction_code_commit=FIXTURE_CODE_COMMIT)
    evaluation = evaluate_baseline(dataset)

    assert evaluation["baseline_artifact_version"] == BASELINE_ARTIFACT_VERSION
    assert evaluation["selected_threshold"] == SELECTED_THRESHOLD == 30
    assert evaluation["calibration"] == "not_applicable_score_not_probability"
    assert evaluation["synthetic"] is True
    metrics = evaluation["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["validation"] == {
        "false_negative": 0,
        "false_positive": 0,
        "f1": 1.0,
        "negative_count": 2,
        "positive_count": 2,
        "precision": 1.0,
        "prevalence": 0.5,
        "pr_auc_average_precision": 1.0,
        "recall": 1.0,
        "roc_auc": 1.0,
        "row_count": 4,
        "threshold": 30,
        "true_negative": 2,
        "true_positive": 2,
    }
    test_metrics = metrics["test"]
    assert isinstance(test_metrics, dict)
    assert test_metrics["true_positive"] == 2
    assert test_metrics["false_positive"] == 2
    assert test_metrics["true_negative"] == 0
    assert test_metrics["false_negative"] == 0
    assert len(str(evaluation["evaluation_hash"])) == 64


def test_baseline_is_a_versioned_score_not_a_probability_and_can_abstain() -> None:
    dataset = build_fixture_dataset(extraction_code_commit=FIXTURE_CODE_COMMIT)
    row = next(item for item in dataset.rows if item.snapshot_id == "m4-012")
    scored = score_features(
        feature_schema_version=row.feature_schema_version,
        values=row.feature_values,
    )
    assert scored.score == 35
    assert scored.band is RiskBand.MEDIUM
    assert scored.calibrated_probability is None
    assert scored.proxy_prediction is True
    assert scored.artifact_version == BASELINE_ARTIFACT_VERSION

    missing = dict(row.feature_values)
    missing["lines_added"] = None
    unknown = score_features(feature_schema_version=row.feature_schema_version, values=missing)
    assert unknown.score is None
    assert unknown.band is RiskBand.UNKNOWN
    assert unknown.proxy_prediction is None
    assert unknown.missing_required == ("lines_added",)

    with pytest.raises(ValueError, match="incompatible"):
        score_features(feature_schema_version="future-features-v2", values=row.feature_values)


def test_committed_raw_artifact_rebuilds_from_its_recorded_code_commit() -> None:
    committed = _json_object(DEFAULT_OUTPUT)
    dataset = committed["dataset"]
    assert isinstance(dataset, dict)
    manifest = dataset["manifest"]
    assert isinstance(manifest, dict)
    code_commit = manifest["extraction_code_commit"]
    assert isinstance(code_commit, str)

    assert build_artifact(extraction_code_commit=code_commit) == committed
    assert any(command[-2:] == ("eng.evaluate_m4_baseline", "--check") for command in COMMANDS)
