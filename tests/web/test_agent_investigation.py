from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from adapters.agent import DeterministicAgentNodeProvider
from apps.web.analysis.agent_investigation import run_agent_investigation
from tests.factories import membership, user
from tests.integration.test_agent_investigation_persistence import (
    _policy_inputs,
    _scope,
    _selections,
)

pytestmark = pytest.mark.django_db


def _client_for(organization: object, *, username: str) -> Client:
    account = user(username=username)
    membership(organization=organization, user=account)
    client = Client()
    client.force_login(account)
    selected = client.post(reverse("select-organization", args=[organization.public_id]))
    assert selected.status_code == 302
    return client


def test_agent_api_and_html_render_only_the_safe_tenant_scoped_trace() -> None:
    organization, _repository, feature_set = _scope(suffix="web", number=4)
    persisted = run_agent_investigation(
        organization=organization,  # type: ignore[arg-type]
        feature_set=feature_set,  # type: ignore[arg-type]
        selections=_selections(feature_set),
        policy_inputs=_policy_inputs(),
        provider=DeterministicAgentNodeProvider(),
    )
    client = _client_for(organization, username="agent-web-reviewer")

    api = client.get(
        reverse("api-agent-investigation-detail", args=[persisted.evidence_item.public_id])
    )
    page = client.get(
        reverse("agent-investigation-detail", args=[persisted.evidence_item.public_id])
    )

    assert api.status_code == 200
    assert api.json()["result"]["termination_reason"] == "completed"
    assert api.json()["result"]["auto_merge"] is False
    assert page.status_code == 200
    assert b"Bounded agent investigation" in page.content
    assert b"Hidden chain-of-thought is neither stored nor displayed" in page.content
    assert b"cannot merge or deploy" in page.content

    other, _other_repository, _other_feature = _scope(suffix="web-other", number=5)
    denied_client = _client_for(other, username="agent-web-other")
    denied = denied_client.get(
        reverse("api-agent-investigation-detail", args=[persisted.evidence_item.public_id])
    )
    assert denied.status_code == 404
