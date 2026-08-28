"""PostgreSQL-authoritative jobs and transactional outbox state."""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models

from apps.web.changes.models import PullRequestSnapshot
from apps.web.organizations.models import Organization


def validate_outbox_payload(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"organization_id", "job_id"}:
        raise ValidationError("outbox payload may contain only organization_id and job_id")
    try:
        uuid.UUID(str(value["organization_id"]))
        uuid.UUID(str(value["job_id"]))
    except (ValueError, TypeError) as error:
        raise ValidationError("outbox identifiers must be opaque UUIDs") from error


class JobState(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class JobType(models.TextChoices):
    PULL_REQUEST_SNAPSHOT = "pull_request_snapshot", "Pull-request snapshot"
    INSTALLATION_LIFECYCLE = "installation_lifecycle", "Installation lifecycle"
    REPOSITORY_LIFECYCLE = "repository_lifecycle", "Repository lifecycle"


class AnalysisJobQuerySet(models.QuerySet["AnalysisJob"]):
    def for_organization(self, organization: Organization | int) -> AnalysisJobQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)


class AnalysisJob(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="analysis_jobs",
    )
    snapshot = models.ForeignKey(
        PullRequestSnapshot,
        on_delete=models.PROTECT,
        related_name="analysis_jobs",
        null=True,
        blank=True,
    )
    job_type = models.CharField(max_length=32, choices=JobType)
    task_version = models.CharField(max_length=32, default="v1")
    idempotency_key = models.CharField(max_length=255, unique=True)
    state = models.CharField(max_length=16, choices=JobState, default=JobState.PENDING)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    available_at = models.DateTimeField()
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    outcome_code = models.CharField(max_length=64, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    correlation_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AnalysisJobQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"),
                name="analysis_job_org_id_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(attempt_count__lte=models.F("max_attempts")),
                name="analysis_job_attempts_bounded",
            ),
        ]
        ordering = ("available_at", "id")


class OutboxState(models.TextChoices):
    PENDING = "pending", "Pending"
    PUBLISHED = "published", "Published"
    FAILED = "failed", "Failed"


class OutboxEventQuerySet(models.QuerySet["OutboxEvent"]):
    def for_organization(self, organization: Organization | int) -> OutboxEventQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)

    def pending(self) -> OutboxEventQuerySet:
        return self.filter(state=OutboxState.PENDING)


class OutboxEvent(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="outbox_events",
    )
    job = models.OneToOneField(
        AnalysisJob,
        on_delete=models.PROTECT,
        related_name="outbox_event",
    )
    topic = models.CharField(max_length=128, default="releaseproof.analysis.process_job.v1")
    payload_version = models.CharField(max_length=16, default="v1")
    payload = models.JSONField(validators=[validate_outbox_payload])
    state = models.CharField(max_length=16, choices=OutboxState, default=OutboxState.PENDING)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    available_at = models.DateTimeField()
    published_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OutboxEventQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"),
                name="analysis_outbox_org_id_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(topic="releaseproof.analysis.process_job.v1"),
                name="analysis_outbox_topic_allowlisted",
            ),
            models.CheckConstraint(
                condition=models.Q(attempt_count__lte=models.F("max_attempts")),
                name="analysis_outbox_attempts_bounded",
            ),
        ]
        ordering = ("available_at", "id")
