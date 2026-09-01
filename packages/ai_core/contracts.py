"""Provider-neutral contracts for evidence-grounded advisory LLM analysis."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class LLMProviderError(RuntimeError):
    """Base error carrying only a stable, safe provider-neutral code."""

    error_code = "llm_provider_error"
    retryable = False


class LLMUnavailableError(LLMProviderError):
    """The provider is unavailable after its bounded retry policy."""

    error_code = "llm_provider_unavailable"
    retryable = True


class LLMTimeoutError(LLMUnavailableError):
    """The provider exceeded the configured timeout."""

    error_code = "llm_provider_timeout"


class LLMSchemaError(LLMProviderError):
    """The provider response violates the strict boundary schema."""

    error_code = "llm_schema_invalid"


class LLMBudgetExceededError(LLMProviderError):
    """A request cannot fit within its declared byte/token/cost budget."""

    error_code = "llm_budget_exceeded"


class LLMCancelledError(LLMProviderError):
    """The caller cancelled before accepting provider output."""

    error_code = "llm_cancelled"


class ContentClass(StrEnum):
    METADATA = "metadata"
    DETERMINISTIC_EVIDENCE = "deterministic_evidence"
    RETRIEVAL_EXCERPT = "retrieval_excerpt"
    DIFF_EXCERPT = "diff_excerpt"
    SOURCE_EXCERPT = "source_excerpt"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConfidenceCategory(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def _validate_identifier(value: str, *, field: str, maximum: int = 160) -> None:
    if not value or len(value) > maximum or not value.isascii():
        raise ValueError(f"{field} must be 1..{maximum} ASCII characters")
    if any(ord(character) < 32 for character in value):
        raise ValueError(f"{field} contains control characters")


def _validate_text(value: str, *, field: str, maximum: int, allow_empty: bool = False) -> None:
    if (not value and not allow_empty) or len(value) > maximum or "\x00" in value:
        minimum = 0 if allow_empty else 1
        raise ValueError(f"{field} must contain {minimum}..{maximum} characters")


def _validate_references(values: tuple[str, ...], *, field: str, allow_empty: bool) -> None:
    if (not values and not allow_empty) or len(values) > 50 or len(set(values)) != len(values):
        raise ValueError(f"{field} must contain a bounded unique reference list")
    for value in values:
        _validate_identifier(value, field=field)


@dataclass(frozen=True, slots=True)
class EvidenceContext:
    evidence_id: str
    content_class: ContentClass
    content: str
    source_reference: str

    def __post_init__(self) -> None:
        _validate_identifier(self.evidence_id, field="evidence_id")
        _validate_text(self.content, field="evidence content", maximum=16_000)
        _validate_text(self.source_reference, field="source_reference", maximum=1_200)


@dataclass(frozen=True, slots=True)
class LLMBudget:
    max_input_bytes: int
    max_input_tokens: int
    max_output_tokens: int
    max_cost_microusd: int
    connect_timeout_seconds: float
    read_timeout_seconds: float
    max_attempts: int
    retry_backoff_seconds: float

    def __post_init__(self) -> None:
        if not 256 <= self.max_input_bytes <= 262_144:
            raise ValueError("max_input_bytes must be between 256 and 262144")
        if not 256 <= self.max_input_tokens <= 262_144:
            raise ValueError("max_input_tokens must be between 256 and 262144")
        if not 64 <= self.max_output_tokens <= 8_192:
            raise ValueError("max_output_tokens must be between 64 and 8192")
        if not 1 <= self.max_cost_microusd <= 100_000_000:
            raise ValueError("max_cost_microusd must be between 1 and 100000000")
        if not math.isfinite(self.connect_timeout_seconds) or not (
            0.1 <= self.connect_timeout_seconds <= 60.0
        ):
            raise ValueError("connect timeout must be between 0.1 and 60 seconds")
        if not math.isfinite(self.read_timeout_seconds) or not (
            0.1 <= self.read_timeout_seconds <= 300.0
        ):
            raise ValueError("read timeout must be between 0.1 and 300 seconds")
        if not 1 <= self.max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")
        if not math.isfinite(self.retry_backoff_seconds) or not (
            0.0 <= self.retry_backoff_seconds <= 5.0
        ):
            raise ValueError("retry backoff must be between 0 and 5 seconds")


@dataclass(frozen=True, slots=True)
class PromptIdentity:
    prompt_version: str
    prompt_sha256: str
    schema_version: str
    schema_sha256: str

    def __post_init__(self) -> None:
        _validate_identifier(self.prompt_version, field="prompt_version", maximum=64)
        _validate_identifier(self.schema_version, field="schema_version", maximum=64)
        for field, value in (
            ("prompt_sha256", self.prompt_sha256),
            ("schema_sha256", self.schema_sha256),
        ):
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError(f"{field} must be a lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class LLMAnalysisRequest:
    change_id: str
    evidence: tuple[EvidenceContext, ...]
    instructions: str
    input_text: str
    prompt: PromptIdentity
    budget: LLMBudget
    cancelled: bool = False

    def __post_init__(self) -> None:
        _validate_identifier(self.change_id, field="change_id")
        if len(self.evidence) > 50:
            raise ValueError("evidence exceeds 50 items")
        evidence_ids = tuple(item.evidence_id for item in self.evidence)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("evidence IDs must be unique")
        _validate_text(self.instructions, field="instructions", maximum=16_000)
        _validate_text(self.input_text, field="input_text", maximum=262_144)
        input_bytes = len(self.instructions.encode()) + len(self.input_text.encode())
        if input_bytes > self.budget.max_input_bytes:
            raise LLMBudgetExceededError("provider input exceeds the byte budget")
        # One UTF-8 byte per token is an intentionally conservative upper estimate.
        if input_bytes > self.budget.max_input_tokens:
            raise LLMBudgetExceededError("provider input exceeds the conservative token budget")

    @property
    def allowed_evidence_ids(self) -> tuple[str, ...]:
        return tuple(item.evidence_id for item in self.evidence)

    @property
    def conservative_input_tokens(self) -> int:
        return len(self.instructions.encode()) + len(self.input_text.encode())


@dataclass(frozen=True, slots=True)
class GroundedRisk:
    statement: str
    severity: Severity
    confidence: ConfidenceCategory
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_text(self.statement, field="risk statement", maximum=800)
        _validate_references(self.evidence_ids, field="risk evidence IDs", allow_empty=False)

    def as_dict(self) -> dict[str, object]:
        return {
            "statement": self.statement,
            "severity": self.severity.value,
            "confidence": self.confidence.value,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class RiskHypothesis:
    statement: str
    severity: Severity
    confidence: ConfidenceCategory
    evidence_ids: tuple[str, ...]
    uncertainty: str

    def __post_init__(self) -> None:
        _validate_text(self.statement, field="hypothesis statement", maximum=800)
        _validate_references(self.evidence_ids, field="hypothesis evidence IDs", allow_empty=True)
        _validate_text(self.uncertainty, field="hypothesis uncertainty", maximum=500)

    def as_dict(self) -> dict[str, object]:
        return {
            "statement": self.statement,
            "severity": self.severity.value,
            "confidence": self.confidence.value,
            "evidence_ids": list(self.evidence_ids),
            "uncertainty": self.uncertainty,
        }


@dataclass(frozen=True, slots=True)
class RequestedTest:
    description: str
    rationale: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_text(self.description, field="requested test", maximum=800)
        _validate_text(self.rationale, field="test rationale", maximum=800)
        _validate_references(self.evidence_ids, field="test evidence IDs", allow_empty=True)

    def as_dict(self) -> dict[str, object]:
        return {
            "description": self.description,
            "rationale": self.rationale,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class AnalysisSuggestionV1:
    summary: str
    summary_evidence_ids: tuple[str, ...]
    risks: tuple[GroundedRisk, ...]
    hypotheses: tuple[RiskHypothesis, ...]
    requested_tests: tuple[RequestedTest, ...]
    missing_information: tuple[str, ...]
    uncertainty: str
    insufficient_evidence: bool

    def __post_init__(self) -> None:
        _validate_text(self.summary, field="summary", maximum=2_000)
        _validate_references(
            self.summary_evidence_ids,
            field="summary evidence IDs",
            allow_empty=self.insufficient_evidence,
        )
        if len(self.risks) > 20 or len(self.hypotheses) > 20 or len(self.requested_tests) > 20:
            raise ValueError("suggestion item counts exceed the strict schema")
        if len(self.missing_information) > 20:
            raise ValueError("missing information exceeds 20 items")
        for item in self.missing_information:
            _validate_text(item, field="missing information", maximum=500)
        _validate_text(self.uncertainty, field="uncertainty", maximum=1_000)
        if self.insufficient_evidence and self.risks:
            raise ValueError("insufficient-evidence output cannot contain grounded risks")
        if not self.insufficient_evidence and not self.summary_evidence_ids:
            raise ValueError("a sufficient-evidence summary requires citations")

    @property
    def cited_evidence_ids(self) -> tuple[str, ...]:
        references = list(self.summary_evidence_ids)
        for risk in self.risks:
            references.extend(risk.evidence_ids)
        for hypothesis in self.hypotheses:
            references.extend(hypothesis.evidence_ids)
        for requested_test in self.requested_tests:
            references.extend(requested_test.evidence_ids)
        return tuple(dict.fromkeys(references))

    def as_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "summary_evidence_ids": list(self.summary_evidence_ids),
            "risks": [item.as_dict() for item in self.risks],
            "hypotheses": [item.as_dict() for item in self.hypotheses],
            "requested_tests": [item.as_dict() for item in self.requested_tests],
            "missing_information": list(self.missing_information),
            "uncertainty": self.uncertainty,
            "insufficient_evidence": self.insufficient_evidence,
        }


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_microusd: int

    def __post_init__(self) -> None:
        if min(self.input_tokens, self.output_tokens, self.total_tokens, self.cost_microusd) < 0:
            raise ValueError("provider usage values cannot be negative")
        if self.total_tokens < self.input_tokens + self.output_tokens:
            raise ValueError("total tokens cannot be lower than input plus output tokens")

    def as_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_microusd": self.cost_microusd,
        }


@dataclass(frozen=True, slots=True)
class LLMProviderResponse:
    suggestion: AnalysisSuggestionV1
    provider_name: str
    model_id: str
    adapter_version: str
    sdk_version: str
    usage: ProviderUsage
    elapsed_ms: float

    def __post_init__(self) -> None:
        for field, value in (
            ("provider_name", self.provider_name),
            ("model_id", self.model_id),
            ("adapter_version", self.adapter_version),
            ("sdk_version", self.sdk_version),
        ):
            _validate_identifier(value, field=field, maximum=160)
        if not math.isfinite(self.elapsed_ms) or self.elapsed_ms < 0:
            raise ValueError("elapsed_ms must be finite and non-negative")


class AnalysisLLMProvider(Protocol):
    def analyze_change(self, request: LLMAnalysisRequest) -> LLMProviderResponse: ...
