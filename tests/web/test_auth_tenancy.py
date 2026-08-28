from __future__ import annotations

from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib import admin
from django.core.cache import cache
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.web.organizations.admin import OrganizationAdmin
from apps.web.organizations.models import MembershipRole, Organization
from apps.web.repositories.admin import RepositoryAdmin
from apps.web.repositories.models import Repository
from tests.factories import installation, membership, organization, repository, user

pytestmark = pytest.mark.django_db


def _csrf_client() -> tuple[Client, str]:
    client = Client(enforce_csrf_checks=True)
    response = client.get(reverse("login"))
    assert response.status_code == 200
    return client, client.cookies[settings.CSRF_COOKIE_NAME].value


def test_login_requires_csrf_uses_secure_session_cookie_contract_and_logs_out_by_post() -> None:
    account = user(username="reviewer")
    client, csrf_token = _csrf_client()

    forbidden = client.post(
        reverse("login"),
        {"username": account.username, "password": "correct-horse-battery-staple"},
    )
    assert forbidden.status_code == 403

    response = client.post(
        reverse("login"),
        {"username": account.username, "password": "correct-horse-battery-staple"},
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    assert response.status_code == 302
    session_cookie = response.cookies[settings.SESSION_COOKIE_NAME]
    assert session_cookie["httponly"] is True
    assert session_cookie["samesite"] == "Lax"
    rotated_csrf_token = client.cookies[settings.CSRF_COOKIE_NAME].value

    assert client.get(reverse("logout")).status_code == 405
    assert client.post(reverse("logout")).status_code == 403
    logout = client.post(reverse("logout"), HTTP_X_CSRFTOKEN=rotated_csrf_token)
    assert logout.status_code == 302


def test_login_throttle_blocks_repeated_failures_without_raw_username_cache_key() -> None:
    cache.clear()
    user(username="bounded-user")
    client, csrf_token = _csrf_client()
    for _attempt in range(5):
        response = client.post(
            reverse("login"),
            {"username": "bounded-user", "password": "wrong-password"},
            HTTP_X_CSRFTOKEN=csrf_token,
            REMOTE_ADDR="192.0.2.10",
        )
        assert response.status_code == 200
    blocked = client.post(
        reverse("login"),
        {"username": "bounded-user", "password": "wrong-password"},
        HTTP_X_CSRFTOKEN=csrf_token,
        REMOTE_ADDR="192.0.2.10",
    )
    assert blocked.status_code == 429


def test_login_fails_closed_when_throttle_storage_is_unavailable() -> None:
    account = user(username="cache-outage")
    client, csrf_token = _csrf_client()
    with patch("apps.web.identity.throttling.cache.get", side_effect=OSError("offline")):
        response = client.post(
            reverse("login"),
            {"username": account.username, "password": "correct-horse-battery-staple"},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
    assert response.status_code == 503
    assert settings.SESSION_COOKIE_NAME not in response.cookies


def test_active_organization_selection_and_repository_direct_id_are_tenant_scoped() -> None:
    account = user(username="member")
    organization_a = organization(name="Organization A", slug="organization-a")
    organization_b = organization(name="Organization B", slug="organization-b")
    member = membership(organization=organization_a, user=account)
    install_a = installation(
        organization=organization_a,
        github_installation_id=101,
        github_account_id=201,
    )
    install_b = installation(
        organization=organization_b,
        github_installation_id=102,
        github_account_id=202,
    )
    repository_a = repository(
        organization=organization_a,
        installation=install_a,
        github_repository_id=301,
        name="repo-a",
    )
    repository_b = repository(
        organization=organization_b,
        installation=install_b,
        github_repository_id=302,
        name="repo-b",
    )
    client, csrf_token = _csrf_client()
    client.force_login(account)

    assert (
        client.post(reverse("select-organization", args=[organization_a.public_id])).status_code
        == 403
    )
    selected = client.post(
        reverse("select-organization", args=[organization_a.public_id]),
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    assert selected.status_code == 302
    assert (
        client.get(reverse("api-repository-detail", args=[repository_a.public_id])).status_code
        == 200
    )
    denied_repository = client.get(reverse("api-repository-detail", args=[repository_b.public_id]))
    assert denied_repository.status_code == 404
    assert denied_repository.json()["error"]["code"] == "not_found"
    assert denied_repository.json()["error"]["correlation_id"]
    assert (
        client.post(
            reverse("select-organization", args=[organization_b.public_id]),
            HTTP_X_CSRFTOKEN=csrf_token,
        ).status_code
        == 404
    )
    role_denied = client.post(
        reverse("api-repository-lifecycle", args=[repository_a.public_id]),
        {"action": "disable"},
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    assert role_denied.status_code == 404

    member.role = MembershipRole.ADMIN
    member.save(update_fields=("role", "updated_at"))
    assert (
        client.post(
            reverse("api-repository-lifecycle", args=[repository_a.public_id]),
            {"action": "disable"},
        ).status_code
        == 403
    )
    role_allowed = client.post(
        reverse("api-repository-lifecycle", args=[repository_a.public_id]),
        {"action": "disable"},
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    assert role_allowed.status_code == 200
    repository_a.refresh_from_db()
    assert repository_a.lifecycle == "disabled"


def test_non_superuser_admin_querysets_are_tenant_scoped() -> None:
    staff = user(username="staff")
    staff.is_staff = True
    staff.save(update_fields=("is_staff",))
    organization_a = organization(name="Admin A", slug="admin-a")
    organization_b = organization(name="Admin B", slug="admin-b")
    membership(
        organization=organization_a,
        user=staff,
        role=MembershipRole.ADMIN,
    )
    install_a = installation(
        organization=organization_a,
        github_installation_id=401,
        github_account_id=501,
    )
    install_b = installation(
        organization=organization_b,
        github_installation_id=402,
        github_account_id=502,
    )
    repository_a = repository(
        organization=organization_a,
        installation=install_a,
        github_repository_id=601,
        name="visible",
    )
    repository(
        organization=organization_b,
        installation=install_b,
        github_repository_id=602,
        name="hidden",
    )
    request = RequestFactory().get("/admin/")
    request.user = staff

    organizations = OrganizationAdmin(Organization, admin.site).get_queryset(request)
    repositories = RepositoryAdmin(Repository, admin.site).get_queryset(request)
    assert list(organizations) == [organization_a]
    assert list(repositories) == [repository_a]
