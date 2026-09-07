from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import DatabaseError, connection, transaction
from django.http import Http404

from apps.web.organizations.models import MembershipRole
from apps.web.risk.governance_services import (
    ModelGovernanceError,
    activate_model,
    ingest_deployment_outcome,
    promote_model_to_staging,
    record_drift_assessment,
    register_model_artifact,
    review_drift_assessment,
    rollback_model,
)
from apps.web.risk.models import (
    DriftReviewDecision,
    GovernedModelArtifact,
    ModelLifecycleEvent,
    RiskScore,
)
from packages.change_intel import canonical_hash
from packages.ml_core import (
    CompatibilityReport,
    DriftDecision,
    DriftPolicy,
    FeatureProfile,
    LifecycleAction,
    MonitoringProfile,
    OutcomeKind,
    PerformanceProfile,
    PromotionApproval,
    assess_drift,
)
from tests import factories
from tests.integration.test_llm_evidence_persistence import _scope

pytestmark = pytest.mark.django_db


def _sha(character: str) -> str:
    return character * 64


def _approval(
    actor_id: int, *, artifact: GovernedModelArtifact, action: LifecycleAction
) -> PromotionApproval:
    checks = {
        "artifact_checksum": True,
        "evaluation_gate": True,
        "feature_schema": True,
        "input_schema": True,
        "privacy_license": True,
        "runtime": True,
    }
    return PromotionApproval(
        artifact_sha256=artifact.artifact_sha256,
        approved_action=action,
        reviewer_id=f"user:{actor_id}",
        reviewer_role="admin",
        reason="Synthetic evaluation and compatibility evidence passed.",
        evaluation_sha256=_sha("e"),
        compatibility=CompatibilityReport(
            checks=checks,
            report_sha256=canonical_hash(dict(sorted(checks.items()))),
        ),
    )


def _register(
    *, organization: object, actor: object, version: str, character: str
) -> GovernedModelArtifact:
    return register_model_artifact(
        organization=organization,  # type: ignore[arg-type]
        actor=actor,  # type: ignore[arg-type]
        model_name="release-risk",
        artifact_version=version,
        artifact_sha256=_sha(character),
        artifact_uri=f"mlflow-artifacts:/models/release-risk/{version}",
        algorithm="deterministic-heuristic",
        formal_experiment_sha256=_sha("a"),
        mlflow_run_id=f"run-{version}",
        dataset_version="m13-synthetic-v1",
        dataset_manifest_sha256=_sha("b"),
        feature_schema_version="change-features-v1",
        input_schema_sha256=_sha("c"),
        runtime_compatibility={"python": "3.13.15", "runtime": "django-monolith"},
        synthetic=True,
        contains_customer_data=False,
    ).artifact


def _profile(*, shifted: bool) -> MonitoringProfile:
    return MonitoringProfile(
        feature_schema_version="change-features-v1",
        features=(
            FeatureProfile(
                name="changed_lines",
                row_count=100,
                missing_count=0,
                histogram=(90, 10) if shifted else (50, 50),
            ),
        ),
        performance=PerformanceProfile(
            metric_name="recall",
            value=0.70 if shifted else 0.80,
            labeled_row_count=100,
        ),
    )


def test_model_promotion_activation_and_rollback_are_tenant_scoped_and_auditable() -> None:
    organization, _repository, _feature_set = _scope(suffix="governance", number=131)
    admin = factories.user(username="m13-admin")
    factories.membership(
        organization=organization,  # type: ignore[arg-type]
        user=admin,
        role=MembershipRole.ADMIN,
    )
    first = _register(
        organization=organization,
        actor=admin,
        version="deterministic-v1",
        character="1",
    )
    second = _register(
        organization=organization,
        actor=admin,
        version="candidate-v2",
        character="2",
    )

    promote_model_to_staging(
        organization=organization,  # type: ignore[arg-type]
        artifact_public_id=first.public_id,
        approval=_approval(admin.pk, artifact=first, action=LifecycleAction.PROMOTE_TO_STAGING),
        actor=admin,
    )
    first_deployment = activate_model(
        organization=organization,  # type: ignore[arg-type]
        artifact_public_id=first.public_id,
        approval=_approval(admin.pk, artifact=first, action=LifecycleAction.ACTIVATE),
        actor=admin,
    )
    promote_model_to_staging(
        organization=organization,  # type: ignore[arg-type]
        artifact_public_id=second.public_id,
        approval=_approval(admin.pk, artifact=second, action=LifecycleAction.PROMOTE_TO_STAGING),
        actor=admin,
    )
    second_deployment = activate_model(
        organization=organization,  # type: ignore[arg-type]
        artifact_public_id=second.public_id,
        approval=_approval(admin.pk, artifact=second, action=LifecycleAction.ACTIVATE),
        actor=admin,
        retirement_approval=_approval(admin.pk, artifact=first, action=LifecycleAction.RETIRE),
    )
    rolled_back = rollback_model(
        organization=organization,  # type: ignore[arg-type]
        model_name="release-risk",
        approval=_approval(admin.pk, artifact=first, action=LifecycleAction.ROLLBACK),
        retirement_approval=_approval(admin.pk, artifact=second, action=LifecycleAction.RETIRE),
        actor=admin,
    )

    assert first_deployment.deployment.generation == 1
    assert second_deployment.deployment.generation == 2
    assert rolled_back.deployment.generation == 3
    assert rolled_back.deployment.active_artifact_id == first.pk
    assert rolled_back.deployment.rollback_artifact_id == second.pk
    assert list(first.lifecycle_events.order_by("sequence").values_list("to_state", flat=True)) == [
        "candidate",
        "staging",
        "active",
        "retired",
        "active",
    ]
    assert list(
        second.lifecycle_events.order_by("sequence").values_list("to_state", flat=True)
    ) == ["candidate", "staging", "active", "retired"]
    assert ModelLifecycleEvent.objects.count() == 9
    assert all(
        event.approval_sha256
        for event in ModelLifecycleEvent.objects.exclude(action=LifecycleAction.REGISTER)
    )

    other = factories.organization(name="Other", slug="m13-other")
    factories.membership(organization=other, user=admin, role=MembershipRole.ADMIN)
    with pytest.raises(Http404):
        promote_model_to_staging(
            organization=other,
            artifact_public_id=first.public_id,
            approval=_approval(admin.pk, artifact=first, action=LifecycleAction.PROMOTE_TO_STAGING),
            actor=admin,
        )
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE risk_governedmodelartifact SET artifact_sha256 = %s WHERE id = %s",
            [_sha("9"), first.pk],
        )


def test_registration_is_idempotent_and_checksum_conflicts_fail_closed() -> None:
    organization, _repository, _feature_set = _scope(suffix="registry", number=132)
    admin = factories.user(username="m13-registry-admin")
    factories.membership(
        organization=organization,  # type: ignore[arg-type]
        user=admin,
        role=MembershipRole.ADMIN,
    )

    first = _register(organization=organization, actor=admin, version="v1", character="3")
    repeated = _register(organization=organization, actor=admin, version="v1", character="3")

    assert repeated.pk == first.pk
    assert first.lifecycle_events.count() == 1
    with pytest.raises(ModelGovernanceError, match="identity_conflict"):
        _register(organization=organization, actor=admin, version="v1", character="4")


def test_delayed_outcome_keeps_prediction_immutable_and_never_enters_shared_training() -> None:
    organization, _repository, feature_set = _scope(suffix="feedback", number=133)
    organization.organization_learning_enabled = True  # type: ignore[attr-defined]
    organization.save(update_fields=("organization_learning_enabled", "updated_at"))  # type: ignore[attr-defined]
    snapshot = feature_set.snapshot  # type: ignore[attr-defined]
    prediction = RiskScore.objects.get(feature_set=feature_set)
    original_prediction_hash = prediction.result_hash
    window_start = snapshot.created_at
    window_end = window_start + timedelta(days=30)
    source_hash = _sha("5")

    with pytest.raises(ModelGovernanceError, match="window completes"):
        ingest_deployment_outcome(
            organization=organization,  # type: ignore[arg-type]
            snapshot=snapshot,
            prediction=prediction,
            outcome=OutcomeKind.HOTFIX,
            source_kind="deployment_system",
            source_event_sha256=source_hash,
            provenance_known=True,
            observation_window_started_at=window_start,
            observation_window_ended_at=window_end,
            signal_observed_at=window_start + timedelta(days=2),
            explicit_learning_opt_in=True,
            ingested_at=window_end - timedelta(seconds=1),
        )

    outcome, created = ingest_deployment_outcome(
        organization=organization,  # type: ignore[arg-type]
        snapshot=snapshot,
        prediction=prediction,
        outcome=OutcomeKind.HOTFIX,
        source_kind="deployment_system",
        source_event_sha256=source_hash,
        provenance_known=True,
        observation_window_started_at=window_start,
        observation_window_ended_at=window_end,
        signal_observed_at=window_start + timedelta(days=2),
        explicit_learning_opt_in=True,
        ingested_at=window_end,
    )
    repeated, repeated_created = ingest_deployment_outcome(
        organization=organization,  # type: ignore[arg-type]
        snapshot=snapshot,
        prediction=prediction,
        outcome=OutcomeKind.HOTFIX,
        source_kind="deployment_system",
        source_event_sha256=source_hash,
        provenance_known=True,
        observation_window_started_at=window_start,
        observation_window_ended_at=window_end,
        signal_observed_at=window_start + timedelta(days=2),
        explicit_learning_opt_in=True,
        ingested_at=window_end + timedelta(days=1),
    )

    prediction.refresh_from_db()
    assert created is True
    assert repeated_created is False
    assert repeated.pk == outcome.pk
    assert outcome.organization_training_eligible is True
    assert outcome.shared_training_eligible is False
    assert outcome.explicit_learning_opt_in is True
    assert outcome.organization_learning_enabled_at_ingest is True
    assert outcome.organization_policy_version == organization.policy_version  # type: ignore[attr-defined]
    assert outcome.ingested_at == window_end
    assert prediction.result_hash == original_prediction_hash
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE risk_deploymentoutcome SET outcome = %s WHERE id = %s",
            ["no_issue", outcome.pk],
        )


def test_drift_record_requires_human_review_and_never_triggers_automation() -> None:
    organization, _repository, _feature_set = _scope(suffix="drift", number=134)
    admin = factories.user(username="m13-drift-admin")
    factories.membership(
        organization=organization,  # type: ignore[arg-type]
        user=admin,
        role=MembershipRole.ADMIN,
    )
    artifact = _register(organization=organization, actor=admin, version="v1", character="6")
    assessment = assess_drift(
        reference=_profile(shifted=False),
        current=_profile(shifted=True),
        policy=DriftPolicy(),
    )

    record, created = record_drift_assessment(
        organization=organization,  # type: ignore[arg-type]
        artifact=artifact,
        assessment=assessment,
    )
    repeated, repeated_created = record_drift_assessment(
        organization=organization,  # type: ignore[arg-type]
        artifact=artifact,
        assessment=assessment,
    )
    review = review_drift_assessment(
        organization=organization,  # type: ignore[arg-type]
        assessment_public_id=record.public_id,
        decision=DriftReviewDecision.APPROVE_EXPERIMENT,
        reason="Investigate only through a separately reviewed retraining experiment.",
        actor=admin,
    )

    assert created is True
    assert repeated_created is False
    assert repeated.pk == record.pk
    assert record.decision == DriftDecision.REVIEW
    assert record.human_review_required is True
    assert record.automatic_retraining_allowed is False
    assert record.automatic_promotion_allowed is False
    assert review.decision == DriftReviewDecision.APPROVE_EXPERIMENT
    with pytest.raises(ModelGovernanceError, match="already_reviewed"):
        review_drift_assessment(
            organization=organization,  # type: ignore[arg-type]
            assessment_public_id=record.public_id,
            decision=DriftReviewDecision.NO_ACTION,
            reason="Duplicate review is forbidden.",
            actor=admin,
        )
