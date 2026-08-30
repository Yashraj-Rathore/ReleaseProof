from __future__ import annotations

import copy
from functools import lru_cache
from typing import cast

import pytest

from eng.evaluate_m4_baseline import build_fixture_dataset
from packages.dataset_core import DatasetBuild, DatasetSplit
from packages.ml_core import (
    BASELINE_ARTIFACT_VERSION,
    CALIBRATION_MINIMUM_ROWS,
    LOGISTIC_ARTIFACT_VERSION,
    XGBOOST_ARTIFACT_VERSION,
    ModelCompatibilityError,
    fit_preprocessor,
    score_classical_candidate,
    train_classical_models,
    validate_classical_artifact,
)


@lru_cache(maxsize=1)
def _dataset() -> DatasetBuild:
    return build_fixture_dataset(extraction_code_commit="a" * 40)


@lru_cache(maxsize=1)
def _artifact() -> dict[str, object]:
    return train_classical_models(_dataset(), training_code_commit="b" * 40)


def test_preprocessing_is_fit_only_on_train_and_records_explicit_missingness() -> None:
    dataset = _dataset()
    train = tuple(row for row in dataset.rows if row.split is DatasetSplit.TRAIN)
    preprocessing = fit_preprocessor(train)

    assert preprocessing["training_row_count"] == 6
    assert preprocessing["feature_schema_version"] == "change-features-v1"
    input_names = cast(list[str], preprocessing["input_feature_names"])
    output_names = cast(list[str], preprocessing["output_feature_names"])
    assert len(input_names) == 25
    assert "missing__blast_max_depth" in output_names
    assert "missing__ownership_familiarity_90d" in output_names
    imputation = cast(dict[str, dict[str, object]], preprocessing["imputation"])
    assert imputation["blast_max_depth"]["strategy"] in {
        "training_median",
        "zero_no_training_observation",
    }
    assert len(cast(str, preprocessing["preprocessor_hash"])) == 64


def test_training_freezes_selection_and_prohibits_probability_on_small_synthetic_data() -> None:
    artifact = _artifact()
    validate_classical_artifact(artifact)
    selection = cast(dict[str, object], artifact["active_selection"])
    declaration = cast(dict[str, object], artifact["experiment_declaration"])
    calibration = cast(dict[str, object], declaration["calibration"])
    models = cast(dict[str, dict[str, object]], artifact["models"])

    assert selection["active_artifact_version"] == BASELINE_ARTIFACT_VERSION
    assert selection["decision"] == "keep_deterministic_heuristic"
    assert selection["probability_display_allowed"] is False
    minimum = cast(dict[str, int], calibration["minimum_sample"])
    assert minimum["total_rows"] == CALIBRATION_MINIMUM_ROWS
    for version in (LOGISTIC_ARTIFACT_VERSION, XGBOOST_ARTIFACT_VERSION):
        model = models[version]
        calibration_result = cast(dict[str, object], model["calibration"])
        assert calibration_result["status"] == "not_attempted_insufficient_validation_sample"
        assert calibration_result["probability_display_allowed"] is False
        assert calibration_result["calibrated_probability"] is None
        assert cast(dict[str, object], model["test_metrics"])["row_count"] == 4
        assert len(cast(list[object], model["raw_test_predictions"])) == 4
        assert model["lifecycle"] == "candidate_not_promoted"


@pytest.mark.parametrize("model_version", [LOGISTIC_ARTIFACT_VERSION, XGBOOST_ARTIFACT_VERSION])
def test_candidate_inference_uses_exact_artifact_and_never_returns_probability(
    model_version: str,
) -> None:
    artifact = _artifact()
    row = next(row for row in _dataset().rows if row.split is DatasetSplit.TEST)

    score = score_classical_candidate(
        artifact,
        model_artifact_version=model_version,
        feature_schema_version=row.feature_schema_version,
        values=row.feature_values,
    )

    assert score.model_score is not None
    assert 0 <= score.model_score <= 100
    assert score.calibrated_probability is None
    assert score.probability_display_allowed is False
    assert score.band in {"low", "medium", "high"}
    assert score.contributions
    assert all("not a causal claim" in item.explanation for item in score.contributions)


def test_inference_fails_closed_on_schema_checksum_and_required_missingness() -> None:
    artifact = _artifact()
    row = next(row for row in _dataset().rows if row.split is DatasetSplit.TEST)
    with pytest.raises(ModelCompatibilityError, match="feature schema"):
        score_classical_candidate(
            artifact,
            model_artifact_version=LOGISTIC_ARTIFACT_VERSION,
            feature_schema_version="change-features-v999",
            values=row.feature_values,
        )

    tampered = copy.deepcopy(artifact)
    tampered["training_code_commit"] = "c" * 40
    with pytest.raises(ModelCompatibilityError, match="checksum"):
        validate_classical_artifact(tampered)

    missing = dict(row.feature_values)
    missing["files_changed"] = None
    score = score_classical_candidate(
        artifact,
        model_artifact_version=LOGISTIC_ARTIFACT_VERSION,
        feature_schema_version=row.feature_schema_version,
        values=missing,
    )
    assert score.band == "unknown"
    assert score.model_score is None
    assert score.missing_required == ("files_changed",)


def test_training_is_repeatable_in_the_same_pinned_environment() -> None:
    first = train_classical_models(_dataset(), training_code_commit="d" * 40)
    second = train_classical_models(_dataset(), training_code_commit="d" * 40)
    assert first == second
