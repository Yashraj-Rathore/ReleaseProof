from __future__ import annotations

import pytest

from apps.web.analysis.change_intelligence import analyze_snapshot_for_organization
from apps.web.risk.models import RiskScore
from apps.web.risk.services import persist_deterministic_score
from packages.ml_core import (
    BASELINE_ARTIFACT_VERSION,
    SELECTED_THRESHOLD,
    THRESHOLD_POLICY_VERSION,
    RiskBand,
    baseline_artifact_hash,
)
from tests.factories import installation, organization, repository
from tests.integration.test_change_intelligence_persistence import _snapshot

pytestmark = pytest.mark.django_db


def test_analysis_persists_one_versioned_non_probability_baseline_score() -> None:
    tenant = organization(name="M4 Risk Tenant", slug="m4-risk")
    github_installation = installation(
        organization=tenant,
        github_installation_id=7101,
        github_account_id=7201,
    )
    bound_repository = repository(
        organization=tenant,
        installation=github_installation,
        github_repository_id=7301,
        name="releaseproof",
    )
    snapshot = _snapshot(
        tenant=tenant,
        github_installation=github_installation,
        bound_repository=bound_repository,
        label="7",
        path="src/auth/risk_policy.py",
        author_key=None,
        failed=None,
    )

    feature_set, created = analyze_snapshot_for_organization(
        organization=tenant,
        snapshot_public_id=snapshot.public_id,
    )
    assert created is True
    score = RiskScore.objects.get(feature_set=feature_set)
    assert score.raw_score == 35
    assert score.band == RiskBand.MEDIUM
    assert score.proxy_prediction is True
    assert score.calibrated_probability is None
    assert score.threshold == SELECTED_THRESHOLD
    assert score.artifact_version == BASELINE_ARTIFACT_VERSION
    assert score.artifact_hash == baseline_artifact_hash()
    assert score.threshold_policy_version == THRESHOLD_POLICY_VERSION
    assert score.feature_schema_version == feature_set.feature_schema_version
    assert score.contributions

    repeated, repeated_created = persist_deterministic_score(
        organization=tenant,
        feature_set=feature_set,
    )
    assert repeated_created is False
    assert repeated.pk == score.pk
    assert RiskScore.objects.count() == 1
