"""Deterministic LLM fake that cannot perform network calls."""

from __future__ import annotations

from packages.ai_core import LLMProviderError, LLMRequest, LLMSchemaError, LLMSuggestion


class FakeLLMProvider:
    def __init__(
        self,
        suggestion: LLMSuggestion,
        *,
        failure: LLMProviderError | None = None,
    ) -> None:
        self._suggestion = suggestion
        self._failure = failure

    def suggest(self, request: LLMRequest) -> LLMSuggestion:
        if self._failure is not None:
            raise self._failure
        if not set(self._suggestion.cited_evidence_ids).issubset(request.evidence_ids):
            raise LLMSchemaError("fake response cites evidence outside the request")
        return self._suggestion
