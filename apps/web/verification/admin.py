"""Read-only tenant-scoped administration for generated-test evidence."""

from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest

from apps.web.organizations.admin import TenantScopedAdminMixin
from apps.web.verification.models import GeneratedTestProposal, ProposalLifecycleEvent


class _ReadOnlyProposalAdmin(TenantScopedAdminMixin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return False

    def has_delete_permission(self, request: HttpRequest, obj: object | None = None) -> bool:
        del request, obj
        return False


@admin.register(GeneratedTestProposal)
class GeneratedTestProposalAdmin(_ReadOnlyProposalAdmin):
    list_display = (
        "public_id",
        "organization",
        "proposal_group_id",
        "revision",
        "file_path",
        "created_at",
    )
    readonly_fields = tuple(field.name for field in GeneratedTestProposal._meta.fields)


@admin.register(ProposalLifecycleEvent)
class ProposalLifecycleEventAdmin(_ReadOnlyProposalAdmin):
    list_display = (
        "public_id",
        "organization",
        "proposal",
        "sequence",
        "to_lifecycle",
        "occurred_at",
    )
    readonly_fields = tuple(field.name for field in ProposalLifecycleEvent._meta.fields)
