"""Tenant-scoped M13 model, outcome, and drift governance services."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone

from apps.web.audit.services import record_audit
from apps.web.changes.models import PullRequestSnapshot
from apps.web.organizations.models import MembershipRole, Organization
from apps.web.organizations.services import require_minimum_role
from apps.web.risk.models import (
    DeploymentOutcome,
    DriftAssessmentRecord,
    DriftReview,
    DriftReviewDecision,
    GovernedModelArtifact,
    ModelDeployment,
    ModelLifecycleEvent,
    RiskScore,
)
from packages.change_intel import canonical_hash
from packages.ml_core import (
    DriftAssessment,
    GovernanceError,
    LifecycleAction,
    ModelLifecycle,
    OutcomeKind,
    PromotionApproval,
    evaluate_feedback_eligibility,
    validate_model_transition,
)

MINIMUM_OUTCOME_WINDOW_DAYS = 30
MAXIMUM_OUTCOME_WINDOW_DAYS = 365


class ModelGovernanceError(ValueError):
    """A stable rejection at the model-governance boundary."""


@dataclass(frozen=True, slots=True)
class ArtifactRegistration:
    artifact: GovernedModelArtifact
    event: ModelLifecycleEvent
    created: bool


@dataclass(frozen=True, slots=True)
class DeploymentChange:
    deployment: ModelDeployment
    event: ModelLifecycleEvent


def _same_outcome_signal(
    existing: DeploymentOutcome,
    *,
    snapshot: PullRequestSnapshot,
    prediction: RiskScore,
    outcome: OutcomeKind,
    source_kind: str,
    provenance_known: bool,
    explicit_learning_opt_in: bool,
    observation_window_started_at: datetime,
    observation_window_ended_at: datetime,
    signal_observed_at: datetime,
) -> bool:
    return (
        existing.repository_id == snapshot.repository_id
        and existing.snapshot_id == snapshot.id
        and existing.prediction_id == prediction.id
        and existing.outcome == outcome.value
        and existing.source_kind == source_kind
        and existing.provenance_known is provenance_known
        and existing.explicit_learning_opt_in is explicit_learning_opt_in
        and existing.observation_window_started_at == observation_window_started_at
        and existing.observation_window_ended_at == observation_window_ended_at
        and existing.signal_observed_at == signal_observed_at
    )


def _require_model_admin(*, organization: Organization, actor: AbstractBaseUser) -> MembershipRole:
    membership = require_minimum_role(
        user=actor,
        organization=organization,
        minimum_role=MembershipRole.ADMIN,
    )
    return MembershipRole(membership.role)


def _state(artifact: GovernedModelArtifact) -> ModelLifecycle | None:
    event = artifact.lifecycle_events.order_by("-sequence", "-id").first()
    return None if event is None else ModelLifecycle(event.to_state)


def _validate_approval_actor(
    *, approval: PromotionApproval, actor: AbstractBaseUser, role: MembershipRole
) -> None:
    if approval.reviewer_id != f"user:{actor.pk}" or approval.reviewer_role != role.value:
        raise ModelGovernanceError("approval_actor_mismatch")


def _event(
    *,
    artifact: GovernedModelArtifact,
    current: ModelLifecycle | None,
    target: ModelLifecycle,
    action: LifecycleAction,
    actor: AbstractBaseUser,
    reason: str,
    approval: PromotionApproval | None,
) -> ModelLifecycleEvent:
    validate_model_transition(
        current=current,
        target=target,
        action=action,
        approval=approval,
    )
    if approval is not None and approval.artifact_sha256 != artifact.artifact_sha256:
        raise ModelGovernanceError("approval_artifact_mismatch")
    if approval is not None and approval.reason != reason:
        raise ModelGovernanceError("approval_reason_mismatch")
    latest = artifact.lifecycle_events.order_by("-sequence", "-id").first()
    sequence = 1 if latest is None else latest.sequence + 1
    compatibility = {} if approval is None else dict(sorted(approval.compatibility.checks.items()))
    event_payload = {
        "action": action.value,
        "actor_id": actor.pk,
        "artifact_sha256": artifact.artifact_sha256,
        "compatibility_sha256": "" if approval is None else approval.compatibility.report_sha256,
        "evaluation_sha256": "" if approval is None else approval.evaluation_sha256,
        "from_state": None if current is None else current.value,
        "policy_version": "model-lifecycle-v1",
        "approval_sha256": "" if approval is None else approval.approval_sha256,
        "reviewer_role": "" if approval is None else approval.reviewer_role,
        "reason": reason,
        "sequence": sequence,
        "to_state": target.value,
    }
    event = ModelLifecycleEvent(
        organization=artifact.organization,
        artifact=artifact,
        sequence=sequence,
        from_state=None if current is None else current.value,
        to_state=target.value,
        action=action.value,
        evaluation_sha256="" if approval is None else approval.evaluation_sha256,
        compatibility=compatibility,
        compatibility_sha256="" if approval is None else approval.compatibility.report_sha256,
        reviewer_role="" if approval is None else approval.reviewer_role,
        approval_sha256="" if approval is None else approval.approval_sha256,
        reason=reason,
        actor_id=actor.pk,
        event_sha256=canonical_hash(event_payload),
    )
    event.full_clean()
    event.save()
    return event


def register_model_artifact(
    *,
    organization: Organization,
    actor: AbstractBaseUser,
    model_name: str,
    artifact_version: str,
    artifact_sha256: str,
    artifact_uri: str,
    algorithm: str,
    formal_experiment_sha256: str,
    mlflow_run_id: str,
    dataset_version: str,
    dataset_manifest_sha256: str,
    feature_schema_version: str,
    input_schema_sha256: str,
    runtime_compatibility: dict[str, str],
    synthetic: bool,
    contains_customer_data: bool,
) -> ArtifactRegistration:
    _require_model_admin(organization=organization, actor=actor)
    existing = (
        GovernedModelArtifact.objects.for_organization(organization)
        .filter(model_name=model_name, artifact_version=artifact_version)
        .first()
    )
    if existing is not None:
        expected = {
            "algorithm": algorithm,
            "artifact_sha256": artifact_sha256,
            "artifact_uri": artifact_uri,
            "contains_customer_data": contains_customer_data,
            "dataset_manifest_sha256": dataset_manifest_sha256,
            "dataset_version": dataset_version,
            "feature_schema_version": feature_schema_version,
            "formal_experiment_sha256": formal_experiment_sha256,
            "input_schema_sha256": input_schema_sha256,
            "mlflow_run_id": mlflow_run_id,
            "runtime_compatibility": runtime_compatibility,
            "synthetic": synthetic,
        }
        actual = {field: getattr(existing, field) for field in expected}
        if actual != expected:
            raise ModelGovernanceError("artifact_version_identity_conflict")
        event = existing.lifecycle_events.order_by("sequence", "id").first()
        if event is None:
            raise ModelGovernanceError("artifact_registration_event_missing")
        return ArtifactRegistration(existing, event, False)
    correlation_id = uuid.uuid4()
    try:
        with transaction.atomic():
            artifact = GovernedModelArtifact(
                organization=organization,
                model_name=model_name,
                artifact_version=artifact_version,
                artifact_sha256=artifact_sha256,
                artifact_uri=artifact_uri,
                algorithm=algorithm,
                formal_experiment_sha256=formal_experiment_sha256,
                mlflow_run_id=mlflow_run_id,
                dataset_version=dataset_version,
                dataset_manifest_sha256=dataset_manifest_sha256,
                feature_schema_version=feature_schema_version,
                input_schema_sha256=input_schema_sha256,
                runtime_compatibility=runtime_compatibility,
                synthetic=synthetic,
                contains_customer_data=contains_customer_data,
                created_by_id=actor.pk,
            )
            artifact.full_clean()
            artifact.save()
            event = _event(
                artifact=artifact,
                current=None,
                target=ModelLifecycle.CANDIDATE,
                action=LifecycleAction.REGISTER,
                actor=actor,
                reason="Registered exact immutable artifact as a candidate.",
                approval=None,
            )
            record_audit(
                organization=organization,
                action="risk.model_artifact.registered",
                resource_type="governed_model_artifact",
                resource_public_id=artifact.public_id,
                correlation_id=correlation_id,
                actor=actor,
                metadata={
                    "artifact_sha256": artifact.artifact_sha256,
                    "artifact_version": artifact.artifact_version,
                    "model_name": artifact.model_name,
                },
            )
            return ArtifactRegistration(artifact, event, True)
    except IntegrityError as error:
        raise ModelGovernanceError("artifact_registration_conflict") from error


def promote_model_to_staging(
    *,
    organization: Organization,
    artifact_public_id: uuid.UUID,
    approval: PromotionApproval,
    actor: AbstractBaseUser,
) -> ModelLifecycleEvent:
    role = _require_model_admin(organization=organization, actor=actor)
    _validate_approval_actor(approval=approval, actor=actor, role=role)
    with transaction.atomic():
        artifact = (
            GovernedModelArtifact.objects.select_for_update()
            .for_organization(organization)
            .filter(public_id=artifact_public_id)
            .first()
        )
        if artifact is None:
            raise Http404("model artifact not found")
        event = _event(
            artifact=artifact,
            current=_state(artifact),
            target=ModelLifecycle.STAGING,
            action=LifecycleAction.PROMOTE_TO_STAGING,
            actor=actor,
            reason=approval.reason,
            approval=approval,
        )
        record_audit(
            organization=organization,
            action="risk.model_artifact.staged",
            resource_type="governed_model_artifact",
            resource_public_id=artifact.public_id,
            correlation_id=uuid.uuid4(),
            actor=actor,
            metadata={"artifact_version": artifact.artifact_version, "event": event.event_sha256},
        )
        return event


def activate_model(
    *,
    organization: Organization,
    artifact_public_id: uuid.UUID,
    approval: PromotionApproval,
    actor: AbstractBaseUser,
    retirement_approval: PromotionApproval | None = None,
) -> DeploymentChange:
    role = _require_model_admin(organization=organization, actor=actor)
    _validate_approval_actor(approval=approval, actor=actor, role=role)
    with transaction.atomic():
        artifact = (
            GovernedModelArtifact.objects.select_for_update()
            .for_organization(organization)
            .filter(public_id=artifact_public_id)
            .first()
        )
        if artifact is None:
            raise Http404("model artifact not found")
        deployment = (
            ModelDeployment.objects.select_for_update()
            .filter(organization=organization, model_name=artifact.model_name)
            .first()
        )
        previous = None if deployment is None else deployment.active_artifact
        if previous is not None:
            if previous.pk == artifact.pk:
                raise ModelGovernanceError("artifact_already_active")
            if retirement_approval is None:
                raise ModelGovernanceError("replacement_retirement_approval_required")
            _validate_approval_actor(
                approval=retirement_approval,
                actor=actor,
                role=role,
            )
            _event(
                artifact=previous,
                current=_state(previous),
                target=ModelLifecycle.RETIRED,
                action=LifecycleAction.RETIRE,
                actor=actor,
                reason=retirement_approval.reason,
                approval=retirement_approval,
            )
        activation = _event(
            artifact=artifact,
            current=_state(artifact),
            target=ModelLifecycle.ACTIVE,
            action=LifecycleAction.ACTIVATE,
            actor=actor,
            reason=approval.reason,
            approval=approval,
        )
        if deployment is None:
            deployment = ModelDeployment(
                organization=organization,
                model_name=artifact.model_name,
                active_artifact=artifact,
                rollback_artifact=None,
                generation=1,
            )
        else:
            deployment.rollback_artifact = previous
            deployment.active_artifact = artifact
            deployment.generation += 1
        deployment.full_clean()
        deployment.save()
        record_audit(
            organization=organization,
            action="risk.model_artifact.activated",
            resource_type="governed_model_artifact",
            resource_public_id=artifact.public_id,
            correlation_id=uuid.uuid4(),
            actor=actor,
            metadata={
                "artifact_version": artifact.artifact_version,
                "event": activation.event_sha256,
                "generation": deployment.generation,
            },
        )
        return DeploymentChange(deployment, activation)


def rollback_model(
    *,
    organization: Organization,
    model_name: str,
    approval: PromotionApproval,
    retirement_approval: PromotionApproval,
    actor: AbstractBaseUser,
) -> DeploymentChange:
    role = _require_model_admin(organization=organization, actor=actor)
    _validate_approval_actor(approval=approval, actor=actor, role=role)
    _validate_approval_actor(approval=retirement_approval, actor=actor, role=role)
    with transaction.atomic():
        deployment = (
            ModelDeployment.objects.select_for_update()
            .filter(organization=organization, model_name=model_name)
            .select_related("active_artifact", "rollback_artifact")
            .first()
        )
        if deployment is None or deployment.rollback_artifact is None:
            raise ModelGovernanceError("rollback_artifact_unavailable")
        current = deployment.active_artifact
        rollback = deployment.rollback_artifact
        _event(
            artifact=current,
            current=_state(current),
            target=ModelLifecycle.RETIRED,
            action=LifecycleAction.RETIRE,
            actor=actor,
            reason=retirement_approval.reason,
            approval=retirement_approval,
        )
        rollback_event = _event(
            artifact=rollback,
            current=_state(rollback),
            target=ModelLifecycle.ACTIVE,
            action=LifecycleAction.ROLLBACK,
            actor=actor,
            reason=approval.reason,
            approval=approval,
        )
        deployment.active_artifact = rollback
        deployment.rollback_artifact = current
        deployment.generation += 1
        deployment.full_clean()
        deployment.save()
        record_audit(
            organization=organization,
            action="risk.model_artifact.rolled_back",
            resource_type="governed_model_artifact",
            resource_public_id=rollback.public_id,
            correlation_id=uuid.uuid4(),
            actor=actor,
            metadata={
                "artifact_version": rollback.artifact_version,
                "event": rollback_event.event_sha256,
                "generation": deployment.generation,
            },
        )
        return DeploymentChange(deployment, rollback_event)


def ingest_deployment_outcome(
    *,
    organization: Organization,
    snapshot: PullRequestSnapshot,
    prediction: RiskScore,
    outcome: OutcomeKind,
    source_kind: str,
    source_event_sha256: str,
    provenance_known: bool,
    observation_window_started_at: datetime,
    observation_window_ended_at: datetime,
    signal_observed_at: datetime,
    explicit_learning_opt_in: bool,
    ingested_at: datetime | None = None,
) -> tuple[DeploymentOutcome, bool]:
    if snapshot.organization_id != organization.id or prediction.organization_id != organization.id:
        raise ModelGovernanceError("outcome_lineage_unavailable")
    if prediction.snapshot_id != snapshot.id:
        raise ModelGovernanceError("outcome_prediction_snapshot_mismatch")
    existing = (
        DeploymentOutcome.objects.for_organization(organization)
        .filter(source_event_sha256=source_event_sha256)
        .first()
    )
    if existing is not None:
        same_signal = _same_outcome_signal(
            existing,
            snapshot=snapshot,
            prediction=prediction,
            outcome=outcome,
            source_kind=source_kind,
            provenance_known=provenance_known,
            explicit_learning_opt_in=explicit_learning_opt_in,
            observation_window_started_at=observation_window_started_at,
            observation_window_ended_at=observation_window_ended_at,
            signal_observed_at=signal_observed_at,
        )
        if not same_signal:
            raise ModelGovernanceError("outcome_idempotency_conflict")
        return existing, False
    duration = observation_window_ended_at - observation_window_started_at
    if not (
        timedelta(days=MINIMUM_OUTCOME_WINDOW_DAYS)
        <= duration
        <= timedelta(days=MAXIMUM_OUTCOME_WINDOW_DAYS)
    ):
        raise ModelGovernanceError("outcome_window_duration_invalid")
    recorded_at = ingested_at or timezone.now()
    try:
        eligibility = evaluate_feedback_eligibility(
            snapshot_created_at=snapshot.created_at,
            observation_window_started_at=observation_window_started_at,
            observation_window_ended_at=observation_window_ended_at,
            signal_observed_at=signal_observed_at,
            ingested_at=recorded_at,
            outcome=outcome,
            provenance_known=provenance_known,
            organization_learning_enabled=organization.organization_learning_enabled,
            explicit_learning_opt_in=explicit_learning_opt_in,
        )
    except GovernanceError as error:
        raise ModelGovernanceError(str(error)) from error
    payload = {
        "eligibility_reason": eligibility.reason,
        "explicit_learning_opt_in": explicit_learning_opt_in,
        "ingested_at": recorded_at.isoformat(),
        "organization_learning_enabled_at_ingest": (organization.organization_learning_enabled),
        "organization_policy_version": organization.policy_version,
        "organization_training_eligible": eligibility.organization_training_eligible,
        "outcome": outcome.value,
        "prediction_result_sha256": prediction.result_hash,
        "provenance_known": provenance_known,
        "schema_version": "deployment-outcome-v1",
        "signal_observed_at": signal_observed_at.isoformat(),
        "source_event_sha256": source_event_sha256,
        "source_kind": source_kind,
        "window_ended_at": observation_window_ended_at.isoformat(),
        "window_started_at": observation_window_started_at.isoformat(),
    }
    record_hash = canonical_hash(payload)
    try:
        with transaction.atomic():
            record = DeploymentOutcome(
                organization=organization,
                repository=snapshot.repository,
                snapshot=snapshot,
                prediction=prediction,
                outcome=outcome.value,
                source_kind=source_kind,
                source_event_sha256=source_event_sha256,
                provenance_known=provenance_known,
                explicit_learning_opt_in=explicit_learning_opt_in,
                organization_learning_enabled_at_ingest=(
                    organization.organization_learning_enabled
                ),
                organization_policy_version=organization.policy_version,
                observation_window_started_at=observation_window_started_at,
                observation_window_ended_at=observation_window_ended_at,
                signal_observed_at=signal_observed_at,
                ingested_at=recorded_at,
                organization_training_eligible=eligibility.organization_training_eligible,
                shared_training_eligible=False,
                eligibility_reason=eligibility.reason,
                record_sha256=record_hash,
            )
            record.full_clean()
            record.save()
            record_audit(
                organization=organization,
                action="risk.deployment_outcome.recorded",
                resource_type="deployment_outcome",
                resource_public_id=record.public_id,
                correlation_id=uuid.uuid4(),
                metadata={
                    "eligible": eligibility.organization_training_eligible,
                    "outcome": outcome.value,
                    "provenance_known": provenance_known,
                },
            )
            return record, True
    except IntegrityError as error:
        duplicate = (
            DeploymentOutcome.objects.for_organization(organization)
            .filter(source_event_sha256=source_event_sha256)
            .first()
        )
        if duplicate is not None and _same_outcome_signal(
            duplicate,
            snapshot=snapshot,
            prediction=prediction,
            outcome=outcome,
            source_kind=source_kind,
            provenance_known=provenance_known,
            explicit_learning_opt_in=explicit_learning_opt_in,
            observation_window_started_at=observation_window_started_at,
            observation_window_ended_at=observation_window_ended_at,
            signal_observed_at=signal_observed_at,
        ):
            return duplicate, False
        raise ModelGovernanceError("outcome_ingestion_conflict") from error


def record_drift_assessment(
    *,
    organization: Organization,
    artifact: GovernedModelArtifact,
    assessment: DriftAssessment,
) -> tuple[DriftAssessmentRecord, bool]:
    if artifact.organization_id != organization.id:
        raise ModelGovernanceError("drift_artifact_unavailable")
    existing = (
        DriftAssessmentRecord.objects.for_organization(organization)
        .filter(
            artifact=artifact,
            current_profile_sha256=assessment.current_profile_sha256,
            policy_version=assessment.policy.version,
        )
        .first()
    )
    if existing is not None:
        if existing.assessment_sha256 != assessment.assessment_sha256:
            raise ModelGovernanceError("drift_idempotency_conflict")
        return existing, False
    record = DriftAssessmentRecord(
        organization=organization,
        artifact=artifact,
        policy_version=assessment.policy.version,
        reference_profile_sha256=assessment.reference_profile_sha256,
        current_profile_sha256=assessment.current_profile_sha256,
        decision=assessment.decision.value,
        row_count=assessment.row_count,
        report=assessment.as_dict(),
        assessment_sha256=assessment.assessment_sha256,
        human_review_required=assessment.human_review_required,
        automatic_retraining_allowed=False,
        automatic_promotion_allowed=False,
    )
    record.full_clean()
    record.save()
    return record, True


def review_drift_assessment(
    *,
    organization: Organization,
    assessment_public_id: uuid.UUID,
    decision: DriftReviewDecision,
    reason: str,
    actor: AbstractBaseUser,
) -> DriftReview:
    require_minimum_role(
        user=actor,
        organization=organization,
        minimum_role=MembershipRole.REVIEWER,
    )
    if not 1 <= len(reason) <= 1_000:
        raise ModelGovernanceError("drift_review_reason_invalid")
    with transaction.atomic():
        assessment = (
            DriftAssessmentRecord.objects.for_organization(organization)
            .select_for_update()
            .filter(public_id=assessment_public_id)
            .first()
        )
        if assessment is None:
            raise Http404("drift assessment not found")
        if hasattr(assessment, "review"):
            raise ModelGovernanceError("drift_assessment_already_reviewed")
        review = DriftReview(
            organization=organization,
            assessment=assessment,
            decision=decision,
            reason=reason,
            actor_id=actor.pk,
        )
        review.full_clean()
        review.save()
        record_audit(
            organization=organization,
            action="risk.drift_assessment.reviewed",
            resource_type="drift_assessment",
            resource_public_id=assessment.public_id,
            correlation_id=uuid.uuid4(),
            actor=actor,
            metadata={"decision": decision.value},
        )
        return review
