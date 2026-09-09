"""Explicit OpenTelemetry SDK bootstrap for web and worker processes."""

from __future__ import annotations

import os
import threading

_LOCK = threading.Lock()
_CONFIGURED_SERVICES: set[str] = set()


def configure_telemetry(*, service_name: str) -> bool:
    """Configure bounded OTLP traces/metrics once; return whether export is enabled."""

    if os.getenv("OTEL_SDK_DISABLED", "true").strip().casefold() == "true":
        return False
    if not service_name.isascii() or not 1 <= len(service_name) <= 64:
        raise ValueError("OpenTelemetry service name must be bounded ASCII")
    with _LOCK:
        if service_name in _CONFIGURED_SERVICES:
            return True
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {
                "service.name": service_name,
                "service.namespace": "releaseproof",
                "service.version": "0.1.0",
            }
        )
        trace_provider = TracerProvider(resource=resource)
        trace_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(timeout=5)))
        trace.set_tracer_provider(trace_provider)
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(timeout=5), export_interval_millis=10_000
        )
        metrics.set_meter_provider(
            MeterProvider(resource=resource, metric_readers=(metric_reader,))
        )
        _CONFIGURED_SERVICES.add(service_name)
    return True


def instrument_django() -> bool:
    if not configure_telemetry(service_name="releaseproof-web"):
        return False
    from opentelemetry.instrumentation.django import DjangoInstrumentor

    if not DjangoInstrumentor().is_instrumented_by_opentelemetry:
        DjangoInstrumentor().instrument(is_sql_commentor_enabled=False)
    return True


def instrument_celery() -> bool:
    if not configure_telemetry(service_name="releaseproof-worker"):
        return False
    from opentelemetry.instrumentation.celery import CeleryInstrumentor

    if not CeleryInstrumentor().is_instrumented_by_opentelemetry:  # type: ignore[no-untyped-call]
        CeleryInstrumentor().instrument()  # type: ignore[no-untyped-call]
    return True
