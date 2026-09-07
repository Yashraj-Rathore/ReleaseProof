"""Build or verify frozen M13 lineage, evaluation-registry, and drift evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, cast

from packages.change_intel import canonical_hash
from packages.ml_core import (
    ArtifactReference,
    CompatibilityReport,
    DataScope,
    DriftPolicy,
    EvaluationComponent,
    EvaluationRegistryEntry,
    ExperimentKind,
    FeatureProfile,
    FormalExperimentRecord,
    LifecycleAction,
    ModelLifecycle,
    MonitoringProfile,
    PerformanceProfile,
    PromotionApproval,
    assess_drift,
    validate_model_transition,
)

ROOT = Path(__file__).resolve().parents[1]
M4_PATH = ROOT / "tests" / "golden" / "m4_synthetic_baseline_v1.json"
M5_PATH = ROOT / "models" / "public" / "m5_classical_ml_v1.json"
M6_PATH = ROOT / "artifacts" / "evaluation" / "m6_retrieval_eval_v1.json"
M7_PATH = ROOT / "artifacts" / "evaluation" / "m7_llm_eval_v1.json"
M11_PATH = ROOT / "artifacts" / "evaluation" / "m11_semantic_eval_v1.json"
M11_MODEL_PATH = ROOT / "models" / "public" / "m11_semantic_head_v1.json"
M12_PATH = ROOT / "artifacts" / "evaluation" / "m12_agent_eval_v1.json"
DRIFT_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "governance" / "m13_drift_profiles_v1.json"
ARTIFACT_PATH = ROOT / "artifacts" / "evaluation" / "m13_governance_eval_v1.json"


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return cast(dict[str, Any], value)


def _artifact(role: str, uri: str, sha256: str) -> ArtifactReference:
    return ArtifactReference(role=role, uri=f"artifact://releaseproof/{uri}", sha256=sha256)


def formal_experiments() -> tuple[FormalExperimentRecord, ...]:
    m4 = _json(M4_PATH)
    m5 = _json(M5_PATH)
    m11 = _json(M11_PATH)
    m11_model = _json(M11_MODEL_PATH)
    m4_manifest = m4["dataset"]["manifest"]
    m4_evaluation = m4["evaluation"]
    m5_models = m5["models"]
    m11_metrics = m11["held_out"]["metrics"]
    return (
        FormalExperimentRecord(
            experiment_name="releaseproof-risk-baselines",
            run_name="m4-deterministic-heuristic-v1",
            kind=ExperimentKind.HEURISTIC,
            dataset_version=m4_manifest["dataset_version"],
            dataset_manifest_sha256=m4_manifest["manifest_hash"],
            feature_schema_version=m4_manifest["feature_schema_version"],
            code_sha=m4_manifest["extraction_code_commit"],
            parameters={
                "artifact_version": m4_evaluation["baseline_artifact_version"],
                "leakage_report_sha256": m4_manifest["leakage_report"]["report_hash"],
                "selected_threshold": m4_evaluation["selected_threshold"],
                "threshold_policy": m4_evaluation["threshold_policy_version"],
            },
            metrics={
                "test_f1": m4_evaluation["metrics"]["test"]["f1"],
                "test_precision": m4_evaluation["metrics"]["test"]["precision"],
                "test_prevalence": m4_evaluation["metrics"]["test"]["prevalence"],
                "test_recall": m4_evaluation["metrics"]["test"]["recall"],
            },
            environment={"python": "3.13.15", "registration": "m13_historical_import"},
            artifacts=(
                _artifact(
                    "baseline",
                    "models/deterministic-heuristic-v1",
                    m4_evaluation["baseline_artifact_hash"],
                ),
                _artifact(
                    "evaluation",
                    "evaluations/m4-synthetic-evidence-v1",
                    m4_evaluation["evaluation_hash"],
                ),
            ),
            data_scope=DataScope.PUBLIC_SYNTHETIC,
            synthetic=True,
        ),
        FormalExperimentRecord(
            experiment_name="releaseproof-risk-candidates",
            run_name="m5-classical-risk-v1",
            kind=ExperimentKind.CLASSICAL,
            dataset_version=m5["dataset"]["dataset_version"],
            dataset_manifest_sha256=m5["dataset"]["manifest_hash"],
            feature_schema_version=m5["dataset"]["feature_schema_version"],
            code_sha=m5["training_code_commit"],
            parameters={
                "experiment_version": m5["experiment_declaration"]["version"],
                "preprocessor_version": m5["preprocessing"]["version"],
                "split_sha256": m5["dataset"]["split_hash"],
            },
            metrics={
                "logistic_test_f1": m5_models["logistic-risk-v1"]["test_metrics"]["f1"],
                "logistic_test_recall": m5_models["logistic-risk-v1"]["test_metrics"]["recall"],
                "xgboost_test_f1": m5_models["xgboost-risk-v1"]["test_metrics"]["f1"],
                "xgboost_test_recall": m5_models["xgboost-risk-v1"]["test_metrics"]["recall"],
            },
            environment=m5["runtime_compatibility"],
            artifacts=(
                _artifact("model_bundle", "models/m5-classical-risk-v1", m5["artifact_hash"]),
                _artifact(
                    "dataset_manifest",
                    "datasets/releaseproof-m4-synthetic-v1",
                    m5["dataset"]["manifest_hash"],
                ),
            ),
            data_scope=DataScope.PUBLIC_SYNTHETIC,
            synthetic=True,
        ),
        FormalExperimentRecord(
            experiment_name="releaseproof-semantic-candidates",
            run_name="m11-semantic-minilm-linear-head-v1",
            kind=ExperimentKind.SEMANTIC,
            dataset_version=m11["dataset"]["dataset_version"],
            dataset_manifest_sha256=m11["dataset"]["manifest_sha256"],
            feature_schema_version=m11["dataset"]["text_version"],
            code_sha=m11["training_code_commit"],
            parameters={
                "encoder_model": m11_model["encoder"]["model_id"],
                "encoder_revision": m11_model["encoder"]["revision"],
                "experiment_version": m11_model["experiment_version"],
                "threshold_policy": m11_model["threshold_policy_version"],
            },
            metrics={
                "test_exact_match": m11_metrics["exact_match"],
                "test_hamming_loss": m11_metrics["hamming_loss"],
                "test_macro_f1": m11_metrics["macro_f1"],
                "test_micro_f1": m11_metrics["micro_f1"],
            },
            environment=m11["runtime_compatibility"],
            artifacts=(
                _artifact(
                    "model",
                    "models/m11-semantic-minilm-linear-head-v1",
                    m11["model_artifact_sha256"],
                ),
                _artifact("evaluation", "evaluations/m11-semantic-eval-v1", m11["root_sha256"]),
                _artifact(
                    "dataset_manifest",
                    "datasets/releaseproof-m11-synthetic-semantic-v1",
                    m11["dataset"]["manifest_sha256"],
                ),
            ),
            data_scope=DataScope.PUBLIC_SYNTHETIC,
            synthetic=True,
        ),
    )


def evaluation_registry() -> tuple[EvaluationRegistryEntry, ...]:
    m6 = _json(M6_PATH)
    m7 = _json(M7_PATH)
    m12 = _json(M12_PATH)
    m6_hybrid = m6["quality"]["hybrid_rrf"]
    m7_quality = m7["quality"]
    m12_comparison = m12["quality"]["comparison"]
    return (
        EvaluationRegistryEntry(
            component=EvaluationComponent.RETRIEVAL,
            evaluation_dataset_version="m6-relevance-fixture-v1",
            evaluation_dataset_sha256=m6["fixture"]["sha256"],
            configuration_versions={
                "embedding": m6["configuration"]["evaluation_embedding"]["version"],
                "fts": m6["configuration"]["fts_profile_version"],
                "fusion": m6["configuration"]["fusion_version"],
                "normalizer": m6["configuration"]["normalizer_version"],
            },
            aggregate_metrics={
                "mrr_at_3": m6_hybrid["mrr_at_k"],
                "ndcg_at_3": m6_hybrid["ndcg_at_k"],
                "recall_at_3": m6_hybrid["recall_at_k"],
            },
            result_artifact=_artifact(
                "evaluation", "evaluations/m6-retrieval-eval-v1", m6["root_sha256"]
            ),
            license_spdx=m6["fixture"]["license"],
            synthetic=True,
        ),
        EvaluationRegistryEntry(
            component=EvaluationComponent.LLM,
            evaluation_dataset_version="m7-grounding-fixture-v1",
            evaluation_dataset_sha256=m7["fixture"]["sha256"],
            configuration_versions={
                "model": m7["configuration"]["model"],
                "prompt_sha256": m7["configuration"]["prompt_sha256"],
                "prompt_version": m7["configuration"]["prompt_version"],
                "schema_sha256": m7["configuration"]["schema_sha256"],
                "schema_version": m7["configuration"]["schema_version"],
            },
            aggregate_metrics={
                "citation_support_rate": m7_quality["citation_support_rate"],
                "schema_validity_rate": m7_quality["schema_validity_rate"],
                "unsupported_claim_rate": m7_quality["unsupported_claim_rate"],
            },
            result_artifact=_artifact(
                "evaluation", "evaluations/m7-llm-eval-v1", m7["root_sha256"]
            ),
            license_spdx=m7["fixture"]["license"],
            synthetic=True,
        ),
        EvaluationRegistryEntry(
            component=EvaluationComponent.AGENT,
            evaluation_dataset_version="m12-agent-fixture-v1",
            evaluation_dataset_sha256=m12["fixture"]["sha256"],
            configuration_versions={
                "critic": m12["configuration"]["critic"],
                "graph": m12["configuration"]["agent_graph"],
                "provider": m12["configuration"]["agent_provider"],
                "recommendation_policy": m12["configuration"]["recommendation_policy"],
            },
            aggregate_metrics={
                "agent_groundedness_rate": m12_comparison["agent"]["groundedness_rate"],
                "agent_task_success_rate": m12_comparison["agent"]["task_success_rate"],
                "agent_tool_error_rate": m12_comparison["agent"]["tool_error_rate"],
                "non_agent_task_success_rate": m12_comparison["non_agent_m7"]["task_success_rate"],
            },
            result_artifact=_artifact(
                "evaluation", "evaluations/m12-agent-eval-v1", m12["root_sha256"]
            ),
            license_spdx=m12["fixture"]["license"],
            synthetic=True,
        ),
    )


def _profile(value: dict[str, Any]) -> MonitoringProfile:
    performance = value.get("performance")
    return MonitoringProfile(
        feature_schema_version=value["feature_schema_version"],
        features=tuple(
            FeatureProfile(
                name=item["name"],
                row_count=item["row_count"],
                missing_count=item["missing_count"],
                histogram=tuple(item["histogram"]),
            )
            for item in value["features"]
        ),
        performance=None
        if performance is None
        else PerformanceProfile(
            metric_name=performance["metric_name"],
            value=performance["value"],
            labeled_row_count=performance["labeled_row_count"],
        ),
    )


def _drift_evidence() -> dict[str, object]:
    fixture = _json(DRIFT_FIXTURE_PATH)
    if (
        fixture.get("schema_version") != "m13-drift-fixture-v1"
        or fixture.get("synthetic") is not True
        or fixture.get("license") != "CC0-1.0"
    ):
        raise ValueError("M13 drift fixture identity is invalid")
    profiles = fixture["profiles"]
    reference = _profile(profiles["reference"])
    policy = DriftPolicy()
    cases = {
        name: assess_drift(reference=reference, current=_profile(profiles[name]), policy=policy)
        for name in ("stable", "shifted", "insufficient", "schema_mismatch")
    }
    expected = {
        "stable": "pass",
        "shifted": "review",
        "insufficient": "insufficient_data",
        "schema_mismatch": "incompatible_schema",
    }
    if any(cases[name].decision.value != decision for name, decision in expected.items()):
        raise ValueError("M13 drift controls did not produce their expected decisions")
    return {
        "cases": {name: result.as_dict() for name, result in cases.items()},
        "fixture": {
            "license": fixture["license"],
            "path": DRIFT_FIXTURE_PATH.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(_canonical_bytes(fixture)).hexdigest(),
            "synthetic": True,
            "usage": fixture["usage"],
        },
        "policy": policy.as_dict(),
    }


def _rollback_drill() -> dict[str, object]:
    checks = {
        "artifact_checksum": True,
        "evaluation_gate": True,
        "feature_schema": True,
        "input_schema": True,
        "privacy_license": True,
        "runtime": True,
    }
    compatibility = CompatibilityReport(
        checks=checks,
        report_sha256=canonical_hash(checks),
    )
    artifact_sha256 = canonical_hash({"artifact": "m13-rollback-drill-v1"})

    def approval(action: LifecycleAction) -> PromotionApproval:
        return PromotionApproval(
            artifact_sha256=artifact_sha256,
            approved_action=action,
            reviewer_id="synthetic-m13-control-reviewer",
            reviewer_role="owner",
            reason=(
                "Exercise lifecycle and rollback mechanics in a non-production synthetic control."
            ),
            evaluation_sha256=canonical_hash({"fixture": "m13-rollback-drill-v1"}),
            compatibility=compatibility,
        )

    transitions = (
        (None, ModelLifecycle.CANDIDATE, LifecycleAction.REGISTER, None),
        (
            ModelLifecycle.CANDIDATE,
            ModelLifecycle.STAGING,
            LifecycleAction.PROMOTE_TO_STAGING,
            approval(LifecycleAction.PROMOTE_TO_STAGING),
        ),
        (
            ModelLifecycle.STAGING,
            ModelLifecycle.ACTIVE,
            LifecycleAction.ACTIVATE,
            approval(LifecycleAction.ACTIVATE),
        ),
        (
            ModelLifecycle.ACTIVE,
            ModelLifecycle.RETIRED,
            LifecycleAction.RETIRE,
            approval(LifecycleAction.RETIRE),
        ),
        (
            ModelLifecycle.RETIRED,
            ModelLifecycle.ACTIVE,
            LifecycleAction.ROLLBACK,
            approval(LifecycleAction.ROLLBACK),
        ),
    )
    for current, target, action, evidence in transitions:
        validate_model_transition(current=current, target=target, action=action, approval=evidence)
    return {
        "final_state": ModelLifecycle.ACTIVE.value,
        "lifecycle_policy_version": "model-lifecycle-v1",
        "product_model_changed": False,
        "synthetic": True,
        "transition_count": len(transitions),
        "transitions": [
            {
                "action": action.value,
                "from": None if current is None else current.value,
                "to": target.value,
            }
            for current, target, action, _evidence in transitions
        ],
    }


def build_artifact() -> dict[str, object]:
    experiments = formal_experiments()
    evaluations = evaluation_registry()
    active = experiments[0]
    return {
        "schema_version": "m13-governance-evaluation-v1",
        "synthetic": True,
        "mlflow": {
            "artifact_store": "s3://releaseproof-local/mlflow",
            "backend_store": "postgresql://postgres/releaseproof",
            "client_server_exact_version_required": True,
            "local_customer_data_allowed": False,
            "pinned_version": "3.15.2",
            "service_authentication": "none_loopback_only",
        },
        "formal_experiments": [
            record.as_dict() | {"record_sha256": record.record_sha256} for record in experiments
        ],
        "evaluation_registry": [
            entry.as_dict() | {"record_sha256": entry.record_sha256} for entry in evaluations
        ],
        "model_registry": {
            "active": {
                "artifact_sha256": active.artifacts[0].sha256,
                "artifact_version": active.parameters["artifact_version"],
                "formal_experiment_sha256": active.record_sha256,
                "lifecycle": "active",
                "probability_display_allowed": False,
                "scope": "fixture_demo",
            },
            "automatic_promotion_allowed": False,
            "candidates_remain_unpromoted": [
                "logistic-risk-v1",
                "xgboost-risk-v1",
                "semantic-minilm-linear-head-v1",
            ],
            "rollback_target": None,
            "rollback_target_reason": "No second artifact has passed the promotion gate.",
        },
        "rollback_drill": _rollback_drill(),
        "drift": _drift_evidence(),
        "feedback": {
            "minimum_observation_window_days": 30,
            "organization_learning_requires_explicit_opt_in": True,
            "original_prediction_mutable": False,
            "shared_training_eligible": False,
        },
        "limitations": [
            "All registered experiment, evaluation, drift and rollback evidence is "
            "synthetic fixture evidence.",
            "The local MLflow service has no application tenant authentication and "
            "rejects customer-data records by policy.",
            "No learned model passed promotion; deterministic-heuristic-v1 remains "
            "active for the fixture/demo path.",
            "The rollback drill validates lifecycle mechanics only and does not deploy "
            "or serve a model.",
            "Drift thresholds and aggregate profiles are synthetic controls, not "
            "estimates of a production distribution.",
            "No automatic retraining, model promotion, hosted provider call or customer-"
            "data pooling occurred.",
        ],
    }


def _with_hash(value: dict[str, object]) -> dict[str, object]:
    return value | {"root_sha256": canonical_hash(value)}


def _verify() -> None:
    committed = _json(ARTIFACT_PATH)
    root_sha256 = committed.pop("root_sha256", None)
    if root_sha256 != canonical_hash(committed):
        raise ValueError("committed M13 governance artifact checksum is invalid")
    expected = build_artifact()
    if committed != expected:
        raise ValueError("committed M13 governance artifact is stale")
    print(
        json.dumps(
            {
                "drift_decisions": {
                    name: value["decision"] for name, value in committed["drift"]["cases"].items()
                },
                "evaluation_registry_entries": len(committed["evaluation_registry"]),
                "formal_experiments": len(committed["formal_experiments"]),
                "root_sha256": root_sha256,
                "status": "verified",
            },
            indent=2,
            sort_keys=True,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write == args.check:
        parser.error("choose exactly one of --write or --check")
    if args.write:
        ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_PATH.write_bytes(_canonical_bytes(_with_hash(build_artifact())))
        print(f"wrote {ARTIFACT_PATH.relative_to(ROOT)}")
    else:
        _verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
