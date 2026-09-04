"""Versioned, immutable contracts for advisory agent investigations."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from packages.recommendation_core import Recommendation, RecommendationDecisionV1

AGENT_GRAPH_VERSION = "bounded-investigation-graph-v1"
AGENT_STATE_SCHEMA_VERSION = "agent-state-v1"
AGENT_EVALUATION_VERSION = "m12-agent-eval-v1"


def _identifier(value: str, *, field: str, maximum: int = 192) -> None:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or not value.isascii()
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{field} must be bounded printable ASCII")


def _text(value: str, *, field: str, maximum: int) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or "\x00" in value:
        raise ValueError(f"{field} must contain 1..{maximum} safe characters")


def _identifiers(values: tuple[str, ...], *, field: str, maximum: int = 64) -> None:
    if len(values) > maximum or len(set(values)) != len(values):
        raise ValueError(f"{field} must be a bounded unique tuple")
    for value in values:
        _identifier(value, field=field)


class EvidenceCategory(StrEnum):
    FEATURE = "feature"
    GRAPH = "graph"
    RETRIEVAL = "retrieval"
    RISK = "risk"
    TEST_RESULT = "test_result"
    EXECUTION = "execution"


class ToolName(StrEnum):
    GET_FEATURES = "get_features"
    GET_GRAPH = "get_graph"
    SEARCH_HISTORY = "search_history"
    GET_RISK = "get_risk"
    GET_TEST_RESULTS = "get_test_results"
    GET_EXECUTION_EVIDENCE = "get_execution_evidence"


class ToolStatus(StrEnum):
    COMPLETED = "completed"
    MISSING = "missing"
    FAILED = "failed"


class AgentNode(StrEnum):
    CHANGE_ANALYST = "change_analyst"
    HISTORICAL_INVESTIGATOR = "historical_investigator"
    RISK_SYNTHESIZER = "risk_synthesizer"
    TEST_PLANNER = "test_planner"
    EXECUTION_READER = "execution_reader"
    EVIDENCE_CRITIC = "evidence_critic"
    RECOMMENDATION_COMPOSER = "recommendation_composer"


class TerminationReason(StrEnum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    STEP_BUDGET_EXCEEDED = "step_budget_exceeded"
    TOOL_BUDGET_EXCEEDED = "tool_budget_exceeded"
    LLM_BUDGET_EXCEEDED = "llm_budget_exceeded"
    WALL_TIME_EXCEEDED = "wall_time_exceeded"
    NODE_TIMEOUT = "node_timeout"
    LOOP_DETECTED = "loop_detected"
    TOOL_FAILURE = "tool_failure"
    PROVIDER_FAILURE = "provider_failure"
    CRITIC_REJECTED = "critic_rejected"


class CriticVerdict(StrEnum):
    ACCEPT = "pass"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """A bounded safe summary plus machine-checkable facts, never a raw source blob."""

    evidence_id: str
    category: EvidenceCategory
    summary: str
    source_reference: str
    fact_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.evidence_id, field="evidence_id")
        if not isinstance(self.category, EvidenceCategory):
            raise ValueError("evidence category is invalid")
        _text(self.summary, field="evidence summary", maximum=500)
        _text(self.source_reference, field="source reference", maximum=1_200)
        _identifiers(self.fact_codes, field="fact codes", maximum=32)
        if not self.fact_codes:
            raise ValueError("evidence must name at least one structured fact")

    def safe_dict(self) -> dict[str, object]:
        return {
            "category": self.category.value,
            "evidence_id": self.evidence_id,
            "fact_codes": list(self.fact_codes),
            "source_reference": self.source_reference,
            "summary": self.summary,
        }


@dataclass(frozen=True, slots=True)
class AgentLimits:
    max_steps: int = 8
    max_tool_calls: int = 8
    max_llm_calls: int = 5
    max_input_tokens: int = 16_384
    max_output_tokens: int = 4_096
    max_cost_microusd: int = 100_000
    max_wall_time_seconds: float = 30.0
    per_node_timeout_seconds: float = 10.0
    max_evidence_per_tool: int = 10

    def __post_init__(self) -> None:
        integer_bounds = (
            ("max_steps", self.max_steps, 1, 32),
            ("max_tool_calls", self.max_tool_calls, 1, 32),
            ("max_llm_calls", self.max_llm_calls, 1, 16),
            ("max_input_tokens", self.max_input_tokens, 256, 262_144),
            ("max_output_tokens", self.max_output_tokens, 64, 32_768),
            ("max_cost_microusd", self.max_cost_microusd, 1, 100_000_000),
            ("max_evidence_per_tool", self.max_evidence_per_tool, 1, 50),
        )
        for field, value, minimum, maximum in integer_bounds:
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"{field} must be between {minimum} and {maximum}")
        for time_field, time_value, time_minimum, time_maximum in (
            ("max_wall_time_seconds", self.max_wall_time_seconds, 0.1, 600.0),
            ("per_node_timeout_seconds", self.per_node_timeout_seconds, 0.1, 300.0),
        ):
            if not math.isfinite(time_value) or not time_minimum <= time_value <= time_maximum:
                raise ValueError(f"{time_field} must be between {time_minimum} and {time_maximum}")
        if self.per_node_timeout_seconds > self.max_wall_time_seconds:
            raise ValueError("per-node timeout cannot exceed the graph wall-time budget")

    def as_dict(self) -> dict[str, int | float]:
        return {
            "max_cost_microusd": self.max_cost_microusd,
            "max_evidence_per_tool": self.max_evidence_per_tool,
            "max_input_tokens": self.max_input_tokens,
            "max_llm_calls": self.max_llm_calls,
            "max_output_tokens": self.max_output_tokens,
            "max_steps": self.max_steps,
            "max_tool_calls": self.max_tool_calls,
            "max_wall_time_seconds": self.max_wall_time_seconds,
            "per_node_timeout_seconds": self.per_node_timeout_seconds,
        }


@dataclass(frozen=True, slots=True)
class AgentUsage:
    steps: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_microusd: int = 0

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 0
            for value in (
                self.steps,
                self.tool_calls,
                self.tool_errors,
                self.llm_calls,
                self.input_tokens,
                self.output_tokens,
                self.cost_microusd,
            )
        ):
            raise ValueError("agent usage counters must be non-negative integers")
        if self.tool_errors > self.tool_calls:
            raise ValueError("tool errors cannot exceed tool calls")

    def as_dict(self) -> dict[str, int]:
        return {
            "cost_microusd": self.cost_microusd,
            "input_tokens": self.input_tokens,
            "llm_calls": self.llm_calls,
            "output_tokens": self.output_tokens,
            "steps": self.steps,
            "tool_calls": self.tool_calls,
            "tool_errors": self.tool_errors,
        }


@dataclass(frozen=True, slots=True)
class NodeProviderUsage:
    input_tokens: int
    output_tokens: int
    cost_microusd: int
    elapsed_ms: float

    def __post_init__(self) -> None:
        if (
            any(
                type(value) is not int or value < 0
                for value in (self.input_tokens, self.output_tokens, self.cost_microusd)
            )
            or not math.isfinite(self.elapsed_ms)
            or self.elapsed_ms < 0
        ):
            raise ValueError("node provider usage is invalid")


@dataclass(frozen=True, slots=True)
class AgentClaim:
    statement: str
    evidence_ids: tuple[str, ...]
    fact_codes: tuple[str, ...]
    hypothesis: bool = False

    def __post_init__(self) -> None:
        _text(self.statement, field="claim statement", maximum=800)
        _identifiers(self.evidence_ids, field="claim evidence IDs", maximum=16)
        _identifiers(self.fact_codes, field="claim fact codes", maximum=16)
        if not self.hypothesis and (not self.evidence_ids or not self.fact_codes):
            raise ValueError("factual claims require citations and structured facts")

    def as_dict(self) -> dict[str, object]:
        return {
            "evidence_ids": list(self.evidence_ids),
            "fact_codes": list(self.fact_codes),
            "hypothesis": self.hypothesis,
            "statement": self.statement,
        }


@dataclass(frozen=True, slots=True)
class NodeInput:
    node: AgentNode
    snapshot_id: str
    evidence: tuple[EvidenceReference, ...]
    missing_categories: tuple[EvidenceCategory, ...]
    policy_recommendation: Recommendation
    max_input_tokens: int
    max_output_tokens: int
    max_cost_microusd: int
    timeout_seconds: float
    cancelled: bool

    def __post_init__(self) -> None:
        if not isinstance(self.node, AgentNode):
            raise ValueError("node input identity is invalid")
        _identifier(self.snapshot_id, field="node snapshot_id")
        if len(self.evidence) > 100 or len({item.evidence_id for item in self.evidence}) != len(
            self.evidence
        ):
            raise ValueError("node evidence is invalid")
        if len(self.missing_categories) > len(EvidenceCategory) or len(
            set(self.missing_categories)
        ) != len(self.missing_categories):
            raise ValueError("node missing categories are invalid")
        if not isinstance(self.policy_recommendation, Recommendation):
            raise ValueError("node policy recommendation is invalid")
        for field, value, minimum, maximum in (
            ("input-token", self.max_input_tokens, 1, 262_144),
            ("output-token", self.max_output_tokens, 1, 32_768),
            ("cost", self.max_cost_microusd, 1, 100_000_000),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"node {field} limit is invalid")
        if not math.isfinite(self.timeout_seconds) or not 0.1 <= self.timeout_seconds <= 300.0:
            raise ValueError("node timeout is invalid")
        if type(self.cancelled) is not bool:
            raise ValueError("node cancellation state is invalid")


@dataclass(frozen=True, slots=True)
class NodeOutput:
    node: AgentNode
    safe_summary: str
    claims: tuple[AgentClaim, ...]
    usage: NodeProviderUsage
    proposed_recommendation: Recommendation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.node, AgentNode):
            raise ValueError("node output identity is invalid")
        _text(self.safe_summary, field="node summary", maximum=1_000)
        if len(self.claims) > 20:
            raise ValueError("node output exceeds the claim limit")
        if self.proposed_recommendation is not None and not isinstance(
            self.proposed_recommendation, Recommendation
        ):
            raise ValueError("proposed recommendation is invalid")


class AgentNodeProvider(Protocol):
    provider_name: str
    model_id: str
    adapter_version: str
    local_only: bool

    def generate_node(self, request: NodeInput) -> NodeOutput: ...


@dataclass(frozen=True, slots=True)
class AgentDraft:
    proposed_recommendation: Recommendation
    claims: tuple[AgentClaim, ...]
    missing_categories: tuple[EvidenceCategory, ...]
    confidence: str
    advisory_only: bool = True
    auto_merge: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.proposed_recommendation, Recommendation):
            raise ValueError("draft recommendation is invalid")
        if len(self.claims) > 80 or len(set(self.missing_categories)) != len(
            self.missing_categories
        ):
            raise ValueError("draft collections are invalid")
        if self.confidence not in {"low", "medium", "high"}:
            raise ValueError("draft confidence is invalid")
        if not self.advisory_only or self.auto_merge:
            raise ValueError("agent drafts cannot authorize merge or deploy")

    def as_dict(self) -> dict[str, object]:
        return {
            "advisory_only": self.advisory_only,
            "auto_merge": self.auto_merge,
            "claims": [claim.as_dict() for claim in self.claims],
            "confidence": self.confidence,
            "missing_categories": [item.value for item in self.missing_categories],
            "proposed_recommendation": self.proposed_recommendation.value,
        }


@dataclass(frozen=True, slots=True)
class CriticResult:
    verdict: CriticVerdict
    reason_codes: tuple[str, ...]
    claim_count: int
    supported_claim_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.verdict, CriticVerdict):
            raise ValueError("critic verdict is invalid")
        _identifiers(self.reason_codes, field="critic reason codes", maximum=32)
        if (
            type(self.claim_count) is not int
            or type(self.supported_claim_count) is not int
            or not 0 <= self.supported_claim_count <= self.claim_count
        ):
            raise ValueError("critic claim counts are invalid")
        if self.verdict is CriticVerdict.REJECT and not self.reason_codes:
            raise ValueError("a rejecting critic must give reason codes")

    @property
    def groundedness_rate(self) -> float:
        return 1.0 if self.claim_count == 0 else self.supported_claim_count / self.claim_count

    def as_dict(self) -> dict[str, object]:
        return {
            "claim_count": self.claim_count,
            "groundedness_rate": round(self.groundedness_rate, 12),
            "reason_codes": list(self.reason_codes),
            "supported_claim_count": self.supported_claim_count,
            "verdict": self.verdict.value,
        }


@dataclass(frozen=True, slots=True)
class AgentTraceEvent:
    sequence: int
    event_type: str
    node: AgentNode
    status: str
    summary: str
    evidence_ids: tuple[str, ...]
    elapsed_ms: float

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("trace sequence is invalid")
        _identifier(self.event_type, field="trace event type", maximum=32)
        _identifier(self.status, field="trace status", maximum=64)
        _text(self.summary, field="trace summary", maximum=1_000)
        _identifiers(self.evidence_ids, field="trace evidence IDs")
        if not math.isfinite(self.elapsed_ms) or self.elapsed_ms < 0:
            raise ValueError("trace elapsed time is invalid")

    def as_dict(self) -> dict[str, object]:
        return {
            "elapsed_ms": round(self.elapsed_ms, 6),
            "event_type": self.event_type,
            "evidence_ids": list(self.evidence_ids),
            "node": self.node.value,
            "sequence": self.sequence,
            "status": self.status,
            "summary": self.summary,
        }


@dataclass(frozen=True, slots=True)
class InvestigationRequest:
    run_id: str
    snapshot_id: str
    evidence: tuple[EvidenceReference, ...]
    policy_decision: RecommendationDecisionV1
    limits: AgentLimits = AgentLimits()
    cancelled: bool = False
    graph_version: str = AGENT_GRAPH_VERSION
    state_schema_version: str = AGENT_STATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _identifier(self.run_id, field="run_id")
        _identifier(self.snapshot_id, field="snapshot_id")
        if len(self.evidence) > 100:
            raise ValueError("investigation evidence exceeds 100 references")
        evidence_ids = tuple(item.evidence_id for item in self.evidence)
        _identifiers(evidence_ids, field="investigation evidence IDs", maximum=100)
        if self.graph_version != AGENT_GRAPH_VERSION:
            raise ValueError("agent graph version is unsupported")
        if self.state_schema_version != AGENT_STATE_SCHEMA_VERSION:
            raise ValueError("agent state schema version is unsupported")
        if type(self.cancelled) is not bool:
            raise ValueError("cancelled must be boolean")
        if not isinstance(self.policy_decision, RecommendationDecisionV1):
            raise ValueError("policy decision is invalid")

    @property
    def request_sha256(self) -> str:
        payload = {
            "evidence": [item.safe_dict() for item in self.evidence],
            "graph_version": self.graph_version,
            "limits": self.limits.as_dict(),
            "policy_decision_sha256": self.policy_decision.decision_sha256,
            "run_id": self.run_id,
            "snapshot_id": self.snapshot_id,
            "state_schema_version": self.state_schema_version,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class InvestigationResult:
    run_id: str
    snapshot_id: str
    recommendation: Recommendation
    termination_reason: TerminationReason
    partial: bool
    evidence_ids: tuple[str, ...]
    draft: AgentDraft | None
    critic: CriticResult | None
    trace: tuple[AgentTraceEvent, ...]
    usage: AgentUsage
    error_codes: tuple[str, ...]
    policy_decision_sha256: str
    request_sha256: str
    graph_version: str = AGENT_GRAPH_VERSION
    state_schema_version: str = AGENT_STATE_SCHEMA_VERSION
    advisory_only: bool = True
    auto_merge: bool = False

    def __post_init__(self) -> None:
        _identifier(self.run_id, field="result run_id")
        _identifier(self.snapshot_id, field="result snapshot_id")
        if not isinstance(self.recommendation, Recommendation) or not isinstance(
            self.termination_reason, TerminationReason
        ):
            raise ValueError("result recommendation or termination is invalid")
        if type(self.partial) is not bool:
            raise ValueError("result partial flag is invalid")
        _identifiers(self.evidence_ids, field="result evidence IDs", maximum=100)
        _identifiers(self.error_codes, field="result error codes", maximum=32)
        if not self.advisory_only or self.auto_merge:
            raise ValueError("agent results cannot authorize merge or deploy")
        for field, value in (
            ("policy decision hash", self.policy_decision_sha256),
            ("request hash", self.request_sha256),
        ):
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError(f"{field} is invalid")
        if self.termination_reason is TerminationReason.COMPLETED and self.partial:
            raise ValueError("a completed result cannot be partial")
        if self.termination_reason is not TerminationReason.COMPLETED and not self.partial:
            raise ValueError("a non-completed result must be partial")

    def safe_dict(self) -> dict[str, object]:
        """Serialize only bounded decisions, counters, citations, and safe summaries."""

        return {
            "advisory_only": self.advisory_only,
            "auto_merge": self.auto_merge,
            "critic": self.critic.as_dict() if self.critic else None,
            "draft": self.draft.as_dict() if self.draft else None,
            "error_codes": list(self.error_codes),
            "evidence_ids": list(self.evidence_ids),
            "graph_version": self.graph_version,
            "partial": self.partial,
            "policy_decision_sha256": self.policy_decision_sha256,
            "recommendation": self.recommendation.value,
            "request_sha256": self.request_sha256,
            "run_id": self.run_id,
            "snapshot_id": self.snapshot_id,
            "state_schema_version": self.state_schema_version,
            "termination_reason": self.termination_reason.value,
            "trace": [event.as_dict() for event in self.trace],
            "usage": self.usage.as_dict(),
        }

    @property
    def result_sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.safe_dict(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


CancellationCheck = Callable[[], bool]
