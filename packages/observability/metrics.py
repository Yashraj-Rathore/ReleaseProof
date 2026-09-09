"""Low-cardinality telemetry primitives for product trust boundaries."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Protocol


class MetricComponent(StrEnum):
    WEB = "web"
    WEBHOOK = "webhook"
    CELERY = "celery"
    RETRIEVAL = "retrieval"
    EMBEDDING = "embedding"
    LLM = "llm"
    MODEL = "model"
    RUNNER = "runner"
    RETENTION = "retention"


class MetricOutcome(StrEnum):
    COMPLETED = "completed"
    DENIED = "denied"
    FAILED = "failed"
    UNKNOWN = "unknown"


class _Counter(Protocol):
    def add(self, amount: int, attributes: dict[str, str]) -> None: ...


class _Histogram(Protocol):
    def record(self, amount: float, attributes: dict[str, str]) -> None: ...


class _NoopCounter:
    def add(self, amount: int, attributes: dict[str, str]) -> None:
        del amount, attributes


class _NoopHistogram:
    def record(self, amount: float, attributes: dict[str, str]) -> None:
        del amount, attributes


@lru_cache(maxsize=1)
def _instruments() -> tuple[_Counter, _Histogram]:
    try:
        from opentelemetry import metrics
    except ImportError:
        return _NoopCounter(), _NoopHistogram()
    meter = metrics.get_meter("releaseproof.operations", "1")
    return (
        meter.create_counter(
            "releaseproof.operation.count",
            description="Bounded ReleaseProof operation outcomes",
        ),
        meter.create_histogram(
            "releaseproof.operation.duration",
            unit="ms",
            description="Bounded ReleaseProof operation duration",
        ),
    )


def record_operation(
    *, component: MetricComponent, outcome: MetricOutcome, duration_ms: float
) -> None:
    attributes = {"component": component.value, "outcome": outcome.value}
    counter, histogram = _instruments()
    counter.add(1, attributes)
    histogram.record(max(0.0, min(duration_ms, 86_400_000.0)), attributes)
