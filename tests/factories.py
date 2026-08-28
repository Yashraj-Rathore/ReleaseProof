"""Small deterministic persistence helpers for ReleaseProof tests."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.utils import timezone

from apps.web.organizations.models import Membership, MembershipRole, Organization
from apps.web.repositories.models import GitHubInstallation, Repository


def user(*, username: str, password: str | None = None) -> User:
    resolved_password = password or "correct-horse-battery-staple"
    return get_user_model().objects.create_user(username=username, password=resolved_password)


def organization(*, name: str, slug: str) -> Organization:
    return Organization.objects.create(name=name, slug=slug)


def membership(
    *,
    organization: Organization,
    user: User,
    role: MembershipRole = MembershipRole.MEMBER,
) -> Membership:
    return Membership.objects.create(organization=organization, user=user, role=role)


def installation(
    *,
    organization: Organization,
    github_installation_id: int,
    github_account_id: int,
) -> GitHubInstallation:
    return GitHubInstallation.objects.create(
        organization=organization,
        github_installation_id=github_installation_id,
        github_account_id=github_account_id,
        account_login=f"owner-{github_account_id}",
        permissions={"metadata": "read", "pull_requests": "read", "checks": "write"},
        credential_reference="env:GITHUB_APP_PRIVATE_KEY_PATH",
        installed_at=timezone.now(),
    )


def repository(
    *,
    organization: Organization,
    installation: GitHubInstallation,
    github_repository_id: int,
    name: str,
) -> Repository:
    return Repository.objects.create(
        organization=organization,
        installation=installation,
        github_repository_id=github_repository_id,
        owner=installation.account_login,
        name=name,
        default_branch="main",
    )
