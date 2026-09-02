"""Read-only tenant-scoped administration for generated-test evidence."""

from __future__ import annotations

from django.contrib import admin
from django.http import HttpRequest

from apps.web.organizations.admin import TenantScopedAdminMixin
from apps.web.verification.models import (
    ExecutionApproval,
    ExecutionPlan,
    ExecutionRun,
    GeneratedTestProposal,
    ProposalLifecycleEvent,
)


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


@admin.register(ExecutionPlan)
class ExecutionPlanAdmin(_ReadOnlyProposalAdmin):
    list_display = ("public_id", "organization", "plan_hash", "created_at")
    readonly_fields = tuple(field.name for field in ExecutionPlan._meta.fields)


@admin.register(ExecutionApproval)
class ExecutionApprovalAdmin(_ReadOnlyProposalAdmin):
    list_display = ("public_id", "organization", "plan", "actor", "occurred_at")
    readonly_fields = tuple(field.name for field in ExecutionApproval._meta.fields)


@admin.register(ExecutionRun)
class ExecutionRunAdmin(_ReadOnlyProposalAdmin):
    list_display = ("public_id", "organization", "plan", "attempt", "outcome", "recorded_at")
    readonly_fields = tuple(field.name for field in ExecutionRun._meta.fields)
