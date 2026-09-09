from __future__ import annotations

from dataclasses import replace

import pytest

from packages.release_core import (
    ArtifactIdentity,
    DatabaseRollbackStrategy,
    PromotionEvidence,
    PromotionStage,
    ReleaseManifest,
    RollbackEvidence,
    ServingDecision,
    ServingDecisionRecord,
    WorkloadBudget,
    validate_promotion,
    validate_rollback,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


def _artifact(name: str, digest: str = SHA_A) -> ArtifactIdentity:
    return ArtifactIdentity(
        name=name,
        version="v1",
        sha256=digest,
        source_path=f"artifacts/{name}.json",
    )


def _manifest() -> ReleaseManifest:
    return ReleaseManifest(
        source_revision="c" * 40,
        application_image_digest=f"sha256:{SHA_A}",
        sbom=_artifact("sbom"),
        active_model=_artifact("model", SHA_B),
        dataset=_artifact("dataset"),
        model_registry_manifest_sha256=SHA_A,
        dataset_manifest_sha256=SHA_A,
        migration_tree_sha256=SHA_A,
        evaluation_bundle_sha256=SHA_A,
        build_provenance_sha256=SHA_A,
    )


def test_release_manifest_rejects_mutable_image_and_external_execution() -> None:
    manifest = _manifest()

    with pytest.raises(ValueError, match="must use sha256"):
        replace(manifest, application_image_digest="releaseproof-app:latest")
    with pytest.raises(ValueError, match="cannot enable external"):
        replace(manifest, external_repository_execution_enabled=True)


def test_promotion_requires_same_immutable_artifacts_and_all_gates() -> None:
    manifest = _manifest()
    evidence = PromotionEvidence(
        stage=PromotionStage.STAGING,
        release_manifest_sha256=manifest.sha256,
        application_image_digest=manifest.application_image_digest,
        active_model_sha256=manifest.active_model.sha256,
        migrations_passed=True,
        evaluations_passed=True,
        smoke_passed=True,
        compatibility_passed=True,
        protected_approval_reference="github-environment:staging:run-1",
    )

    validate_promotion(manifest, evidence)
    with pytest.raises(ValueError, match="different application image"):
        validate_promotion(manifest, replace(evidence, application_image_digest=f"sha256:{SHA_B}"))
    with pytest.raises(ValueError, match="requires migration"):
        validate_promotion(manifest, replace(evidence, smoke_passed=False))


def test_rollback_is_compatibility_gated_and_never_reverses_database_migrations() -> None:
    evidence = RollbackEvidence(
        current_release_manifest_sha256=SHA_A,
        target_release_manifest_sha256=SHA_B,
        target_compatibility_passed=True,
        target_smoke_passed=True,
        database_strategy=DatabaseRollbackStrategy.FORWARD_FIX_ONLY,
    )

    validate_rollback(evidence)
    with pytest.raises(ValueError, match="compatibility and smoke"):
        validate_rollback(replace(evidence, target_compatibility_passed=False))


def test_fastapi_extraction_requires_a_measured_trigger_and_accepted_cost() -> None:
    budget = WorkloadBudget(768, 10_000, 250, 4.0, 2_000, 75.0)
    values = {
        "component": "fastapi-model-service",
        "decision": ServingDecision.EXTRACT_FASTAPI,
        "workload": "bounded inference",
        "budget": budget,
        "evidence_paths": ("evidence.json",),
        "measured_dimensions": ("p95_ms",),
        "missing_dimensions": (),
        "extraction_criteria_met": (),
        "operational_security_cost_accepted": False,
        "rationale": ("comparison",),
    }

    with pytest.raises(ValueError, match="requires a measured criterion"):
        ServingDecisionRecord(**values)  # type: ignore[arg-type]
    record = ServingDecisionRecord(
        **(
            values
            | {
                "decision": ServingDecision.DEFER_INSUFFICIENT_EVIDENCE,
                "missing_dimensions": ("worker_rss",),
            }
        )  # type: ignore[arg-type]
    )
    assert record.decision is ServingDecision.DEFER_INSUFFICIENT_EVIDENCE
