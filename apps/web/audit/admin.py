"""Read-only, tenant-scoped audit administration."""

from django.contrib import admin

from apps.web.audit.models import AuditLog
from apps.web.organizations.admin import TenantScopedAdminMixin


@admin.register(AuditLog)
class AuditLogAdmin(TenantScopedAdminMixin):
    list_display = ("public_id", "organization", "action", "resource_type", "occurred_at")

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False
