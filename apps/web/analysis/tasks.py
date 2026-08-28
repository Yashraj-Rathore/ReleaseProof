"""Celery transport entry points with opaque, tenant-scoped payloads."""

from __future__ import annotations

from celery import shared_task

from apps.web.analysis.services import process_ingestion_job


@shared_task(
    name="releaseproof.analysis.process_job.v1",
    acks_late=True,
    reject_on_worker_lost=True,
    ignore_result=True,
)  # type: ignore[untyped-decorator]
def process_job(*, organization_id: str, job_id: str) -> str:
    return process_ingestion_job(
        organization_public_id=organization_id,
        job_public_id=job_id,
    )
