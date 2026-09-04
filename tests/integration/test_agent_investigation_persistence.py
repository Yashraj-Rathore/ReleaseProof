from __future__ import annotations

import json

import pytest
from django.core.exceptions import ValidationError

from adapters.agent import DeterministicAgentNodeProvider
from apps.web.analysis.agent_investigation import (
    AgentEvidenceSelection,
    run_agent_investigation,
)
from apps.web.analysis.change_intelligence import analyze_snapshot_for_organization
from apps.web.evidence.models import EvidenceItem, EvidenceKind
from packages.agent_core import EvidenceCategory
from packages.recommendation_core import (
    ComponentEvidence,
    ComponentStatus,
    RecommendationInputsV1,
)
from tests import factories
from tests.integration.test_change_intelligence_persistence import _snapshot

pytestmark = pytest.mark.django_db


def _policy_inputs() -> RecommendationInputsV1:
    clear = ComponentEvidence(
        status=ComponentStatus.AVAILABLE,
        fact="clear",
        evidence_ids=("policy:synthetic",),
    )
    return RecommendationInputsV1(
        model_risk=clear,
        retrieval=clear,
        generated_tests=clear,
        execution=clear,
        differential=clear,
        mutation=clear,
        mutation_score_percent=100,
    )


def _scope(*, suffix: str, number: int) -> tuple[object, object, object]:
    organization = factories.organization(name=f"Agent {suffix}", slug=f"agent-{suffix}")
    installation = factories.installation(
        organization=organization,
        github_installation_id=120_000 + number,
        github_account_id=121_000 + number,
    )
    repository = factories.repository(
        organization=organization,
        installation=installation,
        github_repository_id=122_000 + number,
        name=f"agent-{suffix}",
    )
    snapshot = _snapshot(
        tenant=organization,
        github_installation=installation,
        bound_repository=repository,
        label=str(number),
        path="src/agent/fixture.py",
        author_key=None,
        failed=None,
    )
    feature_set, _created = analyze_snapshot_for_organization(
        organization=organization,
        snapshot_public_id=snapshot.public_id,
    )
    return organization, repository, feature_set


def _selections(feature_set: object) -> tuple[AgentEvidenceSelection, ...]:
    rows = list(EvidenceItem.objects.filter(feature_set=feature_set).order_by("sequence")[:6])
    assert len(rows) == 6
    return tuple(
        AgentEvidenceSelection(public_id=row.public_id, category=category)
        for row, category in zip(rows, EvidenceCategory, strict=True)
    )


def test_agent_result_is_idempotent_append_only_and_contains_only_safe_trace() -> None:
    organization, _repository, feature_set = _scope(suffix="persist", number=1)
    provider = DeterministicAgentNodeProvider()
    selections = _selections(feature_set)

    first = run_agent_investigation(
        organization=organization,  # type: ignore[arg-type]
        feature_set=feature_set,  # type: ignore[arg-type]
        selections=selections,
        policy_inputs=_policy_inputs(),
        provider=provider,
    )
    repeated = run_agent_investigation(
        organization=organization,  # type: ignore[arg-type]
        feature_set=feature_set,  # type: ignore[arg-type]
        selections=selections,
        policy_inputs=_policy_inputs(),
        provider=provider,
    )

    assert first.created is True
    assert repeated.created is False
    assert repeated.evidence_item.pk == first.evidence_item.pk
    assert first.evidence_item.kind == EvidenceKind.AGENT
    assert provider.call_count == 5
    persisted = json.dumps(first.evidence_item.value, sort_keys=True)
    assert "input_text" not in persisted
    assert "source_content" not in persisted
    assert "chain_of_thought" not in persisted
    assert first.evidence_item.value["result"]["advisory_only"] is True
    assert first.evidence_item.value["result"]["auto_merge"] is False
    with pytest.raises(ValidationError):
        first.evidence_item.save()


def test_cross_tenant_evidence_and_nonlocal_provider_fail_closed() -> None:
    organization_a, _repository_a, feature_set_a = _scope(suffix="tenant-a", number=2)
    organization_b, _repository_b, feature_set_b = _scope(suffix="tenant-b", number=3)
    foreign = EvidenceItem.objects.filter(feature_set=feature_set_b).first()
    assert foreign is not None
    with pytest.raises(ValueError, match="active tenant/snapshot"):
        run_agent_investigation(
            organization=organization_a,  # type: ignore[arg-type]
            feature_set=feature_set_a,  # type: ignore[arg-type]
            selections=(
                AgentEvidenceSelection(
                    public_id=foreign.public_id,
                    category=EvidenceCategory.FEATURE,
                ),
            ),
            policy_inputs=_policy_inputs(),
            provider=DeterministicAgentNodeProvider(),
        )

    provider = DeterministicAgentNodeProvider()
    provider.local_only = False  # type: ignore[misc]
    with pytest.raises(ValueError, match="only a local provider"):
        run_agent_investigation(
            organization=organization_b,  # type: ignore[arg-type]
            feature_set=feature_set_b,  # type: ignore[arg-type]
            selections=_selections(feature_set_b),
            policy_inputs=_policy_inputs(),
            provider=provider,
        )
