"""Transactional outbox and idempotent M2 worker services."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.db import models, transaction
from django.utils import timezone

from apps.web.analysis.models import (
    AnalysisJob,
    JobState,
    JobType,
    OutboxEvent,
    OutboxState,
)
from apps.web.changes.models import PullRequestSnapshot
from apps.web.organizations.models import Organization
from packages.domain import TaskMessage, TaskPublisher, TaskPublisherError


@dataclass(frozen=True, slots=True)
class RelayResult:
    published: int
    failed: int


def create_job_with_outbox(
    *,
    organization: Organization,
    job_type: JobType,
    idempotency_key: str,
    correlation_id: uuid.UUID,
    snapshot: PullRequestSnapshot | None = None,
) -> tuple[AnalysisJob, bool]:
    """Create both authoritative rows; caller owns the surrounding transaction."""

    now = timezone.now()
    job, created = AnalysisJob.objects.for_organization(organization).get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "organization": organization,
            "snapshot": snapshot,
            "job_type": job_type,
            "correlation_id": correlation_id,
            "available_at": now,
        },
    )
    if job.organization_id != organization.id:
        raise ValueError("idempotency key resolved outside the organization scope")
    if created:
        OutboxEvent.objects.create(
            organization=organization,
            job=job,
            payload={
                "organization_id": str(organization.public_id),
                "job_id": str(job.public_id),
            },
            available_at=now,
        )
    return job, created


def relay_outbox_for_organization(
    *,
    organization: Organization,
    publisher: TaskPublisher,
    limit: int = 100,
) -> RelayResult:
    if limit < 1 or limit > 1_000:
        raise ValueError("outbox relay limit must be between 1 and 1000")
    published = 0
    failed = 0
    event_ids = list(
        OutboxEvent.objects.pending()
        .for_organization(organization)
        .filter(
            available_at__lte=timezone.now(),
            attempt_count__lt=models.F("max_attempts"),
        )
        .values_list("id", flat=True)[:limit]
    )
    for event_id in event_ids:
        with transaction.atomic():
            event = (
                OutboxEvent.objects.select_for_update()
                .pending()
                .for_organization(organization)
                .select_related("job")
                .filter(id=event_id)
                .first()
            )
            if event is None:
                continue
            message = TaskMessage(
                topic=event.topic,
                payload={key: str(value) for key, value in event.payload.items()},
                idempotency_key=str(event.job.public_id),
            )
            try:
                publisher.publish(message)
            except TaskPublisherError:
                event.attempt_count += 1
                event.last_error_code = "broker_unavailable"
                if event.attempt_count >= event.max_attempts:
                    event.state = OutboxState.FAILED
                event.save(
                    update_fields=(
                        "attempt_count",
                        "last_error_code",
                        "state",
                        "updated_at",
                    )
                )
                failed += 1
                continue
            event.attempt_count += 1
            event.state = OutboxState.PUBLISHED
            event.published_at = timezone.now()
            event.last_error_code = ""
            event.save(
                update_fields=(
                    "attempt_count",
                    "state",
                    "published_at",
                    "last_error_code",
                    "updated_at",
                )
            )
            published += 1
    return RelayResult(published=published, failed=failed)


def process_ingestion_job(*, organization_public_id: str, job_public_id: str) -> str:
    """Idempotently acknowledge M2 durable work without beginning M3 analysis."""

    with transaction.atomic():
        job = (
            AnalysisJob.objects.select_for_update()
            .filter(
                organization__public_id=organization_public_id,
                organization__lifecycle="active",
                public_id=job_public_id,
            )
            .first()
        )
        if job is None:
            return "not_found"
        if job.state == JobState.COMPLETED:
            return "duplicate"
        if job.state == JobState.FAILED or job.attempt_count >= job.max_attempts:
            return "terminal"
        job.state = JobState.RUNNING
        job.started_at = job.started_at or timezone.now()
        job.attempt_count += 1
        job.save(update_fields=("state", "started_at", "attempt_count", "updated_at"))

        job.state = JobState.COMPLETED
        job.finished_at = timezone.now()
        job.outcome_code = (
            "snapshot_ready"
            if job.job_type == JobType.PULL_REQUEST_SNAPSHOT
            else "lifecycle_recorded"
        )
        job.save(update_fields=("state", "finished_at", "outcome_code", "updated_at"))
        return "completed"
