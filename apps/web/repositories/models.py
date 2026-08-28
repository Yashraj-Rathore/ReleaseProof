"""GitHub installation and tenant-bound repository persistence."""

from __future__ import annotations

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from apps.web.organizations.models import Organization

_credential_reference_validator = RegexValidator(
    regex=r"^(env|file|vault|aws-secretsmanager|gcp-secret-manager|azure-key-vault):[^\s]{1,480}$",
    message="credential reference must name an approved secret source without containing a token",
)
_name_validator = RegexValidator(
    regex=r"^[A-Za-z0-9_.-]{1,100}$",
    message="GitHub owner and repository names must use the bounded GitHub name subset",
)

ALLOWED_GITHUB_PERMISSIONS: dict[str, set[str]] = {
    "metadata": {"read"},
    "pull_requests": {"read"},
    "contents": {"read"},
    "checks": {"write"},
    "statuses": {"write"},
}
REQUIRED_GITHUB_PERMISSIONS = {"metadata": "read", "pull_requests": "read"}


def validate_github_permissions(value: Any) -> None:
    if not isinstance(value, dict) or len(value) > len(ALLOWED_GITHUB_PERMISSIONS):
        raise ValidationError("permissions must be a bounded object")
    for name, access in value.items():
        if not isinstance(name, str) or not isinstance(access, str):
            raise ValidationError("permission names and access levels must be strings")
        if name not in ALLOWED_GITHUB_PERMISSIONS or access not in ALLOWED_GITHUB_PERMISSIONS[name]:
            raise ValidationError("permission snapshot exceeds the ReleaseProof allowlist")
    for name, access in REQUIRED_GITHUB_PERMISSIONS.items():
        if value.get(name) != access:
            raise ValidationError(f"required GitHub permission missing: {name}={access}")


class InstallationLifecycle(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    REVOKED = "revoked", "Revoked"


class RepositoryLifecycle(models.TextChoices):
    ACTIVE = "active", "Active"
    DISABLED = "disabled", "Disabled"
    REMOVED = "removed", "Removed"


class GitHubInstallationQuerySet(models.QuerySet["GitHubInstallation"]):
    def active(self) -> GitHubInstallationQuerySet:
        return self.filter(lifecycle=InstallationLifecycle.ACTIVE)

    def for_organization(
        self,
        organization: Organization | int,
    ) -> GitHubInstallationQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)


class GitHubInstallation(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="github_installations",
    )
    github_installation_id = models.PositiveBigIntegerField(unique=True)
    github_account_id = models.PositiveBigIntegerField()
    account_login = models.CharField(max_length=100, validators=[_name_validator])
    permissions = models.JSONField(default=dict, validators=[validate_github_permissions])
    credential_reference = models.CharField(
        max_length=512,
        validators=[_credential_reference_validator],
    )
    lifecycle = models.CharField(
        max_length=16,
        choices=InstallationLifecycle,
        default=InstallationLifecycle.ACTIVE,
    )
    installed_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = GitHubInstallationQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"),
                name="repositories_installation_org_id_unique",
            ),
            models.UniqueConstraint(
                fields=("organization", "github_account_id"),
                name="repositories_installation_org_account_unique",
            ),
        ]
        ordering = ("organization_id", "id")

    def __str__(self) -> str:
        return f"{self.account_login}:{self.github_installation_id}"


class RepositoryQuerySet(models.QuerySet["Repository"]):
    def active(self) -> RepositoryQuerySet:
        return self.filter(
            lifecycle=RepositoryLifecycle.ACTIVE,
            installation__lifecycle=InstallationLifecycle.ACTIVE,
        )

    def for_organization(self, organization: Organization | int) -> RepositoryQuerySet:
        organization_id = (
            organization.pk if isinstance(organization, Organization) else organization
        )
        return self.filter(organization_id=organization_id)


class Repository(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="repositories",
    )
    installation = models.ForeignKey(
        GitHubInstallation,
        on_delete=models.PROTECT,
        related_name="repositories",
    )
    github_repository_id = models.PositiveBigIntegerField(unique=True)
    owner = models.CharField(max_length=100, validators=[_name_validator])
    name = models.CharField(max_length=100, validators=[_name_validator])
    default_branch = models.CharField(max_length=255, default="main")
    primary_language = models.CharField(max_length=64, blank=True)
    lifecycle = models.CharField(
        max_length=16,
        choices=RepositoryLifecycle,
        default=RepositoryLifecycle.ACTIVE,
    )
    analysis_enabled = models.BooleanField(default=True)
    indexing_enabled = models.BooleanField(default=True)
    execution_allowed = models.BooleanField(default=False, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = RepositoryQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "id"),
                name="repositories_repository_org_id_unique",
            ),
            models.UniqueConstraint(
                fields=("organization", "owner", "name"),
                name="repositories_repository_org_name_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(execution_allowed=False),
                name="repositories_execution_disabled_before_m9",
            ),
        ]
        ordering = ("organization_id", "owner", "name")

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    def clean(self) -> None:
        super().clean()
        if self.installation_id and self.organization_id:
            installation_organization_id = getattr(
                self.installation,
                "organization_id",
                None,
            )
            if installation_organization_id != self.organization_id:
                raise ValidationError("repository and installation organizations must match")

    def __str__(self) -> str:
        return self.full_name
