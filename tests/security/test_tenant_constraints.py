from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.web.repositories.models import GitHubInstallation, Repository
from tests.factories import installation, organization

pytestmark = pytest.mark.django_db


def test_database_rejects_cross_organization_repository_installation_pair() -> None:
    organization_a = organization(name="Constraint A", slug="constraint-a")
    organization_b = organization(name="Constraint B", slug="constraint-b")
    installation_b = installation(
        organization=organization_b,
        github_installation_id=701,
        github_account_id=801,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        Repository.objects.create(
            organization=organization_a,
            installation=installation_b,
            github_repository_id=901,
            owner="constraint-owner",
            name="constraint-repo",
        )


def test_installation_schema_has_no_access_token_field_and_permissions_fail_closed() -> None:
    field_names = {field.name.casefold() for field in GitHubInstallation._meta.get_fields()}
    assert not any("token" in name for name in field_names)
    organization_a = organization(name="Permission A", slug="permission-a")
    overbroad = GitHubInstallation(
        organization=organization_a,
        github_installation_id=702,
        github_account_id=802,
        account_login="permission-owner",
        permissions={"metadata": "read", "pull_requests": "write"},
        credential_reference="env:GITHUB_APP_PRIVATE_KEY_PATH",
    )
    with pytest.raises(ValidationError, match="allowlist"):
        overbroad.full_clean()
