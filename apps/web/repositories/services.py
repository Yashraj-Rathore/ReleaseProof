"""Tenant-scoped repository and installation application services."""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.http import Http404

from apps.web.organizations.models import Organization
from apps.web.repositories.models import GitHubInstallation, Repository


def get_repository(
    *,
    organization: Organization,
    public_id: uuid.UUID | str,
) -> Repository:
    try:
        normalized_id = uuid.UUID(str(public_id))
    except ValueError as error:
        raise Http404("repository not found") from error
    try:
        return (
            Repository.objects.active()
            .for_organization(organization)
            .select_related("installation")
            .get(public_id=normalized_id)
        )
    except Repository.DoesNotExist as error:
        raise Http404("repository not found") from error


def get_repository_binding(
    *,
    organization: Organization,
    public_id: uuid.UUID | str,
) -> Repository:
    try:
        normalized_id = uuid.UUID(str(public_id))
    except ValueError as error:
        raise Http404("repository not found") from error
    try:
        return (
            Repository.objects.for_organization(organization)
            .exclude(lifecycle="removed")
            .filter(installation__lifecycle="active")
            .select_related("installation")
            .get(public_id=normalized_id)
        )
    except Repository.DoesNotExist as error:
        raise Http404("repository not found") from error


def get_installation_by_github_id(github_installation_id: int) -> GitHubInstallation:
    """Audited webhook lookup: the verified installation ID derives tenant scope."""

    if github_installation_id < 1:
        raise Http404("installation not found")
    try:
        return GitHubInstallation.objects.select_related("organization").get(
            github_installation_id=github_installation_id
        )
    except GitHubInstallation.DoesNotExist as error:
        raise Http404("installation not found") from error


def bind_repository(
    *,
    organization: Organization,
    installation: GitHubInstallation,
    github_repository_id: int,
    owner: str,
    name: str,
    default_branch: str,
) -> tuple[Repository, bool]:
    if installation.organization_id != organization.id:
        raise ValidationError("installation does not belong to organization")
    # Audited binding lookup: GitHub repository IDs are global immutable provider identities.
    existing = Repository.objects.filter(github_repository_id=github_repository_id).first()
    if existing is not None and existing.organization_id != organization.id:
        raise ValidationError("GitHub repository is already bound to another organization")
    repository, created = Repository.objects.update_or_create(
        organization=organization,
        github_repository_id=github_repository_id,
        defaults={
            "organization": organization,
            "installation": installation,
            "owner": owner,
            "name": name,
            "default_branch": default_branch,
            "lifecycle": "active",
        },
    )
    repository.full_clean()
    return repository, created
