"""Tenant-scoped read-only risk evidence administration."""

from django.contrib import admin

from apps.web.changes.admin import ImmutableAdminMixin
from apps.web.risk.models import (
    DeploymentOutcome,
    DriftAssessmentRecord,
    DriftReview,
    GovernedModelArtifact,
    ModelDeployment,
    ModelLifecycleEvent,
    RiskScore,
)


@admin.register(RiskScore)
class RiskScoreAdmin(ImmutableAdminMixin):
    list_display = (
        "public_id",
        "organization",
        "artifact_version",
        "raw_score",
        "band",
        "created_at",
    )


@admin.register(GovernedModelArtifact)
class GovernedModelArtifactAdmin(ImmutableAdminMixin):
    list_display = ("public_id", "organization", "model_name", "artifact_version", "created_at")


@admin.register(ModelLifecycleEvent)
class ModelLifecycleEventAdmin(ImmutableAdminMixin):
    list_display = ("public_id", "organization", "artifact", "action", "to_state", "created_at")


@admin.register(ModelDeployment)
class ModelDeploymentAdmin(ImmutableAdminMixin):
    list_display = ("organization", "model_name", "active_artifact", "generation", "updated_at")


@admin.register(DeploymentOutcome)
class DeploymentOutcomeAdmin(ImmutableAdminMixin):
    list_display = ("public_id", "organization", "repository", "outcome", "created_at")


@admin.register(DriftAssessmentRecord)
class DriftAssessmentRecordAdmin(ImmutableAdminMixin):
    list_display = ("public_id", "organization", "artifact", "decision", "created_at")


@admin.register(DriftReview)
class DriftReviewAdmin(ImmutableAdminMixin):
    list_display = ("public_id", "organization", "assessment", "decision", "created_at")
