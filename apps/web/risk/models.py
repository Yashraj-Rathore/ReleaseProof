"""Append-only, tenant-bound deterministic and later learned risk scores."""

from __future__ import annotations

import math
import uuid
from datetime import timedelta
from typing import Any, NoReturn
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.web.changes.models import (
    ChangeFeatureSet,
    ImmutableQuerySet,
    PullRequestSnapshot,
    validate_checksum,
)
from apps.web.organizations.models import MembershipRole, Organization
from apps.web.repositories.models import Repository
from packages.change_intel import canonical_hash
from packages.ml_core import (
    DEPLOYMENT_OUTCOME_SCHEMA_VERSION,
    DRIFT_ASSESSMENT_SCHEMA_VERSION,
    DRIFT_POLICY_VERSION,
    MODEL_ARTIFACT_SCHEMA_VERSION,
    MODEL_LIFECYCLE_POLICY_VERSION,
    DriftDecision,
    LifecycleAction,
    ModelLifecycle,
    OutcomeKind,
    RiskBand,
)


def validate_contributions(value: Any) -> None:
    if not isinstance(value, list) or len(value) > 32:
        raise ValidationError("baseline contributions must be a bounded list")
    for item in value:
        if not isinstance(item, dict) or set(item) != {
            "points",
            "reason",
            "rule_id",
            "source_features",
        }:
            raise ValidationError("baseline contribution schema is invalid")
        if (
            isinstance(item["points"], bool)
            or not isinstance(item["points"], int)
            or item["points"] < 0
            or item["points"] > 100
        ):
            raise ValidationError("baseline contribution points are invalid")
        if not isinstance(item["rule_id"], str) or not 1 <= len(item["rule_id"]) <= 160:
            raise ValidationError("baseline contribution rule ID is invalid")
        if not isinstance(item["reason"], str) or not 1 <= len(item["reason"]) <= 512:
            raise ValidationError("baseline contribution reason is invalid")
        features = item["source_features"]
        if (
            not isinstance(features, list)
            or len(features) > 16
            or not all(
                isinstance(feature, str) and 1 <= len(feature) <= 128 for feature in features
            )
        ):
            raise ValidationError("baseline contribution source features are invalid")


def validate_missing_required(value: Any) -> None:
    if (
        not isinstance(value, list)
        or len(value) > 64
        or not all(isinstance(item, str) and 1 <= len(item) <= 128 for item in value)
    ):
        raise ValidationError("missing required features must be a bounded string list")


class RiskScoreQuerySet(ImmutableQuerySet["RiskScore"]):
    def for_organization(self, organization: Organization | int) -> RiskScoreQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)


class RiskScore(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="risk_scores",
    )
    snapshot = models.ForeignKey(
        PullRequestSnapshot,
        on_delete=models.PROTECT,
        related_name="risk_scores",
    )
    feature_set = models.ForeignKey(
        ChangeFeatureSet,
        on_delete=models.PROTECT,
        related_name="risk_scores",
    )
    schema_version = models.CharField(max_length=64)
    artifact_version = models.CharField(max_length=64)
    artifact_hash = models.CharField(max_length=64, validators=[validate_checksum])
    feature_schema_version = models.CharField(max_length=64)
    threshold_policy_version = models.CharField(max_length=64)
    threshold = models.PositiveSmallIntegerField()
    raw_score = models.PositiveSmallIntegerField(null=True, blank=True)
    calibrated_probability = models.FloatField(null=True, blank=True)
    band = models.CharField(max_length=16, choices=[(item.value, item.value) for item in RiskBand])
    proxy_prediction = models.BooleanField(null=True, blank=True)
    contributions = models.JSONField(
        default=list,
        blank=True,
        validators=[validate_contributions],
    )
    missing_required = models.JSONField(
        default=list,
        blank=True,
        validators=[validate_missing_required],
    )
    result_hash = models.CharField(max_length=64, validators=[validate_checksum])
    created_at = models.DateTimeField(auto_now_add=True)

    objects = RiskScoreQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"),
                name="risk_score_org_id_unique",
            ),
            models.UniqueConstraint(
                fields=("id", "snapshot"),
                name="risk_score_id_snapshot_unique",
            ),
            models.UniqueConstraint(
                fields=(
                    "feature_set",
                    "artifact_version",
                    "artifact_hash",
                    "threshold_policy_version",
                ),
                name="risk_score_feature_artifact_unique",
            ),
        ]
        ordering = ("-created_at", "-id")

    def clean(self) -> None:
        super().clean()
        if self.calibrated_probability is not None:
            raise ValidationError("deterministic baseline scores cannot contain a probability")
        if self.threshold > 100:
            raise ValidationError("risk threshold must be between 0 and 100")
        if self.raw_score is not None and self.raw_score > 100:
            raise ValidationError("raw score must be between 0 and 100")
        if self.band == RiskBand.UNKNOWN:
            if self.raw_score is not None or self.proxy_prediction is not None:
                raise ValidationError("UNKNOWN scores cannot contain a numeric prediction")
        elif self.raw_score is None or self.proxy_prediction is None:
            raise ValidationError("known risk bands require a score and proxy prediction")
        if self.organization_id is None or self.snapshot_id is None or self.feature_set_id is None:
            return
        if self.snapshot.organization_id != self.organization_id:
            raise ValidationError("risk score and snapshot must share an organization")
        if self.feature_set.organization_id != self.organization_id:
            raise ValidationError("risk score and feature set must share an organization")
        if self.feature_set.snapshot_id != self.snapshot_id:
            raise ValidationError("risk score must reference its feature set snapshot")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("risk scores are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("risk scores are immutable")


def validate_safe_string_mapping(value: Any) -> None:
    if not isinstance(value, dict) or not 1 <= len(value) <= 64:
        raise ValidationError("runtime compatibility must be a bounded object")
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or not 1 <= len(key) <= 128
            or not key.isascii()
            or not isinstance(item, (str, int, float, bool))
            or (isinstance(item, float) and not math.isfinite(item))
            or (isinstance(item, str) and (not 1 <= len(item) <= 512 or not item.isascii()))
        ):
            raise ValidationError("runtime compatibility contains an invalid value")


def validate_compatibility_report(value: Any) -> None:
    required = {
        "artifact_checksum",
        "evaluation_gate",
        "feature_schema",
        "input_schema",
        "privacy_license",
        "runtime",
    }
    if (
        not isinstance(value, dict)
        or set(value) != required
        or not all(isinstance(item, bool) for item in value.values())
    ):
        raise ValidationError("compatibility report must contain the exact boolean checks")


def validate_drift_report(value: Any) -> None:
    required = {
        "automatic_promotion_allowed",
        "automatic_retraining_allowed",
        "current_profile_sha256",
        "decision",
        "human_review_required",
        "missingness_delta",
        "policy",
        "population_stability_index",
        "performance_drop",
        "reason_codes",
        "reference_profile_sha256",
        "row_count",
        "schema_match",
        "schema_version",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValidationError("drift report has an invalid shape")
    if (
        value["automatic_promotion_allowed"] is not False
        or value["automatic_retraining_allowed"] is not False
    ):
        raise ValidationError("drift reports cannot authorize retraining or promotion")
    if value["schema_version"] != DRIFT_ASSESSMENT_SCHEMA_VERSION:
        raise ValidationError("drift report schema is unsupported")
    if value["decision"] not in {item.value for item in DriftDecision}:
        raise ValidationError("drift report decision is invalid")
    if not isinstance(value["schema_match"], bool) or not isinstance(
        value["human_review_required"], bool
    ):
        raise ValidationError("drift report boolean fields are invalid")
    if value["human_review_required"] != (value["decision"] != DriftDecision.PASS):
        raise ValidationError("drift report review requirement disagrees with its decision")
    if (
        isinstance(value["row_count"], bool)
        or not isinstance(value["row_count"], int)
        or value["row_count"] < 1
    ):
        raise ValidationError("drift report row count is invalid")
    reason_codes = value["reason_codes"]
    if (
        not isinstance(reason_codes, list)
        or len(reason_codes) > 16
        or not all(
            isinstance(item, str) and 1 <= len(item) <= 128 and item.isascii()
            for item in reason_codes
        )
    ):
        raise ValidationError("drift report reason codes are invalid")
    for field in ("missingness_delta", "population_stability_index"):
        metrics = value[field]
        if not isinstance(metrics, dict) or len(metrics) > 256:
            raise ValidationError("drift report feature metrics are invalid")
        if not all(
            isinstance(key, str)
            and 1 <= len(key) <= 128
            and key.isascii()
            and not isinstance(item, bool)
            and isinstance(item, (int, float))
            and math.isfinite(item)
            for key, item in metrics.items()
        ):
            raise ValidationError("drift report feature metrics are invalid")
    performance_drop = value["performance_drop"]
    if performance_drop is not None and (
        isinstance(performance_drop, bool)
        or not isinstance(performance_drop, (int, float))
        or not math.isfinite(performance_drop)
    ):
        raise ValidationError("drift report performance value is invalid")
    policy = value["policy"]
    if not isinstance(policy, dict) or set(policy) != {
        "maximum_missingness_delta",
        "maximum_performance_drop",
        "maximum_population_stability_index",
        "minimum_labeled_rows",
        "minimum_rows",
        "version",
    }:
        raise ValidationError("drift report policy shape is invalid")
    if policy["version"] != DRIFT_POLICY_VERSION:
        raise ValidationError("drift report policy version is invalid")
    for field in ("minimum_labeled_rows", "minimum_rows"):
        if (
            isinstance(policy[field], bool)
            or not isinstance(policy[field], int)
            or policy[field] < 2
        ):
            raise ValidationError("drift report policy sample minimum is invalid")
    for field in (
        "maximum_missingness_delta",
        "maximum_performance_drop",
        "maximum_population_stability_index",
    ):
        item = policy[field]
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(item)
            or item < 0
        ):
            raise ValidationError("drift report policy threshold is invalid")
    for field in ("reference_profile_sha256", "current_profile_sha256"):
        if not isinstance(value[field], str):
            raise ValidationError("drift profile checksum is invalid")
        validate_checksum(value[field])


class GovernedModelArtifactQuerySet(ImmutableQuerySet["GovernedModelArtifact"]):
    def for_organization(self, organization: Organization | int) -> GovernedModelArtifactQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)


class GovernedModelArtifact(models.Model):
    """An immutable tenant registry record for one exact artifact checksum."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="governed_model_artifacts"
    )
    schema_version = models.CharField(max_length=64, default=MODEL_ARTIFACT_SCHEMA_VERSION)
    model_name = models.CharField(max_length=128)
    artifact_version = models.CharField(max_length=128)
    artifact_sha256 = models.CharField(max_length=64, validators=[validate_checksum])
    artifact_uri = models.CharField(max_length=1_024)
    algorithm = models.CharField(max_length=128)
    formal_experiment_sha256 = models.CharField(max_length=64, validators=[validate_checksum])
    mlflow_run_id = models.CharField(max_length=64)
    dataset_version = models.CharField(max_length=128)
    dataset_manifest_sha256 = models.CharField(max_length=64, validators=[validate_checksum])
    feature_schema_version = models.CharField(max_length=128)
    input_schema_sha256 = models.CharField(max_length=64, validators=[validate_checksum])
    runtime_compatibility = models.JSONField(validators=[validate_safe_string_mapping])
    synthetic = models.BooleanField(default=False)
    contains_customer_data = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="governed_model_artifacts_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = GovernedModelArtifactQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"), name="risk_model_artifact_org_id_unique"
            ),
            models.UniqueConstraint(
                fields=("organization", "model_name", "artifact_version"),
                name="risk_model_artifact_org_name_version_unique",
            ),
            models.UniqueConstraint(
                fields=("organization", "model_name", "artifact_sha256"),
                name="risk_model_artifact_org_name_hash_unique",
            ),
            models.UniqueConstraint(
                fields=("organization", "model_name", "id"),
                name="risk_model_artifact_org_name_id_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(schema_version=MODEL_ARTIFACT_SCHEMA_VERSION),
                name="risk_model_artifact_schema_v1",
            ),
        ]
        ordering = ("organization_id", "model_name", "created_at", "id")

    def clean(self) -> None:
        super().clean()
        parsed = urlparse(self.artifact_uri)
        if parsed.scheme not in {"artifact", "s3", "mlflow-artifacts"}:
            raise ValidationError("model artifact URI scheme is not allowlisted")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValidationError(
                "model artifact URI cannot contain credentials, query, or fragment"
            )
        if self.synthetic and self.contains_customer_data:
            raise ValidationError("synthetic model artifacts cannot contain customer data")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("governed model artifacts are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("governed model artifacts are immutable")


class ModelLifecycleEventQuerySet(ImmutableQuerySet["ModelLifecycleEvent"]):
    def for_organization(self, organization: Organization | int) -> ModelLifecycleEventQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)


class ModelLifecycleEvent(models.Model):
    """Append-only lifecycle evidence; approval is evidence, not a lifecycle state."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="model_lifecycle_events"
    )
    artifact = models.ForeignKey(
        GovernedModelArtifact, on_delete=models.PROTECT, related_name="lifecycle_events"
    )
    sequence = models.PositiveIntegerField()
    policy_version = models.CharField(max_length=64, default=MODEL_LIFECYCLE_POLICY_VERSION)
    from_state = models.CharField(
        max_length=16,
        choices=[(item.value, item.value) for item in ModelLifecycle],
        null=True,
        blank=True,
    )
    to_state = models.CharField(
        max_length=16, choices=[(item.value, item.value) for item in ModelLifecycle]
    )
    action = models.CharField(
        max_length=32, choices=[(item.value, item.value) for item in LifecycleAction]
    )
    evaluation_sha256 = models.CharField(max_length=64, blank=True, validators=[validate_checksum])
    compatibility = models.JSONField(default=dict, blank=True)
    compatibility_sha256 = models.CharField(
        max_length=64, blank=True, validators=[validate_checksum]
    )
    reviewer_role = models.CharField(
        max_length=16,
        blank=True,
        choices=[
            (MembershipRole.OWNER.value, MembershipRole.OWNER.label),
            (MembershipRole.ADMIN.value, MembershipRole.ADMIN.label),
        ],
    )
    approval_sha256 = models.CharField(max_length=64, blank=True, validators=[validate_checksum])
    reason = models.CharField(max_length=1_000)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="model_lifecycle_events",
    )
    event_sha256 = models.CharField(max_length=64, validators=[validate_checksum])
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ModelLifecycleEventQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"), name="risk_model_event_org_id_unique"
            ),
            models.UniqueConstraint(
                fields=("artifact", "sequence"), name="risk_model_event_artifact_sequence_unique"
            ),
            models.UniqueConstraint(
                fields=("artifact", "event_sha256"), name="risk_model_event_artifact_hash_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(policy_version=MODEL_LIFECYCLE_POLICY_VERSION),
                name="risk_model_event_policy_v1",
            ),
        ]
        ordering = ("artifact_id", "sequence", "id")

    def clean(self) -> None:
        super().clean()
        if (
            self.organization_id
            and self.artifact_id
            and self.artifact.organization_id != self.organization_id
        ):
            raise ValidationError("model lifecycle event and artifact must share an organization")
        if self.action == LifecycleAction.REGISTER:
            if (
                self.from_state is not None
                or self.evaluation_sha256
                or self.compatibility
                or self.compatibility_sha256
                or self.reviewer_role
                or self.approval_sha256
            ):
                raise ValidationError("candidate registration cannot contain promotion approval")
        else:
            if (
                not self.evaluation_sha256
                or not self.compatibility_sha256
                or not self.reviewer_role
                or not self.approval_sha256
            ):
                raise ValidationError("model transition requires approval evidence")
            validate_compatibility_report(self.compatibility)
            if not all(self.compatibility.values()):
                raise ValidationError("model transition compatibility checks must pass")
            if self.compatibility_sha256 != canonical_hash(
                dict(sorted(self.compatibility.items()))
            ):
                raise ValidationError("model compatibility checksum is invalid")
            approval_payload = {
                "approved_action": self.action,
                "artifact_sha256": self.artifact.artifact_sha256,
                "compatibility": {
                    "checks": dict(sorted(self.compatibility.items())),
                    "passed": True,
                    "report_sha256": self.compatibility_sha256,
                },
                "evaluation_sha256": self.evaluation_sha256,
                "reason": self.reason,
                "reviewer_id": f"user:{self.actor_id}",
                "reviewer_role": self.reviewer_role,
            }
            if self.approval_sha256 != canonical_hash(approval_payload):
                raise ValidationError("model transition approval checksum is invalid")
        event_payload = {
            "action": self.action,
            "actor_id": self.actor_id,
            "approval_sha256": self.approval_sha256,
            "artifact_sha256": self.artifact.artifact_sha256,
            "compatibility_sha256": self.compatibility_sha256,
            "evaluation_sha256": self.evaluation_sha256,
            "from_state": self.from_state,
            "policy_version": self.policy_version,
            "reason": self.reason,
            "reviewer_role": self.reviewer_role,
            "sequence": self.sequence,
            "to_state": self.to_state,
        }
        if self.event_sha256 != canonical_hash(event_payload):
            raise ValidationError("model lifecycle event checksum is invalid")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("model lifecycle events are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("model lifecycle events are immutable")


class ModelDeployment(models.Model):
    """The transactionally updated active/rollback pointer; events preserve history."""

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="model_deployments"
    )
    model_name = models.CharField(max_length=128)
    active_artifact = models.ForeignKey(
        GovernedModelArtifact,
        on_delete=models.PROTECT,
        related_name="active_deployments",
    )
    rollback_artifact = models.ForeignKey(
        GovernedModelArtifact,
        on_delete=models.PROTECT,
        related_name="rollback_deployments",
        null=True,
        blank=True,
    )
    generation = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager["ModelDeployment"]()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"), name="risk_model_deployment_org_id_unique"
            ),
            models.UniqueConstraint(
                fields=("organization", "model_name"), name="risk_model_deployment_org_name_unique"
            ),
        ]
        ordering = ("organization_id", "model_name")

    def clean(self) -> None:
        super().clean()
        for artifact in (self.active_artifact, self.rollback_artifact):
            if artifact is not None and (
                artifact.organization_id != self.organization_id
                or artifact.model_name != self.model_name
            ):
                raise ValidationError("model deployment artifacts must share tenant and model name")
        if self.rollback_artifact_id == self.active_artifact_id:
            raise ValidationError("active and rollback artifacts must differ")


class DeploymentOutcomeQuerySet(ImmutableQuerySet["DeploymentOutcome"]):
    def for_organization(self, organization: Organization | int) -> DeploymentOutcomeQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)


class DeploymentOutcome(models.Model):
    """A delayed append-only outcome linked to, never replacing, prediction evidence."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="deployment_outcomes"
    )
    repository = models.ForeignKey(
        Repository, on_delete=models.PROTECT, related_name="deployment_outcomes"
    )
    snapshot = models.ForeignKey(
        PullRequestSnapshot, on_delete=models.PROTECT, related_name="deployment_outcomes"
    )
    prediction = models.ForeignKey(
        RiskScore, on_delete=models.PROTECT, related_name="deployment_outcomes"
    )
    schema_version = models.CharField(max_length=64, default=DEPLOYMENT_OUTCOME_SCHEMA_VERSION)
    outcome = models.CharField(
        max_length=32, choices=[(item.value, item.value) for item in OutcomeKind]
    )
    source_kind = models.CharField(
        max_length=32,
        choices=[
            ("deployment_system", "deployment_system"),
            ("incident_system", "incident_system"),
            ("manual_review", "manual_review"),
            ("repository_event", "repository_event"),
        ],
    )
    source_event_sha256 = models.CharField(max_length=64, validators=[validate_checksum])
    provenance_known = models.BooleanField(default=False)
    explicit_learning_opt_in = models.BooleanField(default=False)
    organization_learning_enabled_at_ingest = models.BooleanField(default=False)
    organization_policy_version = models.PositiveIntegerField()
    observation_window_started_at = models.DateTimeField()
    observation_window_ended_at = models.DateTimeField()
    signal_observed_at = models.DateTimeField()
    ingested_at = models.DateTimeField()
    organization_training_eligible = models.BooleanField(default=False)
    shared_training_eligible = models.BooleanField(default=False, editable=False)
    eligibility_reason = models.CharField(max_length=128)
    record_sha256 = models.CharField(max_length=64, validators=[validate_checksum])
    created_at = models.DateTimeField(auto_now_add=True)

    objects = DeploymentOutcomeQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"), name="risk_outcome_org_id_unique"
            ),
            models.UniqueConstraint(
                fields=("organization", "source_event_sha256"),
                name="risk_outcome_org_source_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(shared_training_eligible=False),
                name="risk_outcome_never_shared_training",
            ),
            models.CheckConstraint(
                condition=models.Q(schema_version=DEPLOYMENT_OUTCOME_SCHEMA_VERSION),
                name="risk_outcome_schema_v1",
            ),
        ]
        ordering = ("-created_at", "-id")

    def clean(self) -> None:
        super().clean()
        if self.shared_training_eligible:
            raise ValidationError("deployment outcomes cannot enter shared training")
        if self.organization_id is None or self.snapshot_id is None or self.prediction_id is None:
            return
        if (
            self.repository.organization_id != self.organization_id
            or self.snapshot.organization_id != self.organization_id
            or self.prediction.organization_id != self.organization_id
            or self.snapshot.repository_id != self.repository_id
            or self.prediction.snapshot_id != self.snapshot_id
        ):
            raise ValidationError(
                "deployment outcome lineage must share tenant/repository/snapshot"
            )
        timestamps = (
            self.snapshot.created_at,
            self.observation_window_started_at,
            self.observation_window_ended_at,
            self.signal_observed_at,
            self.ingested_at,
        )
        if any(value.tzinfo is None or value.utcoffset() is None for value in timestamps):
            raise ValidationError("deployment outcome timestamps must be timezone aware")
        duration = self.observation_window_ended_at - self.observation_window_started_at
        if not timedelta(days=30) <= duration <= timedelta(days=365):
            raise ValidationError("deployment outcome window must be 30..365 days")
        if self.observation_window_started_at < self.snapshot.created_at:
            raise ValidationError("deployment outcome window predates its snapshot")
        if not (
            self.observation_window_started_at
            <= self.signal_observed_at
            <= self.observation_window_ended_at
        ):
            raise ValidationError("deployment outcome signal is outside its window")
        if self.ingested_at < self.observation_window_ended_at:
            raise ValidationError("deployment outcome was ingested before its window completed")
        if self.organization_training_eligible and not (
            self.explicit_learning_opt_in
            and self.organization_learning_enabled_at_ingest
            and self.provenance_known
            and self.outcome != OutcomeKind.UNKNOWN
        ):
            raise ValidationError("deployment outcome learning eligibility is inconsistent")
        if self.outcome == OutcomeKind.UNKNOWN or not self.provenance_known:
            expected_eligible = False
            expected_reason = "outcome_or_provenance_unknown"
        elif not self.organization_learning_enabled_at_ingest:
            expected_eligible = False
            expected_reason = "organization_learning_disabled"
        elif not self.explicit_learning_opt_in:
            expected_eligible = False
            expected_reason = "outcome_not_explicitly_opted_in"
        else:
            expected_eligible = True
            expected_reason = "eligible_for_organization_local_learning"
        if (
            self.organization_training_eligible is not expected_eligible
            or self.eligibility_reason != expected_reason
        ):
            raise ValidationError("deployment outcome eligibility decision is invalid")
        payload = {
            "eligibility_reason": self.eligibility_reason,
            "explicit_learning_opt_in": self.explicit_learning_opt_in,
            "ingested_at": self.ingested_at.isoformat(),
            "organization_learning_enabled_at_ingest": (
                self.organization_learning_enabled_at_ingest
            ),
            "organization_policy_version": self.organization_policy_version,
            "organization_training_eligible": self.organization_training_eligible,
            "outcome": self.outcome,
            "prediction_result_sha256": self.prediction.result_hash,
            "provenance_known": self.provenance_known,
            "schema_version": self.schema_version,
            "signal_observed_at": self.signal_observed_at.isoformat(),
            "source_event_sha256": self.source_event_sha256,
            "source_kind": self.source_kind,
            "window_ended_at": self.observation_window_ended_at.isoformat(),
            "window_started_at": self.observation_window_started_at.isoformat(),
        }
        if self.record_sha256 != canonical_hash(payload):
            raise ValidationError("deployment outcome checksum is invalid")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("deployment outcomes are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("deployment outcomes are immutable")


class DriftAssessmentRecordQuerySet(ImmutableQuerySet["DriftAssessmentRecord"]):
    def for_organization(self, organization: Organization | int) -> DriftAssessmentRecordQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)


class DriftAssessmentRecord(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="drift_assessments"
    )
    artifact = models.ForeignKey(
        GovernedModelArtifact, on_delete=models.PROTECT, related_name="drift_assessments"
    )
    schema_version = models.CharField(max_length=64, default=DRIFT_ASSESSMENT_SCHEMA_VERSION)
    policy_version = models.CharField(max_length=64, default=DRIFT_POLICY_VERSION)
    reference_profile_sha256 = models.CharField(max_length=64, validators=[validate_checksum])
    current_profile_sha256 = models.CharField(max_length=64, validators=[validate_checksum])
    decision = models.CharField(
        max_length=32, choices=[(item.value, item.value) for item in DriftDecision]
    )
    row_count = models.PositiveIntegerField()
    report = models.JSONField(validators=[validate_drift_report])
    assessment_sha256 = models.CharField(max_length=64, validators=[validate_checksum])
    human_review_required = models.BooleanField()
    automatic_retraining_allowed = models.BooleanField(default=False, editable=False)
    automatic_promotion_allowed = models.BooleanField(default=False, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = DriftAssessmentRecordQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("organization", "id"), name="risk_drift_org_id_unique"),
            models.UniqueConstraint(
                fields=("artifact", "current_profile_sha256", "policy_version"),
                name="risk_drift_artifact_profile_policy_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(automatic_retraining_allowed=False),
                name="risk_drift_no_automatic_retraining",
            ),
            models.CheckConstraint(
                condition=models.Q(automatic_promotion_allowed=False),
                name="risk_drift_no_automatic_promotion",
            ),
        ]
        ordering = ("-created_at", "-id")

    def clean(self) -> None:
        super().clean()
        if (
            self.organization_id
            and self.artifact_id
            and self.artifact.organization_id != self.organization_id
        ):
            raise ValidationError("drift assessment and artifact must share an organization")
        validate_drift_report(self.report)
        if (
            self.report["decision"] != self.decision
            or self.report["reference_profile_sha256"] != self.reference_profile_sha256
            or self.report["current_profile_sha256"] != self.current_profile_sha256
            or self.report["human_review_required"] != self.human_review_required
        ):
            raise ValidationError("drift assessment columns and payload disagree")
        if self.report["policy"]["version"] != self.policy_version:
            raise ValidationError("drift assessment policy version is inconsistent")
        if self.report["row_count"] != self.row_count:
            raise ValidationError("drift assessment row count is inconsistent")
        if self.assessment_sha256 != canonical_hash(self.report):
            raise ValidationError("drift assessment checksum is invalid")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("drift assessments are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("drift assessments are immutable")


class DriftReviewDecision(models.TextChoices):
    NO_ACTION = "no_action", "No action"
    INVESTIGATE = "investigate", "Investigate"
    APPROVE_EXPERIMENT = "approve_experiment", "Approve retraining experiment only"


class DriftReviewQuerySet(ImmutableQuerySet["DriftReview"]):
    def for_organization(self, organization: Organization | int) -> DriftReviewQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)


class DriftReview(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="drift_reviews"
    )
    assessment = models.OneToOneField(
        DriftAssessmentRecord, on_delete=models.PROTECT, related_name="review"
    )
    decision = models.CharField(max_length=32, choices=DriftReviewDecision)
    reason = models.CharField(max_length=1_000)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="drift_reviews"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = DriftReviewQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"), name="risk_drift_review_org_id_unique"
            )
        ]
        ordering = ("-created_at", "-id")

    def clean(self) -> None:
        super().clean()
        if (
            self.organization_id
            and self.assessment_id
            and self.assessment.organization_id != self.organization_id
        ):
            raise ValidationError("drift review and assessment must share an organization")

    def save(self, *args: object, **kwargs: object) -> None:
        if self.pk is not None:
            raise ValidationError("drift reviews are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise ValidationError("drift reviews are immutable")
