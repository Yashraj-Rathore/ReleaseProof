"""Celery transport entry points with opaque, tenant-scoped payloads."""

from __future__ import annotations

from celery import shared_task

from apps.web.analysis.models import AnalysisJob
from apps.web.analysis.services import process_ingestion_job
from packages.observability import correlation_scope


@shared_task(
    name="releaseproof.analysis.process_job.v1",
    acks_late=True,
    reject_on_worker_lost=True,
    ignore_result=True,
)  # type: ignore[untyped-decorator]
def process_job(*, organization_id: str, job_id: str) -> str:
    correlation_id = (
        AnalysisJob.objects.filter(organization__public_id=organization_id, public_id=job_id)
        .values_list("correlation_id", flat=True)
        .first()
    )
    with correlation_scope(correlation_id):
        return process_ingestion_job(
            organization_public_id=organization_id,
            job_public_id=job_id,
        )
