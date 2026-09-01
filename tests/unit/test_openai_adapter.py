from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import openai
import pytest

from adapters.llm.openai_responses import (
    OPENAI_ADAPTER_VERSION,
    OPENAI_MODEL_ID,
    OPENAI_SDK_VERSION,
    OpenAIAdapterConfig,
    OpenAIResponsesAdapter,
    ProviderPricing,
)
from packages.ai_core import (
    ContentClass,
    EvidenceContext,
    LLMAnalysisRequest,
    LLMBudget,
    LLMCancelledError,
    LLMSchemaError,
    RetentionMode,
    TrainingUseMode,
)
from packages.ai_core.prompting import build_analysis_request


def _request() -> LLMAnalysisRequest:
    return build_analysis_request(
        change_id="change:openai:fixture",
        evidence=(
            EvidenceContext(
                evidence_id="evidence:openai:1",
                content_class=ContentClass.DETERMINISTIC_EVIDENCE,
                content="A fixture schema migration is present.",
                source_reference="fixture:evidence:openai:1",
            ),
        ),
        budget=LLMBudget(
            max_input_bytes=16_384,
            max_input_tokens=16_384,
            max_output_tokens=512,
            max_cost_microusd=100_000,
            connect_timeout_seconds=2.0,
            read_timeout_seconds=10.0,
            max_attempts=2,
            retry_backoff_seconds=0.5,
        ),
    )


def _output() -> str:
    return json.dumps(
        {
            "summary": "The cited migration evidence warrants review.",
            "summary_evidence_ids": ["evidence:openai:1"],
            "risks": [
                {
                    "statement": "The schema change may require rollout ordering.",
                    "severity": "high",
                    "confidence": "medium",
                    "evidence_ids": ["evidence:openai:1"],
                }
            ],
            "hypotheses": [],
            "requested_tests": [
                {
                    "description": "Run the forward migration fixture.",
                    "rationale": "Confirm the cited schema change applies cleanly.",
                    "evidence_ids": ["evidence:openai:1"],
                }
            ],
            "missing_information": [],
            "uncertainty": "No deployment topology evidence was supplied.",
            "insufficient_evidence": False,
        },
        separators=(",", ":"),
    )


class _Responses:
    def __init__(self, output: str) -> None:
        self.output = output
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(
            status="completed",
            output_text=self.output,
            usage=SimpleNamespace(input_tokens=100, output_tokens=50, total_tokens=150),
        )


class _RetryingResponses(_Responses):
    def __init__(self, output: str) -> None:
        super().__init__(output)
        self.attempts = 0

    def create(self, **kwargs: Any) -> object:
        self.attempts += 1
        if self.attempts == 1:
            raise openai.APITimeoutError(request=SimpleNamespace())  # type: ignore[arg-type]
        return super().create(**kwargs)


def _adapter(responses: _Responses) -> OpenAIResponsesAdapter:
    pricing = ProviderPricing(
        model_id=OPENAI_MODEL_ID,
        version="synthetic-test-pricing-v1",
        source_reference="fixture://openai-pricing",
        input_microusd_per_million_tokens=100,
        output_microusd_per_million_tokens=200,
    )
    client = SimpleNamespace(responses=responses)
    return OpenAIResponsesAdapter(
        api_key="fixture-key-never-sent",
        config=OpenAIAdapterConfig(
            pricing=pricing,
            region="fixture-region",
            training_use_mode=TrainingUseMode.CONTRACT_REVIEWED,
            retention_mode=RetentionMode.CUSTOM_DURATION,
            retention_days=30,
        ),
        client_factory=lambda request: client,  # type: ignore[return-value]
    )


def test_openai_responses_adapter_uses_strict_stateless_bounded_request() -> None:
    endpoint = _Responses(_output())
    response = _adapter(endpoint).analyze_change(_request())

    assert response.model_id == OPENAI_MODEL_ID
    assert response.adapter_version == OPENAI_ADAPTER_VERSION
    assert response.sdk_version == OPENAI_SDK_VERSION
    assert response.suggestion.cited_evidence_ids == ("evidence:openai:1",)
    assert endpoint.kwargs["store"] is False
    assert endpoint.kwargs["tools"] == []
    assert endpoint.kwargs["parallel_tool_calls"] is False
    assert endpoint.kwargs["truncation"] == "disabled"
    assert endpoint.kwargs["model"] == OPENAI_MODEL_ID
    assert endpoint.kwargs["text"]["format"]["type"] == "json_schema"
    assert endpoint.kwargs["text"]["format"]["strict"] is True
    assert endpoint.kwargs["max_output_tokens"] == 512


def test_openai_responses_adapter_rejects_invalid_or_uncited_output() -> None:
    invalid = json.loads(_output())
    invalid["summary_evidence_ids"] = ["evidence:outside"]

    with pytest.raises(LLMSchemaError):
        _adapter(_Responses(json.dumps(invalid))).analyze_change(_request())


def test_openai_responses_adapter_retries_only_within_request_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = _RetryingResponses(_output())
    monkeypatch.setattr("adapters.llm.openai_responses.time.sleep", lambda _seconds: None)

    response = _adapter(endpoint).analyze_change(_request())

    assert endpoint.attempts == 2
    assert response.suggestion.summary_evidence_ids == ("evidence:openai:1",)


def test_openai_responses_adapter_honors_preflight_cancellation() -> None:
    endpoint = _Responses(_output())
    request = _request()
    cancelled = LLMAnalysisRequest(
        change_id=request.change_id,
        prompt=request.prompt,
        instructions=request.instructions,
        input_text=request.input_text,
        evidence=request.evidence,
        budget=request.budget,
        cancelled=True,
    )

    with pytest.raises(LLMCancelledError, match="cancelled"):
        _adapter(endpoint).analyze_change(cancelled)

    assert endpoint.kwargs == {}
