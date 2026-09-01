"""Deterministic groundedness metrics for frozen M7 fixtures."""

from __future__ import annotations

from dataclasses import dataclass

from packages.ai_core.contracts import AnalysisSuggestionV1

LLM_EVALUATION_VERSION = "m7-llm-eval-v1"


@dataclass(frozen=True, slots=True)
class SuggestionMetrics:
    citation_support_rate: float
    unsupported_claim_rate: float
    claim_count: int
    supported_claim_count: int

    def as_dict(self) -> dict[str, int | float]:
        return {
            "citation_support_rate": self.citation_support_rate,
            "unsupported_claim_rate": self.unsupported_claim_rate,
            "claim_count": self.claim_count,
            "supported_claim_count": self.supported_claim_count,
        }


def evaluate_suggestion(
    suggestion: AnalysisSuggestionV1,
    *,
    allowed_evidence_ids: tuple[str, ...],
) -> SuggestionMetrics:
    """Score claims with deterministic citation assertions, never model self-grading."""

    allowed = set(allowed_evidence_ids)
    claim_references = [suggestion.summary_evidence_ids]
    claim_references.extend(item.evidence_ids for item in suggestion.risks)
    # Hypotheses are explicitly uncertainty-labelled and do not become factual claims.
    claim_count = len(claim_references)
    supported = sum(bool(refs) and set(refs).issubset(allowed) for refs in claim_references)
    if suggestion.insufficient_evidence and not allowed:
        claim_count = 0
        supported = 0
    citation_rate = 1.0 if claim_count == 0 else supported / claim_count
    return SuggestionMetrics(
        citation_support_rate=round(citation_rate, 12),
        unsupported_claim_rate=round(1.0 - citation_rate, 12),
        claim_count=claim_count,
        supported_claim_count=supported,
    )
