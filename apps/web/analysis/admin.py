"""Tenant-scoped job and outbox administration."""

from django.contrib import admin

from apps.web.analysis.models import AnalysisJob, OutboxEvent
from apps.web.organizations.admin import TenantScopedAdminMixin


@admin.register(AnalysisJob)
class AnalysisJobAdmin(TenantScopedAdminMixin):
    list_display = ("public_id", "organization", "job_type", "state", "attempt_count")
    readonly_fields = (
        "public_id",
        "organization",
        "snapshot",
        "job_type",
        "task_version",
        "idempotency_key",
        "correlation_id",
        "created_at",
    )


@admin.register(OutboxEvent)
class OutboxEventAdmin(TenantScopedAdminMixin):
    list_display = ("public_id", "organization", "topic", "state", "attempt_count")
    readonly_fields = ("public_id", "organization", "job", "topic", "payload", "created_at")
