"""Request correlation and bounded request outcome telemetry."""

from __future__ import annotations

import time
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from packages.observability.context import correlation_scope, current_trace_id
from packages.observability.metrics import MetricComponent, MetricOutcome, record_operation


class CorrelationMiddleware:
    """Use a server-generated identifier; never trust an inbound correlation value."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        started = time.perf_counter()
        with correlation_scope() as correlation_id:
            request.correlation_id = correlation_id  # type: ignore[attr-defined]
            try:
                response = self.get_response(request)
            except Exception:
                record_operation(
                    component=MetricComponent.WEB,
                    outcome=MetricOutcome.FAILED,
                    duration_ms=(time.perf_counter() - started) * 1_000,
                )
                raise
            outcome = (
                MetricOutcome.COMPLETED
                if response.status_code < 400
                else MetricOutcome.DENIED
                if response.status_code in {401, 403, 413, 429}
                else MetricOutcome.FAILED
            )
            record_operation(
                component=MetricComponent.WEB,
                outcome=outcome,
                duration_ms=(time.perf_counter() - started) * 1_000,
            )
            response.headers["X-Correlation-ID"] = str(correlation_id)
            trace_id = current_trace_id()
            if trace_id is not None:
                response.headers["X-Trace-ID"] = trace_id
            return response
