"""Deterministic schema, citation, structured-entailment, and policy critic."""

from __future__ import annotations

from packages.agent_core.contracts import (
    AgentDraft,
    CriticResult,
    CriticVerdict,
    EvidenceCategory,
    EvidenceReference,
)
from packages.recommendation_core import Recommendation, RecommendationDecisionV1


def critique_draft(
    draft: AgentDraft,
    *,
    evidence: tuple[EvidenceReference, ...],
    policy_decision: RecommendationDecisionV1,
) -> CriticResult:
    """Check exact structured facts; this is independent of any generating model."""

    evidence_by_id = {item.evidence_id: item for item in evidence}
    reasons: set[str] = set()
    supported = 0
    factual_claims = tuple(claim for claim in draft.claims if not claim.hypothesis)
    for claim in factual_claims:
        cited = tuple(evidence_by_id.get(identifier) for identifier in claim.evidence_ids)
        if any(item is None for item in cited):
            reasons.add("citation_not_returned_by_tool")
            continue
        supported_facts = {fact for item in cited if item is not None for fact in item.fact_codes}
        if not set(claim.fact_codes).issubset(supported_facts):
            reasons.add("claim_not_entailed_by_structured_facts")
            continue
        supported += 1

    if draft.proposed_recommendation is not policy_decision.recommendation:
        reasons.add("recommendation_conflicts_with_deterministic_policy")
    if draft.missing_categories and draft.confidence != "low":
        reasons.add("missing_evidence_requires_low_confidence")
    execution_failed = any(
        item.category is EvidenceCategory.EXECUTION and "execution:failed" in item.fact_codes
        for item in evidence
    )
    if execution_failed and draft.proposed_recommendation is Recommendation.SHIP:
        reasons.add("execution_failure_cannot_ship")
    if not draft.advisory_only or draft.auto_merge:
        reasons.add("agent_authority_violation")

    ordered = tuple(sorted(reasons))
    return CriticResult(
        verdict=CriticVerdict.REJECT if ordered else CriticVerdict.ACCEPT,
        reason_codes=ordered,
        claim_count=len(factual_claims),
        supported_claim_count=supported,
    )
