"""Pinned OpenAI Responses API adapter for strict advisory analysis."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

import openai

from packages.ai_core import (
    ANALYSIS_JSON_SCHEMA,
    LLMAnalysisRequest,
    LLMBudgetExceededError,
    LLMCancelledError,
    LLMProviderResponse,
    LLMSchemaError,
    LLMTimeoutError,
    LLMUnavailableError,
    ProviderConfiguration,
    ProviderKind,
    ProviderUsage,
    RetentionMode,
    TrainingUseMode,
    parse_suggestion_json,
    validate_suggestion_citations,
)

OPENAI_SDK_VERSION = "3.6.0"
OPENAI_ADAPTER_VERSION = "openai-responses-adapter-v1"
OPENAI_MODEL_ID = "gpt-5.4-mini-2026-03-17"


class _ResponsesEndpoint(Protocol):
    def create(self, **kwargs: Any) -> object: ...


class _OpenAIClient(Protocol):
    responses: _ResponsesEndpoint


ClientFactory = Callable[[LLMAnalysisRequest], _OpenAIClient]


@dataclass(frozen=True, slots=True)
class ProviderPricing:
    model_id: str
    version: str
    source_reference: str
    input_microusd_per_million_tokens: int
    output_microusd_per_million_tokens: int

    def __post_init__(self) -> None:
        if self.model_id != OPENAI_MODEL_ID:
            raise ValueError("pricing must name the adapter's exact model snapshot")
        if not self.version or not self.source_reference:
            raise ValueError("pricing requires an external version and source reference")
        if (
            min(
                self.input_microusd_per_million_tokens,
                self.output_microusd_per_million_tokens,
            )
            < 0
        ):
            raise ValueError("pricing values cannot be negative")

    def estimate(self, *, input_tokens: int, output_tokens: int) -> int:
        numerator = (
            input_tokens * self.input_microusd_per_million_tokens
            + output_tokens * self.output_microusd_per_million_tokens
        )
        return math.ceil(numerator / 1_000_000)


@dataclass(frozen=True, slots=True)
class OpenAIAdapterConfig:
    pricing: ProviderPricing
    region: str
    training_use_mode: TrainingUseMode
    retention_mode: RetentionMode
    retention_days: int | None
    reasoning_effort: str = "low"
    verbosity: str = "low"
    service_tier: str = "default"
    store_response: bool = False

    def __post_init__(self) -> None:
        ProviderConfiguration(
            provider_name="openai",
            model_id=OPENAI_MODEL_ID,
            kind=ProviderKind.HOSTED,
            region=self.region,
            training_use_mode=self.training_use_mode,
            retention_mode=self.retention_mode,
            retention_days=self.retention_days,
            supports_response_storage_disabled=True,
        )
        if self.reasoning_effort not in {"none", "low", "medium", "high"}:
            raise ValueError("reasoning effort is outside the approved bound")
        if self.verbosity not in {"low", "medium", "high"}:
            raise ValueError("verbosity is outside the approved bound")
        if self.service_tier != "default":
            raise ValueError("M7 permits only the default service tier")
        if self.store_response:
            raise ValueError("M7 requires provider-side response storage disabled")


class OpenAIResponsesAdapter:
    provider_name = "openai"
    model_id = OPENAI_MODEL_ID
    adapter_version = OPENAI_ADAPTER_VERSION
    sdk_version = OPENAI_SDK_VERSION

    def __init__(
        self,
        *,
        api_key: str,
        config: OpenAIAdapterConfig,
        client_factory: ClientFactory | None = None,
    ) -> None:
        if openai.__version__ != OPENAI_SDK_VERSION:
            raise RuntimeError("installed OpenAI SDK does not match the pinned adapter version")
        if not api_key:
            raise ValueError("OpenAI adapter requires an API key from approved secret storage")
        self._api_key = api_key
        self._config = config
        self._client_factory = client_factory or self._real_client

    @property
    def configuration(self) -> ProviderConfiguration:
        return ProviderConfiguration(
            provider_name=self.provider_name,
            model_id=self.model_id,
            kind=ProviderKind.HOSTED,
            region=self._config.region,
            training_use_mode=self._config.training_use_mode,
            retention_mode=self._config.retention_mode,
            retention_days=self._config.retention_days,
            supports_response_storage_disabled=True,
        )

    def _real_client(self, request: LLMAnalysisRequest) -> _OpenAIClient:
        timeout = openai.Timeout(
            connect=request.budget.connect_timeout_seconds,
            read=request.budget.read_timeout_seconds,
            write=request.budget.read_timeout_seconds,
            pool=request.budget.connect_timeout_seconds,
        )
        return cast(
            _OpenAIClient,
            openai.OpenAI(
                api_key=self._api_key,
                timeout=timeout,
                max_retries=0,
            ),
        )

    @staticmethod
    def _usage_value(usage: object, field: str) -> int:
        value = getattr(usage, field, None)
        if not isinstance(value, int) or value < 0:
            raise LLMSchemaError("provider usage metadata is missing or invalid")
        return value

    def analyze_change(self, request: LLMAnalysisRequest) -> LLMProviderResponse:
        if request.cancelled:
            raise LLMCancelledError("analysis was cancelled")
        max_cost = self._config.pricing.estimate(
            input_tokens=request.conservative_input_tokens,
            output_tokens=request.budget.max_output_tokens,
        )
        if max_cost > request.budget.max_cost_microusd:
            raise LLMBudgetExceededError("configured request exceeds the cost budget")

        started = time.perf_counter_ns()
        client = self._client_factory(request)
        response: object | None = None
        last_error: LLMUnavailableError | LLMTimeoutError | None = None
        for attempt in range(request.budget.max_attempts):
            try:
                response = client.responses.create(
                    model=self.model_id,
                    instructions=request.instructions,
                    input=request.input_text,
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "analysis_suggestion_v1",
                            "strict": True,
                            "schema": ANALYSIS_JSON_SCHEMA,
                        },
                        "verbosity": self._config.verbosity,
                    },
                    reasoning={"effort": self._config.reasoning_effort},
                    max_output_tokens=request.budget.max_output_tokens,
                    service_tier=self._config.service_tier,
                    store=False,
                    tools=[],
                    parallel_tool_calls=False,
                    truncation="disabled",
                )
                break
            except openai.APITimeoutError as error:
                last_error = LLMTimeoutError("OpenAI request timed out")
                last_error.__cause__ = error
            except (openai.APIConnectionError, openai.RateLimitError) as error:
                last_error = LLMUnavailableError("OpenAI request unavailable after bounded retries")
                last_error.__cause__ = error
            except openai.APIStatusError as error:
                if error.status_code not in {408, 409, 429} and error.status_code < 500:
                    raise LLMSchemaError("OpenAI rejected the configured request") from error
                last_error = LLMUnavailableError("OpenAI request unavailable after bounded retries")
                last_error.__cause__ = error
            if attempt + 1 < request.budget.max_attempts:
                time.sleep(min(5.0, request.budget.retry_backoff_seconds * (2**attempt)))
        if response is None:
            if last_error is None:
                raise LLMUnavailableError("OpenAI request did not produce a response")
            raise last_error

        if request.cancelled:
            raise LLMCancelledError("analysis was cancelled")
        if getattr(response, "status", None) != "completed":
            raise LLMUnavailableError("OpenAI response did not complete")
        raw_output = getattr(response, "output_text", None)
        if not isinstance(raw_output, str):
            raise LLMSchemaError("OpenAI response has no structured output text")
        suggestion = parse_suggestion_json(raw_output)
        validate_suggestion_citations(
            suggestion,
            allowed_evidence_ids=request.allowed_evidence_ids,
        )
        usage = getattr(response, "usage", None)
        if usage is None:
            raise LLMSchemaError("OpenAI response has no usage metadata")
        input_tokens = self._usage_value(usage, "input_tokens")
        output_tokens = self._usage_value(usage, "output_tokens")
        total_tokens = self._usage_value(usage, "total_tokens")
        cost = self._config.pricing.estimate(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        if cost > request.budget.max_cost_microusd:
            raise LLMBudgetExceededError("provider usage exceeds the cost budget")
        return LLMProviderResponse(
            suggestion=suggestion,
            provider_name=self.provider_name,
            model_id=self.model_id,
            adapter_version=self.adapter_version,
            sdk_version=self.sdk_version,
            usage=ProviderUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost_microusd=cost,
            ),
            elapsed_ms=(time.perf_counter_ns() - started) / 1_000_000.0,
        )
