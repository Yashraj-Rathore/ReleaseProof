from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from adapters.mlflow import MLflowTracker, MLflowTrackingSettings
from packages.change_intel import canonical_hash
from packages.ml_core import (
    ArtifactReference,
    CompatibilityReport,
    DataScope,
    DriftDecision,
    DriftPolicy,
    EvaluationComponent,
    EvaluationRegistryEntry,
    ExperimentKind,
    FeatureProfile,
    FormalExperimentRecord,
    GovernanceError,
    LifecycleAction,
    ModelLifecycle,
    MonitoringProfile,
    OutcomeKind,
    PerformanceProfile,
    PromotionApproval,
    assess_drift,
    evaluate_feedback_eligibility,
    validate_model_transition,
)


def _sha(character: str) -> str:
    return character * 64


def _experiment(*, scope: DataScope = DataScope.PUBLIC_SYNTHETIC) -> FormalExperimentRecord:
    return FormalExperimentRecord(
        experiment_name="releaseproof-risk",
        run_name="synthetic-baseline",
        kind=ExperimentKind.HEURISTIC,
        dataset_version="synthetic-v1",
        dataset_manifest_sha256=_sha("a"),
        feature_schema_version="features-v1",
        code_sha="b" * 40,
        parameters={"threshold": 45, "enabled": True},
        metrics={"recall": 1.0},
        environment={"python": "3.13.15"},
        artifacts=(ArtifactReference("model", "artifact://model-v1", _sha("c")),),
        data_scope=scope,
        synthetic=scope is DataScope.PUBLIC_SYNTHETIC,
        contains_customer_code=scope is DataScope.ORGANIZATION_LOCAL,
    )


def _evaluation() -> EvaluationRegistryEntry:
    return EvaluationRegistryEntry(
        component=EvaluationComponent.RETRIEVAL,
        evaluation_dataset_version="retrieval-synthetic-v1",
        evaluation_dataset_sha256=_sha("d"),
        configuration_versions={"embedding": "hash-v1", "retrieval": "hybrid-v1"},
        aggregate_metrics={"recall_at_3": 1.0},
        result_artifact=ArtifactReference("evaluation", "artifact://retrieval-eval-v1", _sha("e")),
        license_spdx="MIT",
        synthetic=True,
    )


def _approval(
    *,
    action: LifecycleAction = LifecycleAction.PROMOTE_TO_STAGING,
    artifact_sha256: str | None = None,
    passed: bool = True,
) -> PromotionApproval:
    checks = {
        "artifact_checksum": passed,
        "evaluation_gate": True,
        "feature_schema": True,
        "input_schema": True,
        "privacy_license": True,
        "runtime": True,
    }
    compatibility = CompatibilityReport(
        checks=checks,
        report_sha256=canonical_hash(dict(sorted(checks.items()))),
    )
    return PromotionApproval(
        artifact_sha256=artifact_sha256 or _sha("a"),
        approved_action=action,
        reviewer_id="user:1",
        reviewer_role="admin",
        reason="Synthetic evidence passed the declared gate.",
        evaluation_sha256=_sha("f"),
        compatibility=compatibility,
    )


def _profile(
    *,
    histogram: tuple[int, int] = (50, 50),
    missing: int = 0,
    rows: int = 100,
    performance: float = 0.80,
    labeled_rows: int = 100,
    schema: str = "features-v1",
) -> MonitoringProfile:
    return MonitoringProfile(
        feature_schema_version=schema,
        features=(
            FeatureProfile(
                name="changed_lines",
                row_count=rows,
                missing_count=missing,
                histogram=histogram,
            ),
        ),
        performance=PerformanceProfile(
            metric_name="recall",
            value=performance,
            labeled_row_count=labeled_rows,
        ),
    )


def test_formal_experiment_requires_complete_immutable_lineage() -> None:
    record = _experiment()

    assert record.record_sha256 == canonical_hash(record.as_dict())
    assert record.as_dict()["contains_customer_code"] is False
    with pytest.raises(GovernanceError, match="dataset manifest"):
        FormalExperimentRecord(
            experiment_name=record.experiment_name,
            run_name=record.run_name,
            kind=record.kind,
            dataset_version=record.dataset_version,
            dataset_manifest_sha256="missing",
            feature_schema_version=record.feature_schema_version,
            code_sha=record.code_sha,
            parameters=record.parameters,
            metrics=record.metrics,
            environment=record.environment,
            artifacts=record.artifacts,
            data_scope=record.data_scope,
            synthetic=record.synthetic,
        )


def test_evaluation_registry_rejects_customer_code() -> None:
    entry = _evaluation()

    assert entry.record_sha256 == canonical_hash(entry.as_dict())
    with pytest.raises(GovernanceError, match="customer code"):
        EvaluationRegistryEntry(
            component=entry.component,
            evaluation_dataset_version=entry.evaluation_dataset_version,
            evaluation_dataset_sha256=entry.evaluation_dataset_sha256,
            configuration_versions=entry.configuration_versions,
            aggregate_metrics=entry.aggregate_metrics,
            result_artifact=entry.result_artifact,
            license_spdx=entry.license_spdx,
            synthetic=True,
            contains_customer_code=True,
        )


def test_model_lifecycle_requires_human_approval_and_compatibility() -> None:
    validate_model_transition(
        current=None,
        target=ModelLifecycle.CANDIDATE,
        action=LifecycleAction.REGISTER,
        approval=None,
    )
    validate_model_transition(
        current=ModelLifecycle.CANDIDATE,
        target=ModelLifecycle.STAGING,
        action=LifecycleAction.PROMOTE_TO_STAGING,
        approval=_approval(),
    )

    with pytest.raises(GovernanceError, match="passing compatibility"):
        validate_model_transition(
            current=ModelLifecycle.STAGING,
            target=ModelLifecycle.ACTIVE,
            action=LifecycleAction.ACTIVATE,
            approval=_approval(action=LifecycleAction.ACTIVATE, passed=False),
        )
    with pytest.raises(GovernanceError, match="not allowed"):
        validate_model_transition(
            current=ModelLifecycle.CANDIDATE,
            target=ModelLifecycle.ACTIVE,
            action=LifecycleAction.ACTIVATE,
            approval=_approval(action=LifecycleAction.ACTIVATE),
        )
    with pytest.raises(GovernanceError, match="does not authorize"):
        validate_model_transition(
            current=ModelLifecycle.CANDIDATE,
            target=ModelLifecycle.STAGING,
            action=LifecycleAction.PROMOTE_TO_STAGING,
            approval=_approval(action=LifecycleAction.ACTIVATE),
        )


def test_feedback_is_delayed_org_local_and_never_shared() -> None:
    snapshot_at = datetime(2026, 1, 1, tzinfo=UTC)
    window_end = snapshot_at + timedelta(days=30)
    eligible = evaluate_feedback_eligibility(
        snapshot_created_at=snapshot_at,
        observation_window_started_at=snapshot_at,
        observation_window_ended_at=window_end,
        signal_observed_at=snapshot_at + timedelta(days=2),
        ingested_at=window_end,
        outcome=OutcomeKind.HOTFIX,
        provenance_known=True,
        organization_learning_enabled=True,
        explicit_learning_opt_in=True,
    )

    assert eligible.organization_training_eligible is True
    assert eligible.shared_training_eligible is False
    with pytest.raises(GovernanceError, match="before its window completes"):
        evaluate_feedback_eligibility(
            snapshot_created_at=snapshot_at,
            observation_window_started_at=snapshot_at,
            observation_window_ended_at=window_end,
            signal_observed_at=snapshot_at + timedelta(days=2),
            ingested_at=window_end - timedelta(seconds=1),
            outcome=OutcomeKind.HOTFIX,
            provenance_known=True,
            organization_learning_enabled=True,
            explicit_learning_opt_in=True,
        )


def test_drift_detects_distribution_missingness_performance_and_data_quality() -> None:
    policy = DriftPolicy()
    reference = _profile()

    assert assess_drift(reference=reference, current=_profile(), policy=policy).decision is (
        DriftDecision.PASS
    )
    shifted = assess_drift(
        reference=reference,
        current=_profile(histogram=(90, 0), missing=10, performance=0.70),
        policy=policy,
    )
    assert shifted.decision is DriftDecision.REVIEW
    assert set(shifted.reason_codes) == {"distribution_shift", "performance_shift"}
    assert shifted.human_review_required is True
    assert shifted.automatic_retraining_allowed is False
    assert shifted.automatic_promotion_allowed is False
    insufficient = assess_drift(
        reference=reference,
        current=_profile(histogram=(20, 20), rows=40, labeled_rows=40),
        policy=policy,
    )
    assert insufficient.decision is DriftDecision.INSUFFICIENT_DATA
    incompatible = assess_drift(
        reference=reference,
        current=_profile(schema="features-v2"),
        policy=policy,
    )
    assert incompatible.decision is DriftDecision.INCOMPATIBLE_SCHEMA


@dataclass
class _Info:
    run_id: str


@dataclass
class _Run:
    info: _Info


@dataclass
class _Experiment:
    experiment_id: str


class _FakeMLflowClient:
    def __init__(self) -> None:
        self.experiments: dict[str, _Experiment] = {}
        self.runs: dict[str, _Run] = {}
        self.tags: dict[str, dict[str, str]] = {}
        self.params: list[tuple[str, str, str]] = []
        self.metrics: list[tuple[str, str, float]] = []
        self.artifacts: list[tuple[str, dict[str, object], str]] = []
        self.statuses: list[tuple[str, str]] = []

    def get_experiment_by_name(self, name: str) -> _Experiment | None:
        return self.experiments.get(name)

    def create_experiment(self, name: str) -> str:
        experiment_id = str(len(self.experiments) + 1)
        self.experiments[name] = _Experiment(experiment_id)
        return experiment_id

    def search_runs(
        self, experiment_ids: list[str], *, filter_string: str, max_results: int
    ) -> list[_Run]:
        del experiment_ids, max_results
        digest = filter_string.rsplit("'", 2)[1]
        return [run for run_id, run in self.runs.items() if self.tags[run_id]["hash"] == digest]

    def create_run(self, experiment_id: str, *, tags: dict[str, str]) -> _Run:
        del experiment_id
        run_id = f"run-{len(self.runs) + 1}"
        run = _Run(_Info(run_id))
        self.runs[run_id] = run
        self.tags[run_id] = {"hash": tags["releaseproof_record_sha256"], **tags}
        return run

    def log_param(self, run_id: str, key: str, value: str) -> None:
        self.params.append((run_id, key, value))

    def log_metric(self, run_id: str, key: str, value: float) -> None:
        self.metrics.append((run_id, key, value))

    def log_dict(self, run_id: str, dictionary: dict[str, object], artifact_file: str) -> None:
        self.artifacts.append((run_id, dictionary, artifact_file))

    def set_terminated(self, run_id: str, *, status: str) -> None:
        self.statuses.append((run_id, status))


def test_mlflow_adapter_is_idempotent_and_logs_complete_safe_metadata() -> None:
    client = _FakeMLflowClient()
    tracker = MLflowTracker(
        MLflowTrackingSettings("http://localhost:5000"),
        client=client,
    )

    first = tracker.log_formal_experiment(_experiment())
    repeated = tracker.log_formal_experiment(_experiment())
    evaluation = tracker.log_evaluation(_evaluation())

    assert first.created is True
    assert repeated == type(repeated)(first.run_id, first.record_sha256, False)
    assert evaluation.created is True
    assert len(client.runs) == 2
    assert (first.run_id, "code_sha", "b" * 40) in client.params
    assert (first.run_id, "recall", 1.0) in client.metrics
    assert client.artifacts[0][2] == "governance/formal-experiment.json"
    assert client.statuses == [(first.run_id, "FINISHED"), (evaluation.run_id, "FINISHED")]

    with pytest.raises(GovernanceError, match="public/synthetic"):
        tracker.log_formal_experiment(_experiment(scope=DataScope.ORGANIZATION_LOCAL))


def test_mlflow_tracking_uri_rejects_embedded_credentials() -> None:
    with pytest.raises(ValueError, match="credentials"):
        MLflowTrackingSettings("http://user:secret@localhost:5000")
