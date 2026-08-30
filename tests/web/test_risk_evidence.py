from __future__ import annotations

from functools import lru_cache
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse

from apps.web.analysis.change_intelligence import analyze_snapshot_for_organization
from apps.web.organizations.models import Organization
from eng.evaluate_m4_baseline import build_fixture_dataset
from packages.ml_core import (
    BASELINE_ARTIFACT_VERSION,
    ModelCompatibilityError,
    train_classical_models,
)
from tests.factories import installation, membership, organization, repository, user
from tests.integration.test_change_intelligence_persistence import _snapshot

pytestmark = pytest.mark.django_db


@lru_cache(maxsize=1)
def _model_artifact() -> dict[str, object]:
    dataset = build_fixture_dataset(extraction_code_commit="a" * 40)
    return train_classical_models(dataset, training_code_commit="b" * 40)


def _active_client(*, slug: str) -> tuple[Client, Organization]:
    account = user(username=f"{slug}-member")
    tenant = organization(name=f"{slug} tenant", slug=slug)
    membership(organization=tenant, user=account)
    client = Client()
    client.force_login(account)
    selected = client.post(reverse("select-organization", args=[tenant.public_id]))
    assert selected.status_code == 302
    return client, tenant


def test_current_model_api_and_ui_keep_the_heuristic_active() -> None:
    client, _tenant = _active_client(slug="model-view")

    with patch(
        "apps.web.risk.artifacts.load_public_model_artifact",
        return_value=_model_artifact(),
    ):
        response = client.get(reverse("api-current-model"))
        page = client.get(reverse("current-model"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["active"]["artifact_version"] == BASELINE_ARTIFACT_VERSION
    assert payload["active"]["decision"] == "keep_deterministic_heuristic"
    assert payload["active"]["probability_display_allowed"] is False
    assert len(payload["candidates"]) == 2
    assert all(item["probability_display_allowed"] is False for item in payload["candidates"])
    assert page.status_code == 200
    assert b"this is a risk score, not a probability" in page.content
    assert b"candidate_not_promoted" in page.content


def test_invalid_learned_artifact_falls_back_without_erasing_deterministic_evidence() -> None:
    client, _tenant = _active_client(slug="model-fallback")

    with patch(
        "apps.web.risk.artifacts.load_public_model_artifact",
        side_effect=ModelCompatibilityError("invalid"),
    ):
        response = client.get(reverse("api-current-model"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["active"]["artifact_version"] == BASELINE_ARTIFACT_VERSION
    assert payload["active"]["decision"] == "fallback_model_artifact_unavailable"
    assert payload["candidates"] == []
    assert payload["evaluation_artifact_hash"] is None


def test_snapshot_risk_api_and_ui_are_tenant_scoped_and_never_show_probability() -> None:
    client, tenant = _active_client(slug="risk-view")
    github_installation = installation(
        organization=tenant,
        github_installation_id=8101,
        github_account_id=8201,
    )
    bound_repository = repository(
        organization=tenant,
        installation=github_installation,
        github_repository_id=8301,
        name="releaseproof",
    )
    snapshot = _snapshot(
        tenant=tenant,
        github_installation=github_installation,
        bound_repository=bound_repository,
        label="11",
        path="src/auth/session.py",
        author_key=None,
        failed=None,
    )
    analyze_snapshot_for_organization(
        organization=tenant,
        snapshot_public_id=snapshot.public_id,
    )

    api_response = client.get(reverse("api-snapshot-risk", args=[snapshot.public_id]))
    page = client.get(reverse("snapshot-risk", args=[snapshot.public_id]))

    assert api_response.status_code == 200
    payload = api_response.json()
    assert payload["artifact_version"] == BASELINE_ARTIFACT_VERSION
    assert payload["calibrated_probability"] is None
    assert payload["probability_display_allowed"] is False
    assert payload["contributions"]
    assert page.status_code == 200
    assert b"not a calibrated probability" in page.content
    assert b"Evidence-backed components" in page.content

    other_tenant = organization(name="Other tenant", slug="risk-other")
    other_installation = installation(
        organization=other_tenant,
        github_installation_id=8102,
        github_account_id=8202,
    )
    other_repository = repository(
        organization=other_tenant,
        installation=other_installation,
        github_repository_id=8302,
        name="hidden",
    )
    hidden_snapshot = _snapshot(
        tenant=other_tenant,
        github_installation=other_installation,
        bound_repository=other_repository,
        label="12",
        path="src/private.py",
        author_key=None,
        failed=None,
    )
    denied = client.get(reverse("api-snapshot-risk", args=[hidden_snapshot.public_id]))
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "not_found"
