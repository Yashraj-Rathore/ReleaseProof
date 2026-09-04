"""LangGraph-backed bounded investigation with no autonomous authority."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from typing import TypedDict, cast

from langgraph.graph import END, START, StateGraph

from packages.agent_core.contracts import (
    AgentDraft,
    AgentNode,
    AgentNodeProvider,
    AgentTraceEvent,
    CriticResult,
    CriticVerdict,
    EvidenceCategory,
    EvidenceReference,
    InvestigationRequest,
    InvestigationResult,
    NodeInput,
    NodeOutput,
    TerminationReason,
    ToolName,
    ToolStatus,
)
from packages.agent_core.critic import critique_draft
from packages.agent_core.guards import AgentStopError, BudgetGuard
from packages.agent_core.tools import TOOL_CATEGORY, BoundedInvestigationTools
from packages.recommendation_core import Recommendation


class AgentGraphState(TypedDict):
    request: InvestigationRequest
    collected: tuple[EvidenceReference, ...]
    outputs: tuple[NodeOutput, ...]
    missing_categories: tuple[EvidenceCategory, ...]
    trace: tuple[AgentTraceEvent, ...]
    errors: tuple[str, ...]
    draft: AgentDraft | None
    critic: CriticResult | None
    termination: TerminationReason | None
    partial: bool


_NODE_TOOLS: dict[AgentNode, tuple[ToolName, ...]] = {
    AgentNode.CHANGE_ANALYST: (ToolName.GET_FEATURES, ToolName.GET_GRAPH),
    AgentNode.HISTORICAL_INVESTIGATOR: (ToolName.SEARCH_HISTORY,),
    AgentNode.RISK_SYNTHESIZER: (ToolName.GET_RISK,),
    AgentNode.TEST_PLANNER: (ToolName.GET_TEST_RESULTS,),
    AgentNode.EXECUTION_READER: (ToolName.GET_EXECUTION_EVIDENCE,),
}


def _signature(state: AgentGraphState, node: AgentNode) -> str:
    material = "|".join(
        (
            node.value,
            *(item.evidence_id for item in state["collected"]),
            *state["errors"],
        )
    )
    return hashlib.sha256(material.encode()).hexdigest()


def _event(
    state: AgentGraphState,
    *,
    event_type: str,
    node: AgentNode,
    status: str,
    summary: str,
    evidence_ids: tuple[str, ...] = (),
    elapsed_ms: float = 0.0,
) -> AgentTraceEvent:
    return AgentTraceEvent(
        sequence=len(state["trace"]),
        event_type=event_type,
        node=node,
        status=status,
        summary=summary,
        evidence_ids=evidence_ids,
        elapsed_ms=elapsed_ms,
    )


def _stop_state(
    state: AgentGraphState,
    stop: AgentStopError,
    *,
    node: AgentNode,
) -> AgentGraphState:
    error_codes = tuple(dict.fromkeys((*state["errors"], stop.error_code)))
    trace = (
        *state["trace"],
        _event(
            state,
            event_type="termination",
            node=node,
            status=stop.reason.value,
            summary=f"Investigation stopped: {stop.error_code}.",
        ),
    )
    return {
        **state,
        "errors": error_codes,
        "partial": True,
        "termination": stop.reason,
        "trace": trace,
    }


def _provider_node(
    state: AgentGraphState,
    *,
    node: AgentNode,
    tools: BoundedInvestigationTools,
    provider: AgentNodeProvider,
    guard: BudgetGuard,
) -> AgentGraphState:
    try:
        started = guard.enter_node(node, state_signature=_signature(state, node))
        collected = list(state["collected"])
        known = {item.evidence_id for item in collected}
        missing = set(state["missing_categories"])
        errors = list(state["errors"])
        trace = list(state["trace"])
        for tool_name in _NODE_TOOLS[node]:
            guard.reserve_tool()
            result = tools.read(tool_name)
            if result.status is ToolStatus.FAILED:
                guard.record_tool_error()
                if result.error_code is not None:
                    errors.append(result.error_code)
                missing.add(TOOL_CATEGORY[tool_name])
            elif result.status is ToolStatus.MISSING:
                missing.add(TOOL_CATEGORY[tool_name])
            for reference in result.evidence:
                if reference.evidence_id not in known:
                    collected.append(reference)
                    known.add(reference.evidence_id)
            trace.append(
                AgentTraceEvent(
                    sequence=len(trace),
                    event_type="tool",
                    node=node,
                    status=result.status.value,
                    summary=result.summary,
                    evidence_ids=tuple(item.evidence_id for item in result.evidence),
                    elapsed_ms=0.0,
                )
            )
        remaining_input, remaining_output, remaining_cost = guard.reserve_llm()
        node_input = NodeInput(
            node=node,
            snapshot_id=state["request"].snapshot_id,
            evidence=tuple(collected),
            missing_categories=tuple(sorted(missing, key=lambda item: item.value)),
            policy_recommendation=state["request"].policy_decision.recommendation,
            max_input_tokens=remaining_input,
            max_output_tokens=min(remaining_output, state["request"].limits.max_output_tokens),
            max_cost_microusd=remaining_cost,
            timeout_seconds=min(
                state["request"].limits.per_node_timeout_seconds,
                state["request"].limits.max_wall_time_seconds,
            ),
            cancelled=False,
        )
        if remaining_input <= 0:
            raise AgentStopError(
                TerminationReason.LLM_BUDGET_EXCEEDED,
                "agent_llm_input_budget_exceeded",
            )
        try:
            output = provider.generate_node(node_input)
        except Exception as error:
            del error
            raise AgentStopError(
                TerminationReason.PROVIDER_FAILURE,
                "agent_provider_failure",
            ) from None
        if output.node is not node:
            raise AgentStopError(
                TerminationReason.PROVIDER_FAILURE,
                "agent_provider_node_mismatch",
            )
        guard.record_llm(output.usage)
        elapsed_ms = guard.finish_node(started)
        trace.append(
            AgentTraceEvent(
                sequence=len(trace),
                event_type="node",
                node=node,
                status="completed",
                summary=output.safe_summary,
                evidence_ids=tuple(
                    dict.fromkeys(
                        evidence_id for claim in output.claims for evidence_id in claim.evidence_ids
                    )
                ),
                elapsed_ms=elapsed_ms,
            )
        )
        return {
            **state,
            "collected": tuple(collected),
            "errors": tuple(dict.fromkeys(errors)),
            "missing_categories": tuple(sorted(missing, key=lambda item: item.value)),
            "outputs": (*state["outputs"], output),
            "trace": tuple(trace),
        }
    except AgentStopError as stop:
        return _stop_state(state, stop, node=node)


def _critic_node(state: AgentGraphState, *, guard: BudgetGuard) -> AgentGraphState:
    node = AgentNode.EVIDENCE_CRITIC
    try:
        started = guard.enter_node(node, state_signature=_signature(state, node))
        proposed = next(
            (
                output.proposed_recommendation
                for output in reversed(state["outputs"])
                if output.proposed_recommendation is not None
            ),
            Recommendation.UNKNOWN,
        )
        claims = tuple(claim for output in state["outputs"] for claim in output.claims)
        draft = AgentDraft(
            proposed_recommendation=proposed,
            claims=claims,
            missing_categories=state["missing_categories"],
            confidence="low" if state["missing_categories"] or state["errors"] else "high",
        )
        critic = critique_draft(
            draft,
            evidence=state["collected"],
            policy_decision=state["request"].policy_decision,
        )
        elapsed_ms = guard.finish_node(started)
        trace = (
            *state["trace"],
            _event(
                state,
                event_type="critic",
                node=node,
                status=critic.verdict.value,
                summary=(
                    "Deterministic schema, citation, fact-entailment, and policy checks passed."
                    if critic.verdict is CriticVerdict.ACCEPT
                    else "Deterministic critic rejected the draft."
                ),
                evidence_ids=tuple(item.evidence_id for item in state["collected"]),
                elapsed_ms=elapsed_ms,
            ),
        )
        if critic.verdict is CriticVerdict.REJECT:
            return {
                **state,
                "critic": critic,
                "draft": draft,
                "errors": tuple(dict.fromkeys((*state["errors"], *critic.reason_codes))),
                "partial": True,
                "termination": TerminationReason.CRITIC_REJECTED,
                "trace": trace,
            }
        return {**state, "critic": critic, "draft": draft, "trace": trace}
    except AgentStopError as stop:
        return _stop_state(state, stop, node=node)


def _composer_node(state: AgentGraphState, *, guard: BudgetGuard) -> AgentGraphState:
    node = AgentNode.RECOMMENDATION_COMPOSER
    try:
        started = guard.enter_node(node, state_signature=_signature(state, node))
        if state["errors"]:
            termination = TerminationReason.TOOL_FAILURE
            partial = True
            status = "partial"
            summary = "Tool evidence was incomplete; the safe partial recommendation is UNKNOWN."
        else:
            termination = TerminationReason.COMPLETED
            partial = False
            status = "completed"
            summary = "Deterministic policy was preserved for human review."
        elapsed_ms = guard.finish_node(started)
        trace = (
            *state["trace"],
            _event(
                state,
                event_type="result",
                node=node,
                status=status,
                summary=summary,
                evidence_ids=tuple(item.evidence_id for item in state["collected"]),
                elapsed_ms=elapsed_ms,
            ),
        )
        return {
            **state,
            "partial": partial,
            "termination": termination,
            "trace": trace,
        }
    except AgentStopError as stop:
        return _stop_state(state, stop, node=node)


def _continue_or_end(state: AgentGraphState) -> str:
    return "end" if state["termination"] is not None else "continue"


def _after_tests(state: AgentGraphState) -> str:
    if state["termination"] is not None:
        return "end"
    return (
        "execution"
        if any(item.category is EvidenceCategory.EXECUTION for item in state["request"].evidence)
        else "critic"
    )


def _safe_recommendation(state: AgentGraphState) -> Recommendation:
    policy = state["request"].policy_decision.recommendation
    if state["termination"] is TerminationReason.COMPLETED:
        return policy
    return Recommendation.HOLD if policy is Recommendation.HOLD else Recommendation.UNKNOWN


def run_investigation(
    request: InvestigationRequest,
    *,
    tools: BoundedInvestigationTools,
    provider: AgentNodeProvider,
    cancellation_check: Callable[[], bool] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> InvestigationResult:
    """Run one graph without a native checkpointer; only the returned safe result is persistable."""

    guard = BudgetGuard(
        request.limits,
        cancellation_check=lambda: (
            request.cancelled or (cancellation_check() if cancellation_check is not None else False)
        ),
        clock=clock,
    )
    graph = StateGraph(AgentGraphState)
    graph.add_node(
        AgentNode.CHANGE_ANALYST.value,
        lambda state: _provider_node(
            state,
            node=AgentNode.CHANGE_ANALYST,
            tools=tools,
            provider=provider,
            guard=guard,
        ),
    )
    graph.add_node(
        AgentNode.HISTORICAL_INVESTIGATOR.value,
        lambda state: _provider_node(
            state,
            node=AgentNode.HISTORICAL_INVESTIGATOR,
            tools=tools,
            provider=provider,
            guard=guard,
        ),
    )
    graph.add_node(
        AgentNode.RISK_SYNTHESIZER.value,
        lambda state: _provider_node(
            state,
            node=AgentNode.RISK_SYNTHESIZER,
            tools=tools,
            provider=provider,
            guard=guard,
        ),
    )
    graph.add_node(
        AgentNode.TEST_PLANNER.value,
        lambda state: _provider_node(
            state,
            node=AgentNode.TEST_PLANNER,
            tools=tools,
            provider=provider,
            guard=guard,
        ),
    )
    graph.add_node(
        AgentNode.EXECUTION_READER.value,
        lambda state: _provider_node(
            state,
            node=AgentNode.EXECUTION_READER,
            tools=tools,
            provider=provider,
            guard=guard,
        ),
    )
    graph.add_node(
        AgentNode.EVIDENCE_CRITIC.value,
        lambda state: _critic_node(state, guard=guard),
    )
    graph.add_node(
        AgentNode.RECOMMENDATION_COMPOSER.value,
        lambda state: _composer_node(state, guard=guard),
    )
    graph.add_edge(START, AgentNode.CHANGE_ANALYST.value)
    ordered_edges = (
        (AgentNode.CHANGE_ANALYST, AgentNode.HISTORICAL_INVESTIGATOR),
        (AgentNode.HISTORICAL_INVESTIGATOR, AgentNode.RISK_SYNTHESIZER),
        (AgentNode.RISK_SYNTHESIZER, AgentNode.TEST_PLANNER),
    )
    for current, following in ordered_edges:
        graph.add_conditional_edges(
            current.value,
            _continue_or_end,
            {"continue": following.value, "end": END},
        )
    graph.add_conditional_edges(
        AgentNode.TEST_PLANNER.value,
        _after_tests,
        {
            "execution": AgentNode.EXECUTION_READER.value,
            "critic": AgentNode.EVIDENCE_CRITIC.value,
            "end": END,
        },
    )
    graph.add_conditional_edges(
        AgentNode.EXECUTION_READER.value,
        _continue_or_end,
        {"continue": AgentNode.EVIDENCE_CRITIC.value, "end": END},
    )
    graph.add_conditional_edges(
        AgentNode.EVIDENCE_CRITIC.value,
        _continue_or_end,
        {"continue": AgentNode.RECOMMENDATION_COMPOSER.value, "end": END},
    )
    graph.add_edge(AgentNode.RECOMMENDATION_COMPOSER.value, END)
    initial: AgentGraphState = {
        "request": request,
        "collected": (),
        "outputs": (),
        "missing_categories": (),
        "trace": (),
        "errors": (),
        "draft": None,
        "critic": None,
        "termination": None,
        "partial": False,
    }
    final = cast(
        AgentGraphState,
        graph.compile().invoke(
            initial,
            config={
                "callbacks": [],
                "recursion_limit": request.limits.max_steps + 2,
            },
        ),
    )
    termination = final["termination"] or TerminationReason.PROVIDER_FAILURE
    errors = final["errors"]
    if final["termination"] is None:
        errors = tuple(dict.fromkeys((*errors, "agent_missing_termination")))
    return InvestigationResult(
        run_id=request.run_id,
        snapshot_id=request.snapshot_id,
        recommendation=_safe_recommendation(final),
        termination_reason=termination,
        partial=termination is not TerminationReason.COMPLETED,
        evidence_ids=tuple(item.evidence_id for item in final["collected"]),
        draft=final["draft"],
        critic=final["critic"],
        trace=final["trace"],
        usage=guard.usage,
        error_codes=errors,
        policy_decision_sha256=request.policy_decision.decision_sha256,
        request_sha256=request.request_sha256,
    )
