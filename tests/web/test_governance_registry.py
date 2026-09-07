from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from tests.factories import membership, organization, user

pytestmark = pytest.mark.django_db


def test_latest_evaluation_registry_requires_a_tenant_session_and_exposes_safe_metadata() -> None:
    anonymous = Client()
    assert anonymous.get(reverse("api-latest-evaluations")).status_code == 403

    account = user(username="m13-evaluation-reader")
    tenant = organization(name="M13 evaluation tenant", slug="m13-evaluation")
    membership(organization=tenant, user=account)
    client = Client()
    client.force_login(account)
    assert client.post(reverse("select-organization", args=[tenant.public_id])).status_code == 302

    response = client.get(reverse("api-latest-evaluations"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "m13-governance-evaluation-v1"
    assert payload["synthetic"] is True
    assert len(payload["formal_experiments"]) == 3
    assert {item["component"] for item in payload["evaluation_registry"]} == {
        "retrieval",
        "llm",
        "agent",
    }
    assert all(item["contains_customer_code"] is False for item in payload["evaluation_registry"])
    assert payload["model_registry"]["active"]["artifact_version"] == ("deterministic-heuristic-v1")
    assert "customer source" not in response.content.decode().lower()
