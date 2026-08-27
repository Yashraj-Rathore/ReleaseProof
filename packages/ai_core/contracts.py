"""Minimal M1 advisory-LLM seam.

Budgets, hosted-provider policy, prompts, persistence, and real adapters belong to M7.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LLMProviderError(RuntimeError):
    """Base provider-neutral LLM error."""


class LLMUnavailableError(LLMProviderError):
    """The provider is unavailable."""


class LLMSchemaError(LLMProviderError):
    """The provider response violates the boundary schema."""


def _validate_identifier(value: str, *, field: str) -> None:
    if not value or len(value) > 128 or not value.isascii():
        raise ValueError(f"{field} must be 1..128 ASCII characters")


def _validate_items(values: tuple[str, ...], *, field: str, maximum_items: int) -> None:
    if len(values) > maximum_items:
        raise ValueError(f"{field} exceeds {maximum_items} items")
    for value in values:
        if not value or len(value) > 512 or any(ord(character) < 32 for character in value):
            raise ValueError(f"{field} contains an invalid item")


@dataclass(frozen=True, slots=True)
class LLMRequest:
    change_id: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_identifier(self.change_id, field="change_id")
        if len(self.evidence_ids) > 50 or len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence_ids must contain at most 50 unique values")
        for evidence_id in self.evidence_ids:
            _validate_identifier(evidence_id, field="evidence_id")


@dataclass(frozen=True, slots=True)
class LLMSuggestion:
    summary: str
    risk_hypotheses: tuple[str, ...]
    requested_tests: tuple[str, ...]
    cited_evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.summary or len(self.summary) > 2_000:
            raise ValueError("summary must contain 1..2000 characters")
        _validate_items(self.risk_hypotheses, field="risk_hypotheses", maximum_items=20)
        _validate_items(self.requested_tests, field="requested_tests", maximum_items=20)
        if len(self.cited_evidence_ids) > 50 or len(set(self.cited_evidence_ids)) != len(
            self.cited_evidence_ids
        ):
            raise ValueError("cited_evidence_ids must contain at most 50 unique values")
        for evidence_id in self.cited_evidence_ids:
            _validate_identifier(evidence_id, field="cited_evidence_id")


class LLMProvider(Protocol):
    def suggest(self, request: LLMRequest) -> LLMSuggestion: ...
