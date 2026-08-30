"""Tenant-scoped read-only risk evidence administration."""

from django.contrib import admin

from apps.web.changes.admin import ImmutableAdminMixin
from apps.web.risk.models import RiskScore


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
