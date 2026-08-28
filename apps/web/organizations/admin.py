"""Tenant-scoped admin behavior for non-superuser staff."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.web.organizations.models import Membership, Organization


class TenantScopedAdminMixin(admin.ModelAdmin):  # type: ignore[type-arg]
    organization_lookup = "organization_id"

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        if not request.user.is_authenticated or request.user.pk is None:
            return queryset.none()
        organization_ids = (
            Membership.objects.active().filter(user_id=request.user.pk).values("organization_id")
        )
        if self.organization_lookup:
            return queryset.filter(**{f"{self.organization_lookup}__in": organization_ids})
        return queryset.filter(id__in=organization_ids)

    def has_view_or_change_permission(
        self,
        request: HttpRequest,
        obj: object | None = None,
    ) -> bool:
        base_allowed = bool(super().has_view_or_change_permission(request, obj))
        if not base_allowed or obj is None or request.user.is_superuser:
            return base_allowed
        if not request.user.is_authenticated or request.user.pk is None:
            return False
        organization_id = (
            getattr(obj, "id", None)
            if not self.organization_lookup
            else getattr(obj, self.organization_lookup, None)
        )
        if not isinstance(organization_id, int):
            return False
        return (
            Membership.objects.active()
            .filter(
                user_id=request.user.pk,
                organization_id=organization_id,
            )
            .exists()
        )


@admin.register(Organization)
class OrganizationAdmin(TenantScopedAdminMixin):
    organization_lookup = ""
    list_display = ("public_id", "name", "lifecycle", "policy_version")


@admin.register(Membership)
class MembershipAdmin(TenantScopedAdminMixin):
    list_display = ("public_id", "organization", "user", "role", "lifecycle")
