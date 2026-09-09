from __future__ import annotations

import json
import uuid

import pytest
from django.test import Client

from apps.web.organizations.models import MembershipRole
from apps.web.organizations.views import ACTIVE_ORGANIZATION_SESSION_KEY
from packages.observability import DEFAULT_QUOTA_LIMITS, DEFAULT_RETENTION_DAYS
from tests.factories import membership, organization, user

pytestmark = pytest.mark.django_db


def _select(client: Client, tenant_id: uuid.UUID) -> None:
    session = client.session
    session[ACTIVE_ORGANIZATION_SESSION_KEY] = str(tenant_id)
    session.save()


def test_operational_policy_api_is_session_tenant_scoped_and_admin_only() -> None:
    tenant = organization(name="Ops API", slug="ops-api")
    admin = user(username="ops-admin")
    member = user(username="ops-member")
    membership(organization=tenant, user=admin, role=MembershipRole.ADMIN)
    membership(organization=tenant, user=member, role=MembershipRole.MEMBER)
    payload = {
        "quota_limits": dict(DEFAULT_QUOTA_LIMITS),
        "retention_days": dict(DEFAULT_RETENTION_DAYS),
    }

    member_client = Client()
    member_client.force_login(member)
    _select(member_client, tenant.public_id)
    denied = member_client.post(
        "/api/v1/operations/policy",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert denied.status_code == 404

    admin_client = Client()
    admin_client.force_login(admin)
    _select(admin_client, tenant.public_id)
    created = admin_client.post(
        "/api/v1/operations/policy",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert created.status_code == 201
    current = admin_client.get("/api/v1/operations/policy")
    assert current.status_code == 200
    assert current.json()["version"] == 1
    assert current.json()["persisted"] is True


def test_retention_execution_cannot_cross_active_organization() -> None:
    first = organization(name="First Ops", slug="first-ops")
    second = organization(name="Second Ops", slug="second-ops")
    operator = user(username="dual-ops-admin")
    membership(organization=first, user=operator, role=MembershipRole.OWNER)
    membership(organization=second, user=operator, role=MembershipRole.OWNER)
    client = Client()
    client.force_login(operator)
    _select(client, first.public_id)
    created = client.post(
        "/api/v1/operations/retention-plans",
        data=json.dumps({"dry_run": False}),
        content_type="application/json",
    )
    assert created.status_code == 201

    _select(client, second.public_id)
    denied = client.post(
        f"/api/v1/operations/retention-plans/{created.json()['id']}/execute",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert denied.status_code == 400
    assert denied.json()["error"]["code"] == "invalid_request"


def test_server_replaces_untrusted_correlation_id_and_reuses_it_in_errors() -> None:
    attacker_value = str(uuid.uuid4())
    client = Client()

    live = client.get("/health/live", headers={"X-Correlation-ID": attacker_value})
    assert live.status_code == 200
    assert live.headers["X-Correlation-ID"] != attacker_value
    assert uuid.UUID(live.headers["X-Correlation-ID"])

    invalid = client.post(
        "/webhooks/github",
        data=b"{}",
        content_type="text/plain",
        headers={"X-Correlation-ID": attacker_value},
    )
    assert invalid.status_code == 415
    assert invalid.json()["error"]["correlation_id"] == invalid.headers["X-Correlation-ID"]
