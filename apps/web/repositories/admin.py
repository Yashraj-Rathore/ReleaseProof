"""Tenant-scoped GitHub installation and repository admin."""

from django.contrib import admin

from apps.web.organizations.admin import TenantScopedAdminMixin
from apps.web.repositories.models import GitHubInstallation, Repository


@admin.register(GitHubInstallation)
class GitHubInstallationAdmin(
    TenantScopedAdminMixin,
):
    list_display = (
        "public_id",
        "organization",
        "github_installation_id",
        "account_login",
        "lifecycle",
    )
    exclude = ()


@admin.register(Repository)
class RepositoryAdmin(TenantScopedAdminMixin):
    list_display = ("public_id", "organization", "owner", "name", "lifecycle")
    readonly_fields = ("execution_allowed",)
