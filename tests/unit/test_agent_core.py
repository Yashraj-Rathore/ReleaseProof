from __future__ import annotations

import pytest

from adapters.agent import DeterministicAgentNodeProvider
from packages.agent_core import (
    AgentClaim,
    AgentDraft,
    AgentLimits,
    AgentNode,
    AgentStopError,
    BoundedInvestigationTools,
    BudgetGuard,
    CriticVerdict,
    EvidenceCategory,
    EvidenceReference,
    InvestigationRequest,
    NodeInput,
    NodeOutput,
    NodeProviderUsage,
    TerminationReason,
    ToolName,
    critique_draft,
    run_investigation,
)
from packages.recommendation_core import (
    ComponentEvidence,
    ComponentStatus,
    Recommendation,
    RecommendationInputsV1,
    fuse_recommendation,
)


def _policy(*, recommendation: Recommendation = Recommendation.SHIP) -> object:
    status = (
        ComponentEvidence(
            status=ComponentStatus.AVAILABLE,
            fact="clear",
            evidence_ids=("policy:evidence",),
        )
        if recommendation is Recommendation.SHIP
        else ComponentEvidence(
            status=ComponentStatus.AVAILABLE,
            fact="failed",
            evidence_ids=("policy:evidence",),
            deterministic_hold=True,
        )
    )
    inputs = RecommendationInputsV1(
        model_risk=status,
        retrieval=status,
        generated_tests=status,
        execution=status,
        differential=status,
        mutation=status,
        mutation_score_percent=100,
    )
    return fuse_recommendation(inputs)


def _evidence() -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            evidence_id=f"evidence:{category.value}",
            category=category,
            summary=f"Synthetic {category.value} evidence.",
            source_reference=f"fixture:{category.value}",
            fact_codes=(f"{category.value}:clear",),
        )
        for category in EvidenceCategory
    )


def _request(
    *,
    limits: AgentLimits | None = None,
    cancelled: bool = False,
) -> InvestigationRequest:
    return InvestigationRequest(
        run_id="agent:test-run",
        snapshot_id="snapshot:test",
        evidence=_evidence(),
        policy_decision=_policy(),  # type: ignore[arg-type]
        limits=limits or AgentLimits(),
        cancelled=cancelled,
    )


def test_graph_completes_with_typed_grounded_advisory_trace() -> None:
    request = _request()
    provider = DeterministicAgentNodeProvider()
    tools = BoundedInvestigationTools(request.evidence, request.limits)

    result = run_investigation(request, tools=tools, provider=provider)

    assert result.termination_reason is TerminationReason.COMPLETED
    assert result.recommendation is Recommendation.SHIP
    assert result.partial is False
    assert result.critic is not None
    assert result.critic.verdict is CriticVerdict.ACCEPT
    assert result.critic.groundedness_rate == 1.0
    assert result.usage.steps == 7
    assert result.usage.tool_calls == 6
    assert result.usage.llm_calls == 5
    assert provider.call_count == 5
    assert result.auto_merge is False
    assert "chain_of_thought" not in result.safe_dict()


def test_read_only_tools_are_bounded_and_have_no_mutation_authority() -> None:
    limits = AgentLimits(max_evidence_per_tool=1)
    duplicate_category = (
        *_evidence(),
        EvidenceReference(
            evidence_id="evidence:feature-two",
            category=EvidenceCategory.FEATURE,
            summary="Second bounded feature summary.",
            source_reference="fixture:feature-two",
            fact_codes=("feature:second",),
        ),
    )
    tools = BoundedInvestigationTools(duplicate_category, limits)

    result = tools.read(ToolName.GET_FEATURES)

    assert len(result.evidence) == 1
    assert result.truncated is True
    for forbidden in ("merge", "deploy", "write_repository", "request_execution"):
        assert not hasattr(tools, forbidden)


def test_cancellation_and_step_budget_return_explicit_safe_partial_results() -> None:
    cancelled_request = _request(cancelled=True)
    cancelled_provider = DeterministicAgentNodeProvider()
    cancelled = run_investigation(
        cancelled_request,
        tools=BoundedInvestigationTools(cancelled_request.evidence, cancelled_request.limits),
        provider=cancelled_provider,
    )
    assert cancelled.termination_reason is TerminationReason.CANCELLED
    assert cancelled.recommendation is Recommendation.UNKNOWN
    assert cancelled.partial is True
    assert cancelled_provider.call_count == 0

    limited_request = _request(limits=AgentLimits(max_steps=2))
    limited = run_investigation(
        limited_request,
        tools=BoundedInvestigationTools(limited_request.evidence, limited_request.limits),
        provider=DeterministicAgentNodeProvider(),
    )
    assert limited.termination_reason is TerminationReason.STEP_BUDGET_EXCEEDED
    assert limited.recommendation is Recommendation.UNKNOWN
    assert limited.usage.steps == 2


def test_tool_failure_is_visible_and_cannot_produce_ship() -> None:
    request = _request()
    result = run_investigation(
        request,
        tools=BoundedInvestigationTools(
            request.evidence,
            request.limits,
            failed_tools=(ToolName.SEARCH_HISTORY,),
        ),
        provider=DeterministicAgentNodeProvider(),
    )

    assert result.termination_reason is TerminationReason.TOOL_FAILURE
    assert result.recommendation is Recommendation.UNKNOWN
    assert result.usage.tool_errors == 1
    assert "search_history_failed" in result.error_codes


def test_tool_provider_call_and_output_budgets_fail_closed() -> None:
    tool_request = _request(limits=AgentLimits(max_tool_calls=1))
    tool_limited = run_investigation(
        tool_request,
        tools=BoundedInvestigationTools(tool_request.evidence, tool_request.limits),
        provider=DeterministicAgentNodeProvider(),
    )
    assert tool_limited.termination_reason is TerminationReason.TOOL_BUDGET_EXCEEDED
    assert tool_limited.recommendation is Recommendation.UNKNOWN

    call_request = _request(limits=AgentLimits(max_llm_calls=1))
    call_limited = run_investigation(
        call_request,
        tools=BoundedInvestigationTools(call_request.evidence, call_request.limits),
        provider=DeterministicAgentNodeProvider(),
    )
    assert call_limited.termination_reason is TerminationReason.LLM_BUDGET_EXCEEDED
    assert call_limited.usage.llm_calls == 1

    output_request = _request(limits=AgentLimits(max_output_tokens=64))
    output_limited = run_investigation(
        output_request,
        tools=BoundedInvestigationTools(output_request.evidence, output_request.limits),
        provider=DeterministicAgentNodeProvider(),
    )
    assert output_limited.termination_reason is TerminationReason.LLM_BUDGET_EXCEEDED
    assert output_limited.recommendation is Recommendation.UNKNOWN


def test_independent_critic_rejects_unknown_facts_and_policy_override() -> None:
    evidence = _evidence()
    draft = AgentDraft(
        proposed_recommendation=Recommendation.SHIP,
        claims=(
            AgentClaim(
                statement="This claim invents a fact not present in its citation.",
                evidence_ids=(evidence[0].evidence_id,),
                fact_codes=("invented:fact",),
            ),
        ),
        missing_categories=(),
        confidence="high",
    )

    result = critique_draft(
        draft,
        evidence=evidence,
        policy_decision=_policy(recommendation=Recommendation.HOLD),  # type: ignore[arg-type]
    )

    assert result.verdict is CriticVerdict.REJECT
    assert "claim_not_entailed_by_structured_facts" in result.reason_codes
    assert "recommendation_conflicts_with_deterministic_policy" in result.reason_codes


def test_loop_and_node_timeout_guards_fail_closed() -> None:
    guard = BudgetGuard(AgentLimits())
    guard.enter_node(AgentNode.CHANGE_ANALYST, state_signature="same")
    with pytest.raises(AgentStopError) as loop:
        guard.enter_node(AgentNode.CHANGE_ANALYST, state_signature="same")
    assert loop.value.reason is TerminationReason.LOOP_DETECTED

    now = 0.0

    def clock() -> float:
        return now

    timeout_guard = BudgetGuard(
        AgentLimits(max_wall_time_seconds=20.0, per_node_timeout_seconds=1.0),
        clock=clock,
    )
    started = timeout_guard.enter_node(AgentNode.CHANGE_ANALYST, state_signature="first")
    now = 2.0
    with pytest.raises(AgentStopError) as timeout:
        timeout_guard.finish_node(started)
    assert timeout.value.reason is TerminationReason.NODE_TIMEOUT


class _WrongNodeProvider(DeterministicAgentNodeProvider):
    def generate_node(self, request: NodeInput) -> NodeOutput:
        return NodeOutput(
            node=AgentNode.RECOMMENDATION_COMPOSER,
            safe_summary="Invalid node identity.",
            claims=(),
            usage=NodeProviderUsage(0, 1, 0, 0.0),
        )


def test_provider_schema_failure_returns_unknown_without_leaking_error() -> None:
    request = _request()
    result = run_investigation(
        request,
        tools=BoundedInvestigationTools(request.evidence, request.limits),
        provider=_WrongNodeProvider(),
    )

    assert result.termination_reason is TerminationReason.PROVIDER_FAILURE
    assert result.recommendation is Recommendation.UNKNOWN
    assert result.error_codes == ("agent_provider_node_mismatch",)


class _OverrideProvider(DeterministicAgentNodeProvider):
    def generate_node(self, request: NodeInput) -> NodeOutput:
        output = super().generate_node(request)
        if request.node is AgentNode.TEST_PLANNER:
            return NodeOutput(
                node=output.node,
                safe_summary=output.safe_summary,
                claims=output.claims,
                usage=output.usage,
                proposed_recommendation=Recommendation.SHIP,
            )
        return output


def test_generator_cannot_override_deterministic_hold() -> None:
    request = InvestigationRequest(
        run_id="agent:hold-override",
        snapshot_id="snapshot:hold-override",
        evidence=_evidence(),
        policy_decision=_policy(recommendation=Recommendation.HOLD),  # type: ignore[arg-type]
    )
    result = run_investigation(
        request,
        tools=BoundedInvestigationTools(request.evidence, request.limits),
        provider=_OverrideProvider(),
    )

    assert result.termination_reason is TerminationReason.CRITIC_REJECTED
    assert result.recommendation is Recommendation.HOLD
    assert result.critic is not None
    assert "recommendation_conflicts_with_deterministic_policy" in result.critic.reason_codes
