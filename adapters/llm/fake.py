"""Deterministic advisory LLM fake that cannot perform network calls."""

from __future__ import annotations

import json

from packages.ai_core import (
    AnalysisSuggestionV1,
    ConfidenceCategory,
    GroundedRisk,
    LLMAnalysisRequest,
    LLMCancelledError,
    LLMProviderError,
    LLMProviderResponse,
    ProviderConfiguration,
    ProviderKind,
    ProviderUsage,
    RequestedTest,
    RetentionMode,
    Severity,
    TrainingUseMode,
    parse_suggestion_json,
    validate_suggestion_citations,
)

FAKE_ADAPTER_VERSION = "deterministic-llm-fake-v1"
FAKE_PROVIDER_CONFIGURATION = ProviderConfiguration(
    provider_name="deterministic_fake",
    model_id="deterministic-evidence-synthesizer-v1",
    kind=ProviderKind.DETERMINISTIC_FAKE,
    region="local",
    training_use_mode=TrainingUseMode.UNKNOWN,
    retention_mode=RetentionMode.UNKNOWN,
    retention_days=None,
    supports_response_storage_disabled=True,
)


class FakeLLMProvider:
    provider_name = "deterministic_fake"
    model_id = "deterministic-evidence-synthesizer-v1"
    adapter_version = FAKE_ADAPTER_VERSION
    sdk_version = "none"
    configuration = FAKE_PROVIDER_CONFIGURATION

    def __init__(
        self,
        suggestion: AnalysisSuggestionV1 | None = None,
        *,
        raw_output: str | None = None,
        failure: LLMProviderError | None = None,
    ) -> None:
        if suggestion is not None and raw_output is not None:
            raise ValueError("configure either a typed suggestion or raw output")
        self._suggestion = suggestion
        self._raw_output = raw_output
        self._failure = failure
        self.call_count = 0

    @staticmethod
    def _default_suggestion(request: LLMAnalysisRequest) -> AnalysisSuggestionV1:
        if not request.evidence:
            return AnalysisSuggestionV1(
                summary="No allowed evidence was supplied for advisory analysis.",
                summary_evidence_ids=(),
                risks=(),
                hypotheses=(),
                requested_tests=(),
                missing_information=("Repository-scoped evidence is required.",),
                uncertainty="Risk cannot be assessed from an empty evidence set.",
                insufficient_evidence=True,
            )
        first = request.evidence[0]
        return AnalysisSuggestionV1(
            summary="The supplied evidence warrants focused human review.",
            summary_evidence_ids=(first.evidence_id,),
            risks=(
                GroundedRisk(
                    statement="The cited change evidence may affect the referenced behavior.",
                    severity=Severity.MEDIUM,
                    confidence=ConfidenceCategory.MEDIUM,
                    evidence_ids=(first.evidence_id,),
                ),
            ),
            hypotheses=(),
            requested_tests=(
                RequestedTest(
                    description="Exercise the behavior named by the cited evidence.",
                    rationale="A targeted check can confirm or refute the advisory risk.",
                    evidence_ids=(first.evidence_id,),
                ),
            ),
            missing_information=(),
            uncertainty="The deterministic fake does not infer beyond supplied evidence.",
            insufficient_evidence=False,
        )

    def analyze_change(self, request: LLMAnalysisRequest) -> LLMProviderResponse:
        self.call_count += 1
        if request.cancelled:
            raise LLMCancelledError("analysis was cancelled")
        if self._failure is not None:
            raise self._failure
        suggestion = (
            parse_suggestion_json(self._raw_output)
            if self._raw_output is not None
            else self._suggestion or self._default_suggestion(request)
        )
        validate_suggestion_citations(
            suggestion,
            allowed_evidence_ids=request.allowed_evidence_ids,
        )
        output_tokens = len(
            json.dumps(suggestion.as_dict(), sort_keys=True, separators=(",", ":")).encode()
        )
        return LLMProviderResponse(
            suggestion=suggestion,
            provider_name=self.provider_name,
            model_id=self.model_id,
            adapter_version=self.adapter_version,
            sdk_version=self.sdk_version,
            usage=ProviderUsage(
                input_tokens=request.conservative_input_tokens,
                output_tokens=output_tokens,
                total_tokens=request.conservative_input_tokens + output_tokens,
                cost_microusd=0,
            ),
            elapsed_ms=0.0,
        )
