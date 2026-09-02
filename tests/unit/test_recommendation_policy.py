from __future__ import annotations

from dataclasses import replace

from packages.recommendation_core import (
    ComponentEvidence,
    ComponentStatus,
    Recommendation,
    RecommendationInputsV1,
    fuse_recommendation,
)


def _component(
    name: str,
    *,
    status: ComponentStatus = ComponentStatus.AVAILABLE,
    fact: str = "clear",
    hold: bool = False,
) -> ComponentEvidence:
    return ComponentEvidence(
        status=status,
        fact=fact,
        evidence_ids=(f"evidence:{name}",),
        deterministic_hold=hold,
    )


def _inputs() -> RecommendationInputsV1:
    return RecommendationInputsV1(
        model_risk=_component("risk"),
        retrieval=_component("retrieval"),
        generated_tests=_component("tests"),
        execution=_component("execution"),
        differential=_component("differential"),
        mutation=_component("mutation"),
        mutation_score_percent=100,
    )


def test_clear_complete_evidence_is_advisory_ship_only() -> None:
    decision = fuse_recommendation(_inputs())

    assert decision.recommendation is Recommendation.SHIP
    assert decision.advisory_only is True
    assert decision.auto_merge is False
    assert len(decision.decision_sha256) == 64


def test_missing_or_failed_mandatory_evidence_is_unknown() -> None:
    missing = replace(_inputs(), retrieval=_component("retrieval", status=ComponentStatus.MISSING))
    failed = replace(_inputs(), execution=_component("execution", status=ComponentStatus.FAILED))

    assert fuse_recommendation(missing).recommendation is Recommendation.UNKNOWN
    assert fuse_recommendation(failed).recommendation is Recommendation.UNKNOWN


def test_deterministic_hold_has_precedence_over_llm_ship() -> None:
    inputs = replace(
        _inputs(),
        differential=_component("differential", fact="regression", hold=True),
        llm_suggestion=Recommendation.SHIP,
    )
    decision = fuse_recommendation(inputs)

    assert decision.recommendation is Recommendation.HOLD
    assert decision.reason_codes == ("differential_deterministic_hold",)


def test_surviving_mutations_or_low_score_require_review() -> None:
    survived = replace(
        _inputs(),
        mutation=_component("mutation", fact="survived"),
        mutation_score_percent=50,
    )
    low = replace(_inputs(), mutation_score_percent=0)

    assert fuse_recommendation(survived).recommendation is Recommendation.REVIEW
    assert fuse_recommendation(low).recommendation is Recommendation.REVIEW
