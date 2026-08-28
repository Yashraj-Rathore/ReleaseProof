"""Tenant-scoped immutable snapshot and feature-set administration."""

from django.contrib import admin
from django.http import HttpRequest

from apps.web.changes.models import ChangeFeatureSet, PullRequestSnapshot, WebhookReceipt
from apps.web.organizations.admin import TenantScopedAdminMixin


class ImmutableAdminMixin(TenantScopedAdminMixin):
    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return False

    def has_change_permission(self, request: HttpRequest, obj: object | None = None) -> bool:
        del request, obj
        return False

    def has_delete_permission(self, request: HttpRequest, obj: object | None = None) -> bool:
        del request, obj
        return False


@admin.register(WebhookReceipt)
class WebhookReceiptAdmin(ImmutableAdminMixin):
    list_display = ("public_id", "organization", "event_name", "action", "received_at")


@admin.register(PullRequestSnapshot)
class PullRequestSnapshotAdmin(ImmutableAdminMixin):
    list_display = (
        "public_id",
        "organization",
        "repository",
        "pull_request_number",
        "created_at",
    )


@admin.register(ChangeFeatureSet)
class ChangeFeatureSetAdmin(ImmutableAdminMixin):
    list_display = (
        "public_id",
        "organization",
        "snapshot",
        "feature_schema_version",
        "created_at",
    )
