"""Tenant-scoped, read-only deterministic evidence administration."""

from django.contrib import admin

from apps.web.changes.admin import ImmutableAdminMixin
from apps.web.evidence.models import EvidenceItem


@admin.register(EvidenceItem)
class EvidenceItemAdmin(ImmutableAdminMixin):
    list_display = (
        "public_id",
        "organization",
        "kind",
        "rule_id",
        "missing",
        "created_at",
    )
