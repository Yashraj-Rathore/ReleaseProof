"""Deterministic, local-only agent node provider used by tests and demos."""

from __future__ import annotations

from packages.agent_core.contracts import (
    AgentClaim,
    AgentNode,
    NodeInput,
    NodeOutput,
    NodeProviderUsage,
)


class DeterministicAgentNodeProvider:
    provider_name = "deterministic_fake"
    model_id = "deterministic-agent-node-v1"
    adapter_version = "deterministic-agent-adapter-v1"
    local_only = True

    def __init__(self) -> None:
        self.call_count = 0

    def generate_node(self, request: NodeInput) -> NodeOutput:
        self.call_count += 1
        if request.cancelled:
            raise RuntimeError("cancelled")
        if request.evidence:
            reference = request.evidence[-1]
            fact = reference.fact_codes[0]
            claims = (
                AgentClaim(
                    statement="A structured fact was returned by an authorized read-only tool.",
                    evidence_ids=(reference.evidence_id,),
                    fact_codes=(fact,),
                ),
            )
            summary = f"Reviewed {len(request.evidence)} bounded evidence reference(s)."
        else:
            claims = (
                AgentClaim(
                    statement="No authorized evidence has been collected at this node.",
                    evidence_ids=(),
                    fact_codes=(),
                    hypothesis=True,
                ),
            )
            summary = "No authorized evidence was available; uncertainty remains explicit."
        input_tokens = sum(
            len(item.summary.encode()) + sum(len(fact) for fact in item.fact_codes)
            for item in request.evidence
        )
        output_tokens = len(summary.encode()) + sum(
            len(claim.statement.encode()) for claim in claims
        )
        return NodeOutput(
            node=request.node,
            safe_summary=summary,
            claims=claims,
            usage=NodeProviderUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_microusd=0,
                elapsed_ms=0.0,
            ),
            proposed_recommendation=(
                request.policy_recommendation if request.node is AgentNode.TEST_PLANNER else None
            ),
        )
