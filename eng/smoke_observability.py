"""Emit one bounded metric/span and prove the local telemetry path is live."""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor


def _read_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=3) as response:  # noqa: S310
        payload: Any = json.loads(response.read())
    if not isinstance(payload, dict):
        raise RuntimeError("observability endpoint returned a non-object")
    return payload


def main() -> int:
    with urllib.request.urlopen("http://127.0.0.1:13133/", timeout=3) as response:
        if response.status != 200:
            raise RuntimeError("OpenTelemetry collector is not healthy")

    resource = Resource.create({"service.name": "releaseproof-ci-smoke"})
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(timeout=5)))
    trace.set_tracer_provider(tracer_provider)
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(timeout=5), export_interval_millis=500
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=(reader,))
    metrics.set_meter_provider(meter_provider)
    counter = metrics.get_meter("releaseproof.ci").create_counter("releaseproof.smoke.events")
    with trace.get_tracer("releaseproof.ci").start_as_current_span("releaseproof.smoke"):
        counter.add(1, {"component": "smoke", "outcome": "completed"})
    if not tracer_provider.force_flush(timeout_millis=10_000):
        raise RuntimeError("trace flush timed out")
    if not meter_provider.force_flush(timeout_millis=10_000):
        raise RuntimeError("metric flush timed out")

    query_url = (
        "http://127.0.0.1:9090/api/v1/query?query="
        "releaseproof_smoke_events_total%7Bcomponent%3D%22smoke%22%7D"
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = _read_json(query_url)
        data = result.get("data")
        if result.get("status") == "success" and isinstance(data, dict) and data.get("result"):
            print(json.dumps({"metric": "releaseproof_smoke_events_total", "status": "verified"}))
            meter_provider.shutdown(timeout_millis=5_000)
            tracer_provider.shutdown()
            return 0
        time.sleep(1)
    raise RuntimeError("Prometheus did not ingest the bounded smoke metric")


if __name__ == "__main__":
    raise SystemExit(main())
